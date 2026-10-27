"""Opt-in, scoped LAN transport. The main dashboard never needs a network bind.

Only telemetry and the leader's trade plan cross this listener. Party codes and
connections live in memory; restart or Leave stops sharing. No journal uploads.
"""
import copy
from datetime import datetime, timezone
import hmac
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import math
import secrets
import socket
import threading
import time
from urllib.parse import urlsplit

from elitelab.core.gamedata import norm
from modules.party.loads import recommend

NS = "party"
STALE_SECONDS = 30
REPORT_SECONDS = 1
MAX_MEMBERS = 32
MAX_BODY = 64000


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clean_text(value, limit=160):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("Invalid report text.")
    return value


def amount(value):
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= 1000000:
        raise ValueError("Invalid cargo amount.")
    return value


def sanitize(raw):
    if not isinstance(raw, dict):
        raise ValueError("A commander report is required.")
    out = {k: clean_text(raw.get(k)) for k in ("cmdr", "ship", "ship_name", "ship_ident", "system", "station", "observed_at", "cargo_at")}
    out.update(capacity=amount(raw.get("capacity")), cargo_count=amount(raw.get("cargo_count")), docked=raw.get("docked") is True)
    out["telemetry"] = sanitize_telemetry(raw.get("telemetry"))
    cargo = raw.get("cargo", [])
    if not isinstance(cargo, list) or len(cargo) > 256:
        raise ValueError("Too many cargo entries.")
    out["cargo"] = []
    for item in cargo:
        if not isinstance(item, dict):
            raise ValueError("Invalid cargo entry.")
        out["cargo"].append({"key": clean_text(item.get("key")), "name": clean_text(item.get("name")), "count": amount(item.get("count"))})
    activity = raw.get("activity", "ready")
    if activity not in ("ready", "hauling", "away"):
        raise ValueError("Choose ready, hauling or away.")
    out["activity"] = activity
    work = raw.get("work")
    if work is not None:
        if not isinstance(work, dict) or not isinstance(work.get("operation_id"), str) or len(work["operation_id"]) != 32:
            raise ValueError("Invalid operation report.")
        out["work"] = {"operation_id": work["operation_id"], "loading": amount(work.get("loading", 0)), "unloading": amount(work.get("unloading", 0))}
    return out


