"""HTTP server: static web UI plus a small JSON API. Standard library only."""
import json
import mimetypes
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, config, journal, spansh


class Handler(BaseHTTPRequestHandler):
    server_version = f"EliteLab/{__version__}"

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    # -- helpers ---------------------------------------------------------
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, rel):
        rel = rel.lstrip("/") or "index.html"
        path = os.path.normpath(os.path.join(config.WEB_DIR, rel))
        if not path.startswith(os.path.normpath(config.WEB_DIR)) or not os.path.isfile(path):
            return self._send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(path, "rb") as f:
            return self._send(200, f.read(), ctype)

    # -- routes ----------------------------------------------------------
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        try:
            if u.path == "/api/health":
                return self._send(200, {"ok": True, "version": __version__, "journal_dir": config.JOURNAL_DIR,
                                        "journal_found": bool(journal.journal_files())})
            if u.path == "/api/state":
                return self._send(200, journal.build_state())
            if u.path == "/api/history":
                try:
                    days = int(q.get("days", "30"))
                except ValueError:
                    days = 30
                return self._send(200, journal.history(max(0, days)))
            if u.path == "/api/targets":
                return self._send(200, spansh.targets(q.get("power", "Edmund Mahon"), q.get("ref", "Leesti"),
                                                      q.get("min"), q.get("max"), q.get("pad", "L")))
            if u.path == "/api/powers":
                return self._send(200, spansh.power_summary(q.get("ref", "Leesti")))
            if u.path == "/api/system":
                return self._send(200, spansh.system_info(q.get("name", "Leesti")))
            if u.path == "/api/coords":
                return self._send(200, spansh.coords(q.get("names", "").split("|")))
            if u.path.startswith("/api/"):
                return self._send(404, {"error": "unknown endpoint"})
            return self._static(u.path)
        except Exception as ex:
            return self._send(500, {"error": str(ex)})


def serve(host=None, port=None):
    host = host or config.HOST
    port = port or config.PORT
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"EliteLab {__version__} listening on http://{host}:{port}")
    print(f"Journal dir: {config.JOURNAL_DIR}  (found: {bool(journal.journal_files())})")
    print("Ctrl+C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
