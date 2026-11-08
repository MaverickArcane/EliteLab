"""Buy-source search: explicit radius, measured distance and dated stock reports."""
import math
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

API = "https://api.ardent-insight.com/v2"


def normal(value):
    return "".join(c for c in str(value or "").casefold() if c.isalnum())


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def integer(q, name, default, minimum, maximum):
    raw = q.get(name, default)
    try:
        value = int(raw)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(name + " must be an integer") from None
    if isinstance(raw, bool) or str(raw) != str(value):
        raise ValueError(name + " must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be {minimum}-{maximum}")
    return value


class Sourcing:
    def __init__(self, core):
        self.core = core

    def find(self, q):
        commodity = str(q.get("commodity", "")).strip()
        if not commodity or len(commodity) > 100:
            raise ValueError("commodity is required (maximum 100 characters)")
        radius = integer(q, "max_distance_ly", 25, 1, 500)
        quantity = integer(q, "quantity", 25, 1, 1000000)
        days = integer(q, "max_days", 2, 1, 30)
        limit = integer(q, "limit", 20, 1, 100)
        carriers = q.get("carriers", "include")
        if carriers not in ("include", "only", "exclude"):
            raise ValueError("carriers must be include, only or exclude")
        pad = str(q.get("pad", "L")).upper()
        if pad not in ("S", "M", "L"):
            raise ValueError("pad must be S, M or L")
        journal = self.core.store.get("journal")
        reference = str(q.get("reference") or journal.get("system") or "").strip()
        if not reference or len(reference) > 100:
            raise ValueError("Provide a reference system or wait for a journal location")
        catalog = self.core.services.fetch_json(API + "/commodities", ttl=3600)
        if not isinstance(catalog, list):
            raise ValueError("Ardent returned an invalid commodity catalog")
        names = {normal(commodity)}
        if q.get("commodity_key"):
            names.add(normal(q["commodity_key"]))
        matches = {r["commodityName"] for r in catalog if isinstance(r, dict) and r.get("commodityName")
                   and normal(r["commodityName"]) in names}
        if not matches or len(matches) > 4:
            raise ValueError("Commodity name is unknown or ambiguous in the Ardent catalog: " + commodity)
        aliases = sorted(matches)
        coords = journal.get("star_pos") if reference.casefold() == str(journal.get("system", "")).casefold() else None
        if not isinstance(coords, (list, tuple)) or len(coords) != 3 or not all(numeric(v) for v in coords):
            resolved = self.core.services.edsm_coords([reference])
            entry = next((v for k, v in resolved.items() if k.casefold() == reference.casefold()), {})
            coords = [entry.get(axis) for axis in ("x", "y", "z")]
        if not all(numeric(v) for v in coords):
            raise ValueError("Cannot verify reference coordinates; nearby search requires a known origin")
        params = {"minVolume": quantity, "maxDistance": radius, "maxDaysAgo": days}
        if carriers != "include":
            params["fleetCarriers"] = "1" if carriers == "only" else "0"
        data, urls, capped = [], [], False
        for alias in aliases:
            url = f"{API}/system/name/{quote(reference, safe='')}/commodity/name/{quote(alias, safe='')}/nearby/exports?{urlencode(params)}"
            rows = self.core.services.fetch_json(url, ttl=300)
            if not isinstance(rows, list):
                raise ValueError("Ardent returned an invalid nearby market response")
            capped = capped or len(rows) >= 1000
            data.extend((row, url) for row in rows)
            urls.append(url)
        now = datetime.now(timezone.utc)
        found, rejected = [], {}
        def reject(reason):
            rejected[reason] = rejected.get(reason, 0) + 1
        # A commodity can have display-name and journal-key aliases in the catalog.
        # Keep the newest report per market before filtering, so an older in-stock
        # alias cannot resurrect stock that a newer report says is exhausted.
        latest = {}
        for row, url in data:
            if not isinstance(row, dict):
                continue
            identity = row.get("marketId") or (row.get("systemName"), row.get("stationName"))
            previous = latest.get(identity)
            if not previous or str(row.get("updatedAt", "")) > str(previous[0].get("updatedAt", "")):
                latest[identity] = (row, url)
        for row, url in latest.values():
            if not isinstance(row, dict):
                reject("invalid_row")
                continue
            fc = normal(row.get("stationType")) == "fleetcarrier"
            if (carriers == "only" and not fc) or (carriers == "exclude" and fc):
                reject("carrier_filter")
                continue
            if not row.get("systemName") or not row.get("stationName") or normal(row.get("commodityName")) not in names:
                reject("missing_or_mismatched_identity")
                continue
            price, stock = row.get("buyPrice"), row.get("stock")
            if not numeric(price) or price <= 0 or not numeric(stock) or stock < quantity:
                reject("price_or_stock")
                continue
            size = row.get("maxLandingPadSize")
            if not numeric(size) or size < {"S": 1, "M": 2, "L": 3}[pad]:
                reject("pad_unknown_or_small")
                continue
            target = [row.get("system" + axis) for axis in "XYZ"]
            if not all(numeric(v) for v in target):
                reject("missing_coordinates")
                continue
            distance = math.dist(coords, target)
            if distance > radius:
                reject("outside_radius")
                continue
            try:
                updated = datetime.fromisoformat(row["updatedAt"].replace("Z", "+00:00"))
                if updated.tzinfo is None:
                    raise ValueError("No timezone")
                age = (now - updated).total_seconds() / 3600
            except (ValueError, TypeError, AttributeError, KeyError):
                reject("invalid_timestamp")
                continue
            if age < 0 or age > days * 24:
                reject("stale_or_future_timestamp")
                continue
            found.append({"system": row["systemName"], "station": row["stationName"], "station_type": row.get("stationType"),
                          "market_id": row.get("marketId"), "distance_ly": round(distance, 3),
                          "distance_to_arrival_ls": row.get("distanceToArrival"), "pad": {1: "S", 2: "M", 3: "L"}.get(size),
                          "price": price, "stock": stock, "cost_for_quantity": price * quantity,
                          "updated_at": row["updatedAt"], "age_hours": round(age, 2),
                          "docking_access": "unknown", "carrier_location_verified_live": False if fc else None,
                          "source": "Ardent Insight community market report", "source_url": url})
        # Sort on measured distance, never the provider's price-ranked ordering.
        found.sort(key=lambda r: (r["distance_ly"], r["price"], r["age_hours"]))
        return {"reference": reference, "reference_coordinates": coords, "commodity": commodity,
                "quantity": quantity, "max_distance_ly": radius, "max_days": days, "carriers": carriers, "pad": pad,
                "status": "sources_found" if found else "no_matching_reports_within_radius", "sources": found[:limit],
                "matching_reports": len(found), "provider_rows": len(data), "provider_limit_reached": capped,
                "rejected": rejected, "queried_at": now.isoformat(), "source_urls": urls, "commodity_aliases": aliases,
                "note": "Radius was not widened. Community reports may be stale; stock and carrier location/access are not guaranteed. "
                        "Provider returns at most 1000 price-ranked reports; results are distance-sorted within that coverage. "
                        "No matches does not prove no supply exists. Responses may be cached for 5 minutes."}
