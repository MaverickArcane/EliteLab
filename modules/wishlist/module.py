"""wishlist module: a trackable engineering wishlist against the live materials inventory.

Entries are blueprints to a target grade ('2x G5 FSD increased range'), experimental effects ('mass manager') or
plain materials ('50 tellurium'). Needs are summed per material, compared with ``materials.inventory`` on every
change, and the shortfalls get a material trader plan (what to hand in for what) plus a nearest-trader lookup.

State ``wishlist``: entries [...], needs [...], summary {...}, trades {...}.
Persisted in data/engineering_wishlist.json as the raw entries only.
"""
import math
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from elitelab.core import gamedata as gd
from elitelab.core.synthesis_catalog import BY_KEY as SYNTHESIS, RECIPES as SYNTHESIS_RECIPES
from modules.wishlist.trading import plan_trades

NS = "wishlist"
FILE = "engineering_wishlist.json"
TRADER_TYPES = ["Raw", "Manufactured", "Encoded"]
_WORDS = re.compile(r"[a-z0-9]+")


_RANGE = re.compile(r"(?<![a-z0-9])(?:from\s+)?g?([0-5])\s*(?:-|to|>|\.\.)\s*g?([1-5])(?![a-z0-9])")


def parse_item(text):
    """'2x g5 fsd boost' -> ('fsd boost', 2, 5, None); '50 tellurium' -> ('tellurium', 50, None, None);
    'fsd range 2-5 x2' -> ('fsd range', 2, 5, 2) (from grade 2 to grade 5)."""
    text = (text or "").lower()
    from_grade = None
    m = _RANGE.search(text)
    if m:
        from_grade, grade_to = int(m.group(1)), int(m.group(2))
        text = text[:m.start()] + " " + text[m.end():]
    toks = _WORDS.findall(text)
    qty, grade = None, (grade_to if m else None)
    rest, i = [], 0
    while i < len(toks):
        t = toks[i]
        m = re.fullmatch(r"(\d+)x", t) or re.fullmatch(r"x(\d+)", t)
        if m:
            qty = int(m.group(1) or m.group(2))
        elif re.fullmatch(r"g(?:rade)?([1-5])", t):
            grade = int(t[-1])
        elif t == "grade" and i + 1 < len(toks) and toks[i + 1].isdigit():
            grade = int(toks[i + 1])
            i += 1
        elif t.isdigit():
            if not rest and qty is None:
                qty = int(t)
            elif grade is None and 1 <= int(t) <= 5:
                grade = int(t)
            else:
                rest.append(t)
        else:
            rest.append(t)
        i += 1
    return " ".join(rest), qty, grade, from_grade


