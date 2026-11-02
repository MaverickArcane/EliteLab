"""Rebuildable SQLite cache of selected journal evidence, never raw journals.

Records use (source filename, byte offset), preserving legitimate same-second
events. Changed files are checked against the consumed-prefix SHA256 before
appending; rewritten/truncated files are replaced transactionally.
"""
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import threading
import time

from elitelab.core.gamedata import norm

MAX_LINE = 1024 * 1024
BATCH_BYTES = 8 * 1024 * 1024
MAX_FILES = 20000
WEEK = 7 * 86400
# Existing EliteLab cycle convention: Thursday 07:00 UTC.
CYCLE_ORIGIN = 7 * 3600


def text(value):
    return value.strip()[:160] if isinstance(value, str) else ""


def number(value, maximum=10**15):
    if type(value) not in (int, float):
        return None
    try:
        return value if math.isfinite(value) and 0 <= value <= maximum else None
    except OverflowError:
        return None


def timestamp(value):
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (AttributeError, TypeError, ValueError, OverflowError, OSError):
        return None


def iso(value):
    return dt.datetime.fromtimestamp(value, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def context():
    return {"commander":"unknown", "display":"Unidentified records", "system":"", "body":"", "power":"", "discard":False}


def fold(ev, ctx):
    """Bounded context and one optional normalized record per input line."""
    event = ev.get("event")
    if not isinstance(event, str):
        return None
    if event in ("Commander", "LoadGame"):
        name = text(ev.get("Name" if event == "Commander" else "Commander"))
        fid = text(ev.get("FID"))
        who = "fid:" + fid if fid else "name:" + name if name else "unknown"
        if event == "LoadGame" or who != ctx["commander"]:
            ctx.update(context())
        ctx.update(commander=who, display=name or fid or "Unidentified records")
    if event in ("Location", "FSDJump", "CarrierJump"):
        ctx.update(system=text(ev.get("StarSystem")), body="")
    if event == "Docked" and text(ev.get("StarSystem")):
        if ctx["system"] != text(ev.get("StarSystem")):
            ctx.update(system=text(ev.get("StarSystem")), body="")
    if event in ("ApproachBody", "Touchdown", "SupercruiseExit"):
        ctx["body"] = text(ev.get("Body"))
    if event in ("SupercruiseEntry", "LeaveBody"):
        ctx["body"] = ""
    if event in ("Powerplay", "PowerplayJoin"):
        ctx["power"] = text(ev.get("Power"))
    elif event == "PowerplayDefect":
        ctx["power"] = text(ev.get("ToPower"))
    elif event == "PowerplayLeave":
        ctx["power"] = ""
    ts = timestamp(ev.get("timestamp"))
    if ts is None:
        return None
    row = {"kind":"", "ts":ts, "stamp":iso(ts), "commander":ctx["commander"], "display":ctx["display"],
           "system":ctx["system"], "body":ctx["body"], "item":"", "label":"", "category":"",
           "power":ctx["power"], "amount":0, "x":None, "y":None, "z":None, "event":event, "star_class":""}
    if event == "LoadGame" and number(ev.get("Credits")) is not None:
        row.update(kind="credits", amount=ev["Credits"])
    elif event == "PowerplayMerits":
        n = number(ev.get("MeritsGained"), 10**12)
        if n is None or n != int(n):
            return None
        row.update(kind="merits", amount=n, power=text(ev.get("Power")) or ctx["power"],
                   item=iso(CYCLE_ORIGIN + math.floor((ts - CYCLE_ORIGIN) / WEEK) * WEEK))
    elif event == "MaterialCollected":
        n, item = number(ev.get("Count"), 1000000), norm(text(ev.get("Name")))
        if not item or n is None or n != int(n) or n == 0:
            return None
        row.update(kind="material", amount=n, item=item, label=text(ev.get("Name_Localised")) or text(ev.get("Name")), category=text(ev.get("Category")))
    elif event in ("Location", "FSDJump", "CarrierJump"):
        pos = ev.get("StarPos")
        if not row["system"] or not isinstance(pos, list) or len(pos) != 3 or not all(type(n) in (int,float) and number(abs(n),1000000) is not None for n in pos):
            return None
        row.update(kind="travel", x=pos[0], y=pos[1], z=pos[2], amount=number(ev.get("JumpDist")) or 0)
    elif event == "StartJump" and ev.get("JumpType", "Hyperspace") == "Hyperspace" and text(ev.get("StarSystem")):
        row.update(kind="class", system=text(ev["StarSystem"]), star_class=text(ev.get("StarClass")))
    else:
        return None
    return row


class JournalIndex:
    def __init__(self, core):
        self.core = core
        # Capture paths per instance; requests cannot select arbitrary files.
        self.directory = Path(core.config.JOURNAL_DIR).resolve()
        self.path = Path(core.data_path("history.sqlite3"))
        self.lock = threading.RLock()
        self.last = {}

    def connect(self):
        if self.path.is_symlink():
            raise ValueError("Journal index path must not be a symbolic link.")
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                db.close()
                raise ValueError("Journal index version is unsupported; rebuild the cache with this app version.")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS files(name TEXT PRIMARY KEY, size INTEGER, mtime INTEGER,
                    offset INTEGER, digest TEXT, context TEXT, skipped INTEGER, waiting INTEGER);
                CREATE TABLE IF NOT EXISTS records(file TEXT REFERENCES files(name) ON DELETE CASCADE,
                    offset INTEGER, kind TEXT, ts REAL, stamp TEXT, commander TEXT, display TEXT,
                    system TEXT, body TEXT, item TEXT, label TEXT, category TEXT, power TEXT, amount REAL,
                    x REAL, y REAL, z REAL, event TEXT, star_class TEXT, PRIMARY KEY(file,offset));
                CREATE INDEX IF NOT EXISTS history_filter ON records(commander,kind,ts);
                CREATE INDEX IF NOT EXISTS history_time ON records(kind,ts);
                PRAGMA user_version=1;
            """)
            source = str(self.directory)
            previous = db.execute("SELECT value FROM meta WHERE key='source'").fetchone()
            if previous is None or previous[0] != source:
                with db:
                    db.execute("DELETE FROM files")
                    db.execute("INSERT OR REPLACE INTO meta VALUES('source',?)", (source,))
            return db
        except Exception:
            db.close()
            raise

    def refresh(self, rebuild=False):
        with self.lock:
            try:
                if rebuild and self.path.exists():
                    if self.path.is_symlink():
                        raise ValueError("Journal index path must not be a symbolic link.")
                    # Keep the old derived cache for diagnosis, including corrupt DBs.
                    backup = self.path.with_name("history.sqlite3.backup-" + str(time.time_ns()))
                    os.replace(self.path, backup)
                return self._refresh()
            except (sqlite3.Error, OSError) as exc:
                self.core.log.warning("Journal index unavailable: %s", type(exc).__name__)
                raise ValueError("Journal index unavailable. Check the journal/data folders or rebuild the cache.") from None

    def _refresh(self):
        # No journal I/O occurs in a bus handler. Parsing is batched per request;
        # clients repeat while pending, serving already indexed results meanwhile.
        with os.scandir(self.directory) as entries:
            paths = sorted((Path(e.path) for e in entries if e.name.startswith("Journal.") and e.name.endswith(".log") and e.is_file(follow_symlinks=False)), key=lambda p:p.name)
        excluded = max(0, len(paths) - MAX_FILES)
        paths = paths[-MAX_FILES:]
        db = self.connect()
        scanned, pending, errors, changed, bytes_read = 0, 0, 0, 0, 0
        try:
            with db:
                names = {p.name for p in paths}
                for row in db.execute("SELECT name FROM files").fetchall():
                    if row[0] not in names:
                        db.execute("DELETE FROM files WHERE name=?", (row[0],)); changed += 1
                for path in paths:
                    old = db.execute("SELECT * FROM files WHERE name=?", (path.name,)).fetchone()
                    try:
                        stat = path.stat()
                        same = old is not None and old["size"] == stat.st_size and old["mtime"] == stat.st_mtime_ns
                        if same and (old["offset"] == stat.st_size or old["waiting"]):
                            continue
                        if bytes_read >= BATCH_BYTES:
                            pending += 1
                            continue
                        offset, ctx, skipped = (old["offset"], json.loads(old["context"]), old["skipped"]) if old else (0, context(), 0)
                        digest = hashlib.sha256()
                        with path.open("rb") as stream:
                            # Verify ALL consumed bytes on a changed file, not just
                            # its ends: edits in the middle must invalidate cached data.
                            left = offset
                            while left:
                                block = stream.read(min(MAX_LINE,left))
                                if not block: break
                                digest.update(block); left -= len(block)
                            if old and (left or digest.hexdigest() != old["digest"] or (not same and stat.st_size <= old["size"])):
                                db.execute("DELETE FROM files WHERE name=?", (path.name,))
                                offset, ctx, skipped, digest = 0, context(), 0, hashlib.sha256()
                                stream.seek(0)
                            db.execute("INSERT OR IGNORE INTO files VALUES(?,?,?,?,?,?,?,?)", (path.name,0,0,0,"",json.dumps(ctx),0,0))
                            waiting = False
                            while bytes_read < BATCH_BYTES:
                                start = offset
                                line = stream.readline(MAX_LINE + 1)
                                if not line: break
                                if len(line) <= MAX_LINE and not line.endswith(b"\n"):
                                    waiting = True
                                    break  # leave an in-progress final record for the next append
                                digest.update(line); offset += len(line); bytes_read += len(line)
                                if ctx.get("discard"):
                                    ctx["discard"] = not line.endswith(b"\n")
                                    continue
                                if len(line) > MAX_LINE:
                                    skipped += 1; ctx = context(); ctx["discard"] = not line.endswith(b"\n")
                                    continue
                                try:
                                    ev = json.loads(line)
                                    if not isinstance(ev, dict): raise ValueError()
                                    row = fold(ev, ctx)
                                except (ValueError, TypeError, OverflowError, RecursionError, OSError):
                                    skipped += 1
                                    ctx = context()
                                    continue
                                if row:
                                    columns = list(row)
                                    db.execute("INSERT OR REPLACE INTO records(file,offset," + ",".join(columns) + ") VALUES(" + ",".join("?" for _ in range(len(columns)+2)) + ")", (path.name,start,*row.values()))
                            db.execute("UPDATE files SET size=?,mtime=?,offset=?,digest=?,context=?,skipped=?,waiting=? WHERE name=?", (stat.st_size,stat.st_mtime_ns,offset,digest.hexdigest(),json.dumps(ctx),skipped,int(waiting),path.name))
                            if offset < stat.st_size and not waiting: pending += 1
                        scanned += 1; changed += 1
                    except OSError:
                        errors += 1
                counts = db.execute("SELECT COUNT(*),COALESCE(SUM(skipped),0),COALESCE(SUM(waiting),0) FROM files").fetchone()
                records = db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
                unknown = db.execute("SELECT COUNT(*) FROM records WHERE commander='unknown'").fetchone()[0]
            self.last = {"files":counts[0], "records":records, "unidentified_records":unknown, "skipped_lines":counts[1],
                         "waiting_files":counts[2], "pending_files":pending, "unreadable_files":errors, "excluded_files":excluded,
                         "files_read":scanned, "bytes_parsed":bytes_read, "changed_files":changed, "updated_at":iso(time.time()),
                         "note":"Local derived cache. Partial final lines wait for completion; duplicate copies of journals count separately. Unidentified records are separate. Original journals are never changed."}
            self.core.store.set("history", "index", self.last)
            return dict(self.last)
        finally:
            db.close()

    def query(self, sql, params=()):
        # Callers hold lock around refresh+queries. SQL is fixed by this module;
        # every external value is bound separately.
        db = self.connect()
        try:
            return [dict(row) for row in db.execute(sql, params)]
        finally:
            db.close()
