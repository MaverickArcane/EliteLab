"""Runtime configuration. Everything can be overridden with environment variables."""
import os
import json
import logging
import tempfile
import threading
import ipaddress

from . import journals

from .. import __version__      # elitelab/__init__.py has no imports, so this is safe

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))


_settings_lock = threading.RLock()
RESTART_EXIT_CODE = 75


def settings_path():
    override = os.environ.get("ELITELAB_SETTINGS")
    if override:
        return journals.normalize(override)
    if os.name == "nt":
        return os.path.join(os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming"), "EliteLab", "settings.json")
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "elitelab", "settings.json")


def load_settings(path):
    try:
        with open(path, encoding="utf-8") as stream:
            result = json.load(stream)
        if not isinstance(result, dict):
            raise ValueError("settings must be an object")
        return result
    except (OSError, ValueError, UnicodeError) as ex:
        logging.getLogger(__name__).warning("Cannot read settings %s: %s; using defaults", path, ex)
        return {}


def save_settings(changes, path):
    if not isinstance(changes, dict):
        raise ValueError("Settings changes must be an object.")
    path = journals.normalize(path)
    with _settings_lock:
        merged = {**load_settings(path), **changes}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temp = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=os.path.dirname(path), suffix=".tmp", delete=False) as stream:
                temp = stream.name
                json.dump(merged, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            if temp and os.path.exists(temp):
                os.unlink(temp)
        return merged


def _default_journal_dir():
    if os.path.isdir("/journals"):
        return journals.normalize("/journals")
    rows = journals.candidates(os.path.expanduser("~"))
    return next((r["path"] for r in rows if r["journals"]),
                next((r["path"] for r in rows if r["exists"]), rows[0]["path"]))


def _port(value):
    if isinstance(value, bool) or isinstance(value, float) and not value.is_integer():
        raise ValueError("invalid port")
    value = int(value)
    if not 1024 <= value <= 65535:
        raise ValueError("port must be 1024..65535")
    return value


def _text(value):
    if not isinstance(value, str) or '\x00' in value:
        raise ValueError("expected text")
    return value


def _host(value):
    value = _text(value)
    if value != "localhost":
        ipaddress.ip_address(value)
    return value


def _path(value):
    if not _text(value).strip():
        raise ValueError("empty path")
    return journals.normalize(value)


def _pick(key, env_name, default, cast):
    source = "env" if env_name in os.environ else "file" if key in SETTINGS else "default"
    value = os.environ[env_name] if source == "env" else SETTINGS[key] if source == "file" else default
    try:
        return cast(value), source
    except (TypeError, ValueError, OverflowError):
        logging.getLogger(__name__).warning("Invalid %s in %s; using default", key, source)
        return cast(default), "default"


SETTINGS_PATH = settings_path()
SETTINGS = load_settings(SETTINGS_PATH)
SOURCES = {}
HOST, SOURCES["host"] = _pick("host", "ELITELAB_HOST", "127.0.0.1", _text if "ELITELAB_HOST" in os.environ else _host)
PORT, SOURCES["port"] = _pick("port", "ELITELAB_PORT", 8766, _port)
JOURNAL_DIR, SOURCES["journal_dir"] = _pick("journal_dir", "ELITELAB_JOURNAL_DIR", _default_journal_dir(), _path)
DATA_DIR, SOURCES["data_dir"] = _pick("data_dir", "ELITELAB_DATA_DIR", os.path.join(ROOT, "data"), _path)
BROWSER, SOURCES["browser"] = _pick("browser", "ELITELAB_BROWSER", "", _text)
AUTH_TOKEN = os.environ.get("ELITELAB_AUTH_TOKEN", "")
WEB_DIR = os.environ.get("ELITELAB_WEB_DIR", os.path.join(ROOT, "web"))
MODULES_DIR = os.environ.get("ELITELAB_MODULES_DIR", os.path.join(ROOT, "modules"))
USER_AGENT = f"EliteLab/{__version__} (+https://github.com/MaverickArcane/EliteLab)"

RECENT_JOURNALS = int(os.environ.get("ELITELAB_RECENT_JOURNALS", "3"))   # files replayed at startup
CACHE_TTL = int(os.environ.get("ELITELAB_CACHE_TTL", "600"))             # seconds for Spansh/EDSM responses
POLL_SECONDS = float(os.environ.get("ELITELAB_POLL_SECONDS", "1.0"))     # journal tail interval
DISABLED_MODULES = {m.strip() for m in os.environ.get("ELITELAB_DISABLE", "").split(",") if m.strip()}
OFFLINE = os.environ.get("ELITELAB_OFFLINE", "") not in ("", "0", "false")   # tests/CI: never call Spansh or EDSM
