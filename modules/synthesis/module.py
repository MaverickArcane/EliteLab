"""Read-only synthesis planning and conservative journal evidence for single-jump boosts."""
import copy
import hashlib
import json
import threading
from datetime import datetime, timezone

from elitelab.core.gamedata import MATERIAL_BY_KEY, norm
from elitelab.core.neutron import number

from elitelab.core.synthesis_catalog import CATALOG, RECIPES

MATERIAL_EVENTS = {"Materials", "MaterialCollected", "MaterialDiscarded", "MaterialTrade", "EngineerCraft",
                   "Synthesis", "TechnologyBroker", "MissionCompleted", "ScientificResearch", "EngineerContribution"}


def stamp(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat() if dt.tzinfo else None
    except (TypeError, ValueError, AttributeError):
        return None


def integer(value, label, low, high):
    result = number(value, label, low, high)
    if result != int(result):
        raise ValueError(label + " must be an integer")
    return int(result)


class Synthesis:
    def __init__(self, core):
        self.core = core
        self.lock = threading.RLock()
        self.accounts = core.read_data("synthesis.json", default={})
        self.session = None
        self.inv = None
        self.inventory_at = None
        self.inventory_revision = 0
        self.last_at = ""
        self.ship_id = None
        self.boost = {"status": "unknown"}
        self.last_jump = None
        self.seen = set()
        core.bus.on("journal.*", self.event)
        core.bus.on("state.progression.commander", self.identity_changed)
        core.bus.on("state.progression.session_started_at", self.identity_changed)
        self.identity_changed()

    def identity_changed(self, *args):
        with self.lock:
            p = self.core.store.get("progression")
            session = ((p.get("commander") or {}).get("key"), p.get("session_started_at"))
            if self.session != session:
                self.session = session
                self.inv, self.inventory_at, self.ship_id = None, None, None
                self.inventory_revision += 1
                self.last_at, self.seen = "", set()
                self.boost, self.last_jump = {"status": "unknown"}, None
            self.publish()

    def event(self, topic, e):
        if not isinstance(e, dict):
            return
        kind, at = e.get("event"), stamp(e.get("timestamp"))
        watched = MATERIAL_EVENTS | {"Loadout", "LoadGame", "FSDJump", "JetConeBoost", "ShipyardSwap", "Died", "Shutdown"}
        if kind not in watched or not at:
            return
        with self.lock:
            self.identity_changed()
            key, since = self.session
            if not key or not since or at < since or at < self.last_at:
                return
            signature = hashlib.sha256(json.dumps({k: v for k, v in e.items() if not k.startswith("_")}, sort_keys=True).encode()).hexdigest()
            if signature in self.seen:
                return
            self.seen.add(signature)
            self.last_at = at
            if kind == "Materials" or (kind in MATERIAL_EVENTS and self.inv is not None):
                # Materials owns deduction logic. Read its post-event result once; never deduct twice.
                self.inv = self.core.http.tools["get_material_inventory"].fn({})["inventory"]
                self.inventory_at = at
                self.inventory_revision += 1
            if kind == "Loadout":
                if self.ship_id is not None and self.ship_id != e.get("ShipID"):
                    self.boost = {"status": "unknown", "reason": "Ship changed", "observed_at": at}
                self.ship_id = e.get("ShipID")
            if kind in ("LoadGame", "ShipyardSwap", "Died", "Shutdown"):
                self.boost = {"status": "unknown", "reason": kind, "observed_at": at}
            if kind == "Synthesis":
                costs = {norm(r.get("Name")): r.get("Count") for r in e.get("Materials", []) if isinstance(r, dict)}
                matches = [r for r in RECIPES if r["journal_name"].casefold() == str(e.get("Name", "")).casefold() and r["materials"] == costs]
                recipe = matches[0] if len(matches) == 1 else None
                account = self.accounts.setdefault(key, {"history": [], "counts": {}})
                if not any(r["id"] == signature for r in account["history"]):
                    item = {"id": signature, "observed_at": at, "name": e.get("Name"),
                            "recipe_key": recipe["key"] if recipe else None, "materials_spent": costs, "ship_id": self.ship_id}
                    account["history"].append(item)
                    account["history"] = account["history"][-200:]
                    # Counts describe this retained evidence window, avoiding replay double-counting.
                    account["counts"] = {}
                    for row in account["history"]:
                        label = row["recipe_key"] or row["name"] or "unknown"
                        account["counts"][label] = account["counts"].get(label, 0) + 1
                    self.core.write_data(self.accounts, "synthesis.json")
                if str(e.get("Name", "")).casefold().startswith("fsd "):
                    self.boost = {"status": "injection_observed" if recipe else "unknown_injection", "source": "Synthesis",
                                  "grade": recipe["grade"] if recipe else None,
                                  "multiplier": recipe.get("range_multiplier") if recipe else None,
                                  "observed_at": at, "ship_id": self.ship_id}
            elif kind == "JetConeBoost":
                value = e.get("BoostValue")
                self.boost = {"status": "jet_cone_observed", "source": "JetConeBoost", "observed_at": at,
                              "multiplier": value if type(value) in (int, float) and 1 < value <= 10 else None,
                              "ship_id": self.ship_id}
            elif kind == "FSDJump":
                self.last_jump = {"observed_at": at, "system": e.get("StarSystem"), "boost_used": e.get("BoostUsed"),
                                  "preceding_boost": copy.deepcopy(self.boost)}
                self.boost = {"status": "jump_completed", "observed_at": at,
                              "reason": "Previous boost observation cleared on ship jump; BoostUsed alone does not identify its source"}
            self.publish()

    def recipe(self, recipe, quantity=1):
        ingredients = []
        for key, count in recipe["materials"].items():
            have = self.inv.get(key, 0) if self.inv is not None else None
            ingredients.append({"key": key, "name": MATERIAL_BY_KEY.get(key, {}).get("name", key),
                                "per_craft": count, "required": count * quantity, "have": have,
                                "short": max(0, count * quantity - have) if have is not None else None})
        return {**recipe, "ingredients": ingredients, "quantity": quantity,
                "craftable": min(i["have"] // i["per_craft"] for i in ingredients) if self.inv is not None else None}

    def listing(self, q):
        limit = integer(q.get("limit", 20), "limit", 1, 100)
        quantity = integer(q.get("quantity", 1), "quantity", 1, 10000)
        grade = str(q.get("grade") or "").casefold()
        if grade and grade not in ("basic", "standard", "premium"):
            raise ValueError("grade must be basic, standard or premium")
        words = str(q.get("query") or "").casefold().split()
        with self.lock:
            rows = [r for r in RECIPES if (not grade or grade == r["grade"]) and all(w in (r["name"] + " " + r["key"] + " " + r["journal_name"] + " " + " ".join(r.get("aliases", []))).casefold() for w in words)]
            return {"recipes": [self.recipe(r, quantity) for r in rows[:limit]], "total": len(rows),
                    "truncated": len(rows) > limit, "inventory_observed_at": self.inventory_at,
                    "source": CATALOG["source"], "checked_at": CATALOG["checked_at"], "scope": CATALOG["scope"],
                    "note": "Craftable counts are alternatives sharing the same inventory, not quantities you can add together. No materials are reserved or spent by this tool."}

    def budget(self, q):
        items = q.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise ValueError("items must contain 1-100 recipe/quantity objects")
        totals, recipes = {}, {r["key"]: r for r in RECIPES}
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("key"), str) or item["key"] not in recipes:
                raise ValueError("Use exact recipe keys from list_synthesis_recipes")
            quantity = integer(item.get("quantity", 1), "quantity", 1, 10000)
            for key, count in recipes[item["key"]]["materials"].items():
                totals[key] = totals.get(key, 0) + count * quantity
        with self.lock:
            rows = [{"key": key, "name": MATERIAL_BY_KEY.get(key, {}).get("name", key), "required": count,
                     "have": self.inv.get(key, 0) if self.inv is not None else None,
                     "short": max(0, count - self.inv.get(key, 0)) if self.inv is not None else None} for key, count in sorted(totals.items())]
            return {"materials": rows, "affordable": all(r["short"] == 0 for r in rows) if self.inv is not None else None,
                    "inventory_observed_at": self.inventory_at, "note": "Combined costs account for shared materials. Planning only; nothing is synthesized or reserved."}

    def status(self, q):
        limit = integer(q.get("limit", 10), "limit", 0, 50)
        with self.lock:
            account = self.accounts.get(self.session[0], {})
            history = account.get("history", [])
            return {"commander": self.core.store.get("progression", "commander"), "session_started_at": self.session[1],
                    "boost": copy.deepcopy(self.boost), "last_jump": copy.deepcopy(self.last_jump),
                    "injections": [self.recipe(r) for r in RECIPES if r["name"] == "FSD Injection"],
                    "inventory_observed_at": self.inventory_at, "history": copy.deepcopy(list(reversed(history))[:limit]),
                    "inventory_revision": self.inventory_revision,
                    "recorded_crafts": dict(account.get("counts", {})), "history_window": len(history),
                    "notes": ["Boost state is journal evidence, not a live in-game boost gauge. A new session or ship change makes it unknown.",
                              "Injections and jet-cone boosts do not stack. A later boost replaces the preceding observation; a ship jump clears it.",
                              "Only ship FSDJump clears boost evidence; a carrier jump does not consume an injection.",
                              "Craft history retains up to 200 observed syntheses per commander, not lifetime totals. Inventory requires a Materials event in this session."]}

    def publish(self):
        self.core.store.set("synthesis", "summary", self.status({"limit": 5}))


def setup(core, module):
    obj = Synthesis(core)
    core.http.route("/api/synthesis/recipes", obj.listing, tool="list_synthesis_recipes", module=module.name,
        description="Search synthesis recipes including FSD injections, AFMU refills, heatsinks, life support, limpets, SRV and common ammunition. Includes exact material costs, craftable counts and shortages for quantity. Counts share inventory; use plan_synthesis for combined costs.",
        params={"query": {"type": "string"}, "grade": {"type": "string", "enum": ["basic", "standard", "premium"]},
                "quantity": {"type": "integer", "default": 1}, "limit": {"type": "integer", "default": 20}})
    core.http.route("/api/synthesis/status", obj.status, tool="get_fsd_injection_status", module=module.name,
        description="Observed injection/jet-cone boost, last ship jump BoostUsed, injection craftability and recent synthesis history. No live boost gauge; never multiply injection and neutron bonuses together. Unknown stock until current session Materials snapshot.",
        params={"limit": {"type": "integer", "default": 10, "description": "Recent syntheses 0-50"}})
    core.http.route("/api/synthesis/plan", obj.budget, tool="plan_synthesis", method="POST", module=module.name,
        description="Read-only combined synthesis material budget. Sum exact recipe keys and quantities, accounting for shared ingredients. Returns costs and shortages without reserving materials or crafting anything.",
        params={"items": {"type": "array", "required": True, "items": {"type": "object", "properties": {"key": {"type": "string"}, "quantity": {"type": "integer"}}, "required": ["key"]}}})
