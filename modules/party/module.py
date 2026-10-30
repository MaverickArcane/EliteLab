"""Opt-in, scoped LAN transport. The main dashboard never needs a network bind.

Only telemetry and the leader's trade plan cross this listener. Party codes and
connections live in memory; restart or Leave stops sharing. No journal uploads.
"""
import copy
from datetime import datetime, timezone
import hmac
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler
from elitelab.core.http import ExclusiveHTTPServer
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
from modules.party.desk import project
from modules.party.recovery import deliveries, phase_at, seconds
from elitelab.core.hauling import view as workload_view

NS = "party"
STALE_SECONDS = 30
REPORT_SECONDS = 1
MAX_MEMBERS = 32
MAX_BODY = 64000
CLOSE_GRACE_SECONDS = 3


class PartyClosed(ValueError):
    """A terminal room response, distinct from a temporary network failure."""


class PartyCodeRejected(PartyClosed):
    pass


class LeaderRejected(ValueError):
    """The leader answered 400 with its own reason; repeated ones end the membership."""


class LeaderUnreadable(ValueError):
    """A 200 response that this version cannot render; never adopted as shared state."""


REJECTIONS_BEFORE_LEAVING = 3


def leader_error(data):
    """The leader's plain-text reason for a 400, bounded and printable, or None."""
    try:
        text = json.loads(data).get("error")
    except (ValueError, AttributeError):
        return None
    if not isinstance(text, str):
        return None
    text = "".join(c for c in text if c.isprintable()).strip()
    return text[:200] or None


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clean_text(value, limit=160):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("Invalid report text.")
    return value


def amount(value, maximum=1000000):
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("Invalid cargo amount.")
    return value


def hex_token(value):
    return isinstance(value, str) and len(value) == 32 and all(c in "0123456789abcdef" for c in value)


def job_number(value):
    return value is None or (type(value) in (int, float) and math.isfinite(value))


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
        out["work"] = {"operation_id": work["operation_id"], "loading": amount(work.get("loading", 0), 1000000000), "unloading": amount(work.get("unloading", 0), 1000000000)}
        if any(out["work"][k] is None for k in ("loading", "unloading")):
            raise ValueError("Delivery totals must be whole numbers.")
        entry = work.get("last_entry")
        if entry is not None:
            if not isinstance(entry, dict) or entry.get("kind") not in ("manual", "MarketSell", "CargoTransfer") or entry.get("phase") not in ("loading", "unloading"):
                raise ValueError("Invalid delivery evidence.")
            out["work"]["last_entry"] = {"kind":entry["kind"], "phase":entry["phase"],
                                         "tonnes":amount(entry.get("tonnes")), "at":clean_text(entry.get("at"))}
        evidence = work.get("delivery_evidence", {})
        if not isinstance(evidence, dict) or set(evidence) - {"loading", "unloading"}:
            raise ValueError("Invalid delivery timestamps.")
        if evidence:
            out["work"]["delivery_evidence"] = {}
            for phase, item in evidence.items():
                if not isinstance(item, dict) or item.get("kind") not in ("manual", "MarketSell", "CargoTransfer"):
                    raise ValueError("Invalid delivery evidence.")
                out["work"]["delivery_evidence"][phase] = {"kind":item["kind"], "at":clean_text(item.get("at")),
                                                         "tonnes":amount(item.get("tonnes"))}
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
        if response.status == 403:
            raise PartyCodeRejected("Party code rejected. Copy the current code from the leader; restarting or recreating a party changes it.")
        if response.status == 404:
            raise ValueError("No party listener at that address. Use the leader's party port (usually 8767), not the dashboard port.")
        reason = leader_error(data) if response.status == 400 else None
        if reason:
            raise LeaderRejected(reason)
        if response.status != 200:
            raise ValueError(f"Leader returned HTTP {response.status}. Check the party address and matching EliteLab versions.")
        if len(data) > 256000:
            raise ValueError("Party response too large.")
        result = json.loads(data)
        if not isinstance(result, dict) or not isinstance(result.get("members"), list):
            raise ValueError("Invalid party response.")
        if result.get("closed") is True:
            raise PartyClosed("The leader closed the party. Join again with a new invitation.")
        plan, operation = result.get("plan"), result.get("operation")
        if plan is not None and (not isinstance(plan, dict) or not job_number(plan.get("planned_quantity"))):
            raise ValueError("Invalid party response.")
        if operation is not None and (not isinstance(operation, dict) or not all(job_number(operation.get(k)) for k in ("quantity", "loaded", "unloaded"))):
            raise ValueError("Invalid party response.")
        return result
    finally:
        connection.close()


