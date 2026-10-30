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
    ap.add_argument("--settings", help="settings JSON file (overrides ELITELAB_SETTINGS)")
    ap.add_argument("--open-browser", action="store_true", help="open the dashboard after binding")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="run the server (default)")
    s.add_argument("--host"); s.add_argument("--port", type=int); s.add_argument("--journals"); s.add_argument("-v", "--verbose", action="store_true")
    s.add_argument("--open-browser", action="store_true", default=argparse.SUPPRESS)
    sub.add_parser("mcp", help="MCP stdio server")
    sub.add_parser("modules", help="list modules")
    sub.add_parser("tools", help="list AI tools on a running lab")
    c = sub.add_parser("call", help="call a tool on a running lab")
    c.add_argument("tool"); c.add_argument("args", nargs="*", help="key=value pairs (JSON values allowed)")
    args = ap.parse_args(argv)
    cmd = args.cmd or "serve"
    if args.settings:
        os.environ["ELITELAB_SETTINGS"] = args.settings

    if cmd == "mcp":
        from . import mcp
        return mcp.serve()
    if cmd == "tools":
        from . import mcp
        for t in mcp._tools():
            print(f"{t['name']:<24} {t['description']}")
        return
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
        return
    if cmd == "modules":
        from .core import loader
        for m in loader.resolve_order(loader.discover()):
            print(f"{m.name:<12} requires={m.requires} provides={m.provides} cards={[c['id'] for c in m.cards]}")
        return

    logging.basicConfig(level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s", stream=sys.stderr)
    from .core import Core, config
    if getattr(args, "journals", None):
        config.JOURNAL_DIR = os.path.abspath(os.path.expanduser(args.journals))
        config.SOURCES["journal_dir"] = "flag"
    for key in ("host", "port"):
        value = getattr(args, key, None)
        if value is not None:
            if key == "port" and not (value == 0 or 1024 <= value <= 65535):
                ap.error("port must be 0 or between 1024 and 65535")
            setattr(config, key.upper(), value)
            config.SOURCES[key] = "flag"
    return Core().start(open_browser=args.open_browser)


if __name__ == "__main__":
    sys.exit(main())
