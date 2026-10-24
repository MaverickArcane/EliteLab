"""materials module: engineering materials inventory, wishlist, shortfalls, sources.

State ``materials``: inventory {key: count} (every material seen, by journal key), totals {Raw, Manufactured, Encoded},
wishlist {key: {name, need, label}}, shortfalls [...], inventory_count.

The material catalog (names, grades, caps, trader families) is the shared table in elitelab/core/gamedata.py;
this module's data.json only holds the where-to-find hints.
"""
import json
import os
import threading

from elitelab.core.gamedata import MATERIAL_BY_KEY, MATERIAL_BY_NAME, MATERIAL_CAPS, norm

NS = "materials"
HERE = os.path.dirname(os.path.abspath(__file__))


class Materials:
    def __init__(self, core):
        self.core = core
        self._lock = threading.RLock()
        with open(os.path.join(HERE, "data.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
        self.caps = MATERIAL_CAPS
        self.catalog = MATERIAL_BY_KEY
        self.by_name = dict(MATERIAL_BY_NAME)
        self.sources = data.get("sources", {})
        self.inv = {}      # key -> count
        self.names = {}    # key -> display name seen in journal
        self.cats = {}     # key -> category seen in journal
        self.wishlist = core.read_data("wishlist.json", default={}) or {}
        for e in ("Materials", "MaterialCollected", "MaterialDiscarded", "MaterialTrade", "EngineerCraft", "Synthesis",
                  "TechnologyBroker", "MissionCompleted", "ScientificResearch", "EngineerContribution"):
            core.bus.on("journal." + e, self.on_event)
        core.bus.on("journal.replay.done", lambda n, v: self.publish())
        self.publish()

    # -- resolving names ----------------------------------------------------------
    def resolve(self, name):
        """Accept a journal key, a display name, or a case-insensitive fuzzy name. Returns key or None."""
        if not name:
            return None
        k = norm(name)
        if k in self.catalog or k in self.inv:
            return k
        n = name.strip().lower()
        if n in self.by_name:
            return self.by_name[n]
        for key, disp in self.names.items():
            if disp and disp.lower() == n:
                return key
        # loose: all words present
        words = n.split()
        for key, m in self.catalog.items():
            if all(w in m["name"].lower() for w in words):
                return key
        return None

    def info(self, key):
        m = self.catalog.get(key, {})
        grade = m.get("grade")
        return {"key": key, "name": m.get("name") or self.names.get(key) or key, "category": m.get("category") or self.cats.get(key),
                "grade": grade, "cap": self.caps.get(grade), "count": self.inv.get(key, 0)}

    # -- events ---------------------------------------------------------------------
    def add(self, name, count, category=None, localised=None):
        k = norm(name)
        self.inv[k] = max(0, self.inv.get(k, 0) + int(count or 0))
        if localised:
            self.names[k] = localised
        if category:
            self.cats[k] = category

    def on_event(self, name, ev):
        with self._lock:
            self._on_event(name, ev)

    def _on_event(self, name, ev):
        e = ev.get("event")
        if e == "Materials":
            self.inv = {}
            for cat in ("Raw", "Manufactured", "Encoded"):
                for i in ev.get(cat) or []:
                    self.add(i.get("Name"), i.get("Count", 0), cat, i.get("Name_Localised"))
        elif e == "MaterialCollected":
            self.add(ev.get("Name"), ev.get("Count", 0), ev.get("Category"), ev.get("Name_Localised"))
        elif e == "MaterialDiscarded":
            self.add(ev.get("Name"), -ev.get("Count", 0), ev.get("Category"), ev.get("Name_Localised"))
        elif e == "MaterialTrade":
            p, r = ev.get("Paid") or {}, ev.get("Received") or {}
            self.add(p.get("Material"), -p.get("Quantity", 0), p.get("Category"), p.get("Material_Localised"))
            self.add(r.get("Material"), r.get("Quantity", 0), r.get("Category"), r.get("Material_Localised"))
        elif e in ("EngineerCraft", "Synthesis", "TechnologyBroker", "ScientificResearch"):
            for i in ev.get("Ingredients") or ev.get("Materials") or []:
                if isinstance(i, dict):
                    self.add(i.get("Name"), -i.get("Count", 0), None, i.get("Name_Localised"))
        elif e == "EngineerContribution" and ev.get("Type") == "Materials":
            self.add(ev.get("Material"), -ev.get("Quantity", 0))
        elif e == "MissionCompleted":
            for i in ev.get("MaterialsReward") or []:
                self.add(i.get("Name"), i.get("Count", 0), i.get("Category"), i.get("Name_Localised"))
        self.publish()

    # -- publishing ---------------------------------------------------------------
    def rows(self, category=None, grade=None, only_wishlist=False, only_short=False):
        with self._lock:
            return self._rows(category, grade, only_wishlist, only_short)

    def _rows(self, category=None, grade=None, only_wishlist=False, only_short=False):
        keys = set(self.inv) | set(self.wishlist)
        out = []
        for k in keys:
            r = self.info(k)
            w = self.wishlist.get(k)
            r["need"] = w["need"] if w else 0
            r["label"] = w.get("label") if w else None
            r["short"] = max(0, r["need"] - r["count"])
            if category and (r["category"] or "").lower() != category.lower():
                continue
            if grade and r["grade"] != int(grade):
                continue
            if only_wishlist and not w:
                continue
            if only_short and r["short"] <= 0:
                continue
            out.append(r)
        out.sort(key=lambda r: (-(r["short"] > 0), r["category"] or "", -(r["grade"] or 0), r["name"]))
        return out

    def publish(self):
        with self._lock:
            self._publish()

    def _publish(self):
        totals = {"Raw": 0, "Manufactured": 0, "Encoded": 0}
        for k, c in self.inv.items():
            cat = self.info(k)["category"]
            if cat in totals:
                totals[cat] += c
        self.core.store.update(NS, {"totals": totals, "wishlist": self.wishlist,
                                    "shortfalls": [r for r in self.rows(only_wishlist=True)],
                                    "inventory": dict(self.inv),          # read by the wishlist module (state.materials.inventory)
                                    "inventory_count": len(self.inv)})

    # -- wishlist ------------------------------------------------------------------
    def set_wishlist(self, items, mode="replace", label=None):
        with self._lock:
            return self._set_wishlist(items, mode, label)

    def _set_wishlist(self, items, mode, label):
        if mode not in ("replace", "add", "remove", "clear"):
            raise ValueError("mode must be replace, add, remove, or clear")
        if items is None:
            items = {}
        if isinstance(items, str):
            items = json.loads(items)
        if not isinstance(items, dict):
            raise ValueError("items must be an object mapping material names to quantities")
        if label is not None and not isinstance(label, str):
            raise ValueError("label must be a string")
        wishlist = {} if mode in ("clear", "replace") else dict(self.wishlist)
        unknown = []
        for name, qty in items.items():
            if not isinstance(name, str):
                raise ValueError("material names must be strings")
            try:
                if isinstance(qty, bool) or (isinstance(qty, float) and not qty.is_integer()):
                    raise ValueError()
                qty = int(qty)
            except (ValueError, TypeError, OverflowError):
                raise ValueError(f"quantity for {name} must be an integer") from None
            k = self.resolve(name)
            if not k:
                unknown.append(name); continue
            if mode == "remove":
                wishlist.pop(k, None); continue
            cur = wishlist.get(k, {"need": 0})
            need = cur["need"] + qty if mode == "add" else qty
            wishlist[k] = {"name": self.info(k)["name"], "need": max(0, need), "label": label or cur.get("label")}
        wishlist = {k: v for k, v in wishlist.items() if v["need"] > 0}
        self.core.write_data(wishlist, "wishlist.json")
        self.wishlist = wishlist
        self.publish()
        return {"wishlist": self.rows(only_wishlist=True), "unknown": unknown}

    def source(self, name):
        k = self.resolve(name)
        if not k:
            return {"error": f"unknown material '{name}'"}
        r = self.info(k)
        r["hint"] = self.sources.get(k) or "No specific hint recorded; see general guidance."
        r["general"] = self.sources.get("_general", [])
        return r


def setup(core, module):
    m = Materials(core)
    core.http.route("/api/materials", lambda q: {"totals": core.store.get(NS, "totals"),
                                                 "materials": m.rows(q.get("category"), q.get("grade"), str(q.get("only_wishlist", "")).lower() in ("1", "true"),
                                                                     str(q.get("only_short", "")).lower() in ("1", "true"))},
                    tool="get_materials", module=module.name,
                    description="Engineering materials inventory with grade, cap (300/250/200/150/100 for G1-G5), wishlist need and shortfall per material.",
                    params={"category": {"type": "string", "description": "Raw, Manufactured or Encoded", "enum": ["Raw", "Manufactured", "Encoded"]},
                            "grade": {"type": "integer", "description": "1-5"},
                            "only_wishlist": {"type": "boolean", "description": "Only materials on the wishlist", "default": False},
                            "only_short": {"type": "boolean", "description": "Only materials where need exceeds stock", "default": False}})
    core.http.route("/api/materials/wishlist", lambda q: {"wishlist": m.rows(only_wishlist=True)},
                    tool="get_wishlist", module=module.name, description="The materials wishlist with have/need/short for each entry.")
    core.http.route("/api/materials/wishlist", lambda q: m.set_wishlist(q.get("items"), q.get("mode", "replace"), q.get("label")),
                    tool="set_wishlist", method="POST", module=module.name,
                    description="Set the materials wishlist, e.g. everything needed for a blueprint. Names may be display names "
                                "('Datamined Wake Exceptions') or journal keys. The dashboard then shows shortfalls live as materials are collected.",
                    params={"items": {"type": "object", "description": "Map of material name -> quantity needed", "required": True},
                            "mode": {"type": "string", "description": "replace (default), add (increase needs), remove (drop these), clear (empty the list first)", "enum": ["replace", "add", "remove", "clear"], "default": "replace"},
                            "label": {"type": "string", "description": "What this is for, e.g. 'FSD G5 Increased Range x3'"}})
    core.http.route("/api/materials/sources", lambda q: m.source(q.get("name")),
                    tool="material_sources", module=module.name,
                    description="Where to farm a material: community-known sites and the general approach, plus current stock and cap.",
                    params={"name": {"type": "string", "description": "Material display name or key", "required": True}})
