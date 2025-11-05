from kisiac.common import UserError, confirm_action, run_cmd
from kisiac import users
from kisiac.config import Config
from kisiac.lvm import LVMEntities

import inquirer


def setup_config() -> None:
    answers = inquirer.prompt([
        inquirer.Text("secret_config", message="Paste the secret configuration (YAML format), including the repo key"),
    ])
    with open("/etc/kisiac.yaml", "w") as f:
        f.write(answers["secret_config"])


def update_host(host: str) -> None:
    config = Config()
    for file in config.files.get_files(user=None):
        file.write(overwrite_existing=True, host=host)

    update_system_packages(host)

    update_lvm(host)

    users.setup_users()
    for user in config.users:
        for file in config.files.get_files(user.username):
            # If the user already has the files, we leave him the new file as a
            # template next to the actual file, with the suffix '.updated'.
            user.fix_permissions(file.write(overwrite_existing=False, host=host), host=host)


def update_system_packages() -> None:
    run_cmd(["apt-get", "update"])
    run_cmd(["apt-get", "upgrade"])
    run_cmd(["apt-get", "install"] + Config().system_software)


def update_lvm() -> None:
    desired = Config().lvm
    current = LVMEntities.from_system()

    cmds = []

    cmds.append(
        [
            "lvremove",
            "--yes",
            f"{vg.name}/{lv}",
        ]
        for vg in current.vgs.values()
        for lv in vg.lvs.values()
        if vg.name not in desired.vgs or lv.name not in desired.vgs[vg.name].lvs
    )
    cmds.append(
        ["vgremove", "--yes", vg]
        for vg in current.vgs.keys() - desired.vgs.keys()
    )
    cmds.append(["pvremove", "--yes"] + list(current.pvs - desired.pvs))

    cmds.append(["pvcreate", "--yes"] + list(desired.pvs - current.pvs))
    cmds.append(
        ["vgcreate", vg.name] + [pv.device for pv in vg.pvs]
        for vg_name, vg in desired.vgs.items()
        if vg_name not in current.vgs
    )
    cmds.append(
        [
            "lvcreate",
            "-n",
            lv.name,
            "-L",
            lv.size,
            vg.name,
            "--type",
            lv.layout,
        ]
        for vg in desired.vgs.values()
        for lv in vg.lvs.values()
        if vg.name not in current.vgs or lv.name not in current.vgs[vg.name].lvs
    )

    # update existing VGs and LVs
    for vg_desired in desired.vgs.values():
        vg_current = current.vgs.get(vg_desired.name)
        if vg_current is None:
            continue

        # update pvs in vg
        pvs_to_add = vg_desired.pvs - vg_current.pvs
        if pvs_to_add:
            cmds.append(
                ["vgextend", vg_desired.name] + [pv.device for pv in pvs_to_add]
            )
        pvs_to_remove = vg_current.pvs - vg_desired.pvs
        if pvs_to_remove:
            cmds.append(
                ["vgreduce", "--yes", vg_desired.name]
                + [pv.device for pv in pvs_to_remove]
            )

        # update lvs in vg
        for lv_desired in vg_desired.lvs.values():
            lv_current = vg_current.lvs.get(lv_desired.name)
            if lv_current is None:
                continue
            if lv_current.layout != lv_desired.layout:
                raise UserError(
                    f"Cannot change layout of existing LV {lv_desired.name} "
                    f"from {lv_current.layout} to {lv_desired.layout}. "
                    "Perform this action manually and re-run the update."
                )
            if lv_current.size != lv_desired.size:
                cmds.append(
                    [
                        "lvresize",
                        "--fsmode",
                        "manage",
                        "-L",
                        lv_desired.size,
                        f"{vg_desired.name}/{lv_desired.name}",
                    ]
                )
    cmd_msg = "\n".join(" ".join(cmd) for cmd_list in cmds for cmd in cmd_list)

    if confirm_action(
        f"The following LVM commands will be executed:\n{cmd_msg}\n"
        "\nProceed? If answering no, consider making the changes manually or "
        "adjust the kisiac LVM configuration."
    ):
        for cmd_list in cmds:
            for cmd in cmd_list:
                try:
                    run_cmd(cmd, sudo=True)
                except UserError as e:
                    raise UserError(
                        f"Incomplete LVM update due to error (make sure to manually fix this!): {e}"
                    )

