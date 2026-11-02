"""Spansh neutron waypoint contracts and ship readiness; no network side effects."""
import math
import re

API = "https://spansh.co.uk/api"
MK2_FSD = "int_hyperdrive_overcharge_size8_class5_overchargebooster_mkii"


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value)


def number(value, label, minimum, maximum):
    try:
        n = float(value)
    except (ValueError, TypeError):
        raise ValueError(label + " must be a number") from None
    if isinstance(value, bool) or not math.isfinite(n) or not minimum <= n <= maximum:
        raise ValueError(f"{label} must be {minimum}-{maximum}")
    return n


def system_name(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 100 or any(ord(c) < 32 for c in value):
        raise ValueError(label + " must be a system name (1-100 characters)")
    return value.strip()


def job_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-fA-F0-9-]{32,36}", value):
        raise ValueError("Invalid Spansh job ID")
    return value


def position(row):
    if not isinstance(row, dict):
        return None
    xyz = [row.get(k) for k in ("x", "y", "z")]
    return xyz if all(numeric(v) for v in xyz) else None


def ship_context(flight, commander):
    same = bool(commander and flight.get("commander") == commander)
    loadout = flight.get("loadout") or {} if same else {}
    data = loadout.get("data", {})
    modules = data.get("Modules", [])
    fsd = next((m for m in modules if m.get("Slot") == "FrameShiftDrive"), {})
    dirty = bool(flight.get("loadout_dirty_at")) if same else False
    fresh = bool(loadout and not dirty)
    def fitted(fragment):
        return any(fragment in str(m.get("Item", "")).lower() for m in modules) if fresh else None
    notices = []
    scoop, afmu = fitted("fuelscoop"), fitted("repairer")
    if scoop is not True:
        notices.append("Fuel scoop is missing or unverified. A scoop is needed to supercharge and refuel.")
    if afmu is not True:
        notices.append("AFMU is missing or unverified. Plan station repairs for FSD wear on repeated boosts.")
    health = fsd.get("Health") if fresh else None
    if numeric(health) and health < .8:
        notices.append("Last observed FSD health is below 80%; repair before relying on further boosts.")
    if dirty:
        notices.append("Ship fit changed after the last Loadout; reopen outfitting or relog to refresh it.")
    maximum = data.get("MaxJumpRange") if fresh else None
    return {"ship_id": data.get("ShipID"), "ship": data.get("Ship"), "ship_name": data.get("ShipName"),
            "loadout_observed_at": loadout.get("observed_at"), "loadout_changed": dirty,
            "max_unboosted_range_ly": maximum if numeric(maximum) else None,
            "range_note": "Loadout maximum is a reference, not a guaranteed full-fuel/laden range. Enter your verified normal range.",
            "suggested_supercharge_multiplier": 6 if fresh and fsd.get("Item", "").lower() == MK2_FSD else 4,
            "special_fsd_verified": bool(fresh and fsd.get("Item", "").lower() == MK2_FSD),
            "fuel_scoop_fitted": scoop, "afmu_fitted": afmu, "fsd_health_at_loadout": health,
            "notices": notices}


def parse_result(response, request):
    result = response.get("result")
    if not isinstance(result, dict):
        raise ValueError("Spansh result is missing")
    for key, wanted in (("source_system", request["from"]), ("destination_system", request["to"])):
        if str(result.get(key, "")).casefold() != wanted.casefold():
            raise ValueError("Spansh result endpoints do not match this request")
    rows = result.get("system_jumps")
    if not isinstance(rows, list) or not 2 <= len(rows) <= 10000:
        raise ValueError("Spansh returned an empty or oversized waypoint list")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid waypoint")
        name = system_name(row.get("system"), "Waypoint")
        jumps = row.get("jumps")
        if type(jumps) is not int or not 0 <= jumps <= 100000:
            raise ValueError("Invalid waypoint jump estimate")
        if type(row.get("neutron_star")) is not bool:
            raise ValueError("Missing neutron-star flag")
        out.append({"system": name, "coordinates": position(row), "neutron_star": row["neutron_star"],
                    "estimated_jumps_from_previous": jumps,
                    "distance_from_previous_ly": number(row.get("distance_jumped"), "Segment distance", 0, 200000),
                    "distance_remaining_ly": number(row.get("distance_left"), "Remaining distance", 0, 200000)})
    if out[0]["system"].casefold() != request["from"].casefold() or out[-1]["system"].casefold() != request["to"].casefold():
        raise ValueError("Waypoint endpoints do not match request")
    return out


def palin_check(progression, route):
    exploration = progression.get("exploration") or {}
    greatest = exploration.get("values", {}).get("Greatest_Distance_From_Start")
    greatest = greatest if numeric(greatest) and greatest >= 0 else None
    start = route.get("career_start") or {}
    end = (route.get("waypoints") or [{}])[-1].get("coordinates")
    distance = math.dist(start["coordinates"], end) if start.get("coordinates") and end else None
    return {"greatest_distance_from_start_ly": greatest, "observed_at": exploration.get("observed_at"),
            "distance_requirement_met_when_observed": greatest >= 5000 if greatest is not None else None,
            "career_start_system": start.get("system"), "career_start_source": start.get("source"),
            "destination_distance_from_career_start_ly": round(distance, 3) if distance is not None else None,
            "destination_meets_distance_requirement": distance >= 5000 if distance is not None else None,
            "destination_has_100ly_margin": distance >= 5100 if distance is not None else None,
            "note": "Palin requires 5000 Ly straight-line distance from career start, not accumulated travel. "
                    "No starting system is inferred from Sol, the route origin or the earliest available log. "
                    "The distance milestone alone does not confirm an invitation or the Sensor Fragments donation."}
