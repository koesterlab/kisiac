from pathlib import Path
import subprocess as sp
from typing import Any


cache = Path("~/.cache/kisiac").expanduser()


def run_cmd(
    cmd: list[str],
    input: str | None = None,
    host: str | None = None,
    envvars: dict[str, Any] | None = None,
    sudo: bool = False,
) -> sp.CompletedProcess[str]:
    """Run a system command using subprocess.run and check for errors."""
    # TODO check quotation!
    if sudo:
        cmd = ["sudo", f"bash -c '{' '.join(cmd)}'"]
    if host is not None and host != "localhost":
        cmd = ["ssh", host, f"{' '.join(cmd)}"]
    try:
        return sp.run(
            cmd,
            check=True,
            text=True,
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
            input=input,
            env=envvars,
        )
    except sp.CalledProcessError as e:
        raise UserError(f"Error occurred while running command '{cmd}': {e.stdout}")


class UserError(Exception):
    """Base class for user-related errors."""

    pass
