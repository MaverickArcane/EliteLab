"""Mining session rebuilt from journals; no network requests or persistent writes.

Frontier Player Journal manual v34, sections 7.7 and 13.33:
https://hosting.zaonce.net/community/journal/v34/Journal_Manual_v34.pdf
MiningRefined represents ONE unit of cargo, with no Count field. Prospect
events have no asteroid identifier, so their count is reports, not unique rocks.
"""
import datetime as dt
import math

from elitelab.core.gamedata import norm

NS = "mining"
MAX_COMMODITIES = 256


def text(value):
    return value.strip()[:160] if isinstance(value, str) else ""


def timestamp(value):
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (AttributeError, TypeError, ValueError, OverflowError, OSError):
        return None


def percentage(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return round(value, 2) if math.isfinite(value) and 0 <= value <= 100 else None
    except OverflowError:
        return None


class Mining:
    def __init__(self, core):
        self.core = core
        self.reset()
        core.bus.on("journal.*", self.on_event)
        self.publish()

    def reset(self, commander="", fid="", partial=True):
        self.commander, self.fid, self.partial = commander, fid, partial
        self.started = self.as_of = None
        self.started_ts = self.as_of_ts = None
        self.timing_incomplete = False
        self.ended = False
        self.prospected = self.tons = self.other_tons = 0
        self.last = None
        self.output = {}

    def on_event(self, name, ev):
        # The watcher serializes journal events. HTTP reads only the store copy.
        if not isinstance(ev, dict) or not isinstance(ev.get("event"), str):
            return
        event = ev["event"]
        if event == "LoadGame":
            self.reset(text(ev.get("Commander")), text(ev.get("FID")), partial=False)
            self.publish()
            return
        if event == "Commander":
            commander, fid = text(ev.get("Name")), text(ev.get("FID"))
            if ((fid and self.fid and fid != self.fid) or
                    (commander and self.commander and commander != self.commander)):
                self.reset(commander, fid)
            else:
                self.commander, self.fid = commander or self.commander, fid or self.fid
            self.publish()
            return
        if self.ended:
            return
        mining = event in ("ProspectedAsteroid", "MiningRefined")
        ts = timestamp(ev.get("timestamp"))
        if mining:
            if ts is None:
                self.timing_incomplete = True
            elif self.started_ts is None or ts < self.started_ts:
                self.started_ts, self.started = ts, text(ev["timestamp"])
        if self.started_ts is not None and ts is not None and (self.as_of_ts is None or ts > self.as_of_ts):
            self.as_of_ts, self.as_of = ts, text(ev["timestamp"])
        if event == "ProspectedAsteroid":
            self.prospected += 1
            materials = ev.get("Materials")
            materials = materials if isinstance(materials, list) else []
            rows = []
            for item in materials[:32]:
                if not isinstance(item, dict):
                    continue
                label = text(item.get("Name_Localised")) or text(item.get("Name"))
                if label:
                    rows.append({"name": label, "proportion": percentage(item.get("Proportion"))})
            self.last = {"timestamp": text(ev.get("timestamp")) or None, "materials": rows,
                         "content": text(ev.get("Content_Localised")) or text(ev.get("Content")),
                         "remaining": percentage(ev.get("Remaining")),
                         "motherlode": text(ev.get("MotherlodeMaterial_Localised")) or text(ev.get("MotherlodeMaterial"))}
        elif event == "MiningRefined":
            self.tons += 1
            key = norm(text(ev.get("Type")))
            if not key or (key not in self.output and len(self.output) >= MAX_COMMODITIES):
                self.other_tons += 1
            else:
                row = self.output.setdefault(key, {"key": key, "name": text(ev.get("Type_Localised")) or text(ev.get("Type")), "tons": 0})
                row["tons"] += 1
                if text(ev.get("Type_Localised")):
                    row["name"] = text(ev["Type_Localised"])
        elif event == "Shutdown":
            self.ended = True
        if mining or self.started_ts is not None or event == "Shutdown":
            if not ev.get("_replay"):
                self.publish()

    def publish(self):
        seconds = max(0, self.as_of_ts - self.started_ts) if self.as_of_ts is not None and self.started_ts is not None else 0
        rate = round(self.tons * 3600 / seconds, 1) if seconds >= 60 and not self.timing_incomplete else None
        self.core.store.set(NS, "summary", {
            "commander": self.commander, "partial": self.partial, "ended": self.ended,
            "started_at": self.started, "as_of": self.as_of, "elapsed_seconds": seconds,
            "timing_incomplete": self.timing_incomplete, "tons_per_hour": rate,
            "prospector_reports": self.prospected, "last_prospect": self.last,
            "refined_tons": self.tons, "other_tons": self.other_tons,
            "commodities": sorted(self.output.values(), key=lambda r: (-r["tons"], r["key"])),
            "rate_note": "Refined tons / recorded hours from the first mining event through the latest journal event. "
                         "Includes travel and idle time; available after 60 seconds. Resets when you reload the game or change commander.",
        })


def setup(core, module):
    mining = Mining(core)
    core.bus.on("journal.replay.done", lambda n, v: mining.publish())
    core.http.route("/api/mining", lambda q: core.store.get(NS, "summary"),
                    tool="get_mining_status", module=module.name,
                    description="Latest prospector composition and refinery output by commodity for the current game session. "
                                "Each MiningRefined event adds one ton, regardless of current cargo or sales. Prospector reports "
                                "are not unique asteroids. Rate includes recorded idle/travel time from first mining event to "
                                "as_of, stops at Shutdown, and is unavailable below 60 seconds or with missing mining timestamps. "
                                "LoadGame/commander change resets totals; partial means replay did not include LoadGame.")
