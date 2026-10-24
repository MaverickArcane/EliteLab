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
                _reply(msg_id, {"protocolVersion": requested if requested in SUPPORTED_PROTOCOLS else PROTOCOL, "capabilities": {"tools": {}},
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
            else:
                _reply(msg_id, error={"code": -32601, "message": f"method not found: {method}"})
        except Exception as ex:
            _reply(msg_id, error={"code": -32000, "message": str(ex)})


if __name__ == "__main__":
    serve()
