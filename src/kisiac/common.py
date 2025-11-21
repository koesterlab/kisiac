from pathlib import Path
import subprocess as sp
import sys
from typing import Any, Callable, Self, Sequence
import importlib
import re
import textwrap

import inquirer


cache = Path("~/.cache/kisiac").expanduser()


class Singleton(object):
    _instance: Self | None = None

    def __new__(cls, *args, **kwargs) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.__init__(*args, **kwargs)
        return cls._instance

    @classmethod
    def get_instance(cls) -> Self:
        assert cls._instance is not None
        return cls._instance


def confirm_action(desc: str) -> bool:
    from kisiac.runtime_settings import GlobalSettings

    if GlobalSettings.get_instance().non_interactive:
        return True

    response = inquirer.prompt(
        [inquirer.Checkbox("action", message=desc, choices=["yes", "no"])]
    )
    assert response is not None
    return response["action"] == "yes"


def exists_cmd(cmd: str, host: str, sudo: bool) -> bool:
    try:
        run_cmd(["which", cmd], host=host, sudo=sudo, user_error=False)
        return True
    except sp.CalledProcessError:
        return False


def run_cmd(
    cmd: list[str],
    input: str | None = None,
    host: str = "localhost",
    env: dict[str, Any] | None = None,
    sudo: bool = False,
    user_error: bool = True,
) -> sp.CompletedProcess[str]:
    """Run a system command using subprocess.run and check for errors."""
    # TODO check quotation!
    if sudo:
        cmd = ["sudo", "bash", "-c", f"{' '.join(cmd)}"]
    if host != "localhost":
        if sudo:
            cmd = ["ssh", host, f"sudo bash -c '{' '.join(cmd)}'"]
        else:
            cmd = ["ssh", host, f"{' '.join(cmd)}"]
    print(f"Running command: {' '.join(cmd)}", file=sys.stderr)
    try:
        return sp.run(
            cmd,
            check=True,
            text=True,
            stdout=sp.PIPE,
            stderr=sp.PIPE,
            input=input,
            env=env,
        )
    except sp.CalledProcessError as e:
        if user_error:
            raise UserError(
                f"Error occurred while running command '{cmd}': {e.stderr}"
            ) from e
        else:
            raise


class UserError(Exception):
    """Base class for user-related errors."""

    pass


def check_type(item: str, value: Any, expected_type: Any) -> None:
    if not isinstance(value, expected_type):
        raise UserError(
            f"Expecting {expected_type} for {item}, found "
            f"value {value} of type {type(value)}."
        )


module_import_re: re.Pattern = re.compile(
    r"from kisiac.(?P<module>[a-z0-9_]+) import [a-zA-Z0-0_,+]"
)


def func_to_sh(func: Callable) -> str:
    func_name = func.__name__
    module_code = get_module_code(func.__module__)
    return textwrap.dedent(f"""
    {module_code}
    {func_name}()
    """)


def get_module_code(module_name: str) -> str:
    module_path = importlib.import_module(module_name).__file__
    assert module_path is not None

    with open(module_path, mode="r") as f:
        module_code = module_import_re.sub(
            lambda match: get_module_code(f"kisiac.{match.group('module')}"), f.read()
        )

    return module_code


class HostAgnosticPath:
    def __init__(
        self, path: str | Path, host: str = "localhost", sudo: bool = False
    ) -> None:
        self.path = Path(path)
        self.host = host
        self.sudo = sudo
        if self.is_local_and_user():
            # if non local or sudo, shell commands will be used, which expand
            # the ~ operator automatically
            self.path = self.path.expanduser()

    def read_text(self) -> str:
        if self.is_local_and_user():
            return self.path.read_text()
        else:
            return self._run_cmd(["cat", str(self.path)]).stdout

    def write_text(self, content: str) -> None:
        if self.is_local_and_user():
            self.path.write_text(content)
        else:
            self._run_cmd(
                ["tee", str(self.path)],
                input=content,
            )

    def mkdir(self) -> None:
        if self.is_local_and_user():
            self.path.mkdir(parents=True, exist_ok=True)
        else:
            self._run_cmd(["mkdir", "-p"])

    def chmod(self, mode: int) -> None:
        if self.is_local_and_user():
            self.path.chmod(mode)
        else:
            self._run_cmd(["chmod", oct(mode)[2:], str(self.path)])

    def chown(self, user: str, group: str | None = None) -> None:
        if self.is_local_and_user():
            import shutil

            shutil.chown(self.path, user=user, group=group)
        else:
            owner = f"{user}:{group}" if group else user
            self._run_cmd(["chown", owner, str(self.path)])

    def is_local_and_user(self) -> bool:
        return self.host == "localhost" and not self.sudo

    def _run_cmd(
        self, cmd: list[str], input: str | None = None, user_error: bool = True
    ) -> sp.CompletedProcess[str]:
        return run_cmd(
            cmd,
            input=input,
            host=self.host,
            sudo=self.sudo,
            user_error=user_error,
        )

    def exists(self) -> bool:
        if self.is_local_and_user():
            return self.path.exists()
        else:
            try:
                self._run_cmd(
                    ["test", "-e", str(self.path)],
                    user_error=False,
                )
                return True
            except sp.CalledProcessError:
                return False

    def is_dir(self) -> bool:
        if self.is_local_and_user():
            return self.path.is_dir()
        else:
            try:
                self._run_cmd(
                    ["test", "-d", str(self.path)],
                    user_error=False,
                )
                return True
            except sp.CalledProcessError:
                return False

    def with_suffix(self, suffix: str) -> Self:
        return type(self)(self.path.with_suffix(suffix))

    @property
    def parents(self) -> Sequence[Self]:
        return [type(self)(parent, host=self.host) for parent in self.path.parents]

    def __truediv__(self, other: Any) -> Self:
        return type(self)(self.path / other, host=self.host)

    def __rtruediv__(self, other: Any) -> Self:
        return type(self)(other / self.path, host=self.host)

    def __str__(self) -> str:
        if self.host == "localhost":
            return str(self.path)
        else:
            return f"{self.host}:{self.path}"
