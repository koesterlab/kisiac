from dataclasses import dataclass, field
import json
from typing import Any, Self

from kisiac.common import check_type, exists_cmd, run_cmd


@dataclass(frozen=True)
class PV:
    device: str


@dataclass(frozen=True)
class LV:
    name: str
    layout: str
    size: str


@dataclass(frozen=True)
class VG:
    name: str
    pvs: set[PV] = field(default_factory=set)
    lvs: dict[str, LV] = field(default_factory=dict)


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
                    size=lv_settings["size"],
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

        # load LVM info from report
        data = json.loads(
            run_cmd(
                ["lvm", "fullreport", "--reportformat", "json"],
                host=host,
                sudo=True,
            ).stdout
        )["report"]
        for entry in data:
            for vg in entry["vg"]:
                entities.vgs[vg["vg_name"]] = VG(name=vg["vg_name"])
            for pv in entry["pv"]:
                pv_obj = PV(device=pv["pv_name"])
                entities.pvs.add(pv_obj)
                entities.vgs[pv["vg_name"]].pvs.add(pv_obj)

            for lv in entry["lv"]:
                vg = entities.vgs[lv["vg_name"]]
                vg.lvs[lv["lv_name"]] = LV(
                    name=lv["lv_name"],
                    layout=lv["lv_layout"],
                    size=lv["lv_size"],
                )
        return entities
