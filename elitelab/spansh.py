"""Cached clients for the community data APIs EliteLab leans on.

Spansh (https://spansh.co.uk) : station/system search with Powerplay filters.
EDSM   (https://www.edsm.net) : batch system coordinates.

Both are free public APIs maintained by volunteers. Responses are cached so a
dashboard polling every few seconds never hammers them.
"""
import json
import threading
import time
import urllib.parse
import urllib.request

from . import config

SPANSH_STATIONS = "https://spansh.co.uk/api/stations/search"
SPANSH_SYSTEMS = "https://spansh.co.uk/api/systems/search"
EDSM_SYSTEMS = "https://www.edsm.net/api-v1/systems"

STARPORT_TYPES = ["Coriolis Starport", "Orbis Starport", "Ocellus Starport", "Asteroid base", "Planetary Port"]
MEDIUM_TYPES = STARPORT_TYPES + ["Outpost", "Planetary Outpost"]
POWERS = ["Edmund Mahon", "Li Yong-Rui", "Aisling Duval", "Pranav Antal", "Denton Patreus", "Nakato Kaine",
          "Felicia Winters", "Jerome Archer", "Zemina Torval", "Yuri Grom", "A. Lavigny-Duval", "Archon Delaine"]

_cache = {}
_lock = threading.Lock()


def _cached(key, ttl, fetch):
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    data = fetch()
    with _lock:
        _cache[key] = (time.time(), data)
    return data


def _post_json(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "User-Agent": config.USER_AGENT},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def spansh(url, body, ttl=None):
    key = (url, json.dumps(body, sort_keys=True))
    return _cached(key, ttl or config.CACHE_TTL, lambda: _post_json(url, body))


def _pad(s):
    if s.get("has_large_pad"):
        return "L"
    return "M" if (s.get("medium_pads") or 0) > 0 else "S"


def targets(power, ref, dmin=None, dmax=None, pad="L", size=40):
    """Stations with a market in Unoccupied systems that `power` can acquire, nearest `ref` first."""
    types = STARPORT_TYPES if pad == "L" else MEDIUM_TYPES
    filters = {
        "system_power": {"value": [power]},
        "system_power_state": {"value": ["Unoccupied"]},
        "has_market": {"value": True},
        "type": {"value": types},
    }
    if pad == "L":
        filters["has_large_pad"] = {"value": True}
    if dmin or dmax:
        filters["distance"] = {"min": str(dmin or 0), "max": str(dmax or 500)}
    body = {"filters": filters, "sort": [{"distance": {"direction": "asc"}}], "size": size, "page": 0,
            "reference_system": ref}
    data = spansh(SPANSH_STATIONS, body)
    out = []
    for s in data.get("results", []):
        out.append({
            "system": s.get("system_name"), "station": s.get("name"), "dist": round(s.get("distance", 0), 1),
            "ls": round(s.get("distance_to_arrival") or 0), "type": s.get("type"), "pad": _pad(s),
            "pop": s.get("system_population"), "updated": s.get("market_updated_at"),
            "x": s.get("system_x"), "y": s.get("system_y"), "z": s.get("system_z"),
            "economy": s.get("system_primary_economy"),
        })
    return {"count": data.get("count"), "results": out, "ref": ref, "power": power}


def power_summary(ref):
    """For every power: how many large-pad acquisition starports exist and the three nearest to `ref`."""
    out = []
    for p in POWERS:
        try:
            body = {"filters": {"system_power": {"value": [p]}, "system_power_state": {"value": ["Unoccupied"]},
                                "has_market": {"value": True}, "has_large_pad": {"value": True},
                                "type": {"value": STARPORT_TYPES}},
                    "sort": [{"distance": {"direction": "asc"}}], "size": 3, "page": 0, "reference_system": ref}
            d = spansh(SPANSH_STATIONS, body, ttl=1800)
            out.append({"power": p, "count": d.get("count"),
                        "nearest": [{"system": r.get("system_name"), "dist": round(r.get("distance", 0))}
                                    for r in d.get("results", [])]})
        except Exception as ex:
            out.append({"power": p, "error": str(ex)})
    return out


def system_info(name):
    d = spansh(SPANSH_SYSTEMS, {"filters": {"name": {"value": name}}, "size": 1, "page": 0})
    r = (d.get("results") or [None])[0]
    if not r:
        return {}
    return {"name": r.get("name"), "power_state": r.get("power_state"), "controlling_power": r.get("controlling_power"),
            "powers": r.get("power"), "population": r.get("population"), "allegiance": r.get("allegiance"),
            "x": r.get("x"), "y": r.get("y"), "z": r.get("z")}


def coords(names):
    """Batch coordinates from EDSM. Returns {name: {x,y,z}} for the systems it knows."""
    names = [n for n in dict.fromkeys(n.strip() for n in names) if n]
    if not names:
        return {}
    qs = "&".join("systemName[]=" + urllib.parse.quote(n) for n in names) + "&showCoordinates=1"
    key = ("edsm", ",".join(sorted(names)))
    data = _cached(key, 86400, lambda: _get_json(EDSM_SYSTEMS + "?" + qs))
    out = {}
    for s in data or []:
        c = s.get("coords") or {}
        if "x" in c:
            out[s.get("name")] = {"x": c["x"], "y": c["y"], "z": c["z"]}
    return out
