"""HTTP layer: route registry (self-describing, doubles as the AI tool list),
Server-Sent Events for live state, and static files for the shell and modules.
"""
import functools
import json
import copy
import logging
import re
import hashlib
import hmac
import ipaddress
import secrets
import socket
from http.cookies import SimpleCookie
import mimetypes
import os
import queue
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer

from . import config

LOOPBACK_NAMES = ("127.0.0.1", "localhost", "::1")


@functools.lru_cache(maxsize=1)
def machine_name():
    """This machine's own name, lower-cased; read on first use and cached. gethostname() never touches DNS
    (getfqdn() would, and can block for seconds), so a fully qualified or MagicDNS name goes in ELITELAB_ALLOWED_HOSTS."""
    return socket.gethostname().lower().rstrip(".")


def host_name(header):
    """The name part of a Host header, lower-cased, without the port or IPv6 brackets. None when malformed."""
    h = (header or "").strip().lower()
    if h.startswith("["):
        end = h.find("]")
        rest = h[end + 1:] if end > 0 else "x"
        if rest and not (rest.startswith(":") and rest[1:].isdigit()):
            return None
        name = h[1:end]
        try:
            ipaddress.IPv6Address(name)
        except ValueError:
            return None
        return name
    if h.count(":") > 1:
        return None                     # a bare IPv6 address is not a valid Host header
    name, _, port = h.partition(":")
    if not name or (_ and not port.isdigit()):
        return None
    return name.rstrip(".")


def host_allowed(name):
    """DNS rebinding always needs a DNS name, so IP literals are safe; names must be ones this lab is known by."""
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        pass
    bind = config.HOST.lower().rstrip(".")
    return (name in LOOPBACK_NAMES or (bind != "0.0.0.0" and name == bind)
            or name == machine_name() or name in config.ALLOWED_HOSTS)

MAX_BODY = 1_000_000      # bytes; the largest legitimate POST is a wishlist
LOCAL_ONLY_POSTS = ("/api/setup", "/api/setup/journals", "/api/restart")   # without a token, loopback peers only


