from dataclasses import dataclass
from pathlib import Path
import re
from kisiac.common import HostAgnosticPath, confirm_action, run_cmd
from kisiac.config import Config, Filesystem

from pyfstab import Fstab

blkid_attrs_re = re.compile(r'(?P<attr>[A-Z]+)="(?P<value>\S+)"')


def update_filesystems(host: str) -> None:
    filesystems = set(Config().filesystems)
    device_infos = DeviceInfos(host)

    # First, create filesystems that do not exist yet or need to be changed.
    mkfs_cmds = []
    for filesystem in filesystems:
        device_info = device_infos.get_info(filesystem)
        if device_info is not None and device_info.fstype != filesystem.fstype:
            mkfs_cmds.append(["mkfs", "-t", filesystem.fstype, str(device_info.device)])

    # Second, update /etc/fstab.
    fstab_path = HostAgnosticPath("/etc/fstab", host=host, sudo=True)
    old_fstab = Fstab().read_string(fstab_path.read_text())

    previous_entries = {
        Filesystem.from_fstab_entry(entry) for entry in old_fstab.entries
    }

    unchanged_entries = previous_entries & filesystems
    change_or_remove_msg = "\n".join(map(str, previous_entries - unchanged_entries))
    mkfs_cmds_msg = "\n".join(" ".join(cmd) for cmd in mkfs_cmds)

    if confirm_action(
        f"The following mkfs commands will be executed:\n{mkfs_cmds_msg}"
        f"\nThe following fstab entries will be changed or removed:\n{change_or_remove_msg}"
    ):
        for cmd in mkfs_cmds:
            run_cmd(cmd, sudo=True, host=host)

        new_fstab = Fstab()
        new_fstab.entries = [
            filesystem.to_fstab_entry() for filesystem in sorted(filesystems)
        ]
        fstab_path.write_text(new_fstab.write_string())


@dataclass
class DeviceInfo:
    device: Path
    fstype: str | None
    label: str | None
    uuid: str | None

    def is_targeted_by_filesystem(self, filesystem: Filesystem) -> bool:
        if filesystem.device is not None:
            return self.device == filesystem.device
        elif filesystem.label is not None:
            return self.label == filesystem.label
        elif filesystem.uuid is not None:
            return self.uuid == filesystem.uuid
        else:
            return False


class DeviceInfos:
    def __init__(self, host: str) -> None:
        blkid_output = run_cmd(["blkid"], sudo=True, host=host).stdout.splitlines()
        self.infos = []
        for entry in blkid_output:
            device, attrs = entry.split(":", maxsplit=1)
            attrs = {
                match.group("attr"): match.group("value")
                for match in blkid_attrs_re.findall(attrs)
            }
            self.infos.append(
                DeviceInfo(
                    device=Path(device),
                    fstype=attrs.get("TYPE"),
                    label=attrs.get("LABEL"),
                    uuid=attrs.get("UUID"),
                )
            )

    def get_info(self, filesystem: Filesystem) -> DeviceInfo | None:
        for info in self.infos:
            if info.is_targeted_by_filesystem(filesystem):
                return info
