"""Decoder for Coriolis build links (https://coriolis.io/outfit/<ship>?code=<code>&bn=<name>).

Format (coriolis src/app/shipyard/Ship.js): ``code`` is ``<version letter><bulkhead index><2 chars per slot...>`` where
'-' is an empty slot, slots run standard (power plant, thrusters, FSD, life support, distributor, sensors, fuel tank),
then hardpoints (utility mounts included, size 0), then internals, in the ship's slot order. Dot-separated parts follow:
power-enabled flags, priorities (both LZ-string, ignored here) and the modifications blob: a gzip of a binary struct,
base64 url-safe. Struct: slot id (int8; 0 = bulkheads, 1-7 standard, then hardpoints, then internals), then records of
int8 id + 4 bytes value until id -1; ids -2/-3/-4 carry blueprint id, grade and special id; the slot list ends with -1.
Tables (``coriolis.json``) come from EDCD/coriolis-data.
"""
import base64
import gzip
import json
import os
import re
import struct
import urllib.parse

from elitelab.core import edsy

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "coriolis.json"), "r", encoding="utf-8") as _f:
    _DB = json.load(_f)
SHIPS, STANDARD, HARDPOINTS, INTERNAL = _DB["ships"], _DB["standard"], _DB["hardpoints"], _DB["internal"]
BLUEPRINTS, SPECIALS, STANDARD_ORDER = _DB["blueprints"], _DB["specials"], _DB["standard_order"]
ID_BLUEPRINT, ID_GRADE, ID_SPECIAL, ID_DONE = -2, -3, -4, -1
EDSY_ARMOUR_IDS = ["40131", "40122", "40113", "40114", "40115"]      # EDSY module ids of bulkhead grades 1..5 (lightweight .. reactive)


def is_link(text):
    return bool(re.search(r"/outfit/[a-z0-9_]+", (text or "").lower()))


def parse_link(text):
    """(ship key, code, build name) from a Coriolis URL (query ``code=`` or the older ``/outfit/<ship>/<code>`` path)."""
    url = urllib.parse.unquote((text or "").strip())
    m = re.search(r"/outfit/([a-z0-9_]+)(?:/([^?&#\s]+))?", url, re.I)
    if not m:
        raise ValueError("not a Coriolis build link; expected https://coriolis.io/outfit/<ship>?code=...")
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    code = (qs.get("code") or [m.group(2) or ""])[0]
    if not code:
        raise ValueError("the Coriolis link has no build code")
    return m.group(1).lower(), code, (qs.get("bn") or [""])[0]


def _mods(part):
    """Modification blob -> {slot index: {"blueprint": id, "grade": n, "special": id}}."""
    out = {}
    if not part or ":" in part:                       # the pre-2017 text format carried no blueprints
        return out
    try:
        raw = gzip.decompress(base64.b64decode(part.replace("-", "+").replace("_", "/") + "=" * (-len(part) % 4)))
        return _parse_mods(raw)
    except (OSError, EOFError, ValueError, struct.error) as ex:   # BadGzipFile is an OSError; binascii.Error a ValueError
        raise ValueError(f"the Coriolis link's modification data is damaged ({ex.__class__.__name__}); copy the link again") from None


def _parse_mods(raw):
    out = {}
    pos = 0
    slot = struct.unpack_from("b", raw, pos)[0]; pos += 1
    while slot != ID_DONE and pos < len(raw):
        rec = {}
        mid = struct.unpack_from("b", raw, pos)[0]; pos += 1
        while mid != ID_DONE:
            if mid == 40:                             # a string-valued modification (4 chars)
                val = raw[pos:pos + 4].decode("utf-8", "replace").strip()
            else:
                val = struct.unpack_from("<i", raw, pos)[0]
            pos += 4
            if mid == ID_BLUEPRINT and val:
                rec["blueprint"] = val
            elif mid == ID_GRADE and val:
                rec["grade"] = val
            elif mid == ID_SPECIAL:
                rec["special"] = val
            mid = struct.unpack_from("b", raw, pos)[0]; pos += 1
        out[slot] = rec
        if pos >= len(raw):
            break
        slot = struct.unpack_from("b", raw, pos)[0]; pos += 1
    return out


def _edsy_ship(name):
    for sid, s in edsy.SHIPS.items():
        if (s.get("name") or "").lower() == (name or "").lower():
            return sid, s
    return None, None


