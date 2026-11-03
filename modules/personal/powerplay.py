"""Planning context only: a selected commodity route never proves merit eligibility."""
import hashlib
import json

from elitelab.core.gamedata import POWERS
from modules.personal.plan import label, valid_plan


NOTE = ("Distances start at this stop, not your ship. Review the existing distance and pad filters. "
        "The finder examines reported Powerplay markets using rare cargo aboard; planned goods are not added to that cargo. "
        "Commodity acceptance and merit eligibility remain unknown. Your trade route and recorded merits are unchanged.")


def context(plan, progress, journal, power):
    out = {"ready": False, "status": "no_plan", "message": "Select a trade route first.",
           "token": None, "power": power if power in POWERS else None, "stops": [],
           "eligibility": "unknown", "expected_merits": None, "note": NOTE}
    if not valid_plan(plan) or not isinstance(progress, dict):
        return out
    index = progress.get("leg")
    if index is None or progress.get("stage") == "complete":
        return {**out, "status": "complete", "message": "This route is complete. Select another route before planning a Powerplay stop."}
    if type(index) is not int or not 0 <= index < len(plan["legs"]):
        return {**out, "status": "invalid_progress", "message": "The active trade leg is unavailable. Reselect the route."}
    commander, selector = label(journal.get("cmdr")), label(plan.get("cmdr"))
    if not commander or not selector or commander != selector:
        return {**out, "status": "commander_mismatch", "message": "This route is not verified for the current commander. Reselect it before using a stop."}
    leg = plan["legs"][index]
    out.update(leg=index, commodity=label(leg["commodity"]), quantity=leg["quantity"],
               route_id=plan["id"], selected_at=plan.get("selected_at"), quotes=progress.get("quotes"))
    for role in ("buy", "sell"):
        stop = leg[role]
        out["stops"].append({"role": role, "system": label(stop["system"]), "station": label(stop["station"]),
                             "market_id": stop["market_id"], "reported_at": label(stop.get("observed_at")),
                             "args": {"ref": label(stop["system"]), "power": out["power"]} if out["power"] else None})
    identity = [plan["id"], plan.get("selected_at"), commander, index, out["power"], out["stops"]]
    out["token"] = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    out.update(ready=bool(out["power"]), status="ready" if out["power"] else "pledge_unknown",
               message="Choose which stop to use as the finder origin." if out["power"] else
                       "Pledge unknown. Record your Powerplay pledge in the journal before transferring this route to the finder.")
    return out


def handoff(state, q):
    role = q.get("role", "sell")
    if role not in ("buy", "sell"):
        raise ValueError("Choose the buy or sell stop of the active trade leg.")
    token = q.get("token")
    if token is not None and (not isinstance(token, str) or token != state.get("token")):
        raise ValueError("The trade route, active leg, commander or pledge changed. Refresh the handoff first.")
    stop = next((s for s in state["stops"] if s["role"] == role), None)
    return {**state, "role": role, "stop": stop,
            "next_tool": {"name": "find_sell_targets", "arguments": stop["args"]} if state["ready"] and stop else None}