def sanitize_telemetry(raw):
    """Optional, bounded fields keep old clients compatible and reports scoped."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("Invalid telemetry report.")
    out = {k: clean_text(raw.get(k)) for k in ("status_at", "fuel_at", "hull_at", "body", "destination", "legal")}
    vehicle = raw.get("vehicle")
    if vehicle not in (None, "ship", "fighter", "srv", "foot", "taxi", "crew"):
        raise ValueError("Invalid vehicle.")
    out["vehicle"] = vehicle
    for key in ("game_running", "shields_up", "docked", "landed", "supercruise", "fsd_charging", "fsd_jump", "scooping", "low_fuel", "overheating", "in_danger", "interdicted", "silent_running", "hardpoints"):
        value = raw.get(key)
        if value is not None and type(value) is not bool:
            raise ValueError("Invalid telemetry flag.")
        out[key] = value
    for key in ("fuel", "fuel_reservoir", "fuel_capacity", "hull_health"):
        value = raw.get(key)
        limit = 1 if key == "hull_health" else 1000000
        if value is not None and (type(value) not in (int, float) or not 0 <= value <= limit or not math.isfinite(value)):
            raise ValueError("Invalid telemetry value.")
        out[key] = value
    return out


def private_address(address):
    ip = ipaddress.ip_address(address)
    if ip.is_loopback:
        return True
    networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "fc00::/7")
    return any(ip in ipaddress.ip_network(n) for n in networks)


def exchange(url, token, body):
    """Resolve once, validate, then connect to that IP; never follow redirects/proxies."""
    u = urlsplit(url)
    if u.scheme != "http" or not u.hostname or u.username or u.password or u.path not in ("", "/") or u.query or u.fragment:
        raise ValueError("Use http:// followed by the leader's LAN/tailnet address and party port.")
    port = u.port or 8767
    addresses = socket.getaddrinfo(u.hostname, port, type=socket.SOCK_STREAM)
    address = next((a[4][0] for a in addresses if private_address(a[4][0])), None)
    if not address:
        raise ValueError("The party address must resolve to a LAN or tailnet IP.")
    connection = http.client.HTTPConnection(address, port, timeout=5)
    try:
        connection.request("POST", "/report", json.dumps(body), {"Content-Type": "application/json", "Authorization": "Bearer " + token})
        response = connection.getresponse()
        data = response.read(256001)
        if response.status != 200:
            raise ValueError("Party rejected the report. Check the party code and leader address.")
        if len(data) > 256000:
            raise ValueError("Party response too large.")
        result = json.loads(data)
        if not isinstance(result, dict) or not isinstance(result.get("members"), list):
            raise ValueError("Invalid party response.")
        return result
    finally:
        connection.close()


class Party:
    def __init__(self, core):
        self.core = core
        self.lock = threading.RLock()
        self.operations = threading.Lock()
        self.mode = "idle"
        self.token = ""
        saved = core.read_data("party-local.json", default={}) or {}
        identity = saved.get("id", "")
        self.member_id = identity if isinstance(identity, str) and len(identity) == 32 and all(c in "0123456789abcdef" for c in identity) else secrets.token_hex(16)
        self.activity = "ready"
        try:
            self.work = sanitize({"work": saved.get("work")}).get("work")
        except ValueError:
            self.work = None
        self.auto_seen = [v for v in saved.get("auto_seen", []) if isinstance(v, str) and len(v) == 64][-10000:]
        self.last_auto = saved.get("last_auto") if isinstance(saved.get("last_auto"), dict) else None
        self.docked_market = None
        core.write_data({"id": self.member_id, "work": self.work, "auto_seen": self.auto_seen, "last_auto": self.last_auto}, "party-local.json")
        self.members = {}
        self.remote = {}
        self.error = None
        self.url = ""
        self.server = None
        self.stop = threading.Event()
        self.generation = 0
        self.last_success = None
        core.bus.on("journal.*", self.journal_delivery)
        core.bus.on("state.journal.location", lambda n, v: self.publish())
        core.bus.on("state.journal.status", lambda n, v: self.publish())
        core.bus.on("state.journal.game_running", lambda n, v: self.publish())
        self.publish()

    def local(self):
        j = self.core.store.get("journal")
        c = j.get("cargo") or {}
        status = j.get("status") or {}
        telemetry = {k: status.get(k) for k in ("vehicle", "body", "destination", "legal", "fuel", "fuel_reservoir", "fuel_at", "shields_up", "landed", "supercruise", "fsd_charging", "fsd_jump", "scooping", "low_fuel", "overheating", "in_danger", "interdicted", "silent_running", "hardpoints")}
        telemetry.update(status_at=status.get("timestamp"), docked=status.get("docked_flag"), game_running=j.get("game_running"),
                         fuel_capacity=(j.get("ship_info") or {}).get("fuel_main") if status.get("vehicle") == "ship" else None,
                         hull_health=j.get("hull_health"), hull_at=j.get("hull_at"))
        return sanitize({"cmdr": j.get("cmdr"), "ship": j.get("ship"), "ship_name": j.get("ship_name"), "ship_ident": j.get("ship_ident"), "system": j.get("system"), "station": j.get("station"), "telemetry": telemetry,
            "docked": j.get("docked"), "capacity": j.get("cargo_capacity"), "cargo_count": c.get("count"), "cargo": c.get("items", []),
            "observed_at": j.get("last_event_time"), "cargo_at": c.get("timestamp"), "activity": self.activity, "work": copy.deepcopy(self.work)})

    def shared(self):
        with self.lock:
            clock = time.time()
            self.members = {k: m for k, m in self.members.items() if clock - m["received"] < 300}
            members = [{"id": self.member_id, **self.local(), "leader": True, "stale": False, "last_seen": utc()}]
            members += [{k: v for k, v in m.items() if k != "received"} | {"id": mid, "stale": clock - m["received"] > STALE_SECONDS} for mid, m in self.members.items()]
            plan, operation = self.core.store.get("trade", "plan"), self.core.store.get("trade", "operation")
            suggestion = recommend(plan, operation, members, (self.core.store.get("trade", "calculation") or {}).get("to_haul"))
            return {"members": members, "plan": plan, "operation": operation, "load_suggestion": suggestion, "carrier": self.core.store.get("journal", "carrier"), "leader": self.local().get("cmdr"), "updated_at": utc()}

    def publish(self):
        with self.lock:
            shared = self.shared() if self.mode == "leader" else copy.deepcopy(self.remote)
            stale = self.mode == "member" and (self.last_success is None or time.time() - self.last_success > STALE_SECONDS)
            if stale:
                for member in shared.get("members", []):
                    member["stale"] = True
            self.core.store.update(NS, {"mode": self.mode, "code": self.token if self.mode == "leader" else None,
                "port": self.server.server_port if self.server else None, "url": self.url, "error": self.error,
                "members": shared.get("members", []), "plan": shared.get("plan"), "stale": stale,
                "operation": shared.get("operation"), "carrier": shared.get("carrier"), "activity": self.activity, "work": copy.deepcopy(self.work),
                "load_suggestion": None if stale else shared.get("load_suggestion"),
                "auto_tracking": {"loading": bool((shared.get("plan") or {}).get("carrier_market_id")), "unloading": bool((shared.get("plan") or {}).get("destination_market_id"))}, "last_auto_delivery": copy.deepcopy(self.last_auto),
                "updated_at": shared.get("updated_at"), "local_id": self.member_id})

    def receive(self, body):
        if not isinstance(body, dict):
            raise ValueError("Report must be an object.")
        mid = body.get("id")
        if not isinstance(mid, str) or len(mid) != 32 or any(c not in "0123456789abcdef" for c in mid) or mid == self.member_id:
            raise ValueError("Invalid member identity.")
        report = sanitize(body.get("report", {}))
        with self.lock:
            if self.mode != "leader":
                raise ValueError("Party is closed.")
            self.shared()  # expire old reports before applying the membership limit
            if body.get("leave") is True:
                self.members.pop(mid, None)
            else:
                if mid not in self.members and len(self.members) >= MAX_MEMBERS - 1:
                    raise ValueError("Party is full.")
                self.members[mid] = {**report, "last_seen": utc(), "received": time.time(), "leader": False}
            self.core.bus.emit("party.work", {"id": mid, "report": report})
            self.publish()
            return self.shared()

    def handler(self):
        party = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(5)

            def log_message(self, *args):
                pass

            def reply(self, status, body):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                if self.path != "/report":
                    return self.reply(404, {"error": "not found"})
                auth = self.headers.get("Authorization", "")
                if self.headers.get("Origin") or not party.token or not hmac.compare_digest(auth.encode(), ("Bearer " + party.token).encode()):
                    return self.reply(403, {"error": "invalid party code"})
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= MAX_BODY or self.headers.get_content_type() != "application/json":
                        raise ValueError("Invalid report size or content type.")
                    return self.reply(200, party.receive(json.loads(self.rfile.read(size))))
                except (ValueError, TypeError, UnicodeError) as ex:
                    return self.reply(400, {"error": str(ex)})

        return Handler

    def _leave(self):
        with self.lock:
            old_mode, old_url, old_token = self.mode, self.url, self.token
            self.stop.set()
            self.generation += 1
            server, self.server = self.server, None
            self.mode, self.token, self.url = "idle", "", ""
            self.members, self.remote, self.error = {}, {}, None
            self.last_success = None
            self.publish()
        if server:
            server.shutdown()
            server.server_close()
        if old_mode == "member":
            try:
                exchange(old_url, old_token, {"id": self.member_id, "leave": True})
            except (OSError, ValueError, http.client.HTTPException):
                pass  # the leader expires this report if it could not be removed

    def leave(self, q=None):
        with self.operations:
            self._leave()
        return self.core.store.get(NS)

    def host(self, q):
        try:
            port = int(q.get("port", 8767))
            if not 1024 <= port <= 65535:
                raise ValueError()
        except (TypeError, ValueError):
            raise ValueError("Choose a party port between 1024 and 65535.") from None
        bind = q.get("bind", "0.0.0.0")
        if not isinstance(bind, str) or (bind != "0.0.0.0" and not private_address(bind)):
            raise ValueError("Bind to 0.0.0.0 or this machine's LAN/tailnet IPv4 address.")
        with self.operations:
            with self.lock:
                if self.mode != "idle":
                    raise ValueError("Leave the current party first.")
                try:
                    server = ThreadingHTTPServer((bind, port), self.handler())
                except OSError:
                    raise ValueError("Could not listen on that address and port. Check the address or choose another port.") from None
                self.server, self.mode, self.token = server, "leader", secrets.token_urlsafe(24)
                self.stop = threading.Event()
                self.error = None
                self.generation += 1
                threading.Thread(target=server.serve_forever, name="party-listener", daemon=True).start()
                self.start_worker()
                self.publish()
        return self.core.store.get(NS)

    def join(self, q):
        url, token = q.get("url", ""), q.get("code", "")
        if not isinstance(url, str) or len(url) > 240 or not isinstance(token, str) or not 16 <= len(token) <= 128 or not token.isascii() or any(c.isspace() for c in token):
            raise ValueError("Enter the leader's party URL and code.")
        with self.operations:
            with self.lock:
                if self.mode != "idle":
                    raise ValueError("Leave the current party first.")
            try:
                shared = exchange(url, token, {"id": self.member_id, "report": self.local()})
            except (OSError, http.client.HTTPException):
                raise ValueError("Could not reach the leader. Check Tailscale, the address, port and firewall.") from None
            with self.lock:
                self.mode, self.url, self.token = "member", url, token
                self.remote, self.error, self.last_success = shared, None, time.time()
                self.stop = threading.Event()
                self.generation += 1
                self.start_worker()
                self.publish()
        return self.core.store.get(NS)

    def save_work(self, work, seen=None, last_auto=None):
        seen = self.auto_seen if seen is None else seen
        last_auto = self.last_auto if last_auto is None else last_auto
        self.core.write_data({"id": self.member_id, "work": work, "auto_seen": seen, "last_auto": last_auto}, "party-local.json")
        self.work, self.auto_seen, self.last_auto = work, seen, last_auto

    def journal_delivery(self, name, event):
        if not isinstance(event, dict):
            return
        kind = event.get("event")
        with self.lock:
            if kind in ("Docked", "Location", "CarrierJump"):
                self.docked_market = event.get("MarketID") if kind == "Docked" or event.get("Docked") else None
            elif kind in ("Undocked", "FSDJump", "LoadGame"):
                self.docked_market = None
            # Replays, cargo snapshots, buys and inventory drops are not new deliveries.
            if event.get("_replay") or kind not in ("MarketSell", "CargoTransfer") or self.mode not in ("leader", "member"):
                return
            shared = self.shared() if self.mode == "leader" else self.remote
            op, plan = shared.get("operation"), shared.get("plan")
            if not op or not plan or op["stage"] not in ("loading", "unloading"):
                return
            try:
                event_time = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).timestamp()
                start_time = datetime.fromisoformat(op["started_at"].replace("Z", "+00:00")).timestamp()
                if event_time < int(start_time):
                    return
            except (KeyError, ValueError, TypeError, AttributeError):
                return
            phase = op["stage"]
            market = plan.get("carrier_market_id" if phase == "loading" else "destination_market_id")
            if not market:
                return
            commodity = norm(plan["commodity"])
            tonnes = 0
            if kind == "MarketSell" and event.get("MarketID") == market and norm(event.get("Type")) == commodity:
                count = event.get("Count")
                tonnes = count if type(count) is int and count > 0 else 0
            elif kind == "CargoTransfer" and phase == "loading" and self.docked_market == market:
                tonnes = sum(t["Count"] for t in event.get("Transfers", []) if isinstance(t, dict)
                             and t.get("Direction") == "tocarrier" and norm(t.get("Type")) == commodity
                             and type(t.get("Count")) is int and t["Count"] > 0)
            if not tonnes:
                return
            digest = hashlib.sha256(json.dumps({k:v for k,v in event.items() if not k.startswith("_")}, sort_keys=True).encode()).hexdigest()
            if digest in self.auto_seen:
                return
            work = copy.deepcopy(self.work) if self.work and self.work["operation_id"] == op["id"] else {"operation_id":op["id"], "loading":0, "unloading":0}
            if work[phase] + tonnes > op["quantity"]:
                self.error = "Journal delivery exceeds the planned quantity. Check the operation size and any manual entries."
                self.publish()
                return
            work[phase] += tonnes
            self.save_work(work, (self.auto_seen + [digest])[-10000:], {"operation_id":op["id"],"phase":phase,"tonnes":tonnes,"at":event["timestamp"]})
            self.activity = "hauling"
            if self.mode == "leader":
                self.core.bus.emit("party.work", {"id":self.member_id,"report":self.local()})
            # No network I/O on the watcher thread: the heartbeat sends cumulative totals.
            self.publish()

    def report_work(self, q):
        with self.lock:
            if self.mode not in ("leader", "member"):
                raise ValueError("Create or join the hauling party first.")
            if "activity" in q:
                self.activity = sanitize({"activity": q["activity"]})["activity"]
            if "tonnes" in q:
                op = self.shared().get("operation") if self.mode == "leader" else self.remote.get("operation")
                if (not op or op["id"] != q.get("id") or op["stage"] not in ("loading", "unloading")
                        or (self.mode == "member" and (self.last_success is None or time.time() - self.last_success > STALE_SECONDS))):
                    raise ValueError("Refresh the current active loading/unloading job before reporting a delivery.")
                tonnes = amount(q["tonnes"])
                if not tonnes:
                    raise ValueError("Enter the tonnes you actually delivered.")
                work = copy.deepcopy(self.work) if self.work and self.work["operation_id"] == op["id"] else {"operation_id": op["id"], "loading": 0, "unloading": 0}
                phase = op["stage"]
                if work[phase] + tonnes > op["quantity"]:
                    raise ValueError("Your reported deliveries exceed the operation size.")
                work[phase] += tonnes
                self.save_work(work)
            mode, url, token, generation = self.mode, self.url, self.token, self.generation
            body = {"id": self.member_id, "report": self.local()}
            if mode == "leader":
                self.core.bus.emit("party.work", body)
                self.publish()
        if mode == "member":
            try:
                shared = exchange(url, token, body)
                error = None
            except Exception:
                shared, error = None, "Delivery saved locally; waiting to reach the leader. Do not submit it again."
            with self.lock:
                if generation == self.generation:
                    if shared:
                        self.remote, self.last_success = shared, time.time()
                    self.error = error
                    self.publish()
        return self.core.store.get(NS)

    def start_worker(self):
        stop, generation = self.stop, self.generation

        def run():
            while not stop.wait(REPORT_SECONDS):
                with self.lock:
                    if generation != self.generation:
                        return
                    mode, url, token = self.mode, self.url, self.token
                if mode == "member":
                    try:
                        shared = exchange(url, token, {"id": self.member_id, "report": self.local()})
                        error = None
                    except Exception:
                        shared, error = None, "Leader unavailable. Retrying; last reports may be stale."
                    with self.lock:
                        if generation != self.generation:
                            return
                        self.error = error
                        if shared:
                            self.remote, self.last_success = shared, time.time()
                self.publish()

        threading.Thread(target=run, name="party-reporter", daemon=True).start()


def setup(core, module):
    party = Party(core)
    module.party = party
    core.http.route("/api/party", lambda q: core.store.get(NS), tool="get_hauling_party", module=module.name,
        description="Local hauling party status, commander cargo/location and telemetry (shield up/down, fuel, flight mode, alerts, last-reported hull), observation timestamps and shared leader plan. Party codes appear only on the leader's local dashboard.")
    core.http.route("/api/party/host", party.host, method="POST", tool="host_hauling_party", module=module.name,
        description="Start an opt-in private LAN/tailnet party listener, separate from the dashboard. Returns a random party code. Members share location, ship, cargo and status telemetry; restart or Leave stops sharing.",
        params={"port": {"type": "integer", "default": 8767}, "bind": {"type": "string", "default": "0.0.0.0", "description": "Local IPv4 address to listen on; use your Tailscale IPv4 to restrict the listener to the tailnet."}})
    core.http.route("/api/party/join", party.join, method="POST", tool="join_hauling_party", module=module.name,
        description="Connect this EliteLab to a leader over LAN/Tailscale. Reports commander name, location, ship, cargo and status telemetry every second until Leave or shutdown; never sends credits or the full journal. Shields are up/down; hull is last-reported, not continuous.",
        params={"url": {"type": "string", "required": True}, "code": {"type": "string", "required": True}})
    core.http.route("/api/party/work", party.report_work, method="POST", tool="report_hauling_work", module=module.name,
        description="Set your crew activity (ready/hauling/away) or add actually delivered tonnes for the current shared operation id. Cumulative local totals survive reconnect/restart and are retried without double counting. Delivery reports do not change physical inventory.",
        params={"activity": {"type": "string"}, "id": {"type": "string"}, "tonnes": {"type": "integer"}})
    core.http.route("/api/party/leave", party.leave, method="POST", tool="leave_hauling_party", module=module.name,
        description="Stop sharing immediately. Members leave the party; leaders close the listener and invalidate its code. Saved trade plans remain.")
