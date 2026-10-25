"""One entry point for pinned builds: an EDSY link, a Coriolis link, or SLEF / journal Loadout JSON.

Every source is normalised to the EDSY decoder's shape so the build module compares them the same way:
{source, ship{fdname, name}, name, slots[{group, index, slot, module{fdname, name, class, rating, cost}, blueprint{fdname, name} | None,
grade, experimental{fdname, name} | None}]}.
"""
import json
import re

from elitelab.core import coriolis, edsy
from elitelab.core import gamedata as gd

COSMETIC = ("PaintJob", "Decal", "ShipKit", "Bobble", "VesselVoice", "ShipName", "ShipID", "WeaponColour", "EngineColour", "Hologram",
            "ShipCockpit", "CargoHatch", "PlanetaryApproachSuite", "DataLinkScanner", "CodexScanner", "DiscoveryScanner", "StringLights")


def group_of(slot):
    """Journal slot name -> EDSY slot group."""
    s = slot or ""
    if s in edsy.CORE_SLOTS:
        return "component"
    if s.startswith("Tiny"):
        return "utility"
    if s.startswith(("Small", "Medium", "Large", "Huge")):
        return "hardpoint"
    if s.startswith("Military"):
        return "military"
    return "internal"


def from_loadout(data, name=None):
    """A journal Loadout event (or the ``data`` of a SLEF entry) as a build target."""
    mods = data.get("Modules") or []
    ship_fd = (data.get("Ship") or "").lower()
    eship = edsy.SHIP_BY_FDNAME.get(ship_fd) or {}
    counters = {}
    slots = []
    for m in mods:
        slot = m.get("Slot") or ""
        if slot.startswith(COSMETIC) or not m.get("Item"):
            continue
        group = group_of(slot)
        idx = counters.get(group, 0)
        counters[group] = idx + 1
        item = m["Item"].lower()
        em = edsy.MODULE_BY_FDNAME.get(item, {})
        eng = m.get("Engineering") or {}
        bpk = gd.BLUEPRINT_BY_LOWER.get((eng.get("BlueprintName") or "").lower())
        exk = gd.EXPERIMENTAL_BY_LOWER.get((eng.get("ExperimentalEffect") or "").lower())
        slots.append({"group": group, "index": edsy.CORE_SLOTS.index(slot) if group == "component" and slot in edsy.CORE_SLOTS else idx, "slot": slot,
                      "module": {"id": None, "fdname": item, "name": em.get("name") or item, "class": em.get("class"), "rating": em.get("rating"),
                                 "mount": em.get("mount"), "mtype": None, "cost": em.get("cost") or 0},
                      "blueprint": ({"fdname": eng.get("BlueprintName"), "name": gd.BLUEPRINT_BY_KEY[bpk]["name"] if bpk else eng.get("BlueprintName")}
                                    if eng.get("BlueprintName") else None),
                      "grade": int(eng.get("Level") or 0) if eng.get("BlueprintName") else 0, "roll": eng.get("Quality"),
                      "experimental": ({"fdname": eng.get("ExperimentalEffect"), "name": gd.EXPERIMENTAL_BY_KEY[exk]["name"] if exk else eng.get("ExperimentalEffect")}
                                       if eng.get("ExperimentalEffect") else None),
                      "preengineered": False, "powered": bool(m.get("On", True)), "priority": int(m.get("Priority") or 0) + 1})
    return {"version": None, "ship": {"id": None, "fdname": ship_fd, "name": eship.get("name") or data.get("Ship_Localised") or ship_fd},
            "name": name or data.get("ShipName") or "", "tag": data.get("ShipIdent") or "", "slots": slots, "hash": None}


def parse(text):
    """Detect the source and decode. Returns the target with a ``source`` of 'edsy', 'coriolis' or 'slef'."""
    t = (text or "").strip()
    if not t:
        raise ValueError("paste an EDSY link, a Coriolis link, or SLEF / Loadout JSON")
    if t[0] in "[{":
        try:
            obj = json.loads(t)
        except ValueError:
            raise ValueError("that JSON does not parse") from None
        if isinstance(obj, list):                      # SLEF: [{header, data}]
            obj = next((e for e in obj if isinstance(e, dict) and isinstance(e.get("data"), dict)), None) or {}
            name = ((obj.get("header") or {}).get("appName") or "")
            obj = obj.get("data") or {}
            b = from_loadout(obj)
            b["name"] = b["name"] or (obj.get("ShipName") or f"{name} build".strip())
        elif isinstance(obj, dict) and obj.get("Modules") is not None:
            b = from_loadout(obj)
        else:
            raise ValueError("JSON must be a SLEF export or a journal Loadout event")
        b["source"] = "slef"
        return b
    if re.search(r"L=[0-9A-Za-z_,\-]{8,}", t) and "coriolis" not in t.lower():
        b = edsy.decode(t)
        b["source"] = "edsy"
        return b
    if coriolis.is_link(t):
        b = coriolis.decode(t)
        b["source"] = "coriolis"
        return b
    b = edsy.decode(t)                                 # bare EDSY hash, or a clear error message
    b["source"] = "edsy"
    return b
