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
        return (t.fn({}).get("inventory") if t else None) or {}

    def entry_needs(self, e):
        if e["kind"] == "material":
            return {e["key"]: int(e["qty"])}
        if e["kind"] == "build":
            p = self.core.store.get("build", "progress") or {}
            return {m["key"]: m["need"] for m in (p.get("materials") or []) if m["need"]}
        return gd.recipe_cost(e["key"], e.get("grade"), e.get("from_grade") or 0, e.get("rolls"), e.get("qty") or 1)

    @staticmethod
    def material_row(key, need, have):
        m = gd.MATERIAL_BY_KEY.get(key, {})
        cap = gd.MATERIAL_CAPS.get(m.get("grade"))
        return {"key": key, "name": m.get("name") or key, "category": m.get("category"), "grade": m.get("grade"),
                "family": m.get("family"), "cap": cap, "have": have, "need": need, "short": max(0, need - have)}

    # -- computing ------------------------------------------------------------------
    def compute(self, reserve=0):
        inv = self.inventory()
        need, entries = {}, []
        for e in self.entries:
            n = self.entry_needs(e)
            for k, c in n.items():
                need[k] = need.get(k, 0) + c
            short = sum(max(0, c - inv.get(k, 0)) for k, c in n.items())
            entries.append({**e, "materials": len(n), "units": sum(n.values()), "short": short, "complete": short == 0})
        rows = [self.material_row(k, c, inv.get(k, 0)) for k, c in need.items()]
        rows.sort(key=lambda r: (r["short"] == 0, r["category"] or "", -(r["grade"] or 0), r["name"]))
        summary = {"entries": len(entries), "materials": len(rows), "short": sum(1 for r in rows if r["short"]),
                   "units_short": sum(r["short"] for r in rows), "complete": all(r["short"] == 0 for r in rows)}
        return {"entries": entries, "needs": rows, "summary": summary, "trades": self.plan_trades(rows, inv, reserve)}

    @staticmethod
    def plan_trades(rows, inv, reserve=0):
        """Greedy material trader plan: fill each shortfall from surplus materials of the same type, cheapest ratio first
        (same family down, then same family up, then cross family). Never spends below a material's own need + reserve,
        never receives above the grade cap. An estimate; the trader screen is authoritative."""
        need = {r["key"]: r["need"] for r in rows}
        surplus = {}
        for k, have in inv.items():
            m = gd.MATERIAL_BY_KEY.get(k)
            if m and m.get("family"):
                s = have - need.get(k, 0) - int(reserve or 0)
                if s > 0:
                    surplus[k] = s
        trades, unresolved = [], []
        remaining = {}
        for r in rows:
            if r["short"] > 0 and r.get("family"):
                remaining[r["key"]] = min(r["short"], max(0, r["cap"] - r["have"])) if r["cap"] is not None else r["short"]
        # Every (donor, shortfall) pair, cheapest exchange first across the whole list, so a 6:1 same-family trade
        # is never starved by a 36:1 cross-family one that happened to be considered earlier.
        options = []
        for r in rows:
            if r["key"] not in remaining:
                continue
            for donor, s in surplus.items():
                ratio = gd.trade_ratio(donor, r["key"])
                if ratio:
                    options.append((ratio[0] / ratio[1], -(r["grade"] or 0), -s, donor, r, ratio))
        for _, _, _, donor, r, (give, get) in sorted(options, key=lambda o: o[:3] + (o[3], o[4]["key"])):
            left = remaining[r["key"]]
            if left <= 0:
                continue
            n = min(math.ceil(left / get), surplus[donor] // give)
            if n <= 0:
                continue
            dm = gd.MATERIAL_BY_KEY[donor]
            trades.append({"category": r["category"], "ratio": f"{give}:{get}", "same_family": dm["family"] == r["family"],
                           "give": {"key": donor, "name": dm["name"], "grade": dm["grade"], "qty": n * give},
                           "get": {"key": r["key"], "name": r["name"], "grade": r["grade"], "qty": n * get}})
            surplus[donor] -= n * give
            remaining[r["key"]] = left - n * get
        for r in rows:
            left = remaining.get(r["key"], 0)
            if left > 0:
                unresolved.append({"key": r["key"], "name": r["name"], "grade": r["grade"], "category": r["category"], "short": left})
        trades.sort(key=lambda t: (t["category"], -t["get"]["grade"]))
        for r in rows:
            if r["short"] > 0 and not r.get("family"):
                unresolved.append({"key": r["key"], "name": r["name"], "grade": r["grade"], "category": r["category"], "short": r["short"],
                                   "note": "not tradeable"})
        by = {}
        for t in trades:
            b = by.setdefault(t["category"], {"trades": 0, "give": 0, "get": 0})
            b["trades"] += 1
            b["give"] += t["give"]["qty"]
            b["get"] += t["get"]["qty"]
        return {"trades": trades, "by_trader": by, "unresolved": unresolved, "reserve": int(reserve or 0),
                "covered": sum(t["get"]["qty"] for t in trades),
                "note": "Same family: 1 -> 3 per grade down, 6 -> 1 per grade up; another family costs 6x more. "
                        "Greedy estimate from current surplus; visit the trader type named in category."}

    def publish(self):
        with self._lock:
            self.core.store.update(NS, {**self.compute(), "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

    # -- editing --------------------------------------------------------------------
    def add(self, q):
        with self._lock:
            return self._add(q)

    def _add(self, q):
        text = q.get("item") or q.get("query") or q.get("name") or q.get("key")
        if (q.get("kind") == "build") or (isinstance(text, str) and text.strip().lower() in ("build", "pinned build")):
            return self._add_build(q.get("label"))
        if not text or not isinstance(text, str):
            raise ValueError("item is required: a blueprint ('2x g5 fsd increased range'), an effect ('mass manager'), a material ('50 tellurium') or 'build'")
        query, qty, grade, from_text = parse_item(text)
        qty = int(q.get("qty") or qty or 1)
        grade = q.get("grade") or grade
        grade = int(grade) if grade not in (None, "") else None
        from_grade = int(q.get("from_grade") or from_text or 0)
        kind = q.get("kind") or None
        if qty < 1:
            raise ValueError("qty must be at least 1")
        rolls = self._rolls(q.get("rolls"))
        label = q.get("label")
        if label is not None and not isinstance(label, str):
            raise ValueError("label must be a string")

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
        self.entries.append(entry)
        self.core.write_data(self.entries, FILE)
        self.publish()
        st = self.core.store.get(NS)
        out = [e for e in st["entries"] if e["id"] == entry["id"]][0]
        needs = self.entry_needs(entry)
        inv = self.inventory()
        return {"status": "added", "entry": out, "needs": [self.material_row(k, c, inv.get(k, 0)) for k, c in needs.items()],
                "summary": st["summary"]}

    def _add_build(self, label):
        """Track the pinned build as one entry whose needs follow build.progress.materials (so it shrinks as you engineer)."""
        pinned = self.core.store.get("build", "pinned")
        if not pinned:
            raise ValueError("no build is pinned; pin an EDSY link first")
        self.entries = [e for e in self.entries if e["kind"] != "build"]
        entry = {"kind": "build", "key": "build", "name": pinned.get("name"), "module": pinned.get("ship"), "qty": 1, "label": label,
                 "id": uuid.uuid4().hex[:8], "added": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        self.entries.append(entry)
        self.core.write_data(self.entries, FILE)
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
        with self._lock:
            ids = q.get("id")
            if str(q.get("all", "")).lower() in ("1", "true") or ids in ("all", "*"):
                removed = len(self.entries)
                self.entries = []
            else:
                if not ids:
                    raise ValueError("id is required (or all=true)")
                ids = set(ids.split(",")) if isinstance(ids, str) else set(ids)
                before = len(self.entries)
                self.entries = [e for e in self.entries if e["id"] not in ids]
                removed = before - len(self.entries)
            self.core.write_data(self.entries, FILE)
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

        def one(t):
            filters = {"material_trader": {"value": [t]}}
            if pad == "L":
                filters["has_large_pad"] = {"value": True}
            try:
                d = svc.spansh_stations(filters, ref, size=limit, ttl=1800)
                return t, [{"system": s.get("system_name"), "station": s.get("name"), "dist": round(s.get("distance", 0), 1),
                            "jumps": (math.ceil(s.get("distance", 0) / jr) if jr else None),
                            "ls": round(s.get("distance_to_arrival") or 0), "pad": svc.pad(s), "type": s.get("type"),
                            "economy": s.get("primary_economy")} for s in d.get("results", [])]
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
            "materials": mats, "max_grade": 5}


def setup(core, module):
    w = Wishlist(core)
    core.http.route("/api/wishlist/options", options, tool="wishlist_options", module=module.name,
                    description="Pick-lists behind the wishlist card: every module with its blueprint keys (and max grade) and "
                                "experimental effect keys, every technology broker unlock key, and every material key by category. "
                                "Use the keys with wishlist_add when free text is ambiguous.")
    core.http.route("/api/wishlist", lambda q: {**w.compute(int(q.get("reserve", 0) or 0))},
                    tool="get_engineering_wishlist", module=module.name,
                    description="The engineering wishlist: every entry (blueprint to a grade, experimental effect, or material) with "
                                "its completeness, the per-material needs vs live inventory (have/need/short), a summary, and a material "
                                "trader plan for the shortfalls. Use wishlist_add / wishlist_remove to change it.",
                    params={"reserve": {"type": "integer", "description": "Units of each material to keep back when planning trades", "default": 0}})
    core.http.route("/api/wishlist/add", w.add, tool="wishlist_add", method="POST", module=module.name,
                    description="Add an entry. item is free text or a recipe key: '2x g5 fsd increased range', 'dirty drives 2-5', "
                                "'mass manager', '50 tellurium', 'FSD_LongRange', 'unlock_guardian_fsd_booster', or 'build' to track the "
                                "pinned EDSY build as one entry whose needs follow the build's progress. Quantity, grade and a grade range "
                                "('2-5', 'g2 to g5' = the module already has G2, buy the rolls for G3, G4 and G5) can be in the text or as "
                                "parameters. Blueprints default to the max grade from an unengineered module. If the text matches several "
                                "recipes the reply has status 'ambiguous' and candidates instead of adding anything.",
                    params={"item": {"type": "string", "description": "What to track (free text, key, or 'build')", "required": True},
                            "qty": {"type": "integer", "description": "How many modules / units", "default": 1},
                            "grade": {"type": "integer", "description": "Target grade 1-5 for a blueprint; default = max"},
                            "from_grade": {"type": "integer", "description": "Grade the module already has (0 = unengineered)", "default": 0},
                            "kind": {"type": "string", "description": "Force the kind when the text is ambiguous", "enum": ["blueprint", "experimental", "unlock", "material", "build"]},
                            "module": {"type": "string", "description": "Restrict the recipe search to a module"},
                            "rolls": {"type": "string", "description": "Override rolls per grade as a list, e.g. [1,2,3,4,6]; default is the rolls_per_grade hint"},
                            "label": {"type": "string", "description": "Free note, e.g. the ship this is for"}})
    core.http.route("/api/wishlist/remove", w.remove, tool="wishlist_remove", method="POST", module=module.name,
                    description="Remove entries by id (comma-separated) or everything with all=true.",
                    params={"id": {"type": "string", "description": "Entry id(s) from get_engineering_wishlist"},
                            "all": {"type": "boolean", "description": "Clear the whole list", "default": False}})
    core.http.route("/api/wishlist/trades", lambda q: w.compute(int(q.get("reserve", 0) or 0))["trades"],
                    tool="plan_material_trades", module=module.name,
                    description="Estimate which material trader exchanges would cover the wishlist shortfalls from current surplus: "
                                "a list of give/get trades with ratios, totals per trader type (Raw/Manufactured/Encoded), and what stays "
                                "short. Ratios: same family 1->3 per grade down and 6->1 per grade up, other families cost 6x more.",
                    params={"reserve": {"type": "integer", "description": "Units of each material to keep back", "default": 0}})
    core.http.route("/api/wishlist/traders", w.traders, tool="find_material_traders", module=module.name,
                    description="Nearest material traders by type (Spansh), default from the current system and only for the types "
                                "the trade plan needs. Includes distance, jump estimate, pad size and station type.",
                    params={"types": {"type": "string", "description": "Comma-separated subset of Raw, Manufactured, Encoded; default = types in the trade plan, else all"},
                            "ref": {"type": "string", "description": "Reference system; default = current system"},
                            "limit": {"type": "integer", "description": "Traders per type (<=10)", "default": 3},
                            "pad": {"type": "string", "description": "L = large pads only", "enum": ["L"]}})
