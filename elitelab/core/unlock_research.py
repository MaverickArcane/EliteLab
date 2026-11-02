"""Reviewed unlock requirements joined to observed commander evidence."""
import copy
import json
from pathlib import Path

from .gamedata import norm

DATA = json.loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))


def canonical(value):
    return " ".join(str(value or "").casefold().split())


def resolve(name):
    words = canonical(name).split()
    matches = [r for r in DATA["engineers"] if words and all(w in canonical(r["name"]) for w in words)]
    if len(matches) != 1:
        raise ValueError("Choose one reviewed engineer: " + ", ".join(r["name"] for r in DATA["engineers"]))
    return copy.deepcopy(matches[0])


def evaluate(record, account, engineers):
    observed = {canonical(r["name"]): r for r in engineers}
    access = observed.get(canonical(record["name"]), {"progress": "unknown"})
    state = access["progress"]
    requirement = record.get("requirement", {})
    evidence, value = None, None
    if requirement.get("kind") == "statistic":
        evidence = account.get("statistics")
        value = (evidence or {}).get("values", {}).get(requirement["group"], {}).get(requirement["field"])
    elif requirement.get("kind") == "rank":
        evidence = account.get("ranks", {}).get(requirement["field"])
        value = (evidence or {}).get("value")
    met = value >= requirement["minimum"] if isinstance(value, (int, float)) and requirement else None
    donation = record["donation"]
    donated = account.get("contributions", {}).get(canonical(record["name"]) + ":" + donation["key"])
    cargo = account.get("cargo", {})
    aboard = None
    if donation["kind"] == "Commodity" and cargo:
        aboard = sum(max(0, r.get("Count", 0) - r.get("Stolen", 0)) for r in cargo["items"]
                     if norm(r.get("Name") or "") == donation["key"])
    remaining = max(0, donation["quantity"] - donated["total"]) if donated else None
    parent = record.get("parent")
    parent_access = observed.get(canonical(parent)) if parent else None
    chain, seen = [], set()
    while parent and parent not in seen:
        seen.add(parent)
        chain.insert(0, parent)
        parent = resolve(parent).get("parent")
    if state == "Unlocked":
        action = "Already unlocked; no further unlock donation is needed. Choose the required upgrade grade."
    elif state == "Invited":
        action = f"Visit {record['base']} in {record['system']} and check the remaining {donation['name']} contribution ({donation['quantity']} total)."
    elif state == "Known":
        action = "Referral known. " + ("The recorded meeting threshold is met; check the Engineers panel for the invitation." if met
                                       else "Check the meeting requirement: " + record["meeting"] + ".")
    elif record.get("parent"):
        action = f"Check the referral from {record['parent']} (normally around grade 3-4); stop reputation work once the referral appears."
    else:
        action = "Check the Engineers panel and meeting requirement: " + record["meeting"] + "."
    return {"engineer": record["name"], "location": {"system": record["system"], "base": record["base"]},
            "access": copy.deepcopy(access), "referral_chain": chain, "parent_access": copy.deepcopy(parent_access),
            "meeting_requirement": {"description": record["meeting"], "observed_value": value,
                                    "threshold": requirement.get("minimum"), "met_when_observed": met,
                                    "observed_at": (evidence or {}).get("observed_at"), "source": (evidence or {}).get("source")},
            "donation": {**donation, "evidence": copy.deepcopy(donated), "remaining": 0 if state == "Unlocked" else remaining,
                         "aboard_unstolen": aboard, "cargo_observed_at": cargo.get("observed_at") if aboard is not None else None},
            "unlocked": state == "Unlocked" if state != "unknown" else None,
            "next_action": action, "sources": [record["source"]], "reviewed_on": DATA["reviewed_on"],
            "note": "Missing history is unknown. Meeting a numerical threshold does not prove an invitation. "
                    "Cargo and material holdings are not donations. Career distance is maximum distance from start, not total distance travelled."}
