"""setup module: read, save and restart for the first-run setup page.

State ``setup``: journal_found, journal_dir, restart_required, settings_path.
Saving only writes the settings file; nothing is applied until the lab restarts.
"""
import ipaddress
import os

from elitelab.core import config, journals
from elitelab.core.watcher import journal_files

HERE = os.path.dirname(os.path.abspath(__file__))
NS = "setup"
KEYS = ("journal_dir", "port", "host", "data_dir", "browser")      # reported
SAVEABLE = ("journal_dir", "port", "host", "data_dir")               # browser names an executable: file or env only
PATH_KEYS = ("journal_dir", "data_dir")
HOSTS = ("127.0.0.1", "0.0.0.0", "localhost")
NOT_ALLOWED = "Only journal_dir, port, host and data_dir can be saved here."
BROWSER_NOT_ALLOWED = "browser can only be set in the settings file or with ELITELAB_BROWSER."


def _running():
    return {"journal_dir": config.JOURNAL_DIR, "port": config.PORT, "host": config.HOST,
            "data_dir": config.DATA_DIR, "browser": config.BROWSER}


def _home():
    return os.path.expanduser("~")


def _norm(path):
    return os.path.abspath(os.path.expanduser(str(path)))


def _clean(key, value):
    """Return the value as it will be stored, or raise ValueError with a plain sentence."""
    if key == "port":
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValueError("port must be a whole number between 1024 and 65535.")
        try:
            port = int(str(value).strip())
        except ValueError:
            raise ValueError("port must be a whole number between 1024 and 65535.") from None
        if not 1024 <= port <= 65535:
            raise ValueError("port must be between 1024 and 65535.")
        return port
    if key == "host":
        host = str(value).strip() if isinstance(value, str) else ""
        if host not in HOSTS:
            try:
                ipaddress.ip_address(host)
            except ValueError:
                raise ValueError("host must be 127.0.0.1, 0.0.0.0, localhost or an IP address.") from None
        return host
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a folder path and cannot be empty.")
    return _norm(value.strip())


class Setup:
    def __init__(self, core):
        self.core = core
        self.publish()

    def _pending(self):
        saved = config.load_settings(config.SETTINGS_PATH)
        running = _running()
        out = {}
        for key in KEYS:
            if key in saved and key in SAVEABLE:
                try:
                    value = _clean(key, saved[key])
                except ValueError:
                    continue
                if value != running[key]:
                    out[key] = value
        return out

    def publish(self):
        self.core.store.update(NS, {"journal_found": bool(journal_files()), "journal_dir": config.JOURNAL_DIR,
                                    "restart_required": bool(self._pending()), "settings_path": config.SETTINGS_PATH})

    def status(self, q=None):
        pending = self._pending()
        here = _norm(config.JOURNAL_DIR)
        found = journals.candidates(_home(), extra=[config.JOURNAL_DIR])
        for c in found:
            c["selected"] = _norm(c["path"]) == here
        return {"path": config.SETTINGS_PATH, "exists": os.path.exists(config.SETTINGS_PATH),
                "values": _running(), "sources": {k: config.SOURCES.get(k, "default") for k in KEYS},
                "pending": pending, "restart_required": bool(pending),
                "journal_found": bool(journal_files()), "journal_candidates": found}

    def save(self, q):
        q = q or {}
        if "browser" in q:
            raise ValueError(BROWSER_NOT_ALLOWED)
        known = {k: q[k] for k in SAVEABLE if k in q}
        extra = [k for k in q if k not in SAVEABLE and not k.startswith("_")]
        if extra:
            raise ValueError(NOT_ALLOWED)
        clean = {k: _clean(k, v) for k, v in known.items()}
        saved_now = config.load_settings(config.SETTINGS_PATH)
        running = _running()
        changes, warnings = {}, []
        for key, value in clean.items():
            try:
                before = _clean(key, saved_now[key]) if key in saved_now else running[key]
            except ValueError:
                before = None
            if value == before:
                continue
            changes[key] = value
            if key in PATH_KEYS and not os.path.isdir(value):
                warnings.append(f"Folder does not exist yet: {value}")
        if changes:
            config.save_settings(changes, config.SETTINGS_PATH)
        self.publish()
        out = self.status()
        out["saved"] = list(changes)
        out["warnings"] = warnings
        return out

    def restart(self, q=None):
        self.core.request_restart()
        return {"restarting": True, "exit_code": config.RESTART_EXIT_CODE}


def setup(core, module):
    s = Setup(core)
    core.http.mount("/setup/", os.path.join(HERE, "web", "page"))
    core.http.route("/api/setup", s.status, tool="get_setup", module=module.name,
                    description="First-run setup state: the settings file path, the values the lab is running with and where each "
                                "came from, values saved but not yet applied (pending), whether a restart is needed, whether "
                                "journal files were found, and candidate Elite Dangerous journal folders with journal counts.")
    core.http.route("/api/setup", s.save, tool="save_setup", method="POST", module=module.name,
                    description="Save settings to the settings file. Only journal_dir, port, host and data_dir are accepted; "
                                "other keys are rejected. Nothing is applied live: changed values take effect after "
                                "restart_elitelab. Returns the same shape as get_setup plus saved and warnings.",
                    params={"journal_dir": {"type": "string", "description": "Folder holding Journal.*.log files"},
                            "port": {"type": "integer", "description": "HTTP port, 1024 to 65535"},
                            "host": {"type": "string", "description": "Bind address: 127.0.0.1, 0.0.0.0, localhost or an IP address"},
                            "data_dir": {"type": "string", "description": "Folder for the lab's own files such as wishlists"}})
    core.http.route("/api/restart", s.restart, tool="restart_elitelab", method="POST", module=module.name,
                    description="Restart EliteLab so saved settings apply. The process exits with status 75 and a supervisor "
                                "(the launcher or a service wrapper) must start it again; without one the lab simply stops.")