def is_loopback_peer(address):
    """True for a loopback peer address, including an IPv4-mapped one (::ffff:127.0.0.1)."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except (ValueError, AttributeError):
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    return ip.is_loopback or bool(mapped and mapped.is_loopback)


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
            for key in ("items", "properties", "additionalProperties", "minimum", "maximum", "minItems", "maxItems"):
                if key in spec:
                    p[key] = copy.deepcopy(spec[key])
            if spec.get("required"):
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

        def handle_one_request(self):
            try:
                super().handle_one_request()
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                # Reloading/closing a browser can abandon a keep-alive socket,
                # including before the next request line arrives on Windows.
                self.close_connection = True

        def setup(self):
            super().setup()
            self.connection.settimeout(30)

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
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            connections = "'self'"
            # Setup alone probes a saved port before navigating after restart.
            # Restrict that exception to the current hostname, never other hosts
            # or script/style sources. Validate again before forming a CSP source.
            hostname = host_name(self.headers.get("Host"))
            if urllib.parse.urlsplit(self.path).path in ("/setup/", "/setup/index.html") and hostname and self._trusted_host():
                if re.fullmatch(r"[a-z0-9.-]+", hostname):
                    connections += f" http://{hostname}:* https://{hostname}:*"
            self.send_header("Content-Security-Policy", f"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src {connections}; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            # No CORS headers: cross-origin reads are disabled. POSTs also
            # enforce Origin and JSON content type before invoking handlers.
            self.end_headers()
            self.wfile.write(body)

        def _static(self, directory, rel):
            rel = rel.lstrip("/") or "index.html"
            base = os.path.realpath(directory)
            path = os.path.realpath(os.path.join(base, rel))
            if not path.startswith(base + os.sep) and path != base or not os.path.isfile(path):
                return self._send(404, {"error": "not found"})
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            with open(path, "rb") as f:
                return self._send(200, f.read(), ctype)

        def _body(self):
            """Read the request body (always, so keep-alive connections stay in sync) and parse JSON if possible."""
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding") or len(lengths) > 1:
                self.close_connection = True
                raise ValueError("Ambiguous request framing is not supported")
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self.close_connection = True
                raise ValueError("Invalid Content-Length") from None
            if n < 0 or n > MAX_BODY:
                self.close_connection = True
                raise ValueError(f"request body too large ({n} bytes, max {MAX_BODY})")
            if not n:
                return None
            raw = self.rfile.read(n)
            if len(raw) != n:
                self.close_connection = True
                raise ValueError("Incomplete request body")
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

        def _trusted_host(self):
            """Reject DNS rebinding even when the browser sends a matching Origin."""
            if len(self.headers.get_all("Host", [])) != 1:
                return False
            try:
                host = self.headers["Host"]
                # Older urllib versions accept trailing text after an IPv6
                # bracket. Validate the wire format before URL normalization.
                hostname = host_name(host)
                if not hostname or any(c.isspace() for c in host):
                    return False
                parsed = urllib.parse.urlsplit("//" + host)
                if (parsed.hostname or "").lower().rstrip(".") != hostname:
                    return False
                if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or not hostname:
                    return False
                _ = parsed.port  # validate port syntax
                allowed = {machine_name(), "localhost", "127.0.0.1", "::1", str(config.HOST).lower().rstrip("."), str(self.server.server_address[0]).lower()}
                if hostname in allowed | config.ALLOWED_HOSTS:
                    return True
                # Explicit IP URLs cannot use a hostile DNS rebinding name. This also supports LAN/Docker binds.
                ipaddress.ip_address(hostname)
                return True
            except (ValueError, TypeError):
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
            if not self._trusted_host():
                self.close_connection = True
                return self._send(403, {"error": "Untrusted Host. Use localhost, an IP address, or configure ELITELAB_ALLOWED_HOSTS for your trusted DNS name."})
            u = urllib.parse.urlparse(self.path)
            path = urllib.parse.unquote(u.path)
            q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            body = None
            try:
                if method == "GET" and (path.startswith("/api/") or path == "/events") and self.headers.get("Sec-Fetch-Site") == "cross-site":
                    self.close_connection = True
                    return self._send(403, {"error": "cross-site API requests are not allowed"})
                if (path.startswith("/api/") or path == "/events") and path != "/api/login" and not self._authorized():
                    self.close_connection = True
                    return self._send(401, {"error": "authentication required"})
                if method == "POST":
                    # defence in depth for the setup routes: a LAN client passes the Host rule with an IP literal
                    if path in LOCAL_ONLY_POSTS and not config.AUTH_TOKEN and not is_loopback_peer(self.client_address[0]):
                        self.close_connection = True  # rejected body has not been consumed
                        return self._send(403, {"error": "Setup changes require a local connection or configured authentication."})
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
                    if path == prefix.rstrip("/"):            # /setup -> /setup/ so the page's relative URLs resolve
                        return self._send(302, b"", "text/plain; charset=utf-8", {"Location": prefix})
                    if path.startswith(prefix):
                        return self._static(directory, path[len(prefix):])
                return self._static(config.WEB_DIR, path)
            except ValueError as ex:
                return self._send(400, {"error": str(ex)})
            except Exception as ex:
                core.log.exception("request failed: %s %s", method, path)
                return self._send(500, {"error": "Request failed; details are in the local server log"})

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


class ExclusiveHTTPServer(ThreadingHTTPServer):
    """Never let a second Windows process take over a listening port."""
    allow_reuse_address = os.name != "nt"
    daemon_threads = True

    def server_bind(self):
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        # HTTPServer.server_bind performs reverse DNS for server_name. A slow
        # resolver can block local startup (observed on macOS); this handler
        # needs only the bound address and port, never a reverse-resolved name.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


class HttpServer:
    def __init__(self, core):
        self.core = core
        self.srv = None
        self._stop_requested = False
        self._lock = threading.Lock()

    def bind(self, host, port):
        self.srv = ExclusiveHTTPServer((host, port), make_handler(self.core))

    def serve(self, host=None, port=None, *, open_browser=False):
        """Run the bound server until stop(). A stop requested before this call returns at once."""
        if self.srv is None:
            self.bind(host, port)
        with self._lock:
            if self._stop_requested:
                self._stop_requested = False
                self.srv.server_close()
                return
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
        with self._lock:
            if not self.srv:
                self._stop_requested = True
                return
        threading.Thread(target=self.srv.shutdown, daemon=True).start()
