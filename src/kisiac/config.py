from dataclasses import dataclass
from enum import Enum
import grp
import json
import os
from pathlib import Path
import platform
import pwd
import re
from typing import Any, Iterable, Self, Sequence
import base64

import jinja2
import yaml
import git

from kisiac.common import HostAgnosticPath, cache, UserError, check_type, run_cmd
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


@dataclass
class File:
    target_path: Path
    content: str

    def write(
            self, overwrite_existing: bool, host: str, sudo: bool
    ) -> Sequence[Path]:
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
            self.repo.clone_from(config.repo)
        else:
            # TODO update to latest commit
            self.repo.pull()

    def infrastructure_stack(self) -> Iterable[Path]:
        base = self.repo_cache / "infrastructure"
        yield base / "all"
        if self.infrastructure is not None:
            yield base / self.infrastructure

    def host_stack(self) -> Iterable[Path]:
        hostname = platform.node()
        for infra in self.infrastructure_stack():
            base = infra / "hosts"
            for entry in base.iterdir():
                if not entry.is_dir():
                    raise UserError(f"{base} may only contain directories")
                # yield if all or entry matches hostname
                regex = str(entry).replace("*", r".+")
                if entry == "all" or re.match(regex, hostname):
                    yield base / entry

    def get_config(self) -> dict[str, Any]:
        config = {}
        for infra in self.infrastructure_stack():
            config_path = infra / "kisiac.yaml"
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


class Config:
    _instance: "Config | None" = None

    def __new__(cls) -> "Config":
        if cls._instance is None:
            cls._instance = Config()
        return cls._instance

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

        try:
            update_config(os.environ["KISIAC_CONFIG"])
            config_set = True
        except KeyError as e:
            pass  # ignore missing env var
        except Exception as e:
            raise UserError(f"Error reading KISIAC_CONFIG env var: {e}") from e

        if not config_set:
            raise UserError(
                "KISIAC_CONFIG is not set and no config file found at "
                f"{config_file_path}. Run 'kisiac setup-config' to set up the "
                "configuration."
            )

        self._files: Files | None = None

        self._config.update(self.files.get_config())

    def as_str(self) -> str:
        return yaml.dump(self._config)

    def get(self, key: str, default: Any | None = required_marker) -> Any:
        value = self._config.get(key, default=default)

        if value is required_marker:
            raise UserError(f"KISIAC_CONFIG lacks key {key}.")

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