class Wishlist:
    def __init__(self, core):
        self.core = core
        self._lock = threading.RLock()
        self.entries = [e for e in (core.read_data(FILE, default=[]) or []) if isinstance(e, dict) and e.get("key")]
        core.bus.on("state.materials.inventory_version", lambda n, v: self.publish())
        core.bus.on("state.build.progress", lambda n, v: self.publish())      # a tracked build's needs come from the build module
        self.publish()

    # -- helpers --------------------------------------------------------------------
    def inventory(self):
        """{key: count} from the materials module's tool (the inventory is not in the store; see materials)."""
        t = self.core.http.tools.get("get_material_inventory")
        data = t.fn({}) if t else {}
        self._inventory_known = bool(data.get("inventory_known"))
        self._inventory_at = data.get("observed_at")
        return data.get("inventory") or {}

    def entry_needs(self, e):
        if e["kind"] == "synthesis":
            return {k: c * e["qty"] for k, c in SYNTHESIS[e["key"]]["materials"].items()}
        if e["kind"] == "material":
            return {e["key"]: int(e["qty"])}
        if e["kind"] == "build":
            if not e.get("follow_ship", True):
                return dict(e["saved_needs"])
            return self.build_needs()
        return gd.recipe_cost(e["key"], e.get("grade"), e.get("from_grade") or 0, e.get("rolls"), e.get("qty") or 1)

    def build_needs(self, require_build=False):
        p = self.core.store.get("build", "progress")
        if p is None:
            if require_build:
                raise ValueError("Pin a build before following or saving its requirements.")
            return {}
        return {m["key"]: m["need"] for m in (p.get("materials") or []) if m["need"]}

    @staticmethod
    def material_row(key, need, have):
        m = gd.MATERIAL_BY_KEY.get(key, {})
        cap = gd.MATERIAL_CAPS.get(m.get("grade"))
        return {"key": key, "name": m.get("name") or key, "category": m.get("category"), "grade": m.get("grade"),
                "family": m.get("family"), "cap": cap, "have": have, "need": need, "short": max(0, need - have)}

    # -- computing ------------------------------------------------------------------
    def compute(self, reserve=0):
        with self._lock:
            return self._compute(reserve)

    def _compute(self, reserve=0, extra=None):
        inv = self.inventory()
        known = self._inventory_known
        # Legacy material targets stay in their original file/API; include them
        # as explicit first-priority reservations instead of silently migrating.
        legacy = self.core.store.get("materials", "wishlist") or {}
        source = [{"id":"legacy:"+k, "kind":"material", "key":k, "name":gd.material_name(k),
                   "qty":v["need"], "label":v.get("label"), "legacy":True}
                  for k,v in sorted(legacy.items()) if v.get("need",0)>0]
        source += self.entries + ([extra] if extra else [])
        need, entries, remaining = {}, [], dict(inv)
        for e in source:
            n = self.entry_needs(e)
            ingredients = []
            for k,c in n.items():
                available = max(0, remaining.get(k,0))
                allocated = min(c, available)
                ingredients.append({**self.material_row(k,c,inv.get(k,0)),
                                    "reserved_before":need.get(k,0), "available":available,
                                    "allocated":allocated, "short":max(0,c-available)})
                need[k] = need.get(k,0) + c
                remaining[k] = available-allocated
            short = sum(r["short"] for r in ingredients)
            craftable = None
            if known and e["kind"] == "synthesis":
                craftable = min(r["available"]//SYNTHESIS[e["key"]]["materials"][r["key"]] for r in ingredients)
            entries.append({**e, "materials":len(n), "units":sum(n.values()), "ingredients":ingredients,
                            "short":short, "complete":short==0 if known else None,
                            "craftable":craftable, "inventory_known":known})
        rows = [self.material_row(k,c,inv.get(k,0)) for k,c in need.items()]
        rows.sort(key=lambda r:(r["short"]==0,r["category"] or "",-(r["grade"] or 0),r["name"]))
        summary = {"entries":len(entries), "materials":len(rows), "short":sum(1 for r in rows if r["short"]),
                   "units_short":sum(r["short"] for r in rows), "complete":all(r["short"]==0 for r in rows) if known else None}
        return {"entries":entries, "needs":rows, "summary":summary, "inventory_known":known,
                "inventory_observed_at":self._inventory_at,
                "trades":{**self.plan_trades(rows,inv,reserve),"inventory_known":True} if known else {"trades":[],"unresolved":[],"by_trader":{},"inventory_known":False,"note":"Observe a Materials snapshot before planning exchanges."},
                "note":"Planning only: nothing is crafted or spent. Stock is allocated once, in displayed order; legacy material targets come first. Plans do not auto-decrement after game crafts. Without a Materials snapshot, have/short are provisional and readiness is unknown."}

    def preview(self, q):
        with self._lock:
            entry = self._resolve(q)
            if entry.get("status") == "ambiguous": return entry
            if entry["kind"] == "build":
                raise ValueError("Use the pinned build panel to inspect build requirements.")
            result = self._compute(extra=entry)
            return {"entry":result["entries"][-1], "needs":result["needs"], "summary":result["summary"],
                    "inventory_known":result["inventory_known"], "note":result["note"]}

    def update(self, q):
        ident = q.get("id")
        if not isinstance(ident,str) or len(ident)>200: raise ValueError("Choose a saved entry id.")
        if ident.startswith("legacy:"):
            if "follow_ship" in q:
                raise ValueError("Only pinned build entries can follow the current ship.")
            qty = self.quantity(q.get("qty"))
            # Do not hold our lock during another module's publish callbacks.
            key = ident[7:]
            target = (self.core.store.get("materials","wishlist") or {}).get(key)
            if not target: raise ValueError("Entry is no longer present.")
            return self.core.http.tools["set_wishlist"].fn({"items":{key:qty},"mode":"set"})
        with self._lock:
            current = next((e for e in self.entries if e["id"]==ident),None)
            if not current: raise ValueError("Entry is no longer present.")
            updated = dict(current)
            if current["kind"] == "build":
                if "qty" in q:
                    raise ValueError("Pinned build quantities follow the build panel.")
                follow = q.get("follow_ship")
                if type(follow) is not bool:
                    raise ValueError("follow_ship must be true or false.")
                if not follow and current.get("follow_ship", True):
                    updated["saved_needs"] = self.build_needs(require_build=True)
                    updated["saved_needs_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    updated["build_url"] = (self.core.store.get("build", "pinned") or {}).get("url")
                if follow:
                    self.build_needs(require_build=True)  # Do not enable tracking without a pinned build.
                    updated.pop("saved_needs", None)
                    updated.pop("saved_needs_at", None)
                updated["follow_ship"] = follow
            else:
                if "follow_ship" in q:
                    raise ValueError("Only pinned build entries can follow the current ship.")
                updated["qty"] = self.quantity(q.get("qty"))
            entries = [updated if e["id"]==ident else e for e in self.entries]
            self.core.write_data(entries,FILE)
            self.entries = entries
            self.publish()
            return self.compute()

    @staticmethod
    def quantity(value):
        try:
            n=int(value)
            if isinstance(value,bool) or str(n)!=str(value) or not 1<=n<=10000: raise ValueError()
            return n
        except (TypeError,ValueError,OverflowError):
            raise ValueError("qty must be an integer from 1 to 10000") from None

    plan_trades = staticmethod(plan_trades)

    def publish(self):
        with self._lock:
            self.core.store.update(NS, {**self.compute(), "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

    # -- editing --------------------------------------------------------------------
    def add(self, q):
        with self._lock:
            return self._add(q)

    def _add(self, q):
        if len(self.entries)>=200: raise ValueError("Keep at most 200 saved plan entries.")
        if q.get("kind")=="build" or str(q.get("item","")).strip().lower() in ("build","pinned build"):
            return self._add_build(q.get("label"), q.get("follow_ship"))
        entry = self._resolve(q)
        if entry.get("status")=="ambiguous": return entry
        if entry.get("kind")=="build": return self._add_build(q.get("label"), q.get("follow_ship"))
        entries = self.entries + [entry]
        self.core.write_data(entries, FILE)
        self.entries = entries
        self.publish()
        st = self.core.store.get(NS)
        out = next(e for e in st["entries"] if e["id"]==entry["id"])
        return {"status":"added", "entry":out, "needs":out["ingredients"], "summary":st["summary"]}

    def _resolve(self, q):
        text = q.get("item") or q.get("query") or q.get("name") or q.get("key")
        if (q.get("kind") == "build") or (isinstance(text, str) and text.strip().lower() in ("build", "pinned build")):
            return {"kind":"build"}
        if not text or not isinstance(text, str):
            raise ValueError("item is required: a blueprint ('2x g5 fsd increased range'), an effect ('mass manager'), a material ('50 tellurium') or 'build'")
        if len(text)>500: raise ValueError("item must be at most 500 characters")
        label=q.get("label")
        if label is not None and (not isinstance(label,str) or len(label)>500):
            raise ValueError("label must be text up to 500 characters")
        if q.get("kind")=="synthesis" or text in SYNTHESIS:
            if text not in SYNTHESIS: raise ValueError("Use an exact synthesis key from wishlist_options.")
            r=SYNTHESIS[text]
            return {"id":uuid.uuid4().hex[:8], "kind":"synthesis", "key":text, "name":r["name"],
                    "module":None, "tier":r["grade"], "qty":self.quantity(q.get("qty",1)),
                    "label":label, "added":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
        query, qty, grade, from_text = parse_item(text)
        qty = self.quantity(q.get("qty", qty or 1))
        grade = q.get("grade") or grade
        grade = int(grade) if grade not in (None, "") else None
        from_grade = int(q.get("from_grade") or from_text or 0)
        kind = q.get("kind") or None
        if qty < 1:
            raise ValueError("qty must be at least 1")
        rolls = self._rolls(q.get("rolls"))
        label = q.get("label")
        if label is not None and (not isinstance(label, str) or len(label)>500):
            raise ValueError("label must be text up to 500 characters")

        # Resolution: exact recipe key, then a material by name, then a recipe search; a tie is reported, not guessed.
        key = text.strip()
        hit = None
        if key in gd.BLUEPRINT_BY_KEY or key in gd.EXPERIMENTAL_BY_KEY or key in gd.UNLOCK_BY_KEY:
            hit = gd.resolve_recipe(key)["match"]
        if key.lower() in gd.MATERIAL_BY_KEY and kind in (None, "material"):   # exact journal key (guardian_powercell has an underscore)
            mat = key.lower()
        else:
            mat = gd.resolve_material(query) if (kind in (None, "material") and not hit) else None
        if not hit and kind != "material":
            r = gd.resolve_recipe(query, kind=kind, module=q.get("module") or None)
            if "match" in r and not (mat and gd.MATERIAL_BY_NAME.get(query.lower()) == mat):
                hit = r["match"]
            elif not mat:
                cands = r.get("candidates") or []
                if cands:
                    return {"status": "ambiguous", "candidates": cands,
                            "hint": "several recipes match; repeat with the module or blueprint name, or pass a key from the candidates"}
        if hit:
            entry = {"kind": hit["kind"], "key": hit["key"], "name": hit["name"], "module": hit["module"]}
            if hit["kind"] == "experimental":
                # the search hit lists every module the effect fits; keep the one the user picked (or the only one)
                fits = gd.EXPERIMENTAL_BY_KEY[hit["key"]]["modules"]
                picked = (q.get("module") or "").strip().lower()
                entry["module"] = next((m for m in fits if m.lower() == picked), fits[0] if len(fits) == 1 else None)
                entry["fits"] = fits
            if hit["kind"] == "blueprint":
                b = gd.BLUEPRINT_BY_KEY[hit["key"]]
                if q.get("module"):
                    selected = gd.resolve_recipe(hit["key"], module=q["module"])
                    if "match" not in selected:
                        raise ValueError("This blueprint is not available for the selected module")
                    entry["module"] = selected["match"]["module"]
                grade = grade or b["max_grade"]
                if not 1 <= grade <= b["max_grade"] or not 0 <= from_grade < grade:
                    raise ValueError(f"grade must be 1-{b['max_grade']} and from_grade below it")
                entry.update({"grade": grade, "from_grade": from_grade, "rolls": rolls})
            elif hit["kind"] == "unlock":
                entry["commodities"] = gd.UNLOCK_BY_KEY[hit["key"]]["commodities"]
                entry["broker"] = hit.get("broker")
        elif mat:
            entry = {"kind": "material", "key": mat, "name": gd.material_name(mat), "module": None}
        else:
            raise ValueError(f"nothing matches '{text}'; try list_recipes or a material name")
        entry.update({"id": uuid.uuid4().hex[:8], "qty": qty, "label": label, "added": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        return entry

    def _add_build(self, label, follow_ship=None):
        """Track the pinned build, optionally saving fixed requirements instead of following ship progress."""
        if label is not None and (not isinstance(label,str) or len(label)>500):
            raise ValueError("label must be text up to 500 characters")
        pinned = self.core.store.get("build", "pinned")
        if not pinned:
            raise ValueError("no build is pinned; pin an EDSY link first")
        previous = next((e for e in self.entries if e["kind"] == "build" and e.get("build_url") == pinned.get("url")), None)
        if follow_ship is None:
            follow_ship = previous.get("follow_ship", True) if previous else True
        if type(follow_ship) is not bool:
            raise ValueError("follow_ship must be true or false.")
        entries = [e for e in self.entries if e["kind"] != "build"]
        entry = {"kind": "build", "key": "build", "name": pinned.get("name"), "module": pinned.get("ship"), "qty": 1, "label": label,
                 "id": uuid.uuid4().hex[:8], "added": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "follow_ship": follow_ship, "build_url": pinned.get("url")}
        if not follow_ship:
            if previous and not previous.get("follow_ship", True):
                entry.update(saved_needs=dict(previous["saved_needs"]), saved_needs_at=previous["saved_needs_at"])
            else:
                entry.update(saved_needs=self.build_needs(require_build=True), saved_needs_at=entry["added"])
        entries.append(entry)
        self.core.write_data(entries, FILE)
        self.entries = entries
        self.publish()
        st = self.core.store.get(NS)
        out = [e for e in st["entries"] if e["id"] == entry["id"]][0]
        inv = self.inventory()
        return {"status": "added", "entry": out, "needs": [self.material_row(k, c, inv.get(k, 0)) for k, c in self.entry_needs(entry).items()],
                "summary": st["summary"]}

    @staticmethod
    def _rolls(v):
        if v in (None, ""):
            return None
        if isinstance(v, str):
            v = [p for p in re.split(r"[,\s]+", v.strip().strip("[]")) if p]     # '[1,2,3,4,6]' as documented, or '1 2 3 4 6'
        if isinstance(v, dict):
            v = {str(k): int(n) for k, n in v.items()}
        elif isinstance(v, (list, tuple)):
            v = {str(i + 1): int(n) for i, n in enumerate(v)}
        else:
            raise ValueError("rolls must be a list of per-grade roll counts, e.g. [1,2,3,4,5]")
        if any(n < 0 for n in v.values()) or not set(v) <= {"1", "2", "3", "4", "5"}:
            raise ValueError("rolls must be non-negative counts for grades 1-5")
        return v

    def remove(self, q):
        ident=q.get("id")
        if isinstance(ident,str) and ident.startswith("legacy:"):
            return self.core.http.tools["set_wishlist"].fn({"items":{ident[7:]:0},"mode":"remove"})
        with self._lock:
            ids = q.get("id")
            if str(q.get("all", "")).lower() in ("1", "true") or ids in ("all", "*"):
                removed = len(self.entries)
                entries = []
            else:
                if not ids:
                    raise ValueError("id is required (or all=true)")
                ids = set(ids.split(",")) if isinstance(ids, str) else set(ids)
                before = len(self.entries)
                entries = [e for e in self.entries if e["id"] not in ids]
                removed = before - len(entries)
            self.core.write_data(entries, FILE)
            self.entries = entries
            self.publish()
            return {"removed": removed, "entries": self.core.store.get(NS, "entries")}

    # -- traders --------------------------------------------------------------------
    def traders(self, q):
        svc = self.core.services
        types = q.get("types")
        if isinstance(types, str):
            types = [t.strip().capitalize() for t in types.split(",") if t.strip()]
        if not types:
            by = (self.core.store.get(NS, "trades") or {}).get("by_trader") or {}
            types = [t for t in TRADER_TYPES if t in by] or TRADER_TYPES
        bad = [t for t in types if t not in TRADER_TYPES]
        if bad:
            raise ValueError(f"types must be among {TRADER_TYPES}")
        ref = q.get("ref") or self.core.store.get("journal", "system") or "Sol"
        limit = max(1, min(int(q.get("limit", 3) or 3), 10))
        pad = (q.get("pad") or "").upper()
        jr = self.core.store.get("journal", "jump_range_now")

        def distance(value, digits=0):
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                return None
            return round(value, digits)

        def station(s):
            dist, ls = distance(s.get("distance"), 1), distance(s.get("distance_to_arrival"))
            raw_dist = s.get("distance")
            jumps = math.ceil(raw_dist / jr) if dist is not None and type(jr) in (int, float) and math.isfinite(jr) and jr > 0 else None
            return {"system": s.get("system_name"), "station": s.get("name"), "dist": dist, "jumps": jumps,
                   "ls": ls, "pad": svc.pad(s), "type": s.get("type"), "economy": s.get("primary_economy")}

        def one(t):
            filters = {"material_trader": {"value": [t]}}
            if pad == "L":
                filters["has_large_pad"] = {"value": True}
            try:
                d = svc.spansh_stations(filters, ref, size=limit, ttl=1800)
                return t, [station(s) for s in d.get("results", [])]
            except Exception as ex:
                return t, {"error": str(ex)}

        with ThreadPoolExecutor(max_workers=3) as pool:
            out = dict(pool.map(one, types))
        return {"ref": ref, "pad": pad or None, "traders": out,
                "note": "Raw traders sit in Refinery/Extraction economies, Manufactured in Industrial/Extraction, Encoded in High Tech/Military."}


def options(q):
    """Pick-lists for the card: modules with their blueprints and effects, unlocks by broker, materials by category."""
    mods = {}
    for b in gd.BLUEPRINTS:
        for m in gd.blueprint_modules(b):
            mods.setdefault(m, {"module": m, "blueprints": [], "experimentals": []})["blueprints"].append(
                {"key": b["key"], "name": b["name"], "max_grade": b["max_grade"]})
    for e in gd.EXPERIMENTALS:
        for m in e["modules"]:
            mods.setdefault(m, {"module": m, "blueprints": [], "experimentals": []})["experimentals"].append({"key": e["key"], "name": e["name"]})
    mats = {}
    for m in gd.MATERIALS:
        mats.setdefault(m["category"], []).append({"key": m["key"], "name": m["name"], "grade": m["grade"]})
    for rows in mats.values():
        rows.sort(key=lambda r: (-(r["grade"] or 0), r["name"]))
    return {"modules": sorted(mods.values(), key=lambda x: x["module"]),
            "unlocks": [{"key": u["key"], "name": u["name"], "module": u["module"], "broker": u["broker"]} for u in gd.UNLOCKS],
            "materials": mats, "synthesis": SYNTHESIS_RECIPES, "max_grade": 5}


def setup(core, module):
    w = Wishlist(core)
    core.http.route("/api/wishlist/options", options, tool="wishlist_options", module=module.name,
                    description="Pick-lists behind Materials / Recipe Wishlist, including exact synthesis keys, tiers and costs: every module with its blueprint keys (and max grade) and "
                                "experimental effect keys, every technology broker unlock key, and every material key by category. "
                                "Use the keys with wishlist_add when free text is ambiguous.")
    core.http.route("/api/wishlist", lambda q: {**w.compute(int(q.get("reserve", 0) or 0))},
                    tool="get_engineering_wishlist", module=module.name,
                    description="Unified materials/recipe plan: synthesis, engineering and legacy material targets. Stock is allocated once in entry order. Unknown inventory has provisional numeric shortages, not confirmed readiness. Every entry (blueprint to a grade, experimental effect, or material) with "
                                "its completeness, the per-material needs vs live inventory (have/need/short), a summary, and a material "
                                "trader plan for the shortfalls. Use wishlist_add / wishlist_remove to change it.",
                    params={"reserve": {"type": "integer", "description": "Units of each material to keep back when planning trades", "default": 0}})
    core.http.route("/api/wishlist/add", w.add, tool="wishlist_add", method="POST", module=module.name,
                    description="Add a saved planning entry, never craft in game. For synthesis use kind=synthesis and an exact wishlist_options synthesis key with qty (1-10000). item is free text or a recipe key: '2x g5 fsd increased range', 'dirty drives 2-5', "
                                "'mass manager', '50 tellurium', 'FSD_LongRange', 'unlock_guardian_fsd_booster', or 'build' to track the "
                                "pinned EDSY build as one entry whose needs follow the build's progress. Quantity, grade and a grade range "
                                "('2-5', 'g2 to g5' = the module already has G2, buy the rolls for G3, G4 and G5) can be in the text or as "
                                "parameters. Blueprints default to the max grade from an unengineered module. If the text matches several "
                                "recipes the reply has status 'ambiguous' and candidates instead of adding anything.",
                    params={"item": {"type": "string", "description": "What to track (free text, key, or 'build')", "required": True},
                            "qty": {"type": "integer", "description": "How many modules / units", "default": 1},
                            "grade": {"type": "integer", "description": "Target grade 1-5 for a blueprint; default = max"},
                            "from_grade": {"type": "integer", "description": "Grade the module already has (0 = unengineered)", "default": 0},
                            "kind": {"type": "string", "description": "Force the kind when the text is ambiguous", "enum": ["blueprint", "experimental", "unlock", "material", "build", "synthesis"]},
                            "module": {"type": "string", "description": "Restrict the recipe search to a module"},
                            "rolls": {"type": "string", "description": "Override rolls per grade as a list, e.g. [1,2,3,4,6]; default is the rolls_per_grade hint"},
                            "label": {"type": "string", "description": "Free note, e.g. the ship this is for"},
                            "follow_ship": {"type": "boolean", "description": "For pinned builds: true follows current ship progress; false saves fixed requirements while inventory stays live. Defaults to true for new entries; re-adding the same build preserves its choice."}})
    core.http.route("/api/wishlist/remove", w.remove, tool="wishlist_remove", method="POST", module=module.name,
                    description="Remove saved entries by id (comma-separated), or saved plan entries with all=true. Legacy material targets use individual legacy: ids or set_wishlist mode=clear.",
                    params={"id": {"type": "string", "description": "Entry id(s) from get_engineering_wishlist"},
                            "all": {"type": "boolean", "description": "Clear saved plan entries; legacy targets remain", "default": False}})
    core.http.route("/api/wishlist/trades", lambda q: w.compute(int(q.get("reserve", 0) or 0))["trades"],
                    tool="plan_material_trades", module=module.name,
                    description="Estimate which material trader exchanges would cover the wishlist shortfalls from current surplus: "
                                "ordered give/get steps, totals per trader type (Raw/Manufactured/Encoded), and remaining shortfalls. "
                                "Follow steps in order: direct exchanges and bounded chains through one intermediate can combine donors. "
                                "Protects needs, reserves and storage caps. covered counts original shortfall reduction, not intermediate "
                                "receipts. Not exhaustive; search_limited indicates the work limit was reached. Ratios: same family "
                                "1->3 per grade down and 6->1 per grade up, other families cost 6x more.",
                    params={"reserve": {"type": "integer", "description": "Units of each material to keep back", "default": 0}})
    core.http.route("/api/wishlist/traders", w.traders, tool="find_material_traders", module=module.name,
                    description="Nearest material traders by category (Spansh), default from the current system and only for the categories "
                                "the trade plan needs. Includes system distance (Ly), arrival distance from the main star (ls), "
                                "jump estimate, pad size, station type and economy. Missing distances stay null.",
                    params={"types": {"type": "string", "description": "Comma-separated subset of Raw, Manufactured, Encoded; default = types in the trade plan, else all"},
                            "ref": {"type": "string", "description": "Reference system; default = current system"},
                            "limit": {"type": "integer", "description": "Traders per type (<=10)", "default": 3},
                            "pad": {"type": "string", "description": "L = large pads only", "enum": ["L"]}})

    preview_params = core.http.tools["wishlist_add"].params
    core.http.route("/api/wishlist/preview", w.preview, tool="preview_material_plan", method="POST", module=module.name,
                    description="Preview an additional recipe/material target against stock left after the saved plan. Same parameters as wishlist_add. No persistence or crafting. Includes shared requirements, shortages and inventory_known.", params=preview_params)
    core.http.route("/api/wishlist/update", w.update, tool="wishlist_update", method="POST", module=module.name,
                    description="Set qty for a saved material/recipe entry, or follow_ship for a pinned build entry, by id. Turning follow_ship off saves current requirements across ship changes and restarts; inventory and shortfalls remain live. Turning it on resumes current ship comparison. Does not craft or change inventory.",
                    params={"id":{"type":"string","required":True},"qty":{"type":"integer","minimum":1,"maximum":10000},
                            "follow_ship":{"type":"boolean"}})
