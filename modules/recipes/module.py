"""recipes module: engineering blueprints and experimental effects with their material costs.

Read-only. The tables live in elitelab/core/gamedata.py (engineering.json). State ``recipes`` only carries counts
and the rolls-per-grade planning hint; the data is served by the routes so it never goes over SSE.
"""
from elitelab.core import gamedata as gd

NS = "recipes"


def mats(ingredients):
    """{key: count} -> rows with names, sorted by category and grade."""
    rows = []
    for k, c in ingredients.items():
        m = gd.MATERIAL_BY_KEY.get(k, {})
        rows.append({"key": k, "name": m.get("name") or k, "category": m.get("category"), "grade": m.get("grade"), "count": c})
    rows.sort(key=lambda r: (r["category"] or "", r["grade"] or 0, r["name"]))
    return rows


def detail(hit, grade=None, from_grade=0, qty=1):
    if hit["kind"] == "blueprint":
        b = gd.BLUEPRINT_BY_KEY[hit["key"]]
        grade = int(grade or b["max_grade"])
        from_grade = int(from_grade or 0)
        if not 1 <= grade <= b["max_grade"] or not 0 <= from_grade < grade:
            raise ValueError(f"grade must be 1-{b['max_grade']} and from_grade below it")
        return {"kind": "blueprint", "key": b["key"], "name": b["name"], "module": b["module"], "max_grade": b["max_grade"],
                "grades": {g: mats(ing) for g, ing in b["grades"].items()},
                "engineers": b["engineers"],
                "rolls_per_grade": gd.ROLLS_PER_GRADE,
                "total": {"grade": grade, "from_grade": from_grade, "qty": qty,
                          "materials": mats(gd.recipe_cost(b["key"], grade, from_grade, qty=qty))},
                "note": "grades[g] is the cost of one roll at that grade; total walks every grade from from_grade+1 to grade "
                        "with rolls_per_grade rolls each (a planning hint, not a rule), times qty."}
    if hit["kind"] == "unlock":
        u = gd.UNLOCK_BY_KEY[hit["key"]]
        return {"kind": "unlock", "key": u["key"], "name": u["name"], "module": u["module"], "broker": u["broker"],
                "materials": mats(gd.recipe_cost(u["key"], qty=qty)), "commodities": {k: v * qty for k, v in u["commodities"].items()}, "qty": qty,
                "note": "Technology broker unlock: hand in these materials and commodities once at a broker of this type; the module is "
                        "then purchasable everywhere. Commodities are cargo, not materials, and are not tracked by the wishlist."}
    e = gd.EXPERIMENTAL_BY_KEY[hit["key"]]
    return {"kind": "experimental", "key": e["key"], "name": e["name"], "modules": e["modules"],
            "materials": mats(gd.recipe_cost(e["key"], qty=qty)), "qty": qty,
            "note": "An experimental effect is applied once per module, on top of a blueprint of any grade."}


def setup(core, module):
    core.store.update(NS, {"blueprints": len(gd.BLUEPRINTS), "experimentals": len(gd.EXPERIMENTALS), "unlocks": len(gd.UNLOCKS),
                           "rolls_per_grade": gd.ROLLS_PER_GRADE, "modules": gd.RECIPE_MODULES, "engineers": gd.ENGINEERS})

    def listing(q):
        limit = max(1, min(int(q.get("limit", 20) or 20), 200))
        hits = gd.find_recipes(q.get("query") or "", kind=q.get("kind") or None, module=q.get("module") or None,
                               engineer=q.get("engineer") or None, limit=0)
        return {"count": len(hits), "results": hits[:limit],
                "note": "Pass a result's key to get_recipe for the per-grade materials, or to wishlist_add to track it."}

    def get(q):
        key = q.get("key") or q.get("query")
        if not key:
            raise ValueError("key (or query) is required")
        r = gd.resolve_recipe(key, kind=q.get("kind") or None, module=q.get("module") or None)
        if "match" not in r:
            return {"error": "no single recipe matches; be more specific or pass a key", "candidates": r["candidates"]}
        return detail(r["match"], q.get("grade"), q.get("from_grade") or 0, max(1, int(q.get("qty", 1) or 1)))

    core.http.route("/api/recipes", listing, tool="list_recipes", module=module.name,
                    description="Search engineering blueprints, experimental effects and technology broker unlocks (Guardian modules and "
                                "weapons, human broker items) by free text ('fsd range', 'dirty drives', 'guardian fsd booster', 'mass manager'). "
                                "Returns compact hits with keys; call get_recipe for materials.",
                    params={"query": {"type": "string", "description": "Words to match against module, blueprint/effect/unlock name and aliases; empty lists all"},
                            "kind": {"type": "string", "description": "Only blueprints, experimental effects or unlocks", "enum": ["blueprint", "experimental", "unlock"]},
                            "module": {"type": "string", "description": "Restrict to a module, e.g. 'frame shift drive' or 'shield booster'"},
                            "engineer": {"type": "string", "description": "Only blueprints this engineer offers (e.g. 'Farseer'); adds engineer_grade, the highest grade they do"},
                            "limit": {"type": "integer", "description": "Max hits (<=200)", "default": 20}})
    core.http.route("/api/recipes/get", get, tool="get_recipe", module=module.name,
                    description="One blueprint with the materials for each grade, which engineers offer which grade, and the total "
                                "to take a module from from_grade to grade (default: unengineered to max grade, with the rolls-per-grade "
                                "hint); or one experimental effect with its materials. Accepts a key from list_recipes or free text.",
                    params={"key": {"type": "string", "description": "Recipe key (e.g. FSD_LongRange, special_fsd_heavy) or free text", "required": True},
                            "grade": {"type": "integer", "description": "Target grade 1-5; default = the blueprint's max"},
                            "from_grade": {"type": "integer", "description": "Grade the module already has; default 0", "default": 0},
                            "qty": {"type": "integer", "description": "How many modules", "default": 1},
                            "kind": {"type": "string", "description": "Disambiguate free text", "enum": ["blueprint", "experimental", "unlock"]},
                            "module": {"type": "string", "description": "Disambiguate free text by module"}})
