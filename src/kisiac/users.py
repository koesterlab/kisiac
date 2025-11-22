import grp
import pwd

from kisiac.common import HostAgnosticPath, run_cmd
from kisiac.config import Config


def setup_users(host: str) -> None:
    users = list(Config.get_instance().users)

    groups = {group for user in users for group in user.secondary_groups} | {
        user.primary_group for user in users
    }
    print(groups)

    for group in groups:
        # create group if it does not exist
        if (
            run_cmd(
                ["getent", "group", "koesterlab"], check=False, host=host
            ).returncode
            == 2
        ):
            print(f"Creating group: {group}")
            run_cmd(["groupadd", group], host=host, sudo=True)

    for user in Config.get_instance().users:
        # create user if it does not exist
        if not is_existing_user(user.username):
            print(f"Creating user: {user.username}")
            group_arg = []
            if user.secondary_groups:
                group_arg = ["-G", ",".join(user.secondary_groups)]

            run_cmd(
                [
                    "useradd",
                    "-g",
                    user.primary_group,
                    *group_arg,
                    "--shell",
                    "/bin/bash",
                    "-m",
                    user.username,
                ],
                host=host,
                sudo=True,
            )
        else:
            print(f"Updating user: {user.username}")

        sshdir = HostAgnosticPath(f"~{user.username}/.ssh", host=host, sudo=True)
        sshdir.mkdir()
        sshdir.chown(user.username, user.usergroup)
        sshdir.chmod("u=rwx", "g-rwx", "o-rwx")
        auth_keys_file = sshdir / "authorized_keys"
        auth_keys_file.write_text(user.ssh_pub_key + "\n")
        user.fix_permissions([auth_keys_file.path], host=host)


def is_existing_user(username: str) -> bool:
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def is_existing_group(groupname: str, host: str) -> bool:
    try:
        grp.getgrnam(groupname)
        return True
    except KeyError:
        return False
