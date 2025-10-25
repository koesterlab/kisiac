import subprocess as sp


def run_cmd(cmd: list[str], input: str | None = None) -> sp.CompletedProcess[str]:
    """Run a system command using subprocess.run and check for errors."""
    try:
        return sp.run(
            cmd, check=True, text=True, stdout=sp.PIPE, stderr=sp.STDOUT, input=input
        )
    except sp.CalledProcessError as e:
        raise UserError(f"Error occurred while running command '{cmd}': {e.stdout}")


class UserError(Exception):
    """Base class for user-related errors."""

    pass
