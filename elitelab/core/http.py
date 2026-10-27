"""HTTP layer: route registry (self-describing, doubles as the AI tool list),
Server-Sent Events for live state, and static files for the shell and modules.
"""
import json
import logging
import hashlib
import hmac
import secrets
from http.cookies import SimpleCookie
import mimetypes
import os
import queue
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config

MAX_BODY = 1_000_000      # bytes; the largest legitimate POST is a wishlist


class Route:
    def __init__(self, path, fn, tool, description, params, method, module):
        self.path, self.fn, self.tool, self.description = path, fn, tool, description
        self.params, self.method, self.module = params or {}, method, module

    def schema(self):
        props, required = {}, []
        for name, spec in self.params.items():
            p = {"type": spec.get("type", "string"), "description": spec.get("description", "")}
            if "enum" in spec:
                p["enum"] = spec["enum"]
            if "default" in spec:
                p["default"] = spec["default"]
            elif spec.get("required"):
                required.append(name)
            props[name] = p
        return {"tool": self.tool, "path": self.path, "method": self.method, "module": self.module,
                "description": self.description, "input_schema": {"type": "object", "properties": props, "required": required}}


class Router:
    def __init__(self):
        self.routes = {}            # (method, path) -> Route
        self.tools = {}             # tool name -> Route
        self.static = {}            # url prefix -> directory

    def route(self, path, fn, *, tool=None, description="", params=None, method="GET", module="core"):
        r = Route(path, fn, tool, description, params, method.upper(), module)
        self.routes[(r.method, path)] = r
        if tool:
            self.tools[tool] = r
        return r

    def mount(self, prefix, directory):
        self.static[prefix.rstrip("/") + "/"] = directory


