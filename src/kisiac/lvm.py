from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Self

from humanfriendly import parse_size

from kisiac.common import check_type, exists_cmd, run_cmd


@dataclass(frozen=True)
class PV:
    device: str


@dataclass(frozen=True)
class LV:
    name: str
    layout: str
    size: int

@dataclass(frozen=True)
class VG:
    name: str
    pvs: set[PV] = field(default_factory=set)
    lvs: dict[str, LV] = field(default_factory=dict)

    def get_lv_device(self, lv_name: str) -> Path:
        return Path("/dev") / self.name / lv_name


@dataclass
class LVMSetup:
    pvs: set[PV] = field(default_factory=set)
    vgs: dict[str, VG] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.pvs and not self.vgs

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> Self:
        check_type("lvm key", config, dict)
        entities = cls()
        for pv in config.get("pvs", []):
            check_type("lvm pv entry", pv, str)
            entities.pvs.add(PV(device=pv))
        for name, settings in config.get("vgs", {}).items():
            check_type(f"lvm vg {name} entry", settings, dict)

            lvs = settings.get("lvs", {})
            check_type(f"lvm vg {name} lvs entry", lvs, dict)

            lvs_entities = {}
            for lv_name, lv_settings in lvs.items():
                check_type(f"lvm vg {name} lv {lv_name} entry", lv_settings, dict)
                lvs_entities[lv_name] = LV(
                    name=lv_name,
                    layout=lv_settings["layout"],
                    size=parse_size(lv_settings["size"], binary=True),
                )

            entities.vgs[name] = VG(
                name=name,
                pvs={PV(device=pv) for pv in settings.get("pvs", [])},
                lvs=lvs_entities,
            )
        return entities

    @classmethod
    def from_system(cls, host: str) -> Self:
        # check if lvm2 is installed, return empty LVM entities otherwise
        if not exists_cmd("pvcreate", host=host, sudo=True):
            return cls()

        entities: Self = cls()

        lv_data = json.loads(
            run_cmd(
                [
                    "lvs",
                    "--units",
                    "b",
                    "--options",
                    "lv_name,vg_name,lv_layout,lv_size",
                    "--reportformat",
                    "json",
                ],
                host=host,
                sudo=True,
            ).stdout
        )["report"][0]["lv"]

        vg_data = json.loads(
            run_cmd(
                ["vgs", "--options", "vg_name", "--reportformat", "json"],
                host=host,
                sudo=True,
            ).stdout
        )["report"][0]["vg"]

        pv_data = json.loads(
            run_cmd(
                ["pvs", "--options", "pv_name,vg_name", "--reportformat", "json"],
                host=host,
                sudo=True,
            ).stdout
        )["report"][0]["pv"]

        for entry in vg_data:
            entities.vgs[entry["vg_name"]] = VG(name=entry["vg_name"])
        for entry in pv_data:
            pv_obj = PV(device=entry["pv_name"])
            entities.pvs.add(pv_obj)
            entities.vgs[entry["vg_name"]].pvs.add(pv_obj)

        for entry in lv_data:
            vg = entities.vgs[entry["vg_name"]]
            vg.lvs[entry["lv_name"]] = LV(
                name=entry["lv_name"],
                layout=entry["lv_layout"],
                size=parse_size(entry["lv_size"], binary=True),
            )
        return entities
