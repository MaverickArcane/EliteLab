"""Decoder for EDSY build links (https://edsy.org/#/L=<hash>), hash versions 15 to 20.

The hash is EDSY's own base-64 variant. Per build: version, ship id, hull cost/discount, crew and power
distributor bits, then one comma-separated chunk per slot group (hardpoint, utility, component, military,
internal) holding, per fitted slot: module id (3 chars), slot bits, cost or discount, and when engineered:
blueprint index + grade + experimental index, roll, and the modified attributes (skipped here). The tables
(ships, modules, module types, blueprints, effects) come from EDSY's eddb.js, extracted into edsy.json.
Older links (version < 15) raise ValueError: open them in EDSY and copy the link again.
"""
import json
import os
import re
import urllib.parse

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "edsy.json"), "r", encoding="utf-8") as _f:
    _DB = json.load(_f)
SHIPS, MODULES, MTYPES, BLUEPRINTS, EXPEFFECTS = _DB["ships"], _DB["modules"], _DB["mtypes"], _DB["blueprints"], _DB["expeffects"]
MODULE_BY_FDNAME = {m["fdname"].lower(): {**m, "id": int(k)} for k, m in MODULES.items() if m.get("fdname")}   # journal item -> module
for _s in SHIPS.values():                                                                                        # ship-specific bulkheads
    for _k, _m in (_s.get("module") or {}).items():
        if _m.get("fdname"):
            MODULE_BY_FDNAME.setdefault(_m["fdname"].lower(), {"fdname": _m["fdname"], "name": MODULES.get(_k, {}).get("name") or "Bulkheads",
                                                                "class": 1, "rating": None, "cost": _m.get("cost") or 0, "id": int(_k)})
SHIP_BY_FDNAME = {s["fdname"].lower(): {**s, "id": int(k)} for k, s in SHIPS.items() if s.get("fdname")}

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_-"
TALPHABET = " !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
_CHR = {c: i for i, c in enumerate(ALPHABET)}
GROUPS = ["hardpoint", "utility", "component", "military", "internal"]
CORE_SLOTS = ["Armour", "PowerPlant", "MainEngines", "FrameShiftDrive", "LifeSupport", "PowerDistributor", "Radar", "FuelTank"]
HARDPOINT_SIZE = {0: "Tiny", 1: "Small", 2: "Medium", 3: "Large", 4: "Huge"}
GAP_BASE = 199900


def _num(h):
    n = 0
    for c in h:
        n = (n << 6) | _CHR.get(c, 0)
    return n


def _text(h):
    out, i = [], 0
    while i < len(h):
        c1 = _CHR.get(h[i]); i += 1
        if c1 is None:
            continue
        if c1 < 62:
            out.append(ALPHABET[c1])
        elif c1 == 62 and i < len(h):
            out.append(TALPHABET[_CHR.get(h[i], 0)] if _CHR.get(h[i], 0) < len(TALPHABET) else ""); i += 1
        elif c1 == 63 and i + 1 < len(h):
            out.append(chr(((_CHR.get(h[i], 0) << 6) | _CHR.get(h[i + 1], 0)) + 0x7F)); i += 2
    return "".join(out)


def jump_range(fsd_item, optmass, mass, booster_item=None):
    """Single-jump range in Ly: (maxfuel / fuelmul) ** (1 / fuelpower) * optimal mass / ship mass, plus a Guardian FSD
    booster's flat bonus. ``optmass`` is the engineered value from the Loadout modifiers (or the base value); ``mass``
    is hull + modules + fuel + cargo. Matches the journal's MaxJumpRange when mass = unladen + one jump's fuel.
    Returns None when the FSD is not in the table."""
    fsd = MODULE_BY_FDNAME.get((fsd_item or "").lower())
    if not fsd or not fsd.get("fuelpower") or not mass or not optmass:
        return None
    r = (fsd["maxfuel"] / fsd["fuelmul"]) ** (1.0 / fsd["fuelpower"]) * optmass / mass
    boost = (MODULE_BY_FDNAME.get((booster_item or "").lower()) or {}).get("jumpbst") or 0
    return round(r + boost, 2)


def extract_hash(text):
    """The build hash from an EDSY URL (any host), a '#/L=...' fragment, or a bare hash."""
    text = urllib.parse.unquote((text or "").strip())
    m = re.search(r"L=([0-9A-Za-z_,\-]+)", text)
    h = m.group(1) if m else text
    if not re.fullmatch(r"[0-9A-Za-z_,\-]+", h) or len(h) < 8:
        raise ValueError("not an EDSY build link; expected https://edsy.org/#/L=...")
    return h


