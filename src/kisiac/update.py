from kisiac.common import UserError, run_cmd
from kisiac import users
from kisiac.config import Config
from kisiac.lvm import LVMEntities


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


def update_lvm() -> None:
    desired = Config().lvm
    current = LVMEntities.from_system()

    pvs_to_add = desired.pvs - current.pvs
    pvs_to_remove = current.pvs - desired.pvs

    vgs_to_add = desired.vgs.keys() - current.vgs.keys()
    vgs_to_remove = current.vgs.keys() - desired.vgs.keys()

    lvs_to_add = desired.lvs.keys() - current.lvs.keys()
    lvs_to_remove = current.lvs.keys() - desired.lvs.keys()

    for lv_desired in desired.lvs.values():
        lv_current = current.lvs.get(lv_desired.name)
        if lv_current is None:
            continue
        if lv_current.layout != lv_desired.layout:
            raise UserError(
                f"Cannot change layout of existing LV {lv_desired.name} "
                f"from {lv_current.layout} to {lv_desired.layout}. "
                "Perform this action manually and re-run the update."
            )
        if lv_current.size != lv_desired.size:
            run_cmd(
                [
                    "lvresize",
                    "-L",
                    lv_desired.size,
                    f"{lv_desired.vg.name}/{lv_desired.name}",
                ]
            )

