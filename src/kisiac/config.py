from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import platform
import re
from typing import Any, Iterable, Self, Sequence
import base64

import jinja2
import yaml
import git
from pyfstab.entry import Entry as FstabEntry

from kisiac.common import HostAgnosticPath, Singleton, cache, UserError, check_type
from kisiac.lvm import LVMSetup


config_file_path = Path("/etc/kisiac.yaml")


required_marker = object()


@dataclass
class Package:
    name: str
    cmd_spec: str | None
    desc: str
    with_pkgs: list[str]

    @property
    def cmd(self) -> str:
        return self.cmd_spec or self.name

    @property
    def install_cmd(self) -> str:
        with_pkgs = " ".join(f"--with {pkg}" for pkg in self.with_pkgs)
        return f"pixi global install {self.name} {with_pkgs}"


class FileType(Enum):
    system = "system"
    user = "user"


@dataclass(frozen=True, order=True)
class Filesystem:
    device: Path | None
    label: str | None
    uuid: str | None
    fstype: str
    mountpoint: Path | None
    options: str | None
    dump: int
    fsck: int

    def __post_init__(self) -> None:
        if (
            sum(1 for item in (self.device, self.label, self.uuid) if item is not None)
            != 1
        ):
            raise UserError("Filesystem may only have one of device, label or uuid.")

    @classmethod
    def from_fstab_entry(cls, entry: FstabEntry) -> Self:
        assert entry.device is not None
        assert entry.type is not None
        if entry.device.startswith("LABEL="):
            device = None
            label = entry.device[len("LABEL=") :]
            uuid = None
        elif entry.device.startswith("UUID="):
            device = None
            label = None
            uuid = entry.device[len("UUID=") :]
        else:
            device = Path(entry.device)
            label = None
            uuid = None
        return cls(
            device=device,
            label=label,
            uuid=uuid,
            fstype=entry.type,
            mountpoint=Path(entry.dir) if entry.dir is not None else None,
            options=entry.options,
            dump=entry.dump or 0,
            fsck=entry.fsck or 0,
        )

    def to_fstab_entry(self) -> FstabEntry:
        return FstabEntry(
            _device=str(self.device or self.label or self.uuid),
            _dir=str(self.mountpoint) if self.mountpoint is not None else None,
            _type=self.fstype,
            _options=self.options,
            _dump=self.dump,
            _fsck=self.fsck,
        )


class UserSet(Enum):
    nobody = "nobody"
    owner = "owner"
    group = "group"
    others = "others"


@dataclass
class Permissions:
    owner: str | None
    group: str | None
    read: UserSet | None
    write: UserSet | None
    execute: UserSet | None
    setgid: bool
    setuid: bool
    sticky: bool


@dataclass
class File:
    target_path: Path
    content: str

    def write(self, overwrite_existing: bool, host: str, sudo: bool) -> Sequence[Path]:
        target_path = HostAgnosticPath(self.target_path, host=host, sudo=sudo)
        if target_path.exists() and not overwrite_existing:
            target_path = target_path.with_suffix(".updated")
        created = []
        for ancestor in target_path.parents[::-1][1:]:
            if not ancestor.exists():
                ancestor.mkdir()
                created.append(ancestor)
        target_path.write_text(self.content)
        created.append(target_path)
        return created


class Files:
    def __init__(self, config: "Config") -> None:
        cache_address = base64.b64encode(config.repo.encode()).decode()
        self.repo_cache = cache / cache_address
        self.repo = git.Repo(self.repo_cache)
        self.infrastructure = config.infrastructure
        self.vars = config.vars
        self.user_vars = config.user_vars
        if not self.repo_cache.exists():
            self.repo_cache.parent.mkdir(exist_ok=True)
            self.repo.clone_from(config.repo, self.repo_cache)
        else:
            # update to latest commit
            self.repo.remotes.origin.fetch()
            self.repo.git.reset("--hard", "origin/main")

    def infrastructure_stack(self) -> Iterable[Path]:
        base = self.repo_cache / "infrastructure"
        yield base / "all"
        if self.infrastructure is not None:
            yield base / self.infrastructure

    def host_stack(self, include_infrastructure_root: bool = False) -> Iterable[Path]:
        hostname = platform.node()
        for infra in self.infrastructure_stack():
            base = infra / "hosts"
            if include_infrastructure_root:
                yield infra
            for entry in base.iterdir():
                if not entry.is_dir():
                    raise UserError(f"{base} may only contain directories")
                # yield if all or entry matches hostname
                regex = str(entry).replace("*", r".+")
                if entry == "all" or re.match(regex, hostname):
                    yield base / entry

    def get_config(self) -> dict[str, Any]:
        config = {}
        for base in self.host_stack(include_infrastructure_root=True):
            config_path = base / "kisiac.yaml"
            if config_path.exists():
                with open(config_path, "r") as f:
                    config.update(yaml.safe_load(f))
        return config

    def get_files(self, user: str | None) -> Iterable[File]:
        if user is not None:
            file_type = "user_files"
            vars = dict(self.vars) | self.user_vars(user)

            # yield built-in user files
            templates = jinja2.Environment(
                loader=jinja2.PackageLoader("kisiac", "files"),
                autoescape=jinja2.select_autoescape(),
            )
            content = templates.get_template("kisiac.sh.j2").render(
                packages=Config().user_software
            )
            yield File(target_path=Path("/etc/profile.d/kisiac.sh"), content=content)
        else:
            file_type = "system_files"
            vars = self.vars
        for host in self.host_stack():
            collection = host / file_type
            templates = jinja2.Environment(
                loader=jinja2.FileSystemLoader(host),
                autoescape=jinja2.select_autoescape(),
            )
            for base, _, files in (collection).walk():
                for f in files:
                    if f.endswith(".j2"):
                        content = templates.get_template(str(base / f)).render(vars)
                    else:
                        with open(base / f, "r") as content:
                            content = content.read()
                    yield File((base / f).relative_to(collection), content)


