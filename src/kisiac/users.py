import grp
from pathlib import Path
import pwd

from kisiac.common import run_cmd
from kisiac.config import Config


def setup_users() -> None:
    if not is_existing_group("koesterlab"):
        print("Creating group: koesterlab")
        run_cmd(["groupadd", "koesterlab"])

    for user in Config().users:
        homedir = Path(f"~{user}").expanduser()

        if not is_existing_user(user.username):
            print(f"Creating user: {user}")
            run_cmd(
                [
                    "useradd",
                    "--groups",
                    "koesterlab",
                    "--shell",
                    "/bin/bash",
                    "-m",
                    user.username,
                ]
            )
        else:
            print(f"Updating user: {user}")

        sshdir = homedir / ".ssh"
        sshdir.mkdir(mode=0o700, exist_ok=True)
        auth_keys_file = sshdir / "authorized_keys"
        with auth_keys_file.open("w", encoding="utf-8") as f:
            f.write(user.ssh_pub_key + "\n")
        user.secure_file(auth_keys_file)


def is_existing_user(username: str) -> bool:
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def is_existing_group(groupname: str) -> bool:
    try:
        grp.getgrnam(groupname)
        return True
    except KeyError:
        return False
