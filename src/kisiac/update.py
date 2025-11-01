from kisiac.common import run_cmd
from kisiac import users
from kisiac.config import Config


def update_host() -> None:
    config = Config()
    for file in config.files.get_files(user=None):
        file.write(overwrite_existing=True)
    users.setup_users()
    for user in config.users:
        for file in config.files.get_files(user.username):
            # If the user already has the files, we leave him the new file as a
            # template next to the actual file, with the suffix '.updated'.
            user.fix_permissions(file.write(overwrite_existing=False))
    update_system_packages()


def update_system_packages() -> None:
    run_cmd(["apt-get", "update"])
    run_cmd(["apt-get", "upgrade"])
    run_cmd(["apt-get", "install"] + Config().system_software)