class Party:
    def __init__(self, core):
        self.core = core
        self.lock = threading.RLock()
        self.operations = threading.Lock()
        self.exchange_lock = threading.Lock()
        self.mode = "idle"
        self.token = ""
        saved = core.read_data("party-local.json", default={}) or {}
        identity = saved.get("id", "")
        self.member_id = identity if hex_token(identity) else secrets.token_hex(16)
        # The id is public to the room; the secret proves this client owns it.
        self.secret = saved.get("secret") if hex_token(saved.get("secret")) else secrets.token_hex(16)
        self.secrets = {}  # leader only: member id -> secret seen first
        self.activity = "ready"
        try:
            self.work = sanitize({"work": saved.get("work")}).get("work")
        except ValueError:
            self.work = None
        self.auto_seen = [v for v in saved.get("auto_seen", []) if isinstance(v, str) and len(v) == 64][-10000:]
        self.last_auto = saved.get("last_auto") if isinstance(saved.get("last_auto"), dict) else None
        self.receipts = saved.get("receipts", {}) if isinstance(saved.get("receipts"), dict) else {}
        self.tracking = saved.get("tracking") if isinstance(saved.get("tracking"), dict) else {}
        if seconds(self.tracking.get("since")) is None:
            self.tracking = {}
        self.recovery = {"running":False, "recovered":0, "error":None}
        self.recovery_key = None
        self.recovery_retry = 0
        self.replay_complete = False
        self.docked_market = None
        # Live journal deliveries queue their party-local.json snapshot for the
        # party-writer thread; everything else still writes synchronously.
        self.disk = threading.Condition()
        self.pending = []      # [(snapshot or None, follow-up callable or None)] in save order
        self.busy = False      # the writer holds a batch (disk write and follow-ups)
        self.writing = False   # the writer is inside write_data
        self.writer_thread = None
        self.rejections = 0
        self.save_work(self.work)
        self.members = {}
        self.remote = {}
        self.error = None
        self.url = ""
        self.server = None
        self.closing = False
        self.close_pending = set()
        self.close_acknowledged = threading.Event()
        self.stop = threading.Event()
        self.generation = 0
        self.last_success = None
        core.bus.on("journal.*", self.journal_delivery)
        core.bus.on("journal.replay.done", self.replay_done)
        core.bus.on("state.journal.location", lambda n, v: self.publish())
        core.bus.on("state.journal.status", lambda n, v: self.publish())
        core.bus.on("state.journal.game_running", lambda n, v: self.publish())
        core.bus.on("state.trade.job", self.refresh)
        core.bus.on("state.journal.cargo", self.refresh)
        core.bus.on("state.journal.cargo_capacity", self.refresh)
        self.publish()
        # The local receipt is written before the owner's operation ledger.
        # Reconcile that durable cumulative count after an interrupted second
        # write. Unrelated member jobs are ignored by the operation ID guard.
        if self.work:
            core.bus.emit("party.work", {"id": self.member_id, "report": self.local()})

    def refresh(self, name, value):
        # Trade publishes while holding its ledger lock; party reports acquire
        # those locks in the other order. Never wait here. The reporting thread
        # or the current holder's final publish supplies any skipped refresh.
        if self.lock.acquire(blocking=False):
            try:
                self.publish()
            finally:
                self.lock.release()

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
            job = self.core.store.get("trade", "job") or self.core.store.get("trade")
            plan, operation = job.get("plan"), job.get("operation")
            workload = workload_view(job.get("workload"), operation, members, plan) if plan else None
            suggestion = recommend(plan, operation, members, (job.get("calculation") or {}).get("to_haul"), workload)
            if suggestion and self.recovery["running"]:
                suggestion.update(enabled=False,next_buy=0)
                for row in suggestion["members"]:
                    row["next_buy"] = 0
            if workload and suggestion:
                pickups = {r["id"]:r["next_buy"] for r in suggestion["members"]}
                for row in workload["members"]:
                    row["next_pickup"] = pickups.get(row["id"],0)
                    row["pickup_phase"] = suggestion["phase"]
            return {"members": members, "plan": plan, "operation": operation, "workload": workload, "load_suggestion": suggestion,
                    "recovering":self.recovery["running"], "carrier": self.core.store.get("journal", "carrier"), "leader": self.local().get("cmdr"), "updated_at": utc()}

    def publish(self):
        with self.lock:
            shared = self.shared() if self.mode != "member" else copy.deepcopy(self.remote)
            op = shared.get("operation") or {}
            if (op.get("stage") in ("loading", "transit", "unloading") and op.get("id") and op.get("id") != self.tracking.get("operation_id")
                    and not (self.mode == "idle" and self.tracking and not self.tracking.get("owner"))):
                self.save_work(self.work, tracking={"operation_id":op["id"], "since":utc(),
                                                   "owner":self.mode != "member", "manual_through":{}})
            stale = self.mode == "member" and (self.last_success is None or time.time() - self.last_success > STALE_SECONDS)
            if stale:
                for member in shared.get("members", []):
                    member["stale"] = True
            self.core.store.update(NS, {"mode": self.mode, "code": self.token if self.mode == "leader" else None,
                "port": self.server.server_port if self.server else None, "url": self.url, "error": self.error,
                "members": shared.get("members", []), "plan": shared.get("plan"), "stale": stale, "closing": self.closing,
                "operation": shared.get("operation"), "carrier": shared.get("carrier"), "activity": self.activity, "work": copy.deepcopy(self.work),
                "workload": shared.get("workload"),
                "recovery": copy.deepcopy(self.recovery),
                "load_suggestion": None if stale else shared.get("load_suggestion"),
                "auto_tracking": {"loading": bool((shared.get("plan") or {}).get("carrier_market_id")), "unloading": bool((shared.get("plan") or {}).get("destination_market_id"))}, "last_auto_delivery": copy.deepcopy(self.last_auto),
                "updated_at": shared.get("updated_at"), "local_id": self.member_id,
                "desk": project({**shared,"recovering":self.recovery["running"] or shared.get("recovering",False)}, self.member_id, self.local(), self.work, stale)})

    def replay_done(self, name, value):
        self.replay_complete = True
        self.schedule_recovery()

    def schedule_recovery(self):
        with self.lock:
            if self.core.watcher.is_alive() and not self.replay_complete:
                return
            if self.mode == "idle" and self.tracking and not self.tracking.get("owner"):
                return  # Rejoin before trusting a former leader's job context.
            if self.mode == "member" and (self.last_success is None or time.time() - self.last_success > STALE_SECONDS):
                return  # Confirm that the leader still has this job before catch-up.
            shared = self.remote if self.mode == "member" else self.shared()
            op = shared.get("operation") or {}
            key = (self.generation, op.get("id"), op.get("stage"))
            if (op.get("id") != self.tracking.get("operation_id") or not op.get("id")
                    or op.get("stage") not in ("loading", "transit", "unloading", "complete")
                    or self.recovery["running"] or key == self.recovery_key or time.monotonic() < self.recovery_retry):
                return
            self.recovery_key = key
            self.recovery = {"running":True,"recovered":0,"error":None}
            directory, since = self.core.config.JOURNAL_DIR, self.tracking["since"]
            self.publish()

        def run():
            count, error = 0, None
            try:
                if len(self.auto_seen) >= 10000:
                    raise ValueError("Delivery history is full; check missed deliveries manually.")
                if op["stage"] in ("unloading", "complete") and not (op.get("phase_started_at") or {}).get("unloading"):
                    raise ValueError("This older job has no saved unloading start time; check missed deliveries manually.")
                for event, market in deliveries(directory, since):
                    with self.lock:
                        if self.generation != key[0] or self.tracking.get("operation_id") != key[1]:
                            break
                        count += self.journal_delivery("journal."+event["event"], event, recovering=True, recovered_market=market) or 0
            except (OSError, ValueError) as ex:
                error = "Could not finish delivery catch-up: " + str(ex)
            finally:
                with self.lock:
                    changed = self.generation != key[0] or self.tracking.get("operation_id") != key[1]
                    self.recovery = {"running":False,"recovered":0 if changed else count,"error":None if changed else error}
                    if changed:
                        self.recovery_key, self.recovery_retry = None, 0
                    elif error:
                        self.recovery_key = None
                        self.recovery_retry = time.monotonic()+30
                    self.publish()
        threading.Thread(target=run, name="party-journal-recovery", daemon=True).start()

    def receive(self, body):
        if not isinstance(body, dict):
            raise ValueError("Report must be an object.")
        mid, secret = body.get("id"), body.get("secret")
        if not hex_token(mid) or mid == self.member_id or not hex_token(secret):
            raise ValueError("Invalid member identity.")
        report = sanitize(body.get("report", {}))
        with self.lock:
            bound = self.secrets.get(mid)
            if bound is not None and not hmac.compare_digest(bound, secret):
                raise ValueError("Member identity rejected: another commander already reports with this id.")
            if self.closing:
                # The final authenticated poll tells connected members to clear
                # the room before its listener disappears. Saved work is kept.
                self.close_pending.discard(mid)
                if not self.close_pending:
                    self.close_acknowledged.set()
                return {"closed": True, "members": [], "plan": None, "operation": None}
            if self.mode != "leader":
                raise ValueError("Party is closed.")
            self.shared()  # expire old reports before applying the membership limit
            if body.get("leave") is True:
                self.members.pop(mid, None)
            else:
                if mid not in self.members and len(self.members) >= MAX_MEMBERS - 1:
                    raise ValueError("Party is full.")
                self.secrets.setdefault(mid, secret)
                self.members[mid] = {**report, "last_seen": utc(), "received": time.time(), "leader": False}
            self.core.bus.emit("party.work", {"id": mid, "report": report})
            # Reconcile deliveries first, then let trade assign new crew using
            # this report's roster and cargo before replying with shared work.
            roster = self.shared()["members"]
            if body.get("leave") is True:
                roster.append({"id":mid, **report, "leader":False, "stale":True, "departed":True})
            self.core.bus.emit("party.roster", roster)
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
            closing_server = self.server if self.mode == "leader" else None
            if closing_server:
                self.closing = True
                self.stop.set()
                self.close_pending = {mid for mid, m in self.members.items()
                                      if time.time() - m["received"] <= STALE_SECONDS}
                self.close_acknowledged.clear()
                if not self.close_pending:
                    self.close_acknowledged.set()
                self.publish()
        if closing_server:
            # Allow one normal heartbeat plus headroom; never wait forever on
            # an offline or older client. Keep the current token valid only for
            # the terminal response, then release the listening port.
            self.close_acknowledged.wait(CLOSE_GRACE_SECONDS)
        with self.lock:
            old_mode, old_url, old_token = self.mode, self.url, self.token
            final_report = self.local() if old_mode == "member" else None
            self.stop.set()
            self.generation += 1
            server, self.server = self.server, None
            self.mode, self.token, self.url = "idle", "", ""
            self.closing = False
            self.close_pending.clear()
            self.members, self.remote, self.error = {}, {}, None
            self.secrets = {}
            self.last_success, self.rejections = None, 0
            self.publish()
        if server:
            server.shutdown()
            server.server_close()
        if old_mode == "member":
            try:
                # Finish any in-flight report before Leave, so it cannot re-add
                # this commander to the leader after the departure request.
                with self.exchange_lock:
                    exchange(old_url, old_token, {"id": self.member_id, "secret": self.secret, "leave": True, "report": final_report})
            except (OSError, ValueError, http.client.HTTPException):
                pass  # the leader expires this report if it could not be removed

    def leave(self, q=None):
        with self.operations:
            self._leave()
        self.flush()  # Leave and shutdown both land queued receipts and their ledger follow-ups.
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
                    server = ExclusiveHTTPServer((bind, port), self.handler())
                except OSError:
                    raise ValueError("Could not listen on that address and port. Check the address or choose another port.") from None
                self.server, self.mode, self.token = server, "leader", secrets.token_urlsafe(24)
                self.stop = threading.Event()
                self.error = None
                self.generation += 1
                threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), name="party-listener", daemon=True).start()
                self.start_worker()
                self.publish()
        return self.core.store.get(NS)

    def join(self, q):
        url, token = q.get("url", ""), q.get("code", "")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("Enter the leader's party address.")
        if not isinstance(token, str) or not token.strip():
            raise ValueError("Enter the party code copied from the leader.")
        url, token = url.strip(), token.strip()
        if "://" not in url:
            url = "http://" + url
        if len(url) > 240:
            raise ValueError("The party address is too long. Use the leader's LAN/Tailscale address and party port.")
        if not 16 <= len(token) <= 128 or not token.isascii() or any(not (c.isalnum() or c in "-_") for c in token):
            raise ValueError("Invalid party code format. Copy the complete code without quotes or spaces inside it.")
        with self.operations:
            with self.lock:
                if self.mode != "idle":
                    raise ValueError("Leave the current party first.")
            try:
                shared = self.check(exchange(url, token, {"id": self.member_id, "secret": self.secret, "report": self.local()}))
            except (OSError, http.client.HTTPException):
                raise ValueError("Could not reach the leader. Check Tailscale, the address, port and firewall.") from None
            with self.lock:
                self.mode, self.url, self.token = "member", url, token
                self.remote, self.error, self.last_success = shared, None, time.time()
                self.rejections = 0
                self.stop = threading.Event()
                self.generation += 1
                self.start_worker()
                self.publish()
        return self.core.store.get(NS)

    def save_work(self, work, seen=None, last_auto=None, receipts=None, tracking=None, *, deferred=False):
        """Persist the local receipt. Callers never mutate the saved objects in
        place, so a deferred snapshot can share them with the live state."""
        seen = self.auto_seen if seen is None else seen
        last_auto = self.last_auto if last_auto is None else last_auto
        receipts = self.receipts if receipts is None else receipts
        tracking = self.tracking if tracking is None else tracking
        snapshot = {"id": self.member_id, "secret": self.secret, "work": work, "auto_seen": seen, "last_auto": last_auto, "receipts": receipts,
                    "tracking":tracking}
        if deferred:
            self.work, self.auto_seen, self.last_auto, self.receipts, self.tracking = work, seen, last_auto, receipts, tracking
            self.queue_write(snapshot, None)
            return
        with self.disk:
            # This newer snapshot supersedes queued ones; only an in-flight disk
            # write must finish first, and it never needs the party lock.
            superseded, self.pending = self.pending, []
            self.disk.wait_for(lambda: not self.writing)
        try:
            self.core.write_data(snapshot, "party-local.json")
        except BaseException:
            with self.disk:
                self.pending = superseded + self.pending
                self.disk.notify_all()
            raise
        self.work, self.auto_seen, self.last_auto = work, seen, last_auto
        self.receipts = receipts
        self.tracking = tracking
        for _, after in superseded:
            if after:
                after()

    def queue_write(self, snapshot, after):
        with self.disk:
            self.pending.append((snapshot, after))
            if self.writer_thread is None:
                self.writer_thread = threading.Thread(target=self.writer, name="party-writer", daemon=True)
                self.writer_thread.start()
            self.disk.notify_all()

    def after_write(self, callback):
        """Run callback on the writer thread once every snapshot queued so far is on disk."""
        self.queue_write(None, callback)

    def writer(self):
        while True:
            with self.disk:
                while not self.pending:
                    self.disk.wait()
                batch, self.pending = self.pending, []
                self.busy = True
            snapshot = next((s for s, _ in reversed(batch) if s is not None), None)
            failure = None
            if snapshot is not None:
                with self.disk:
                    self.writing = True
                try:
                    self.core.write_data(snapshot, "party-local.json")
                except Exception as ex:
                    failure = ex
                finally:
                    with self.disk:
                        self.writing = False
                        self.disk.notify_all()
            try:
                if failure is not None:
                    # Memory already holds the delivery; the next snapshot or a
                    # journal catch-up after restart recovers the missing write.
                    with self.lock:
                        self.error = "Could not save party-local.json: " + str(failure)[:160]
                        self.publish()
                for _, after in batch:
                    if after:
                        try:
                            after()
                        except Exception:
                            self.core.log.exception("party-local.json follow-up failed")
            finally:
                with self.disk:
                    self.busy = False
                    self.disk.notify_all()

    def flush(self, timeout=10):
        """Wait until every queued party-local.json write and follow-up has run.
        Never call this while holding self.lock: follow-ups publish under it."""
        with self.disk:
            return self.disk.wait_for(lambda: not self.pending and not self.busy, timeout)

    def check(self, shared):
        """Render a leader snapshot before adopting it. A member without an id or
        a plan without a commodity would otherwise raise inside every publish."""
        try:
            project({**shared, "recovering": False}, self.member_id, self.local(), self.work, False)
        except Exception as ex:
            detail = f"{type(ex).__name__}: {str(ex)[:120]}"
            raise LeaderUnreadable(f"The leader sent an unreadable party update ({detail}). Check that both EliteLab versions match.") from ex
        return shared

    def journal_delivery(self, name, event, *, recovering=False, recovered_market=None):
        if not isinstance(event, dict):
            return
        kind = event.get("event")
        with self.lock:
            if not recovering and kind in ("Docked", "Location", "CarrierJump"):
                self.docked_market = event.get("MarketID") if kind == "Docked" or event.get("Docked") else None
            elif not recovering and kind in ("Undocked", "FSDJump", "LoadGame"):
                self.docked_market = None
            # Replays, cargo snapshots, buys and inventory drops are not new deliveries.
            if event.get("_replay") or kind not in ("MarketSell", "CargoTransfer"):
                return
            shared = self.shared() if self.mode != "member" else self.remote
            op, plan = shared.get("operation"), shared.get("plan")
            if not op or not plan or (not recovering and op["stage"] not in ("loading", "unloading")):
                return
            phase = phase_at(op,event,self.tracking,self.member_id) if recovering else op["stage"]
            if phase is None:
                return
            try:
                event_time = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).timestamp()
                start_time = datetime.fromisoformat(op["started_at"].replace("Z", "+00:00")).timestamp()
                if event_time < int(start_time):
                    return
            except (KeyError, ValueError, TypeError, AttributeError):
                return
            market = plan.get("carrier_market_id" if phase == "loading" else "destination_market_id")
            if not market:
                return
            commodity = norm(plan["commodity"])
            tonnes = 0
            if kind == "MarketSell" and event.get("MarketID") == market and norm(event.get("Type")) == commodity:
                count = event.get("Count")
                tonnes = count if type(count) is int and count > 0 else 0
            elif kind == "CargoTransfer" and phase == "loading" and (recovered_market if recovering else self.docked_market) == market:
                tonnes = sum(t["Count"] for t in event.get("Transfers", []) if isinstance(t, dict)
                             and t.get("Direction") == "tocarrier" and norm(t.get("Type")) == commodity
                             and type(t.get("Count")) is int and t["Count"] > 0)
            if not tonnes:
                return
            digest = hashlib.sha256(json.dumps({k:v for k,v in event.items() if not k.startswith("_")}, sort_keys=True).encode()).hexdigest()
            if digest in self.auto_seen:
                return
            if recovering and len(self.auto_seen) >= 10000:
                raise ValueError("Delivery history is full; check missed deliveries manually.")
            work = copy.deepcopy(self.work) if self.work and self.work["operation_id"] == op["id"] else {"operation_id":op["id"], "loading":0, "unloading":0}
            # Keep observed evidence even if this client's view predates an
            # owner correction. The leader validates credited totals; a report
            # above the target stays pending until the owner reconciles it.
            if work[phase] + tonnes > 1000000000:
                self.error = "Journal delivery counter is out of range. Check the operation and manual entries."
                self.publish()
                return
            work[phase] += tonnes
            work["last_entry"] = {"kind":kind, "phase":phase, "tonnes":tonnes, "at":event["timestamp"]}
            work.setdefault("delivery_evidence", {})[phase] = {"kind":kind,"at":event["timestamp"],"tonnes":tonnes}
            # Live events run on the watcher thread: queue the receipt for the
            # writer. Journal catch-up runs on its own thread and writes directly.
            self.save_work(work, (self.auto_seen + [digest])[-10000:], {"operation_id":op["id"],"phase":phase,"tonnes":tonnes,"at":event["timestamp"]},
                           deferred=not recovering)
            if not recovering:
                self.activity = "hauling"
            if self.mode != "member":
                body = {"id":self.member_id,"report":self.local()}
                if recovering:
                    self.core.bus.emit("party.work", body)
                else:
                    # The local receipt reaches disk before the owner's ledger
                    # learns of it, so a restart always finds the cumulative work.
                    self.after_write(lambda: (self.core.bus.emit("party.work", body), self.publish()))
            # No network I/O on the watcher thread: the heartbeat sends cumulative totals.
            self.publish()
            return tonnes

    def report_work(self, q):
        with self.lock:
            if "activity" in q:
                self.activity = sanitize({"activity": q["activity"]})["activity"]
            if "tonnes" in q:
                request_id = q.get("request_id")
                if request_id is not None and (not isinstance(request_id, str) or not 16 <= len(request_id) <= 80):
                    raise ValueError("Invalid delivery request id.")
                receipt = self.receipts.get(request_id) if request_id else None
                if self.recovery["running"] and not receipt:
                    raise ValueError("Wait for journal catch-up to finish before recording a missed delivery.")
                if receipt and (receipt["operation_id"] != q.get("id") or receipt["tonnes"] != q["tonnes"] or (q.get("phase") and receipt["phase"] != q["phase"])):
                    raise ValueError("This delivery request was already used for a different report.")
                op = self.shared().get("operation") if self.mode != "member" else self.remote.get("operation")
                if not receipt and (not op or op["id"] != q.get("id") or op["stage"] not in ("loading", "unloading")
                        or (q.get("phase") and q["phase"] != op["stage"])
                        or (self.mode == "member" and (self.last_success is None or time.time() - self.last_success > STALE_SECONDS))):
                    raise ValueError("Refresh the current active loading/unloading job before reporting a delivery.")
                tonnes = amount(q["tonnes"])
                if not tonnes:
                    raise ValueError("Enter the tonnes you actually delivered.")
                if not receipt:
                    work = copy.deepcopy(self.work) if self.work and self.work["operation_id"] == op["id"] else {"operation_id": op["id"], "loading": 0, "unloading": 0}
                    phase = op["stage"]
                    adjustment = op.get("reports", {}).get(self.member_id, {}).get("adjustments", {}).get(phase, 0)
                    if work[phase] + tonnes > 1000000000 or work[phase] + tonnes + adjustment > op["quantity"]:
                        raise ValueError("Your reported deliveries exceed the operation size.")
                    work[phase] += tonnes
                    work["last_entry"] = {"kind":"manual", "phase":phase, "tonnes":tonnes, "at":utc()}
                    work.setdefault("delivery_evidence", {})[phase] = {"kind":"manual","at":work["last_entry"]["at"],"tonnes":tonnes}
                    receipts = dict(self.receipts)
                    if request_id:
                        if len(receipts) >= 10000:
                            raise ValueError("Manual report history is full. Use automatic journal tracking.")
                        receipts[request_id] = {"operation_id": op["id"], "phase": phase, "tonnes": tonnes}
                    tracking = copy.deepcopy(self.tracking)
                    if tracking.get("operation_id") == op["id"]:
                        tracking.setdefault("manual_through", {})[phase] = work["last_entry"]["at"]
                    self.save_work(work, receipts=receipts, tracking=tracking)
            mode, generation = self.mode, self.generation
            body = {"id": self.member_id, "report": self.local()}
            if mode != "member":
                self.core.bus.emit("party.work", body)
                self.publish()
        if mode == "member":
            self.synchronize(generation, "Delivery saved locally; waiting to reach the leader. Do not submit it again.")
        return self.core.store.get(NS)

    def synchronize(self, generation, failure_message):
        # Serialize the request AND its application. A delayed heartbeat must
        # never replace a newer manual acknowledgement or operation stage.
        # Take the snapshot after acquiring the exchange lock, so queued sends
        # contain current cumulative work and cargo. Never hold the party lock
        # during network I/O; journal events must remain responsive.
        with self.exchange_lock:
            # Queued journal receipts reach disk before the leader learns of them.
            self.flush()
            with self.lock:
                if generation != self.generation or self.mode != "member":
                    return
                url, token = self.url, self.token
                body = {"id": self.member_id, "secret": self.secret, "report": self.local()}
            terminal, rejected = False, False
            try:
                shared = self.check(exchange(url, token, body))
                error = None
            except PartyClosed as ex:
                shared, terminal = None, True
                error = ("The party invitation is no longer valid. The leader may have closed or recreated it. Join with the current invitation."
                         if isinstance(ex, PartyCodeRejected) else str(ex))
            except LeaderRejected as ex:
                # The leader's own reason, not "unavailable"; persistent rejections end the membership.
                shared, rejected, error = None, True, str(ex)
                if self.rejections + 1 >= REJECTIONS_BEFORE_LEAVING:
                    terminal = True
                    error += " Left the party after repeated rejections. Fix the cause, then join again."
            except LeaderUnreadable as ex:
                # Kept out of the shared state; the heartbeat continues and the UI says why.
                shared, error = None, str(ex)
            except Exception:
                shared, error = None, failure_message
            with self.lock:
                if generation == self.generation:
                    self.rejections = self.rejections + 1 if rejected else 0
                    if terminal:
                        self.stop.set()
                        self.generation += 1
                        self.mode, self.url, self.token = "idle", "", ""
                        self.remote, self.members, self.last_success = {}, {}, None
                    elif shared:
                        self.remote, self.last_success = shared, time.time()
                    self.error = error
                    self.publish()
        self.schedule_recovery()

    def start_worker(self):
        stop, generation = self.stop, self.generation

        def run():
            while not stop.wait(REPORT_SECONDS):
                with self.lock:
                    if generation != self.generation:
                        return
                    mode = self.mode
                if mode == "member":
                    self.synchronize(generation, "Leader unavailable. Retrying; last reports may be stale.")
                else:
                    with self.lock:
                        if self.mode == "leader":
                            self.core.bus.emit("party.roster", self.shared()["members"])
                        self.publish()
                    self.schedule_recovery()

        threading.Thread(target=run, name="party-reporter", daemon=True).start()


def setup(core, module):
    party = Party(core)
    module.party = party
    core.shutdown_callbacks.append(party.leave)
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
        params={"activity": {"type": "string"}, "id": {"type": "string"}, "tonnes": {"type": "integer"},
                "phase": {"type": "string", "description": "Expected loading/unloading phase; rejects a stale form after a stage change."},
                "request_id": {"type": "string", "description": "Unique delivery request id, retained on retries to prevent duplicate manual reports."}})
    core.http.route("/api/party/leave", party.leave, method="POST", tool="leave_hauling_party", module=module.name,
        description="Stop sharing immediately. Members leave the party; leaders close the listener and invalidate its code. Saved trade plans remain.")
