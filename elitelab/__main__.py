"""Command line.

    python -m elitelab                 serve the dashboard + API (default)
    python -m elitelab serve --port 8766 --journals DIR
    python -m elitelab mcp             run the MCP stdio server (proxies a running lab)
    python -m elitelab modules         list discovered modules and their dependency order
    python -m elitelab tools           list AI tools exposed by a running lab
    python -m elitelab call TOOL k=v   call a tool on a running lab and print JSON (handy for any AI with a shell)
"""
import argparse
import json
import logging
import os
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog="elitelab", description="Self-hosted live dashboard for Elite Dangerous")
    ap.add_argument("--settings", help="settings file to use (sets ELITELAB_SETTINGS)")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="run the server (default)")
    s.add_argument("--host"); s.add_argument("--port", type=int); s.add_argument("--journals"); s.add_argument("-v", "--verbose", action="store_true")
    sub.add_parser("mcp", help="MCP stdio server")
    sub.add_parser("modules", help="list modules")
    sub.add_parser("tools", help="list AI tools on a running lab")
    c = sub.add_parser("call", help="call a tool on a running lab")
    c.add_argument("tool"); c.add_argument("args", nargs="*", help="key=value pairs (JSON values allowed)")
    args = ap.parse_args(argv)
    cmd = args.cmd or "serve"
    if args.settings:
        os.environ["ELITELAB_SETTINGS"] = args.settings   # config reads it at import, so before any elitelab.core import

    if cmd == "mcp":
        from . import mcp
        mcp.serve()
        return 0
    if cmd == "tools":
        from . import mcp
        for t in mcp._tools():
            print(f"{t['name']:<24} {t['description']}")
        return 0
    if cmd == "call":
        from . import mcp
        kv = {}
        for a in args.args:
            k, _, v = a.partition("=")
            try:
                kv[k] = json.loads(v)
            except Exception:
                kv[k] = v
        print(json.dumps(mcp._call(args.tool, kv), indent=1))
        return 0
    if cmd == "modules":
        from .core import loader
        for m in loader.resolve_order(loader.discover()):
            print(f"{m.name:<12} requires={m.requires} provides={m.provides} cards={[c['id'] for c in m.cards]}")
        return 0

    logging.basicConfig(level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s", stream=sys.stderr)
    from .core import Core, config
    if getattr(args, "journals", None):
        config.JOURNAL_DIR = args.journals
        config.SOURCES["journal_dir"] = "flag"
    if getattr(args, "host", None):
        config.HOST = args.host                 # the Host rule and get_setup read config, so the flag must land there
        config.SOURCES["host"] = "flag"
    if getattr(args, "port", None) is not None:
        config.PORT = args.port
        config.SOURCES["port"] = "flag"
    return Core().start(getattr(args, "host", None), getattr(args, "port", None))


if __name__ == "__main__":
    sys.exit(main())
