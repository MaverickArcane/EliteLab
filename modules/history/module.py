"""Travel and historical journal analytics from a local, rebuildable index."""
import time

from modules.history.index import JournalIndex

NS = "history"


def days_param(q):
    try:
        raw = q.get("days", 30)
        if isinstance(raw, bool): raise ValueError()
        days = int(raw)
        if str(days) != str(raw) or not 0 <= days <= 36500: raise ValueError()
        return days
    except (TypeError, ValueError, OverflowError):
        raise ValueError("days must be an integer from 0 (all time) to 36500.") from None


class History:
    def __init__(self, core):
        self.core = core
        self.index = JournalIndex(core)
        self.version = 0
        core.store.set(NS, "version", 0)
        for event in ("FSDJump", "CarrierJump", "Location", "StartJump", "LoadGame", "Commander", "MaterialCollected", "PowerplayMerits", "replay.done"):
            core.bus.on("journal." + event, self.bump)

    def bump(self, name, ev):
        if isinstance(ev, dict) and ev.get("_replay"):
            return
        if isinstance(ev, dict) and ev.get("event") == "StartJump" and ev.get("JumpType") != "Hyperspace":
            return
        self.version += 1
        self.core.store.set(NS, "version", self.version)

    def scope(self, q):
        days = days_param(q)
        who = q.get("commander", "auto")
        if not isinstance(who, str) or not who or len(who) > 165:
            raise ValueError("Choose a commander key returned by get_journal_history, or auto.")
        commanders = self.index.query("SELECT commander AS key, display AS name, MAX(ts) AS last_seen FROM records GROUP BY commander ORDER BY last_seen DESC LIMIT 200")
        if who == "auto":
            current = self.core.store.get("journal", "cmdr")
            matches = [c for c in commanders if c["name"] == current]
            who = matches[0]["key"] if len(matches) == 1 else commanders[0]["key"] if len(commanders) == 1 else None
        elif who not in {c["key"] for c in commanders}:
            raise ValueError("Commander is not present in the indexed archive.")
        return {"days":days, "commander":who, "commanders":commanders, "selection_required":bool(commanders and who is None)}, (who, time.time()-days*86400 if days else -62135596800)

    def analytics(self, q):
        material = q.get("material", "")
        if not isinstance(material, str) or len(material) > 160:
            raise ValueError("material must be text up to 160 characters.")
        days_param(q)
        with self.index.lock:
            status = self.index.refresh()
            scope, params = self.scope(q)
            where = "commander=? AND ts>=?"
            credits = self.index.query("""SELECT stamp AS timestamp, amount AS credits FROM (
                SELECT stamp,amount,ts,file,offset,ROW_NUMBER() OVER(PARTITION BY DATE(ts,'unixepoch') ORDER BY ts DESC,file DESC,offset DESC) AS n
                FROM records WHERE """ + where + " AND kind='credits') WHERE n=1 ORDER BY ts DESC LIMIT 400", params)
            credits.reverse()
            merits = self.index.query("SELECT item AS cycle_start,power,SUM(amount) AS merits,COUNT(*) AS events FROM records WHERE " + where + " AND kind='merits' GROUP BY item,power ORDER BY item DESC,power LIMIT 200", params)
            pattern = "%" + material.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            materials = self.index.query("SELECT item,label,category,system,body,SUM(amount) AS collected,COUNT(*) AS events,MAX(stamp) AS last_seen FROM records WHERE " + where + " AND kind='material' AND (item LIKE ? ESCAPE '\\' OR label LIKE ? ESCAPE '\\') GROUP BY item,category,system,body ORDER BY collected DESC,item,system,body LIMIT 100", (*params,pattern,pattern))
            totals = self.index.query("SELECT kind,COUNT(*) AS events,SUM(amount) AS amount FROM records WHERE " + where + " GROUP BY kind", params)
            return {**scope, "index":status, "credits":credits, "merit_cycles":merits, "materials":materials,
                    "totals":{r["kind"]:{"events":r["events"],"amount":r["amount"] if r["kind"] != "credits" else None} for r in totals},
                    "limits":{"credit_days":400,"merit_groups":200,"material_locations":100},
                    "note":"Available indexed journals only. Credits are LoadGame balance snapshots (latest per UTC day), not earnings or a reconstructed ledger. "
                           "Merits are observed gains grouped by Thursday 07:00 UTC cycle and power; a date filter can cover only part of a cycle. "
                           "Materials are MaterialCollected events, not current inventory, mission rewards or trader exchanges. "
                           "Files without commander identity remain unidentified; context is never borrowed from another file. Rows are capped at the stated limits."}

    def travel(self, q):
        days_param(q)
        with self.index.lock:
            status = self.index.refresh()
            scope, params = self.scope(q)
            records = self.index.query("SELECT * FROM records WHERE commander=? AND ts>=? AND kind='travel' ORDER BY ts DESC,file DESC,offset DESC LIMIT 5001", params)
            truncated = len(records) > 5000
            records = list(reversed(records[:5000]))
            classes = {r["system"]:r["star_class"] for r in self.index.query("SELECT system,star_class FROM (SELECT system,star_class,ROW_NUMBER() OVER(PARTITION BY system ORDER BY ts DESC,file DESC,offset DESC) AS n FROM records WHERE commander=? AND kind='class') WHERE n=1 LIMIT 10000", (scope["commander"],))}
            systems, route = {}, []
            for row in records:
                name = row["system"]
                rec = systems.setdefault(name, {"name":name, "pos":[row["x"],row["y"],row["z"]], "visits":0,
                                               "first":row["stamp"], "last":None, "star_class":classes.get(name), "carrier":False})
                rec["last"] = row["stamp"]
                if row["event"] != "Location": rec["visits"] += 1
                if row["event"] == "CarrierJump": rec["carrier"] = True
                if not route or route[-1]["name"] != name:
                    route.append({"name":name, "ts":row["stamp"], "event":row["event"], "dist":round(row["amount"],1)})
            return {**scope, "index":status, "systems":list(systems.values()), "route":route, "truncated":truncated,
                    "total_ly":round(sum(r["dist"] for r in route),1), "jumps":sum(r["event"] == "FSDJump" for r in route),
                    "note":"Latest 5000 indexed location/jump events for the selected commander; totals describe the displayed route."}


