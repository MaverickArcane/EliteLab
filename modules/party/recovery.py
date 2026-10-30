"""Local journal catch-up boundaries; no room credentials or network access."""
from datetime import datetime
from pathlib import Path
import json


def seconds(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (AttributeError, TypeError, ValueError):
        return None


def phase_at(operation, event, tracking, member_id):
    """Only recover events known to belong to this tracked, non-cancelled job."""
    if operation.get("id") != tracking.get("operation_id") or operation.get("stage") == "cancelled":
        return None
    at, since, start = (seconds(v) for v in (event.get("timestamp"), tracking.get("since"), operation.get("started_at")))
    if any(v is None for v in (at, since, start)) or at < max(int(since), int(start)):
        return None
    end = seconds(operation.get("ended_at"))
    if operation.get("stage") == "complete" and (end is None or at >= int(end)):
        return None
    opened = seconds((operation.get("phase_started_at") or {}).get("unloading"))
    if operation.get("stage") in ("unloading", "complete") and opened is None:
        return None  # Older jobs lack an unambiguous phase boundary.
    phase = "unloading" if opened is not None and at >= int(opened) else "loading"
    report = operation.get("reports", {}).get(member_id, {})
    correction = (report.get("correction_at") or {}).get(phase)
    if correction is None and report.get("adjustments", {}).get(phase):
        correction = report.get("updated_at")  # Conservative migration for older corrections.
    cutoffs = [(tracking.get("manual_through") or {}).get(phase), correction]
    if any(seconds(c) is not None and at <= int(seconds(c)) for c in cutoffs):
        return None
    return phase


def deliveries(directory, since):
    """Read complete journal lines with docking context; never alter live state."""
    cutoff = seconds(since)
    if cutoff is None:
        return
    docked = None
    files = sorted(Path(directory).glob("Journal.*.log"), key=lambda p:p.stat().st_mtime)
    for path in files:
        # A journal cannot contain a later game session than its final write.
        if path.stat().st_mtime < int(cutoff):
            continue
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if not line.endswith("\n"):
                    continue  # Writer has not finished this entry yet.
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                kind = event.get("event")
                if kind in ("Docked", "Location", "CarrierJump"):
                    docked = event.get("MarketID") if kind == "Docked" or event.get("Docked") else None
                elif kind in ("Undocked", "FSDJump", "LoadGame"):
                    docked = None
                at = seconds(event.get("timestamp"))
                if kind in ("MarketSell", "CargoTransfer") and at is not None and at >= int(cutoff):
                    yield event, docked
