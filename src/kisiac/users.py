import grp
import os
from pathlib import Path
import pwd

import yaml

from kisiac import common


def setup_users() -> None:
    try:
        users = os.environ["KISIAC_USERS"]
    except KeyError:
        raise common.UserError("Environment variable KISIAC_USERS is not set.")
    users = yaml.safe_load(users)

    if not is_existing_group("koesterlab"):
        print("Creating group: koesterlab")
        common.run_cmd(["groupadd", "koesterlab"])

    for user, spec in users.items():
        try:
            ssh_key = spec["ssh_pub_key"]
        except KeyError:
            raise common.UserError(
                f"User {user} is missing 'ssh_pub_key' specification."
            )

        homedir = Path(f"~{user}").expanduser()

        if not is_existing_user(user):
            print(f"Creating user: {user}")
            common.run_cmd(
                [
                    "useradd",
                    "--groups",
                    "koesterlab",
                    "--shell",
                    "/bin/bash",
                    "-m",
                    user,
                ]
            )
        else:
            print(f"Updating user: {user}")

        sshdir = homedir / ".ssh"
        sshdir.mkdir(mode=0o700, exist_ok=True)
        auth_keys_file = sshdir / "authorized_keys"
        with auth_keys_file.open("w", encoding="utf-8") as f:
            f.write(ssh_key + "\n")
        auth_keys_file.chmod(0o600)
        os.chown(auth_keys_file, pwd.getpwnam(user).pw_uid, grp.getgrnam(user).gr_gid)


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
