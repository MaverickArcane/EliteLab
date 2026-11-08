"""Bounded Spansh ring and station searches, explicitly requested by the user.

Body filter shape verified against Spansh's own bodies UI and live API on
2026-11-02: rings=[{type:'Metallic'}], not rings.value or ring_type.
Ring signals are reported hotspot counts, not overlap geometry or yield.
"""
import datetime as dt
import math
import time

from elitelab.core.gamedata import POWERS, norm
from .ledger import number
from .buyer_routes import check_route

RINGS = ("Metallic", "Metal Rich", "Icy", "Rocky")
ORBITAL = ("Coriolis Starport", "Orbis Starport", "Ocellus Starport", "Dodec Starport", "Asteroid base", "Outpost")
CATALOG = "https://www.spansh.co.uk/api/stations/field_values/market"
POWER_MODES = {"acquisition": ["Unoccupied"], "reinforcement": ["Exploited", "Fortified", "Stronghold"]}
MAX_RADIUS = 2500


def text(value):
    return value.strip()[:160] if isinstance(value, str) else ""


def token(value):
    return "".join(c for c in text(value).casefold() if c.isalnum())


def reported_powers(record):
    value = record.get("system_power")
    return [p for p in (value[:16] if isinstance(value, list) else [value]) if isinstance(p, str) and p in POWERS]


def controlling_power(record):
    value = record.get("system_controlling_power")
    return value if isinstance(value, str) and value in POWERS else None


def parameter(q, key, default, maximum, integer=False):
    value = q.get(key, default)
    try:
        n = float(value)
        if isinstance(value, bool) or not math.isfinite(n) or not 0 < n <= maximum or (integer and n != int(n)):
            raise ValueError()
        return int(n) if integer else n
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{key} must be a positive number up to {maximum}.") from None


