import grp
import pwd

from kisiac.common import HostAgnosticPath, run_cmd
from kisiac.config import Config


def setup_users(host: str) -> None:
    # create group if it does not exist
    if run_cmd(["getent", "group", "koesterlab"], host=host).returncode == 2:
        print("Creating group: koesterlab")
        run_cmd(["groupadd", "koesterlab"], host=host, sudo=True)

    for user in Config().users:
        # create user if it does not exist
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
                ],
                host=host,
                sudo=True,
            )
        else:
            print(f"Updating user: {user}")

        sshdir = HostAgnosticPath(f"~{user}/.ssh", host=host, sudo=True)
        sshdir.mkdir()
        sshdir.chown(user.username, user.usergroup)
        sshdir.chmod(0o700)
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