def setup(core, module):
    history = History(core)
    params = {"days":{"type":"integer", "default":30, "minimum":0, "maximum":36500, "description":"Look back by event time; 0 means all available indexed history"},
              "commander":{"type":"string", "default":"auto", "description":"Key from commanders; auto selects the current unique commander or the sole indexed identity. Multiple ambiguous identities require selection."}}
    core.http.route("/api/history", history.travel, tool="get_travel_history", module=module.name,
                    description="Indexed systems and chronological route, star classes, visits and distances for one commander. Event-time range; latest 5000 travel events. Check index.pending_files and truncated.", params=params)
    core.http.route("/api/history/analytics", history.analytics, tool="get_journal_history", module=module.name,
                    description="Historical credit balance snapshots, observed merits by cycle/power and material collection locations, scoped to one commander. "
                                "Credits are snapshots, not earnings; collections are not inventory. No cross-file identity inference. Check index pending/skipped/unreadable counts and selection_required; repeat while pending. "
                                "Capped at 400 daily credit samples, 200 merit cycle/power groups and 100 material locations.",
                    params={**params,"material":{"type":"string","description":"Optional literal substring in collected material key or display name; up to 160 characters"}})
    core.http.route("/api/history/index", lambda q: history.index.refresh(), tool="get_journal_index", module=module.name,
                    description="Local journal-index coverage, skipped/unidentified counts and refresh progress. Reads a bounded batch of new/changed records; repeat while pending_files is nonzero. Does not modify journals.")
    def rebuild(q):
        if q:
            raise ValueError("Rebuild accepts no parameters; it uses only the configured journal folder.")
        return history.index.refresh(rebuild=True)
    core.http.route("/api/history/rebuild", rebuild, method="POST", tool="rebuild_journal_index", module=module.name,
                    description="Rebuild only the derived local SQLite history cache from the configured journal folder, retaining the prior cache as a backup. Never changes journals. Explicit user request only; repeat get_journal_index while pending.")
