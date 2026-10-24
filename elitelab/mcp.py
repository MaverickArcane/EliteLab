"""Model Context Protocol server (stdio transport), standard library only.

Every EliteLab API route registered with a ``tool`` name becomes an MCP tool,
so an AI client (Claude Code, Claude Desktop, Cursor...) can read your live
game state and drive the lab. This process is a thin proxy: it fetches the
tool list from the running EliteLab server and forwards calls over HTTP.

Run:  python -m elitelab mcp            (ELITELAB_URL defaults to http://127.0.0.1:8766)
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

BASE = os.environ.get("ELITELAB_URL", "http://127.0.0.1:8766").rstrip("/")
# Versions whose initialize/stdio/tools contract this server implements.
SUPPORTED_PROTOCOLS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")
PROTOCOL = SUPPORTED_PROTOCOLS[-1]


def _http(method, path, params=None, body=None):
    url = BASE + path
    if params and method == "GET":
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", "User-Agent": "EliteLab-MCP"})
    if os.environ.get("ELITELAB_AUTH_TOKEN"):
        req.add_header("Authorization", "Bearer " + os.environ["ELITELAB_AUTH_TOKEN"])
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        # surface the lab's own message ({"error": "..."}) instead of "HTTP Error 400: Bad Request"
        try:
            detail = json.loads(ex.read().decode("utf-8")).get("error")
        except Exception:
            detail = None
        raise RuntimeError(detail or f"HTTP {ex.code} from {path}") from None


_tool_cache = {}


def _tools(refresh=False):
    """Tool table from the lab; cached for the life of the process (it only changes when the lab restarts)."""
    if _tool_cache and not refresh:
        return list(_tool_cache.values())
    schema = _http("GET", "/api/schema")
    _tool_cache.clear()
    for t in schema.get("tools", []):
        _tool_cache[t["tool"]] = {"name": t["tool"], "description": t["description"] or t["path"], "inputSchema": t["input_schema"],
                                  "_path": t["path"], "_method": t["method"]}
    return list(_tool_cache.values())


def _call(name, args):
    _tools()
    t = _tool_cache.get(name)
    if not t:
        _tools(refresh=True)                  # the lab may have been restarted with new modules
        t = _tool_cache.get(name)
    if not t:
        raise KeyError(f"unknown tool {name}")
    if t["_method"] == "POST":
        return _http("POST", t["_path"], body=args or {})
    return _http("GET", t["_path"], params=args or {})


PROMPTS = {
    "plan_rares_run": {
        "description": "Plan a rare goods run from where the commander is: which loop, what to buy, where to sell for Powerplay merits.",
        "arguments": [],
        "text": ("Plan a rare goods run for me. Call get_commander_state (where I am, my ship, cargo and jump range), get_rares_loop "
                 "(the active loop and what is already aboard), get_powerplay_status (my power) and find_sell_targets with min=125 "
                 "max=165 (acquisition starports that pay merits; check the refuses list against my hold). Then give me the route: "
                 "the next buy stops in order, then the sell stop, with jump counts, and anything that would stop a station buying.")},
    "engineering_plan": {
        "description": "Work out what to farm, trade or buy for an engineering goal (a pinned build, or a blueprint such as 'G5 dirty drives').",
        "arguments": [{"name": "goal", "description": "What to engineer, e.g. 'the pinned build' or 'G5 dirty drives on my thrusters'", "required": False}],
        "text": ("My engineering goal: {goal}. If it is the pinned build, call get_build_progress and build_to_wishlist; otherwise use "
                 "list_recipes / get_recipe and wishlist_add with the right grades. Then call get_engineering_wishlist (what is short), "
                 "plan_material_trades (what my surplus can be traded into and at which trader type), find_material_traders (where) and "
                 "find_farm_sites for_wishlist=true (where to farm what trading cannot cover). Give me an ordered plan: trade first, "
                 "then farm, nearest first, with the materials each stop covers.")},
    "where_am_i": {
        "description": "A quick situation report: location, ship, fuel, cargo, Powerplay standing, and anything that needs attention.",
        "arguments": [],
        "text": ("Give me a short situation report. Call get_commander_state and get_powerplay_status, then tell me where I am, what I am "
                 "flying, fuel and cargo, my pledge and merits this session, and flag anything that needs attention (low fuel, hot ship, "
                 "a rares loop in progress, a build that is close to done).")},
}


def _resources():
    """Live state as readable resources: the whole snapshot and one per module namespace."""
    state = _http("GET", "/api/state")
    out = [{"uri": "elitelab://state", "name": "Live state (all modules)", "mimeType": "application/json",
            "description": "Every module namespace as one JSON object; prefer the per-namespace resources or the tools when you need one thing."}]
    for ns in sorted(k for k in state if not k.startswith("_")):
        out.append({"uri": f"elitelab://state/{ns}", "name": f"{ns} state", "mimeType": "application/json",
                    "description": f"The {ns} module's live namespace."})
    return out


def _read_resource(uri):
    state = _http("GET", "/api/state")
    if uri == "elitelab://state":
        return state
    if uri.startswith("elitelab://state/"):
        ns = uri[len("elitelab://state/"):]
        if ns in state:
            return state[ns]
    raise KeyError(f"unknown resource {uri}")


def _reply(msg_id, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def serve():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        method, msg_id, params = req.get("method"), req.get("id"), req.get("params") or {}
        if not method:
            continue            # a response or a malformed message; never answer those
        try:
            if method == "initialize":
                requested = params.get("protocolVersion")
                _reply(msg_id, {"protocolVersion": requested if requested in SUPPORTED_PROTOCOLS else PROTOCOL,
                                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                                "serverInfo": {"name": "elitelab", "version": __version__},
                                "instructions": ("EliteLab exposes the commander's live Elite Dangerous state. Start with "
                                                 "get_commander_state for where they are and what they fly, get_powerplay_status "
                                                 "for merits, get_materials / set_wishlist for engineering, find_sell_targets for "
                                                 "Powerplay trading, get_rares_loop for the rare goods run. All data is read-only "
                                                 "from the game's journal; nothing here can act in the game.")})
            elif method == "notifications/initialized" or method.startswith("notifications/"):
                continue
            elif method == "ping":
                _reply(msg_id, {})
            elif method == "tools/list":
                _reply(msg_id, {"tools": [{k: v for k, v in t.items() if not k.startswith("_")} for t in _tools(refresh=True)]})
            elif method == "tools/call":
                try:
                    result = _call(params.get("name"), params.get("arguments") or {})
                    _reply(msg_id, {"content": [{"type": "text", "text": json.dumps(result, indent=1)}], "isError": False})
                except Exception as ex:
                    _reply(msg_id, {"content": [{"type": "text", "text": f"error: {ex}"}], "isError": True})
            elif method == "resources/list":
                _reply(msg_id, {"resources": _resources()})
            elif method == "resources/templates/list":
                _reply(msg_id, {"resourceTemplates": [{"uriTemplate": "elitelab://state/{namespace}", "name": "Module state",
                                                        "mimeType": "application/json", "description": "One module namespace, e.g. journal, powerplay, wishlist"}]})
            elif method == "resources/read":
                uri = params.get("uri") or ""
                try:
                    data = _read_resource(uri)
                    _reply(msg_id, {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(data, indent=1)}]})
                except KeyError as ex:
                    _reply(msg_id, error={"code": -32002, "message": str(ex)})
            elif method == "prompts/list":
                _reply(msg_id, {"prompts": [{"name": k, "description": v["description"], "arguments": v["arguments"]} for k, v in PROMPTS.items()]})
            elif method == "prompts/get":
                p = PROMPTS.get(params.get("name") or "")
                if not p:
                    _reply(msg_id, error={"code": -32602, "message": f"unknown prompt: {params.get('name')}"})
                else:
                    args = {a["name"]: "the pinned build" for a in p["arguments"]}
                    args.update({k: v for k, v in (params.get("arguments") or {}).items() if v})
                    _reply(msg_id, {"description": p["description"],
                                    "messages": [{"role": "user", "content": {"type": "text", "text": p["text"].format(**args)}}]})
            else:
                _reply(msg_id, error={"code": -32601, "message": f"method not found: {method}"})
        except Exception as ex:
            _reply(msg_id, error={"code": -32000, "message": str(ex)})


if __name__ == "__main__":
    serve()
