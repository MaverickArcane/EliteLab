"""powerplay module: the ``powerplay`` namespace.

Keys: power, merits, rank, time_pledged, session_merits, merit_log (last 20
gains), cycle_end (ISO), cycle_hours_left.
"""
import datetime as dt

from elitelab.core.gamedata import POWERS

NS = "powerplay"


def cycle_end(now=None):
    """Powerplay cycles tick over Thursdays 07:00 UTC."""
    now = now or dt.datetime.now(dt.timezone.utc)
    d = now.replace(hour=7, minute=0, second=0, microsecond=0)
    while d.weekday() != 3 or d <= now:
        d += dt.timedelta(days=1)
    return d


class Powerplay:
    def __init__(self, core):
        self.core = core
        self.st = {"power": None, "merits": None, "rank": None, "time_pledged": None, "session_merits": 0, "merit_log": [], "powers": POWERS}
        self.push()
        for e in ("Powerplay", "PowerplayJoin", "PowerplayLeave", "PowerplayDefect", "PowerplayMerits", "PowerplayRank", "LoadGame"):
            core.bus.on("journal." + e, self.on_event)

    def push(self):
        end = cycle_end()
        self.st["cycle_end"] = end.isoformat()
        self.st["cycle_hours_left"] = round((end - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600, 1)
        self.core.store.update(NS, self.st)

    def on_event(self, name, ev):
        e, st = ev.get("event"), self.st
        if e == "LoadGame":
            st["session_merits"] = 0; st["merit_log"] = []
        elif e == "Powerplay":
            st["power"] = ev.get("Power"); st["merits"] = ev.get("Merits"); st["rank"] = ev.get("Rank"); st["time_pledged"] = ev.get("TimePledged")
        elif e == "PowerplayJoin":
            st.update(power=ev.get("Power"), merits=0, rank=0, time_pledged=0, session_merits=0, merit_log=[])
        elif e == "PowerplayDefect":
            st.update(power=ev.get("ToPower"), merits=0, rank=0, time_pledged=0, session_merits=0, merit_log=[])
        elif e == "PowerplayLeave":
            st.update(power=None, merits=None, rank=None, time_pledged=None, session_merits=0, merit_log=[])
        elif e == "PowerplayMerits":
            gained = ev.get("MeritsGained") or 0
            st["merits"] = ev.get("TotalMerits", st["merits"])
            # Replayed merits count too: LoadGame resets the session, so only the current session's gains survive replay.
            st["session_merits"] = (st.get("session_merits") or 0) + gained
            st["merit_log"] = (st.get("merit_log") or [])[-19:] + [{"ts": ev.get("timestamp"), "gained": gained, "total": st["merits"]}]
        elif e == "PowerplayRank":
            st["rank"] = ev.get("Rank")
        self.push()


def setup(core, module):
    p = Powerplay(core)

    def status(q):
        p.push()
        out = core.store.get(NS)
        j = core.store.get("journal")
        out["current_system"] = {"name": j.get("system"), "controlling_power": j.get("system_power"),
                                 "state": j.get("system_power_state"), "powers_present": j.get("system_powers")}
        return out

    core.http.route("/api/powerplay", status, tool="get_powerplay_status", module=module.name,
                    description="Pledged power, rank, total merits, merits earned this session with a log of recent gains, "
                                "days pledged, when the weekly cycle ends, and who controls the current system.")