@dataclass
class User:
    username: str
    ssh_pub_key: str
    vars: dict[str, Any]

    @property
    def usergroup(self) -> str:
        return self.username

    def fix_permissions(self, paths: Iterable[Path], host: str) -> None:
        for path in paths:
            path = HostAgnosticPath(path, host=host, sudo=True)
            # ensure that only user may read/write the paths
            if path.is_dir():
                path.chmod(0o700)
            else:
                path.chmod(0o600)
            path.chown(self.username, self.usergroup)


class Config(Singleton):
    def __init__(self) -> None:
        # Config is bootstrapped via an env variable that contains YAML or the file config_file_path.
        # It at least has to contain the repo: ... key that points to a
        # git repo containing the actual config.
        # However, it may also contain e.g. user definitions or secret (environment)
        # variables.

        self._config: dict[str, Any] = {}

        def update_config(config) -> None:
            config = yaml.safe_load(config)

            if not isinstance(config, dict):
                raise ValueError("Config has to be a mapping")
            self._config.update(config)

        config_set = False

        try:
            with open(config_file_path, "r") as f:
                update_config(f)
            config_set = True
        except (FileNotFoundError, IOError):
            # ignore missing file or read errors, we fall back to env var
            pass
        except Exception as e:
            # raise other errors
            raise UserError(f"Error reading config file {config_file_path}: {e}") from e

        if not config_set:
            raise UserError(
                "No config file found at "
                f"{config_file_path}. Run 'kisiac setup-config' to set up the "
                "configuration."
            )

        self._files: Files | None = None

        self._config.update(self.files.get_config())

    def as_str(self) -> str:
        return yaml.dump(self._config)

    def get(self, key: str, default: Any | None = required_marker) -> Any:
        value = self._config.get(key, default)

        if value is required_marker:
            raise UserError(f"Config lacks key {key}.")

        return value

    @property
    def users(self) -> Iterable[User]:
        users = self.get("users")
        check_type("users key", users, dict)

        for username, settings in users.items():
            check_type(f"user {username}", settings, dict)
            yield User(
                username,
                ssh_pub_key=settings["ssh_pub_key"],
                vars=settings.get("vars", {}),
            )

    @property
    def vars(self) -> dict[str, Any]:
        vars = self.get("vars", default={})
        check_type("vars key", vars, dict)
        return vars

    def user_vars(self, user: str) -> dict[str, Any]:
        return self.get("users", default={})[user].get("vars", {})

    @property
    def infrastructure(self) -> str:
        infrastructure = self.get("infrastructure", default=None)
        check_type("infrastructure key", infrastructure, (str, None))
        return infrastructure

    @property
    def repo(self) -> str:
        repo_url = self.get("repo")
        check_type("repo key", repo_url, str)
        return repo_url

    @property
    def files(self) -> Files:
        if self._files is None:
            self._files = Files(self)

        return self._files

    @property
    def user_software(self) -> Iterable[Package]:
        user_software = self.get("user_software")
        check_type("user_software key", user_software, list)
        for entry in user_software:
            check_type("user_software entry", entry, dict)
            try:
                yield Package(
                    name=entry["pkg"],
                    cmd_spec=entry.get("cmd"),
                    desc=entry["desc"],
                    with_pkgs=entry.get("with", []),
                )
            except KeyError as e:
                raise UserError(f"Missing {e} in user_software definition.")

    @property
    def system_software(self) -> list[str]:
        system_software = self.get("system_software")
        check_type("system_software key", system_software, list)
        return system_software

    @property
    def messages(self) -> Sequence[str]:
        messages = self.get("messages")
        check_type("message key", messages, list)
        return messages

    @property
    def infrastructure_name(self) -> str:
        infrastructure_name = self.get("infrastructure_name")
        check_type("infrastructure_name key", infrastructure_name, str)
        return infrastructure_name

    @property
    def lvm(self) -> LVMSetup:
        lvm = self.get("lvm", default={})
        return LVMSetup.from_config(lvm)

    @property
    def filesystems(self) -> Iterable[Filesystem]:
        filesystems = self.get("filesystems", default={})
        check_type("filesystems key", filesystems, dict)
        for settings in filesystems:
            check_type("filesystem item", settings, dict)
            yield Filesystem(
                device=settings.get("device"),
                label=settings.get("label"),
                uuid=settings.get("uuid"),
                fstype=settings["type"],
                mountpoint=settings["mount"],
                options=settings.get("options", "defaults"),
                dump=settings.get("dump", 0),
                fsck=settings.get("pass", 0),
            )

    @property
    def permissions(self) -> dict[Path, Permissions]:
        check_type("permissions key", self._config.get("permissions", {}), dict)
        permissions = {}
        for path_str, settings in self._config.get("permissions", {}).items():
            check_type(f"permissions for {path_str}", settings, dict)
            path = Path(path_str)
            permissions[path] = Permissions(
                owner=settings.get("owner"),
                group=settings.get("group"),
                read=UserSet(settings["read"]) if "read" in settings else None,
                write=UserSet(settings["write"]) if "write" in settings else None,
                execute=UserSet(settings["execute"]) if "execute" in settings else None,
                setgid=settings.get("setgid", False),
                setuid=settings.get("setuid", False),
                sticky=settings.get("sticky", False),
            )
        return permissions