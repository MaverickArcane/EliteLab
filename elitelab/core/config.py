"""Runtime configuration. Everything can be overridden with environment variables."""
import json
import logging
import os

from . import journals
from .. import __version__      # elitelab/__init__.py has no imports, so this is safe

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
_log = logging.getLogger("elitelab.config")


def settings_path() -> str:
    """Where the settings file lives. ELITELAB_SETTINGS overrides the platform default."""
    override = os.environ.get("ELITELAB_SETTINGS")
    if override:
        return override
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(base, "EliteLab", "settings.json")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "elitelab", "settings.json")


def load_settings(path: str) -> dict:
    """Read the settings file. A missing or unreadable file is not an error: warn once, return {}."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("top level is not an object")
        return data
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        _log.warning("ignoring settings file %s: %s", path, e)
        return {}


def save_settings(changes: dict, path: str) -> dict:
    """Merge changes over the current file (unknown keys and connections are kept) and write it atomically."""
    merged = load_settings(path)
    merged.update(changes)
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)
    os.replace(tmp, path)
    return merged


def _default_journal_dir() -> str:
    """Docker folder, else the first detected folder with journals, else one that exists, else the Windows path."""
    if os.path.isdir("/journals"):          # Docker convention
        return "/journals"
    home = os.path.expanduser("~")
    found = journals.candidates(home)
    for want in (lambda c: c["journals"] > 0, lambda c: c["exists"]):
        for c in found:
            if want(c):
                return c["path"]
    return os.path.join(home, "Saved Games", "Frontier Developments", "Elite Dangerous")


def _port(value) -> int:
    port = int(value)
    if not 1024 <= port <= 65535:
        raise ValueError(port)
    return port


def _path(value) -> str:
    return os.path.abspath(os.path.expanduser(str(value)))


SETTINGS_PATH = settings_path()
SETTINGS = load_settings(SETTINGS_PATH)
SOURCES: dict = {}          # setting name -> "flag" | "env" | "file" | "default" ("flag" is set by __main__)


def _pick(key, env_name, default, cast=str):
    """Environment beats the settings file beats the default. An invalid value is skipped."""
    for source, raw in (("env", os.environ.get(env_name)), ("file", SETTINGS.get(key))):
        if raw in (None, ""):
            continue
        try:
            value = cast(raw)
        except (TypeError, ValueError):
            _log.warning("ignoring invalid %s from %s: %r", key, source, raw)
            continue
        SOURCES[key] = source
        return value
    SOURCES[key] = "default"
    return default() if callable(default) else default


HOST = _pick("host", "ELITELAB_HOST", "127.0.0.1")
AUTH_TOKEN = os.environ.get("ELITELAB_AUTH_TOKEN", "")
# extra Host header names a POST may use without a token (beyond IP literals, loopback, the bind host and this machine's names)
ALLOWED_HOSTS = {h.strip().lower().rstrip(".") for h in os.environ.get("ELITELAB_ALLOWED_HOSTS", "").split(",") if h.strip()}
PORT = _pick("port", "ELITELAB_PORT", 8766, _port)
JOURNAL_DIR = _pick("journal_dir", "ELITELAB_JOURNAL_DIR", _default_journal_dir, _path)
BROWSER = _pick("browser", "ELITELAB_BROWSER", "")
RESTART_EXIT_CODE = 75      # exit status that tells a supervising wrapper to start the lab again
WEB_DIR = os.environ.get("ELITELAB_WEB_DIR", os.path.join(ROOT, "web"))
MODULES_DIR = os.environ.get("ELITELAB_MODULES_DIR", os.path.join(ROOT, "modules"))
DATA_DIR = _pick("data_dir", "ELITELAB_DATA_DIR", lambda: os.path.join(ROOT, "data"), _path)     # persistent per-user files (wishlists...)
USER_AGENT = f"EliteLab/{__version__} (+https://github.com/MaverickArcane/EliteLab)"

RECENT_JOURNALS = int(os.environ.get("ELITELAB_RECENT_JOURNALS", "3"))   # files replayed at startup
CACHE_TTL = int(os.environ.get("ELITELAB_CACHE_TTL", "600"))             # seconds for Spansh/EDSM responses
POLL_SECONDS = float(os.environ.get("ELITELAB_POLL_SECONDS", "1.0"))     # journal tail interval
DISABLED_MODULES = {m.strip() for m in os.environ.get("ELITELAB_DISABLE", "").split(",") if m.strip()}
OFFLINE = os.environ.get("ELITELAB_OFFLINE", "") not in ("", "0", "false")   # tests/CI: never call Spansh or EDSM
