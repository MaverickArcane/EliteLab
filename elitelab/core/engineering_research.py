"""Reviewed engineering facts. Offline, bounded coverage; never a ship simulator."""
import copy
import json
from pathlib import Path

with Path(__file__).with_name("engineering_research.json").open(encoding="utf-8") as f:
    DATA = json.load(f)


def module_name(value):
    value = " ".join(str(value or "").lower().replace("_", " ").split())
    return {"beam": "beam laser", "beam lasers": "beam laser", "distributor": "power distributor",
            "power distributors": "power distributor", "plant": "power plant", "power plants": "power plant"}.get(value, value)


def records(module=None):
    return [copy.deepcopy(r) for r in DATA["blueprints"]
            if not module or module_name(r["module"]) == module_name(module)]


def lookup(key, module=None):
    matches = [r for r in records(module) if r["key"] == key]
    return matches[0] if len(matches) == 1 else None


def effect(key, module=None):
    return next((copy.deepcopy(r) for r in DATA["effects"] if r["key"] == key
                 and (not module or module_name(r["module"]) == module_name(module))), None)


def provenance(key, module=None):
    row = lookup(key, module) or effect(key, module)
    if not row:
        return {"status": "not_reviewed", "note": "Legacy catalog; no individual source review recorded."}
    return {"status": "reviewed", "module": row["module"], "source": row["source"]}


def validate_catalog(catalog=None):
    """Structural checks for every recipe and drift checks for explicitly reviewed rows."""
    from . import gamedata as gd
    catalog = catalog if catalog is not None else gd._ENG
    errors, warnings = [], []
    known = {m["key"] for m in catalog["materials"]}
    all_rows = catalog["blueprints"] + catalog["experimentals"] + catalog.get("unlocks", [])
    keys = [r["key"] for r in all_rows]
    if len(keys) != len(set(keys)):
        errors.append("Duplicate recipe keys")
    for row in all_rows:
        ingredients = row.get("grades", {}).values() if "grades" in row else [row.get("ingredients", {})]
        for ing in ingredients:
            for key, count in ing.items():
                if key not in known or type(count) is not int or count <= 0:
                    errors.append(f"{row['key']}: invalid ingredient {key}={count}")
        if "grades" in row:
            expected = {str(g) for g in range(1, row["max_grade"] + 1)}
            if set(row["grades"]) - expected:
                errors.append(f"{row['key']}: invalid grades")
            if expected - set(row["grades"]):
                warnings.append(f"{row['key']}: incomplete grade costs; do not assume missing grades are free")
    indexed = {r["key"]: r for r in all_rows}
    for row in DATA["blueprints"] + DATA["effects"]:
        actual = indexed.get(row["key"], {})
        expected = row.get("reviewed_recipe", row.get("ingredients"))
        if actual.get("grades", actual.get("ingredients")) != expected:
            errors.append(f"{row['key']}: recipe differs from reviewed source snapshot")
    reviewed = len(DATA["blueprints"]) + len(DATA["effects"])
    return {"ok": not errors, "errors": errors, "warnings": warnings, "structurally_checked": len(all_rows),
            "source_reviewed": reviewed, "not_source_reviewed": len(all_rows) - reviewed,
            "coverage": DATA["coverage"],
            "sources": [provenance(r["key"]) for r in DATA["blueprints"] + DATA["effects"]]}
