"""Necessary mining-route conditions; never proof that an actual haul earns merits.

Source: https://elitecheatsheet.com/powerplay-2 (checked 2026-11-02).
Reinforcement uses the mined system; acquisition uses a pledged power's
Fortified/Stronghold source within 20/30 Ly. Local activities still need checking.
"""
import math

from .ledger import number


def check_route(mode, power, origin, source, station):
    def result(status, reason):
        return {"status":status, "reason":reason}
    if mode == "none":
        return result("not_checked", "Credit quote only. Mining merit eligibility has not been checked.")
    if not origin:
        return result("unknown", "Mining source unknown. Enter where this cargo was mined; the travel origin is separate.")
    same = origin.casefold() == station["system_name"].strip().casefold()
    if mode == "reinforcement":
        return result("candidate", "Same-system route for the entered source. Local activity and cargo provenance remain unverified.") if same else result("blocked", "Reinforcement requires selling in the system where the cargo was mined.")
    owner, state = source.get("controlling_power"), source.get("power_state")
    if same or (owner and owner != power) or (state and state not in ("Fortified", "Stronghold")):
        return result("blocked", "Acquisition needs a different destination and a Fortified or Stronghold mining source controlled by your power.")
    a, b = [source.get(k) for k in "xyz"], [station.get("system_"+k) for k in "xyz"]
    if owner != power or state not in ("Fortified", "Stronghold") or any(type(v) not in (int, float) or number(abs(v), 1000000) is None for v in a+b):
        return result("unknown", "Source control or coordinates unavailable. Acquisition route eligibility is unknown.")
    distance = math.dist(a, b)
    if distance > (20 if state == "Fortified" else 30):
        return result("blocked", "Destination is outside the entered mining source's reported control range.")
    return result("candidate", "Reported acquisition route within source control range. Local activity and cargo provenance remain unverified.")