def make_handler(core):
    router, store = core.http, core.store

    class Handler(BaseHTTPRequestHandler):
        server_version = "EliteLab"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass

        # -- helpers -------------------------------------------------------
        def _send(self, code, body, ctype="application/json; charset=utf-8", headers=None):
            if isinstance(body, (dict, list)) or body is None:
                body = json.dumps(body).encode("utf-8")
            elif isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            # No CORS headers: cross-origin reads are disabled. POSTs also
            # enforce Origin and JSON content type before invoking handlers.
            self.end_headers()
            self.wfile.write(body)

        def _static(self, directory, rel):
            rel = rel.lstrip("/") or "index.html"
            base = os.path.normpath(directory)
            path = os.path.normpath(os.path.join(base, rel))
            if not path.startswith(base + os.sep) and path != base or not os.path.isfile(path):
                return self._send(404, {"error": "not found"})
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            with open(path, "rb") as f:
                return self._send(200, f.read(), ctype)

        def _body(self):
            """Read the request body (always, so keep-alive connections stay in sync) and parse JSON if possible."""
            n = int(self.headers.get("Content-Length") or 0)
            if n < 0 or n > MAX_BODY:
                self.close_connection = True
                raise ValueError(f"request body too large ({n} bytes, max {MAX_BODY})")
            if not n:
                return None
            raw = self.rfile.read(n)
            try:
                return json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeError):
                raise ValueError("request body must be valid JSON") from None

        def _check_mutation(self):
            origin = self.headers.get("Origin")
            host = self.headers.get("Host", "")
            # same host over http or https (a reverse proxy may terminate TLS in front of us)
            if ((origin is not None and origin not in ("http://" + host, "https://" + host))
                    or self.headers.get("Sec-Fetch-Site") == "cross-site"):
                return 403, "cross-origin mutations are not allowed"
            if self.headers.get_content_type() != "application/json":
                return 415, "Content-Type must be application/json"
            return None

        def _authorized(self):
            if not config.AUTH_TOKEN:
                return True
            authorization = self.headers.get("Authorization", "")
            if authorization.startswith("Bearer ") and hmac.compare_digest(
                    authorization[7:].encode(), config.AUTH_TOKEN.encode()):
                return True
            try:
                cookie = SimpleCookie(self.headers.get("Cookie", ""))
                value = cookie["elitelab_session"].value
                expires, nonce, signature = value.split(".")
                expected = hmac.new(config.AUTH_TOKEN.encode(), f"{expires}.{nonce}".encode(), hashlib.sha256).hexdigest()
                return int(expires) > time.time() and hmac.compare_digest(signature, expected)
            except Exception:                       # no/invalid cookie, or SimpleCookie's CookieError on a junk Cookie header
                return False

        def _login(self, body):
            token = body.get("token", "") if isinstance(body, dict) else ""
            if not isinstance(token, str) or not config.AUTH_TOKEN or not hmac.compare_digest(token.encode(), config.AUTH_TOKEN.encode()):
                return self._send(401, {"error": "invalid token"})
            value = f"{int(time.time()) + 43200}.{secrets.token_hex(16)}"
            signature = hmac.new(config.AUTH_TOKEN.encode(), value.encode(), hashlib.sha256).hexdigest()
            return self._send(200, {"ok": True}, headers={
                "Set-Cookie": f"elitelab_session={value}.{signature}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200"})

        def _dispatch(self, method):
            u = urllib.parse.urlparse(self.path)
            path = urllib.parse.unquote(u.path)
            q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            body = None
            try:
                if (path.startswith("/api/") or path == "/events") and path != "/api/login" and not self._authorized():
                    self.close_connection = True
                    return self._send(401, {"error": "authentication required"})
                if method == "POST":
                    error = self._check_mutation()
                    if error:
                        self.close_connection = True  # rejected body has not been consumed
                        return self._send(error[0], {"error": error[1]})
                    body = self._body()       # read before any reply, even a 404, or the next request on this connection breaks
                    if body is not None and not isinstance(body, dict):
                        raise ValueError("request body must be a JSON object")
                    if path == "/api/login":
                        return self._login(body)
                if path == "/events" and method == "GET":
                    return self._sse()
                r = router.routes.get((method, path))
                if r:
                    if isinstance(body, dict):
                        q = {**q, **body}     # POST bodies and query strings are merged: body wins.
                    return self._send(200, r.fn(q))
                if path.startswith("/api/"):
                    return self._send(404, {"error": f"no {method} route for {path}"})
                if method != "GET":
                    return self._send(405, {"error": "method not allowed"})
                for prefix, directory in router.static.items():
                    if path.startswith(prefix):
                        return self._static(directory, path[len(prefix):])
                return self._static(config.WEB_DIR, path)
            except ValueError as ex:
                return self._send(400, {"error": str(ex)})
            except Exception as ex:
                core.log.exception("request failed: %s %s", method, path)
                return self._send(500, {"error": str(ex)})

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        # -- server-sent events ----------------------------------------------
        def _sse(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            qu = queue.Queue(maxsize=1000)
            # If the queue overflows (slow or background tab) the client sees a gap in 'v' and refetches /api/state.
            off = store.subscribe(lambda ns, key, value, ver: _put(qu, {"ns": ns, "key": key, "value": value, "v": ver}))
            try:
                self._write_event("snapshot", store.snapshot())
                last = time.time()
                while True:
                    try:
                        msg = qu.get(timeout=1.0)
                        self._write_event("state", msg)
                    except queue.Empty:
                        pass
                    if time.time() - last > 15:
                        self.wfile.write(b": ping\n\n"); self.wfile.flush(); last = time.time()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            finally:
                off()

        def _write_event(self, event, data):
            self.wfile.write(f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8"))
            self.wfile.flush()

    return Handler


def _put(qu, msg):
    try:
        qu.put_nowait(msg)
    except queue.Full:
        pass


class HttpServer:
    def __init__(self, core):
        self.core = core
        self.srv = None

    def serve(self, host, port, *, open_browser=False):
        self.srv = ThreadingHTTPServer((host, port), make_handler(self.core))
        self.srv.daemon_threads = True
        try:
            if open_browser:
                browser_host = "127.0.0.1" if host == "0.0.0.0" else host
                url = f"http://{browser_host}:{self.srv.server_address[1]}/"

                def launch_browser():
                    try:
                        webbrowser.open(url)
                    except Exception:
                        logging.getLogger(__name__).warning("Could not open browser; visit %s", url, exc_info=True)

                threading.Thread(target=launch_browser, name="open-browser", daemon=True).start()
            self.srv.serve_forever()
        finally:
            self.srv.server_close()

    def stop(self):
        if self.srv:
            threading.Thread(target=self.srv.shutdown, daemon=True).start()
