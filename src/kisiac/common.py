from pathlib import Path
import subprocess as sp
from typing import Any


import inquirer


cache = Path("~/.cache/kisiac").expanduser()


def confirm_action(desc: str) -> bool:
    response = inquirer.prompt(
        [
            inquirer.Checkbox(
                "action",
                message=desc,
                choices=["yes", "no"]
            )
        ]
    )
    return response["action"] == "yes"


def run_cmd(
    cmd: list[str],
    input: str | None = None,
    host: str | None = None,
    env: dict[str, Any] | None = None,
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
            stderr=sp.PIPE,
            input=input,
            env=env,
        )
    except sp.CalledProcessError as e:
        raise UserError(f"Error occurred while running command '{cmd}': {e.stderr}")


class UserError(Exception):
    """Base class for user-related errors."""

    pass


def check_type(item: str, value: Any, type: Any) -> None:
    if not isinstance(value, type):
        raise UserError(f"Expecting url for {item}, found {type(value)} ({value}).")