def slot_name(ship, group, index, module):
    """The journal slot name EDSY's slot would have in a Loadout event (best effort; used for display only)."""
    if group == "component":
        return CORE_SLOTS[index] if index < len(CORE_SLOTS) else f"Core{index}"
    sizes = (ship.get("slots") or {}).get(group) or []
    if group == "hardpoint":
        size = sizes[index] if index < len(sizes) else None
        nth = sum(1 for s in sizes[:index] if s == size) + 1
        return f"{HARDPOINT_SIZE.get(size, 'Hardpoint')}Hardpoint{nth}"
    if group == "utility":
        return f"TinyHardpoint{index + 1}"
    if group == "military":
        return f"Military{index + 1:02d}"
    names = (ship.get("slotnames") or {}).get("internal") if ship.get("slotnames") else None
    if names and index < len(names):
        return names[index]
    size = sizes[index] if index < len(sizes) else 0
    return f"Slot{index + 1:02d}_Size{size}"


def _module_info(shipid, modid):
    m = MODULES.get(str(modid)) or {}
    fdname = m.get("fdname") or ((SHIPS.get(str(shipid)) or {}).get("module") or {}).get(str(modid), {}).get("fdname")
    return {"id": modid, "fdname": (fdname or "").lower() or None, "name": m.get("name") or f"module {modid}", "class": m.get("class"),
            "rating": m.get("rating"), "mount": m.get("mount"), "mtype": m.get("mtype"), "cost": m.get("cost") or 0}


def decode(text):
    """Decode an EDSY build link into {ship{id, fdname, name}, name, tag, version, slots[...]}.

    Each slot: {group, index, slot (journal-style name), module{id, fdname, name, class, rating, mount, cost},
    blueprint{fdname, name} | None, grade, experimental{fdname, name} | None, preengineered, powered, priority}."""
    h = extract_hash(text)
    version = _num(h[0])
    if version < 15 or version > _DB["hash_version"]:
        raise ValueError(f"unsupported EDSY link version {version}; open the build in EDSY and copy the link again")
    chunks = h[1:].split(",")
    ship_chunk = chunks[0]
    shipid = _num(ship_chunk[0])
    ship = SHIPS.get(str(shipid))
    if not ship:
        raise ValueError(f"unknown EDSY ship id {shipid}; the EDSY tables may need regenerating")
    i = 1
    i += 1                                              # hull discount bits
    costbits = _num(ship_chunk[i]); i += 1
    i += ((costbits >> 4) & 0x3) + 2                    # hull cost
    i += 1 + 2                                          # crew bits, power distributor bits; the rest of the chunk is the cargo hatch
    slots = []
    for g, group in enumerate(GROUPS):
        chunk = chunks[1 + g] if len(chunks) > 1 + g else ""
        j, n = 0, 0
        while j < len(chunk):
            modid = _num(chunk[j:j + 3]); j += 3
            if modid >= GAP_BASE:
                n += modid - GAP_BASE
                continue
            slotbits = _num(chunk[j:j + 1]); j += 1
            costed, engineered = slotbits & 0x20, slotbits & 0x10
            if costed:
                cb = _num(chunk[j:j + 1]); j += 1
                j += ((cb >> 4) & 0x3) + 2
            else:
                j += 1
            module = _module_info(shipid, modid)
            bp = exp = None
            grade, roll, preeng = 0, None, False
            if engineered:
                engbits = _num(chunk[j:j + 2]); j += 2
                preeng = bool((engbits >> 11) & 0x1) if version >= 18 else False
                bpidx, grade, expidx = (engbits >> 7) & 0xF, (engbits >> 4) & 0x7, engbits & 0xF
                roll = _num(chunk[j:j + 2]) / 4000.0; j += 2
                nummods = _num(chunk[j:j + 1]); j += 1
                j += nummods * 4
                mtype = MTYPES.get(module.get("mtype") or "", {})
                if bpidx and bpidx - 1 < len(mtype.get("blueprints", [])):
                    b = BLUEPRINTS.get(mtype["blueprints"][bpidx - 1], {})
                    bp = {"fdname": b.get("fdname"), "name": b.get("name")}
                if expidx and expidx - 1 < len(mtype.get("expeffects", [])):
                    e = EXPEFFECTS.get(mtype["expeffects"][expidx - 1], {})
                    exp = {"fdname": e.get("fdname"), "name": e.get("name")}
            slots.append({"group": group, "index": n, "slot": slot_name(ship, group, n, module), "module": module,
                          "blueprint": bp, "grade": grade if bp else 0, "roll": roll, "experimental": exp, "preengineered": preeng,
                          "powered": not (slotbits & 0x8), "priority": (slotbits & 0x7) + 1})
            n += 1
    return {"version": version, "ship": {"id": shipid, "fdname": (ship.get("fdname") or "").lower(), "name": ship.get("name")},
            "name": _text(chunks[6]) if len(chunks) > 6 else "", "tag": _text(chunks[7]) if len(chunks) > 7 else "",
            "slots": slots, "hash": h}
