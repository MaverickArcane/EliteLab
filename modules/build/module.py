"""build module: pin an EDSY build link and measure the current ship against it.

The target comes from elitelab/core/edsy.py (decoded link). The current ship is ``journal.ship_info.modules`` from the
last Loadout event. Core slots are compared by slot; hardpoints, utilities, military and optional internals are matched
as a multiset per group (same item, preferring the same engineering), so slot order never matters. For every target
slot the verdict is ok / engineer / buy, with the blueprint rolls still to do (from the module's current grade when it
already has the same blueprint), the experimental effect, the credits for modules to buy, and the materials for the
engineering, all summed and compared with the live inventory.

State ``build``: pinned {url, name, ship, pinned_at} | None, progress {...} (see compute()).
Persisted in data/build.json.
"""
import time
import threading

from elitelab.core import builds
from elitelab.core import gamedata as gd
from elitelab.core.builds import group_of

NS = "build"
FILE = "build.json"


def bp_key(name):
    return gd.BLUEPRINT_BY_LOWER.get((name or "").lower())


def exp_key(name):
    return gd.EXPERIMENTAL_BY_LOWER.get((name or "").lower())


class Build:
    def __init__(self, core):
        self.core = core
        self._lock = threading.RLock()
        self.pinned = None
        self.target = None
        saved = core.read_data(FILE, default=None)
        if saved and saved.get("url"):
            try:
                self.target = builds.parse(saved["url"])
                self.pinned = {**saved, "source": self.target.get("source")}
            except Exception as ex:
                core.log.warning("build: pinned build no longer decodes (%s); unpinning", ex)
        for ev in ("state.journal.ship_info", "state.materials.inventory_version", "journal.replay.done"):
            core.bus.on(ev, lambda n, v: self.publish())
        self.publish()

    def inventory(self):
        t = self.core.http.tools.get("get_material_inventory")
        return (t.fn({}).get("inventory") if t else None) or {}

    # -- pinning ----------------------------------------------------------------------
    def pin(self, q):
        url = (q.get("url") or q.get("link") or q.get("build") or "").strip()
        if not url:
            raise ValueError("url is required: an EDSY link (https://edsy.org/#/L=...), a Coriolis link (https://coriolis.io/outfit/...), "
                             "or SLEF / Loadout JSON")
        target = builds.parse(url)
        if not target["slots"]:
            raise ValueError("that build has no modules")
        pinned = {"url": url, "source": target["source"], "hash": target.get("hash"), "name": target["name"] or target["ship"]["name"],
                       "ship": target["ship"]["name"], "ship_fdname": target["ship"]["fdname"], "slots": len(target["slots"]),
                       "pinned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        with self._lock:
            self.core.write_data(pinned, FILE)
            self.target, self.pinned = target, pinned
            self.publish()
            return self.core.store.get(NS)

    def unpin(self, q):
        with self._lock:
            self.core.write_data({}, FILE)
            self.pinned = self.target = None
            self.publish()
        return {"pinned": None}

    # -- comparison -------------------------------------------------------------------
    def compute(self):
        with self._lock:
            return self._compute()

    def _compute(self):
        t = self.target
        if not t:
            return {"pinned": None, "progress": None}
        j = self.core.store.get("journal", "ship_info") or {}
        cur_ship = (j.get("internal") or self.core.store.get("journal", "ship_internal") or "").lower()   # ship_info is the Loadout itself
        same_ship = bool(cur_ship) and cur_ship == t["ship"]["fdname"]
        inv = self.inventory()
        current = [m for m in (j.get("modules") or []) if m.get("item")]
        pools = {}
        for m in current:
            pools.setdefault(group_of(m["slot"]), []).append(m)
        used = set()
        rows, need, wish = [], {}, {}
        credits = 0
        for s in t["slots"]:
            item = s["module"]["fdname"]
            want_bp = bp_key((s["blueprint"] or {}).get("fdname")) if s["blueprint"] else None
            want_bp_name = (s["blueprint"] or {}).get("name")
            want_grade = s["grade"] if s["blueprint"] else 0
            want_exp = exp_key((s["experimental"] or {}).get("fdname")) if s["experimental"] else None
            want_exp_name = (s["experimental"] or {}).get("name")
            # find the current module
            cur = None
            if s["group"] == "component":
                cur = next((m for m in pools.get("component", []) if m["slot"] == s["slot"]), None)
            else:
                cands = [m for m in pools.get(s["group"], []) if m["item"] == item and id(m) not in used]

                def score(m):
                    e = m.get("engineering") or {}
                    return ((bp_key(e.get("blueprint")) == want_bp) * 4 + (e.get("level") == want_grade and want_bp is not None) * 2
                            + (exp_key(e.get("experimental")) == want_exp and want_exp is not None))
                if cands:
                    cur = max(cands, key=score)
                    used.add(id(cur))
            size = "" if s["module"]["class"] is None else str(s["module"]["class"])
            row = {"group": s["group"], "slot": s["slot"], "item": item, "target": f"{size}{s['module']['rating'] or ''} {s['module']['name']}".strip(),
                   "blueprint": want_bp_name, "grade": want_grade, "experimental": want_exp_name, "status": "ok", "todo": [], "materials": {},
                   "current": None, "credits": 0}
            have_item = bool(cur) and cur["item"] == item
            if cur:
                ce = cur.get("engineering") or {}
                row["current"] = {"slot": cur["slot"], "item": cur["item"], "blueprint": ce.get("blueprint"), "level": ce.get("level"),
                                  "experimental": ce.get("experimental")}
            if not have_item:
                row["status"] = "buy"
                row["credits"] = s["module"]["cost"] or 0
                credits += row["credits"]
                row["todo"].append(f"fit {row['target']}" + (f" (replaces {cur['item']})" if cur and s["group"] == "component" else ""))
            from_grade, need_bp, need_exp = 0, False, False
            if want_bp:
                ce = (cur.get("engineering") or {}) if have_item else {}
                if bp_key(ce.get("blueprint")) == want_bp:
                    from_grade = int(ce.get("level") or 0)
                    need_bp = from_grade < want_grade
                    need_exp = bool(want_exp) and exp_key(ce.get("experimental")) != want_exp
                else:
                    need_bp, need_exp = True, bool(want_exp)
                if need_bp:
                    if row["status"] == "ok":
                        row["status"] = "engineer"
                    row["todo"].append(f"{want_bp_name} G{from_grade} to G{want_grade}" if from_grade else f"{want_bp_name} to G{want_grade}")
                    if want_bp in gd.BLUEPRINT_BY_KEY:
                        for k, c in gd.recipe_cost(want_bp, want_grade, from_grade).items():
                            row["materials"][k] = row["materials"].get(k, 0) + c
                        wk = (want_bp, want_grade, from_grade)
                        wish[wk] = wish.get(wk, 0) + 1
                    else:
                        row["todo"].append("materials unknown for this blueprint")
                if need_exp:
                    if row["status"] == "ok":
                        row["status"] = "engineer"
                    row["todo"].append(f"apply {want_exp_name}")
                    if want_exp in gd.EXPERIMENTAL_BY_KEY:
                        for k, c in gd.recipe_cost(want_exp).items():
                            row["materials"][k] = row["materials"].get(k, 0) + c
                        wk = (want_exp, None, None)
                        wish[wk] = wish.get(wk, 0) + 1
            for k, c in row["materials"].items():
                need[k] = need.get(k, 0) + c
            row["materials"] = [{"key": k, "name": gd.material_name(k), "count": c} for k, c in row["materials"].items()]
            rows.append(row)
        extra = [m for g, ms in pools.items() for m in ms if g != "component" and id(m) not in used and not self._is_target_item(t, m["item"])]
        mats = []
        for k, c in need.items():
            m = gd.MATERIAL_BY_KEY.get(k, {})
            have = inv.get(k, 0)
            mats.append({"key": k, "name": m.get("name") or k, "category": m.get("category"), "grade": m.get("grade"), "have": have, "need": c,
                         "short": max(0, c - have)})
        mats.sort(key=lambda r: (r["short"] == 0, r["category"] or "", -(r["grade"] or 0), r["name"]))
        total = len(rows)
        ok = sum(1 for r in rows if r["status"] == "ok")
        fitted = sum(1 for r in rows if r["status"] != "buy")
        eng_total = sum(1 for r in rows if r["blueprint"])
        eng_done = sum(1 for r in rows if r["blueprint"] and r["status"] == "ok")
        units = sum(r["need"] for r in mats)
        short = sum(r["short"] for r in mats)
        progress = {
            "same_ship": same_ship, "current_ship": j.get("type") or cur_ship or None, "target_ship": t["ship"]["name"],
            "slots": rows, "totals": {"slots": total, "ok": ok, "fitted": fitted, "to_buy": total - fitted, "to_engineer": sum(1 for r in rows if r["status"] == "engineer"),
                                      "engineering_total": eng_total, "engineering_done": eng_done, "credits": credits},
            "percent": {"fitted": round(100 * fitted / total) if total else 100, "engineered": round(100 * eng_done / eng_total) if eng_total else 100,
                        "materials": round(100 * (units - short) / units) if units else 100, "overall": round(100 * ok / total) if total else 100},
            "materials": mats, "materials_short": sum(1 for r in mats if r["short"]),
            "wishlist_items": [{"item": k[0], "grade": k[1], "from_grade": k[2], "qty": n} for k, n in wish.items()],
            "not_in_build": [{"slot": m["slot"], "item": m["item"]} for m in extra],
            "note": "Hardpoints, utilities and internals are matched by item within their group, so slot order is ignored. "
                    "Blueprint rolls assume the rolls-per-grade hint. Credits are EDSY list prices without discounts.",
        }
        return {"pinned": self.pinned, "progress": progress}

    @staticmethod
    def _is_target_item(t, item):
        return any(s["module"]["fdname"] == item for s in t["slots"])

    def publish(self):
        try:
            with self._lock:
                self.core.store.update(NS, self.compute())
        except Exception as ex:
            self.core.log.warning("build: publish failed: %s", ex)

    # -- wishlist hand-off ------------------------------------------------------------
    def to_wishlist(self, q):
        with self._lock:
            return self._to_wishlist(q)

    def _to_wishlist(self, q):
        """Track the pinned build on the wishlist as one entry (through the wishlist tools, never an import). Its needs are
        this module's progress.materials, so the entry shrinks as modules get fitted and engineered. Older per-blueprint
        entries labelled for this build are removed."""
        if not self.target:
            raise ValueError("no build pinned")
        tools = self.core.http.tools
        if "wishlist_add" not in tools:
            raise ValueError("the wishlist module is not loaded")
        label = f"build: {self.pinned.get('name')}"
        existing = tools["get_engineering_wishlist"].fn({}).get("entries") or []
        old = [e["id"] for e in existing if e.get("label") == label and e.get("kind") != "build"]
        if old:
            tools["wishlist_remove"].fn({"id": ",".join(old)})
        r = tools["wishlist_add"].fn({"item": "build", "kind": "build"})
        return {"entry": r.get("entry"), "replaced": len(old), "needs": len(r.get("needs") or []), "summary": r.get("summary")}


def setup(core, module):
    b = Build(core)
    core.http.route("/api/build", lambda q: core.store.get(NS), tool="get_build_progress", module=module.name,
                    description="Progress of the current ship toward the pinned EDSY build: per target slot the verdict (ok, engineer, buy) "
                                "with what to do, the blueprint rolls still needed from the module's current grade, experimental effects, "
                                "credits for modules to buy, and every material summed against the live inventory (have/need/short). "
                                "Percentages: fitted, engineered, materials, overall.")
    core.http.route("/api/build/pin", b.pin, tool="pin_build", method="POST", module=module.name,
                    description="Pin a build as the target for the current ship: an EDSY link (https://edsy.org/#/L=...), a Coriolis link "
                                "(https://coriolis.io/outfit/<ship>?code=...), or SLEF / journal Loadout JSON (what both sites export). "
                                "Replaces any pinned build.",
                    params={"url": {"type": "string", "description": "EDSY link, Coriolis link, or SLEF/Loadout JSON text", "required": True}})
    core.http.route("/api/build/unpin", b.unpin, tool="unpin_build", method="POST", module=module.name, description="Remove the pinned build.")
    core.http.route("/api/build/wishlist", b.to_wishlist, tool="build_to_wishlist", method="POST", module=module.name,
                    description="Track the pinned build on the engineering wishlist as a single entry whose material needs follow the "
                                "build's progress. Then the wishlist card, trade plan and farm sites all work from the build.")
