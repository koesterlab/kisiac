import subprocess as sp
import sys
from kisiac.common import (
    HostAgnosticPath,
    UserError,
    confirm_action,
    run_cmd,
)
from kisiac.filesystems import update_filesystems
from kisiac.runtime_settings import GlobalSettings, UpdateHostSettings
from kisiac import users
from kisiac.config import Config
from kisiac.lvm import LVMSetup

import inquirer


default_system_software = [
    "openssh-server",
    "openssh-client",
    "lvm2",
    "e2fsprogs",
    "xfsprogs",
    "btrfs-progs",
]


def setup_config() -> None:
    if GlobalSettings.get_instance().non_interactive:
        content = sys.stdin.read()
    else:
        answers = inquirer.prompt(
            [
                inquirer.Text(
                    "secret_config",
                    message="Paste the secret configuration (YAML format), including the repo key",
                ),
            ]
        )
        assert answers is not None
        content = answers["secret_config"]
    HostAgnosticPath("/etc/kisiac.yaml", sudo=True).write_text(content)


def update_host(host: str) -> None:
    config = Config.get_instance()
    for file in config.files.get_files(user=None):
        file.write(overwrite_existing=True, host=host, sudo=True)

    update_system_packages(host)

    update_lvm(host)

    users.setup_users(host=host)
    for user in config.users:
        for file in config.files.get_files(user.username):
            # If the user already has the files, we leave him the new file as a
            # template next to the actual file, with the suffix '.updated'.
            user.fix_permissions(
                file.write(overwrite_existing=False, host=host, sudo=True), host=host
            )

    update_filesystems(host)


def update_system_packages(host: str) -> None:
    run_cmd(["apt-get", "update"], sudo=True, host=host)
    if not UpdateHostSettings.get_instance().skip_system_upgrade:
        run_cmd(["apt-get", "upgrade"], sudo=True, host=host)
    run_cmd(
        ["apt-get", "install"]
        + list(set(Config.get_instance().system_software + default_system_software)),
        sudo=True,
        host=host,
    )


def update_lvm(host: str) -> None:
    desired = Config.get_instance().lvm
    current = LVMSetup.from_system(host=host)

    cmds = []

    cmds.extend(
        [
            "lvremove",
            "--yes",
            f"{vg.name}/{lv}",
        ]
        for vg in current.vgs.values()
        for lv in vg.lvs.values()
        if vg.name not in desired.vgs or lv.name not in desired.vgs[vg.name].lvs
    )
    cmds.extend(
        ["vgremove", "--yes", vg] for vg in current.vgs.keys() - desired.vgs.keys()
    )
    pvremove = list(current.pvs - desired.pvs)
    if pvremove:
        cmds.append(["pvremove", "--yes", *pvremove])

    pvcreate = list(desired.pvs - current.pvs)
    if pvcreate:
        cmds.append(["pvcreate", "--yes", *pvcreate])
    cmds.extend(
        ["vgcreate", vg.name] + [pv.device for pv in vg.pvs]
        for vg_name, vg in desired.vgs.items()
        if vg_name not in current.vgs
    )
    cmds.extend(
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
        for cmd in cmds:
            try:
                run_cmd(cmd, host=host, sudo=True, user_error=False)
            except sp.CalledProcessError as e:
                raise UserError(
                    f"Incomplete LVM update due to error (make sure to manually fix this!): {e.stderr}"
                )