def name_param(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise ValueError(f"Enter {label} (up to 160 characters).")
    return value.strip()


def age(value, now):
    try:
        stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.timestamp() > now:
            return None
        return (now - stamp.timestamp()) / 3600
    except (AttributeError, ValueError, TypeError, OverflowError, OSError):
        return None


class Discovery:
    def __init__(self, core):
        self.core = core

    def reference(self, q):
        return name_param(q.get("ref") or self.core.store.get("journal", "system"), "a reference system")

    def range_limit(self, journal):
        laden = number(journal.get("jump_range_laden"), 1000)
        current = number(journal.get("jump_range_now"), 1000)
        # A conservative ship jump estimate, not a limit on planning distance.
        # Missing or zero range must not invent reachability or prevent planning.
        return min(laden, current) if laden and current else None

    def context(self, journal=None):
        journal = journal if journal is not None else (self.core.store.get("journal") or {})
        pp = ((self.core.store.get("mining", "summary") or {}).get("powerplay") or {})
        return (journal.get("cmdr"), journal.get("system"), (journal.get("ship_info") or {}).get("id"),
                journal.get("jump_range_laden"), journal.get("jump_range_now"),
                (journal.get("status") or {}).get("cargo_tons"), (journal.get("status") or {}).get("fuel"), journal.get("cargo"), pp.get("power"))

    def search(self, endpoint, filters, ref):
        if self.core.config.OFFLINE:
            raise ValueError("Community searches are unavailable in offline mode. Session tracking still works.")
        records, available, partial = [], None, False
        # A 100-station reply can exceed the shared 8 MiB transport bound. Keep
        # that security limit and fetch at most four smaller, cached pages.
        for page in range(4):
            try:
                data = self.core.services.fetch_json("https://www.spansh.co.uk/api/" + endpoint + "/search",
                    {"filters": filters, "reference_system": ref, "size": 25, "page": page,
                     "sort": [{"distance": {"direction": "asc"}}]}, ttl=300)
                if not isinstance(data, dict) or data.get("error") or not isinstance(data.get("results"), list):
                    raise ValueError()
            except Exception as exc:
                if not records:
                    raise ValueError("Spansh search unavailable. Check the system name and retry.") from exc
                partial = True
                break
            batch = data["results"][:25]
            records.extend(batch)
            available = number(data.get("count"))
            if len(batch) < 25 or available is None or len(records) >= available:
                break
        return {"results": records, "count": available, "partial": partial}

    def spots(self, q):
        journal = self.core.store.get("journal") or {}
        limit, context = self.range_limit(journal), self.context(journal)
        origin = journal.get("system")
        ref = name_param(q.get("ref") or origin, "a reference system")
        radius = parameter(q, "radius", limit or 100, MAX_RADIUS)
        sort = q.get("sort", "distance")
        if not isinstance(sort, str) or sort not in ("distance", "merits"):
            raise ValueError("Sort must be distance or merits.")
        mode = q.get("powerplay_mode", "reinforcement")
        if not isinstance(mode, str) or mode not in POWER_MODES:
            raise ValueError("Choose acquisition or reinforcement for mining opportunities.")
        ring_type = q.get("ring_type", "Metallic")
        if ring_type not in (*RINGS, "Any"):
            raise ValueError("Choose Metallic, Metal Rich, Icy, Rocky or Any rings.")
        hotspot = q.get("hotspot", "")
        if not isinstance(hotspot, str) or len(hotspot) > 160:
            raise ValueError("Hotspot must be text up to 160 characters.")
        pristine = q.get("pristine", "false")
        if pristine not in (True, False, "true", "false"):
            raise ValueError("pristine must be true or false.")
        pristine = pristine in (True, "true")
        power = q.get("power", "")
        if not isinstance(power, str):
            raise ValueError("Choose a known Powerplay power or leave power blank.")
        if sort == "merits" and not power:
            power = ((self.core.store.get("mining", "summary") or {}).get("powerplay") or {}).get("power")
        if not isinstance(power, str) or (power and power not in POWERS):
            raise ValueError("Choose a known Powerplay power or leave power blank.")
        if sort == "merits" and (not power or not hotspot.strip()):
            raise ValueError("Merit planning needs a known power and a hotspot commodity, such as Platinum.")
        if sort == "merits":
            parameter(q, "quantity", 1, 1000000, True)
            parameter(q, "hours", 24, 72)
            if q.get("pad", "L") not in ("S", "M", "L"):
                raise ValueError("Pad must be S, M or L.")
        filters = {"distance": {"min": 0, "max": radius}, "rings": [{}] if ring_type == "Any" else [{"type": ring_type}]}
        if pristine:
            filters["reserve_level"] = {"value": ["Pristine"]}
        if power:
            filters.update({"system_power": {"value": [power]}, "system_power_state": {"value": POWER_MODES["reinforcement"]}})
        data = self.search("bodies", filters, ref)
        now, rows, seen = time.time(), [], set()
        jump = limit
        for body in data["results"][:100]:
            if not isinstance(body, dict):
                continue
            distance = number(body.get("distance"), radius)
            if distance is None or not text(body.get("system_name")):
                continue
            if pristine and body.get("reserve_level") != "Pristine":
                continue
            if power and (body.get("system_power_state") not in POWER_MODES["reinforcement"] or controlling_power(body) != power):
                continue
            rings = body.get("rings")
            for ring in (rings[:16] if isinstance(rings, list) else []):
                if not isinstance(ring, dict) or ring.get("type") not in RINGS or not text(ring.get("name")):
                    continue
                if ring_type != "Any" and ring["type"] != ring_type:
                    continue
                signals = ring.get("signals")
                signals = [{"name": text(s.get("name")), "count": int(number(s.get("count"), 10000) or 0)}
                           for s in (signals[:32] if isinstance(signals, list) else []) if isinstance(s, dict) and text(s.get("name"))]
                if hotspot and not any(token(hotspot) == token(s["name"]) and s["count"] > 0 for s in signals):
                    continue
                identity = (text(body["system_name"]), text(ring["name"]))
                if identity in seen:
                    continue
                seen.add(identity)
                coords = [body.get("system_" + axis) for axis in "xyz"]
                valid_coords = all(type(n) in (int, float) and number(abs(n), 1000000) is not None for n in coords)
                rows.append({"system": identity[0], "body": text(body.get("name")), "ring": identity[1], "ring_type": ring["type"],
                    "reserve": text(body.get("reserve_level")) or "Unknown", "distance": round(distance, 2),
                    "arrival_ls": number(body.get("distance_to_arrival")), "jumps": math.ceil(distance / jump) if jump else None,
                    "signals": signals, "signals_updated_at": text(ring.get("signals_updated_at")) or None,
                    "updated_at": text(body.get("updated_at")) or None, "age_hours": age(body.get("updated_at"), now),
                    "power_state": text(body.get("system_power_state")) or "Unknown",
                    "powers": reported_powers(body),
                    "controlling_power": controlling_power(body),
                    "permit_required": body.get("system_is_permit_required") if type(body.get("system_is_permit_required")) is bool else None,
                    "x": coords[0] if valid_coords else None, "y": coords[1] if valid_coords else None, "z": coords[2] if valid_coords else None})
        rows.sort(key=lambda r: (r["distance"], r["arrival_ls"] if r["arrival_ls"] is not None else math.inf, r["ring"]))
        matched = len(rows)
        rows = rows[:30]
        planning = {}
        if sort == "merits":
            from .opportunities import rank
            planning = rank(self, rows, q, ref, radius, power, mode, hotspot)
        # Reject a response calculated for a ship/location that changed during I/O.
        if self.context() != context:
            raise ValueError("Ship range or location changed during the search. Search again.")
        return {"ref": ref, "radius": radius, "ship_range": limit, "range_limit": limit,
                "manual_origin": ref.casefold() != text(origin).casefold(),
                "range_basis": "Ship jumps use unboosted full-hold/full-tank range limited by current fuel/cargo. Unknown range gives unknown jumps. Search radius is independent.",
                "sort": sort, "power": power, "results": rows, "matched_rings": matched, **planning,
                "bodies_checked": min(len(data["results"]), 100), "bodies_available": number(data.get("count")),
                "source": "Spansh", "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "note": "Nearest matching rings among up to 100 reported bodies; at most 30 shown. Community data can be incomplete. "
                        "Hotspot counts do not establish overlaps, yield or mining method. DSS-scan and prospect on arrival. "
                        "The selected radius can span multiple ship or carrier jumps; manual origins are planning locations, not reachability from your ship. "
                        "Jump counts are straight-line lower bounds; check permits and fuel in game. "
                        + ("A provider page failed; results are partial." if data["partial"] else "")}

    def buyers(self, q, *, _limit=20):
        context = self.context()
        ref, radius = self.reference(q), parameter(q, "radius", 100, MAX_RADIUS)
        mined_in = q.get("mined_in", "")
        if not isinstance(mined_in, str) or len(mined_in) > 160:
            raise ValueError("Mined in must be a system name up to 160 characters.")
        mined_in = mined_in.strip()
        commodity = name_param(q.get("commodity"), "a commodity name")
        quantity = parameter(q, "quantity", 1, 1000000, True)
        hours = parameter(q, "hours", 24, 72)
        pad = q.get("pad", "L")
        if pad not in ("S", "M", "L"):
            raise ValueError("Pad must be S, M or L.")
        mode, power = q.get("powerplay_mode", "none"), q.get("power", "pledged")
        if not isinstance(mode, str) or mode not in ("none", *POWER_MODES):
            raise ValueError("Powerplay mode must be none, acquisition or reinforcement.")
        if not isinstance(power, str) or power not in ("pledged", *POWERS):
            raise ValueError("Choose a known power or pledged.")
        # The shared powerplay card can retain a previous session's pledge until
        # the next snapshot arrives. Use this session's mining evidence only.
        if power == "pledged":
            power = ((self.core.store.get("mining", "summary") or {}).get("powerplay") or {}).get("power")
        if mode != "none" and (not isinstance(power, str) or power not in POWERS):
            raise ValueError("Pledged power is unknown. Select a power explicitly or disable the Powerplay filter.")
        power = power if mode != "none" else None
        if self.core.config.OFFLINE:
            raise ValueError("Community searches are unavailable in offline mode. Session tracking still works.")
        source = {}
        if mode == "acquisition" and mined_in:
            try:
                source = self.core.services.spansh_system(mined_in)
                if not isinstance(source, dict) or text(source.get("name")).casefold() != mined_in.casefold():
                    source = {}
            except Exception:
                source = {}
        try:
            catalog = self.core.services.fetch_json(CATALOG, ttl=86400)
            names = catalog.get("min_max") if isinstance(catalog, dict) else None
            if not isinstance(names, dict):
                raise ValueError()
        except Exception as exc:
            raise ValueError("Spansh commodity catalogue unavailable. Retry later.") from exc
        selected = token(norm(commodity))
        # Frontier's singular journal identifier versus the market display name.
        selected = {"lowtemperaturediamond": "lowtemperaturediamonds"}.get(selected, selected)
        commodity = next((text(n) for n in list(names)[:2000] if token(n) == selected), None)
        if commodity is None:
            raise ValueError("Commodity not found in the Spansh market catalogue. Use its market display name.")
        now = time.time()
        lower = dt.datetime.fromtimestamp(math.floor(now / 300) * 300 - hours * 3600, dt.timezone.utc).isoformat()
        upper = dt.datetime.fromtimestamp(math.floor(now / 300) * 300 + 300, dt.timezone.utc).isoformat()
        filters = {"distance": {"min": 0, "max": radius}, "has_market": {"value": True}, "type": {"value": list(ORBITAL)},
                   "market_updated_at": {"comparison": "<=>", "value": [lower, upper]},
                   "market": [{"name": commodity, "demand": {"comparison": "<=>", "value": [quantity, 10**12]},
                               "sell_price": {"comparison": "<=>", "value": [1, 10**9]}}]}
        if pad == "L":
            filters["has_large_pad"] = {"value": True}
        if mode != "none":
            filters.update({"system_power": {"value": [power]}, "system_power_state": {"value": POWER_MODES[mode]}})
        data = self.search("stations", filters, ref)
        rows, seen, excluded = [], set(), 0
        for station in data["results"][:100]:
            if not isinstance(station, dict) or station.get("type") not in ORBITAL or station.get("is_planetary") or station.get("carrier_name"):
                continue
            if mode != "none" and (station.get("system_power_state") not in POWER_MODES[mode]
                    or (mode == "reinforcement" and controlling_power(station) != power)
                    or (mode == "acquisition" and (power not in reported_powers(station) or controlling_power(station) is not None))):
                continue
            distance, updated = number(station.get("distance"), radius), age(station.get("market_updated_at"), now)
            if distance is None or updated is None or updated > hours or station.get("has_market") is not True:
                continue
            actual_pad = "L" if station.get("has_large_pad") is True else "M" if number(station.get("medium_pads")) else "S" if number(station.get("small_pads")) else None
            if actual_pad is None or "SML".index(actual_pad) < "SML".index(pad):
                continue
            identity = (text(station.get("system_name")), text(station.get("name")))
            if not all(identity) or identity in seen:
                continue
            market = station.get("market")
            for item in (market[:1000] if isinstance(market, list) else []):
                if not isinstance(item, dict) or token(item.get("commodity")) != token(commodity) or item.get("is_prohibited"):
                    continue
                price, demand = number(item.get("sell_price"), 10**9), number(item.get("demand"), 10**12)
                if not price or demand is None or demand < quantity:
                    continue
                seen.add(identity)
                route = check_route(mode, power, mined_in, source, station)
                if route["status"] == "blocked":
                    excluded += 1
                    break
                rows.append({"system": identity[0], "station": identity[1], "distance": round(distance, 2),
                    "arrival_ls": number(station.get("distance_to_arrival")), "pad": actual_pad,
                    "price": price, "demand": demand, "estimated_sale": price * quantity,
                    "powers": reported_powers(station), "power_state": text(station.get("system_power_state")) or "Unknown",
                    "controlling_power": controlling_power(station),
                    "merit_eligibility": "unverified", "merit_route": route,
                    "coordinates": [station.get("system_" + axis) if type(station.get("system_" + axis)) in (int, float)
                                    and number(abs(station["system_" + axis]), 1000000) is not None else None for axis in "xyz"],
                    "updated_at": text(station.get("market_updated_at")), "age_hours": round(updated, 2)})
                break
        rows.sort(key=lambda r: (-r["estimated_sale"], r["distance"], r["station"]))
        if context != self.context():
            raise ValueError("Ship, pledge or location changed during the search. Search again.")
        return {"ref": ref, "commodity": commodity, "quantity": quantity, "results": rows[:_limit],
                "mined_in": mined_in or None, "origin_basis": "user supplied" if mined_in else "unknown", "excluded_routes": excluded,
                "purpose": "credit_quotes" if mode == "none" else "merit_candidates",
                "purpose_note": "Credit buyers only. These results do not validate Powerplay merit eligibility." if mode == "none" else
                    "Merit candidates only. Confirm the mining activity and cargo provenance in game. " +
                    ("Mining source unknown; route eligibility cannot be checked." if not mined_in else "Source is user supplied, not proof of cargo origin.") +
                    (f" {excluded} quotes excluded for an incompatible mining route." if excluded else ""),
                "powerplay_mode": mode, "power": power, "merit_estimate": None,
                "stations_checked": min(100, len(data["results"])), "stations_available": number(data.get("count")),
                "source": "Spansh", "note": "Best reported quotes among up to 100 nearby orbital markets, not a galaxy-wide best price. "
                        "Reported demand covers the entered load; prices/demand may change or fall with the size of your sale. "
                        "No carriers or surface ports. Estimates are unsold value, not realized profit. "
                        "Powerplay filters select reported candidates, not verified merit eligibility. Check the game's local activities, "
                        "mining origin and source-to-destination requirements before selling; user-supplied source, community control and distances are not proof of cargo provenance. "
                        + ("A provider page failed; results are partial." if data["partial"] else "")}
