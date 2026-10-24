"""Journal tailer.

On start it replays the most recent journal files so modules can rebuild
state, then follows the newest file for new lines and watches the snapshot
files (Status.json, Cargo.json, ...) for changes. Everything is emitted on the
bus:

    journal.<Event>           one journal line (payload: the event dict; ``_replay`` True during replay)
    journal.replay.done       replay finished (payload: number of events replayed)
    journal.file.<Name>       a snapshot file changed (payload: parsed JSON, or None if unreadable)
"""
import glob
import json
import logging
import os
import threading
import time

from . import config

log = logging.getLogger("elitelab.watcher")
SNAPSHOT_FILES = ["Status", "Cargo", "Market", "ModulesInfo", "ShipLocker", "Backpack", "NavRoute", "Shipyard", "Outfitting"]


def journal_files(newest_first=False):
    files = glob.glob(os.path.join(config.JOURNAL_DIR, "Journal.*.log"))
    files.sort(key=os.path.getmtime, reverse=newest_first)
    return files


class JournalWatcher(threading.Thread):
    def __init__(self, bus):
        super().__init__(name="journal-watcher", daemon=True)
        self.bus = bus
        self._stop = threading.Event()
        self._file = None
        self._offset = 0
        self._snap_mtime = {}
        self.replayed = 0

    # -- replay ------------------------------------------------------------
    def replay(self):
        files = journal_files()[-config.RECENT_JOURNALS:]
        n = 0
        for fp in files:
            events, offset = self._read_lines(fp, 0)
            for ev in events:
                ev["_replay"] = True
                self.bus.emit("journal." + ev.get("event", "Unknown"), ev)
                n += 1
        if files:
            self._file = files[-1]
            self._offset = offset
        self.replayed = n
        self._check_snapshots(force=True)
        self.bus.emit("journal.replay.done", n)
        log.info("replayed %d events from %d journal files", n, len(files))

    # -- tail --------------------------------------------------------------
    def run(self):
        self.replay()
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                log.exception("watcher tick failed")
            self._stop.wait(config.POLL_SECONDS)

    def stop(self):
        self._stop.set()

    def _tick(self):
        files = journal_files()
        newest = files[-1] if files else None
        if newest and newest != self._file:
            self._file, self._offset = newest, 0
        if self._file:
            size = os.path.getsize(self._file)
            if size < self._offset:          # truncated/rotated
                self._offset = 0
            if size > self._offset:
                events, self._offset = self._read_lines(self._file, self._offset)
                for ev in events:
                    self.bus.emit("journal." + ev.get("event", "Unknown"), ev)
        self._check_snapshots()

    def _read_lines(self, fp, offset):
        out = []
        try:
            with open(fp, "rb") as f:
                f.seek(offset)
                data = f.read()
        except OSError:
            return out, offset
        # Only consume complete lines; the game may be mid-write on the last one.
        end = data.rfind(b"\n")
        if end < 0:
            return out, offset
        for line in data[:end].split(b"\n"):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line.decode("utf-8", "replace")))
            except Exception:
                continue
        return out, offset + end + 1

    def _check_snapshots(self, force=False):
        for name in SNAPSHOT_FILES:
            fp = os.path.join(config.JOURNAL_DIR, name + ".json")
            try:
                mt = os.path.getmtime(fp)
            except OSError:
                continue
            if not force and self._snap_mtime.get(name) == mt:
                continue
            self._snap_mtime[name] = mt
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    payload = json.load(f)
            except Exception:
                payload = None      # mid-write; next tick will retry because mtime changes again
                self._snap_mtime[name] = None
            if payload is not None:
                self.bus.emit("journal.file." + name, payload)
