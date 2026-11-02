"""Read-only, explicit-roll material budgets; never promises engineering outcomes."""
from . import gamedata as gd
from . import engineering_research as research


def integer(q, key, default, low, high):
    raw = q.get(key, default)
    try:
        value = int(raw)
    except (ValueError, TypeError):
        raise ValueError(f"{key} must be an integer") from None
    if isinstance(raw, bool) or str(value) != str(raw) or not low <= value <= high:
        raise ValueError(f"{key} must be an integer from {low} to {high}")
    return value


def plan(q, inventory, engineers):
    module = q.get("module")
    hit = gd.resolve_recipe(q.get("blueprint"), kind="blueprint", module=module)
    if "match" not in hit and module:
        fallback = gd.resolve_recipe(q.get("blueprint"), kind="blueprint").get("match")
        row = gd.BLUEPRINT_BY_KEY.get((fallback or {}).get("key"), {})
        if row.get("module") == "Weapon" and str(module).casefold() in [s.casefold() for s in row.get("aliases", [])]:
            hit = {"match": fallback}
    if "match" not in hit:
        return {"status": "ambiguous_or_unknown_recipe", "candidates": hit.get("candidates", [])}
    bp = gd.BLUEPRINT_BY_KEY[hit["match"]["key"]]
    grade = integer(q, "grade", 1, 1, bp["max_grade"])
    start = integer(q, "from_grade", 0, 0, grade)
    qty = integer(q, "quantity", 1, 1, 20)
    mode = q.get("mode", "estimate")
    if mode not in ("estimate", "single_roll"):
        raise ValueError("mode must be estimate or single_roll")
    rolls = dict(gd.ROLLS_PER_GRADE)
    if q.get("rolls"):
        values = str(q["rolls"]).split(",")
        if len(values) != 5:
            raise ValueError("rolls must contain five positive counts, G1 through G5, e.g. 1,2,3,4,5")
        rolls = {g: integer({"rolls": v.strip()}, "rolls", 1, 1, 20) for g, v in enumerate(values, 1)}
        if mode == "single_roll":
            raise ValueError("Custom rolls cannot be combined with single_roll")
    grades = [grade] if mode == "single_roll" else list(range(start + 1, grade + 1))
    costs, per_grade = {}, []
    for g in grades:
        ingredients = bp["grades"].get(str(g))
        if not ingredients:
            raise ValueError(f"Missing catalog costs for grade {g}; cannot treat that grade as free")
        count = 1 if mode == "single_roll" else rolls[g]
        per_grade.append({"grade": g, "rolls_per_module": count, "per_roll": ingredients})
        for name, amount in ingredients.items():
            costs[name] = costs.get(name, 0) + amount * count * qty
    effect = None
    if q.get("experimental"):
        # A concrete module is required to validate effect compatibility.
        if not module:
            raise ValueError("module is required when adding an experimental effect")
        match = gd.resolve_recipe(q["experimental"], kind="experimental", module=module).get("match")
        if not match:
            raise ValueError("Experimental effect is unknown, ambiguous or incompatible with the requested module")
        effect = gd.EXPERIMENTAL_BY_KEY[match["key"]]
        for name, amount in effect["ingredients"].items():
            costs[name] = costs.get(name, 0) + amount * qty
    if not grades and not effect:
        raise ValueError("No upgrade steps: select a higher target grade, single_roll, or an experimental effect")
    materials = []
    for name, amount in sorted(costs.items()):
        info = gd.MATERIAL_BY_KEY.get(name, {})
        have = inventory.get(name, 0) if inventory is not None else None
        materials.append({"key": name, "name": info.get("name", name), "grade": info.get("grade"), "category": info.get("category"),
                          "need": amount, "have": have, "short": max(0, amount - have) if have is not None else None,
                          "remaining_after": have - amount if have is not None and have >= amount else None})
    concrete = module or bp["module"]
    reviewed = research.lookup(bp["key"], concrete)
    # Generic Weapon rows historically contain beam-centric engineer caps.
    # Never advertise those as capabilities for another concrete weapon.
    caps = reviewed["engineers"] if reviewed else {} if bp["module"] == "Weapon" else bp["engineers"]
    access = {r["name"].casefold(): r for r in engineers}
    choices = []
    for name, cap in caps.items():
        if q.get("engineer") and str(q["engineer"]).casefold() not in name.casefold():
            continue
        row = access.get(name.casefold(), {})
        choices.append({"name": name, "max_grade": cap, "offers_target_grade": cap >= grade,
                        "progress": row.get("progress", "unknown"), "rank": row.get("rank"), "observed_at": row.get("observed_at"),
                        "cap_source": "reviewed_concrete_module" if reviewed else "legacy_catalog"})
    return {"status": "planned", "blueprint": {"key": bp["key"], "name": bp["name"], "module": module or bp["module"]},
            "grade": grade, "from_grade": start, "quantity": qty, "mode": mode, "steps": per_grade,
            "experimental": {"key": effect["key"], "name": effect["name"], "applications": qty,
                             "provenance": research.provenance(effect["key"], module)} if effect else None,
            "materials": materials, "affordable": all(r["short"] == 0 for r in materials) if inventory is not None else None,
            "engineers": choices, "engineer_cap_coverage": "reviewed_concrete_module" if reviewed else "unavailable_for_generic_weapon" if bp["module"] == "Weapon" else "legacy_catalog",
            "provenance": research.provenance(bp["key"], concrete),
            "assumptions": ["from_grade means completed grades of the SAME blueprint; a blueprint change must start at zero.",
                            "Estimated roll counts are planning inputs, not guaranteed costs or engineer reputation gains.",
                            "single_roll budgets one roll at the requested grade; it does not establish access to that grade.",
                            "An experimental effect is charged once per module; omit it if already fitted and retained.",
                            "Inventory affordability does not establish module compatibility, engineer access or grade availability.",
                            "No wishlist, pin or material inventory is changed."]}