def decode(text):
    """Decode a Coriolis link into the same shape as edsy.decode(): {ship{fdname, name}, name, slots[...], hash}."""
    ship_key, code, bn = parse_link(text)
    ship = SHIPS.get(ship_key)
    if not ship:
        raise ValueError(f"unknown Coriolis ship '{ship_key}'; the Coriolis tables may need regenerating")
    parts = code.split(".")
    c = parts[0]
    if not c or not re.match(r"^[0-4]", c):
        c = c[1:]                                     # version letter
    if not c or c[0] not in "01234":
        raise ValueError("malformed Coriolis build code")
    bulk = int(c[0])
    pos = 1

    def take(n):
        nonlocal pos
        ids = []
        for _ in range(n):
            if pos >= len(c) or c[pos] == "-":
                ids.append(None); pos += 1
            else:
                ids.append(c[pos:pos + 2]); pos += 2
        return ids
    std = take(len(STANDARD_ORDER))
    hp = take(len(ship["slots"]["hardpoints"]))
    it = take(len(ship["slots"]["internal"]))
    mods = _mods(parts[3] if len(parts) > 3 else "")
    esid, eship = _edsy_ship(ship["name"])
    fd_ship = (eship or {}).get("fdname", "").lower()

    def module_of(info, fdname):
        em = edsy.MODULE_BY_FDNAME.get((fdname or "").lower(), {})
        return {"id": None, "fdname": (fdname or "").lower() or None, "name": info.get("name") or em.get("name") or fdname,
                "class": info.get("class", em.get("class")), "rating": info.get("rating", em.get("rating")), "mount": info.get("mount"),
                "mtype": None, "cost": info.get("cost") or em.get("cost") or 0}

    def eng(slot_no):
        rec = mods.get(slot_no) or {}
        bp = BLUEPRINTS.get(str(rec.get("blueprint"))) if rec.get("blueprint") else None
        sp = SPECIALS.get(str(rec.get("special"))) if rec.get("special") is not None else None
        return ({"fdname": bp["fdname"], "name": bp["name"]} if bp else None, rec.get("grade", 0) if bp else 0,
                {"fdname": sp["edname"], "name": sp["name"]} if sp else None)

    slots = []
    # bulkheads = modification slot 0, journal slot Armour
    arm_fd = None
    if eship:
        arm_fd = ((eship.get("module") or {}).get(EDSY_ARMOUR_IDS[bulk]) or {}).get("fdname")
    binfo = ship["bulkheads"][bulk] if bulk < len(ship["bulkheads"]) else {}
    bp, grade, sp = eng(0)
    slots.append({"group": "component", "index": 0, "slot": "Armour",
                  "module": {"id": None, "fdname": (arm_fd or "").lower() or None, "name": binfo.get("name") or "Bulkheads", "class": 1,
                             "rating": None, "mount": None, "mtype": None, "cost": binfo.get("cost") or 0},
                  "blueprint": bp, "grade": grade, "roll": None, "experimental": sp, "preengineered": False, "powered": True, "priority": 1})
    slot_no = 1
    for i, mid in enumerate(std):
        if mid:
            info = STANDARD.get(STANDARD_ORDER[i], {}).get(mid) or {}
            bp, grade, sp = eng(slot_no)
            slots.append({"group": "component", "index": i + 1, "slot": edsy.CORE_SLOTS[i + 1], "module": module_of(info, info.get("symbol")),
                          "blueprint": bp, "grade": grade, "roll": None, "experimental": sp, "preengineered": False, "powered": True, "priority": 1})
        slot_no += 1
    n_hp = n_ut = 0
    for j, mid in enumerate(hp):
        size = ship["slots"]["hardpoints"][j]
        group = "utility" if size == 0 else "hardpoint"
        idx = n_ut if group == "utility" else n_hp
        if mid:
            info = HARDPOINTS.get(mid) or {}
            bp, grade, sp = eng(slot_no)
            slots.append({"group": group, "index": idx, "slot": edsy.slot_name(eship or {"slots": {}}, group, idx, None) if eship else f"{group}{idx + 1}",
                          "module": module_of(info, info.get("symbol")), "blueprint": bp, "grade": grade, "roll": None, "experimental": sp,
                          "preengineered": False, "powered": True, "priority": 1})
        if group == "utility":
            n_ut += 1
        else:
            n_hp += 1
        slot_no += 1
    n_in = n_mil = 0
    for k, mid in enumerate(it):
        spec = ship["slots"]["internal"][k]
        kind = (spec.get("name") if isinstance(spec, dict) else None) or ""
        if kind == "PlanetaryApproachSuite":
            slot_no += 1
            continue
        group = "military" if kind == "Military" else "internal"
        idx = n_mil if group == "military" else n_in
        if mid:
            info = INTERNAL.get(mid) or {}
            bp, grade, sp = eng(slot_no)
            size = spec.get("class") if isinstance(spec, dict) else spec
            slots.append({"group": group, "index": idx, "slot": f"Military{idx + 1:02d}" if group == "military" else f"Slot{idx + 1:02d}_Size{size}",
                          "module": module_of(info, info.get("symbol")), "blueprint": bp, "grade": grade, "roll": None, "experimental": sp,
                          "preengineered": False, "powered": True, "priority": 1})
        if group == "military":
            n_mil += 1
        else:
            n_in += 1
        slot_no += 1
    return {"version": None, "ship": {"id": esid, "fdname": fd_ship or ship_key, "name": ship["name"]}, "name": bn, "tag": "",
            "slots": slots, "hash": code}
