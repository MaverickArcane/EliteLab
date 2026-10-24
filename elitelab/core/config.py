"""Runtime configuration. Everything can be overridden with environment variables."""
import os

from .. import __version__      # elitelab/__init__.py has no imports, so this is safe

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))


def _default_journal_dir() -> str:
    env = os.environ.get("ELITELAB_JOURNAL_DIR")
    if env:
        return env
    if os.path.isdir("/journals"):          # Docker convention
        return "/journals"
    return os.path.join(os.path.expanduser("~"), "Saved Games", "Frontier Developments", "Elite Dangerous")


HOST = os.environ.get("ELITELAB_HOST", "127.0.0.1")
AUTH_TOKEN = os.environ.get("ELITELAB_AUTH_TOKEN", "")
PORT = int(os.environ.get("ELITELAB_PORT", "8766"))
JOURNAL_DIR = _default_journal_dir()
WEB_DIR = os.environ.get("ELITELAB_WEB_DIR", os.path.join(ROOT, "web"))
MODULES_DIR = os.environ.get("ELITELAB_MODULES_DIR", os.path.join(ROOT, "modules"))
DATA_DIR = os.environ.get("ELITELAB_DATA_DIR", os.path.join(ROOT, "data"))     # persistent per-user files (wishlists...)
USER_AGENT = f"EliteLab/{__version__} (+https://github.com/MaverickArcane/EliteLab)"

RECENT_JOURNALS = int(os.environ.get("ELITELAB_RECENT_JOURNALS", "3"))   # files replayed at startup
CACHE_TTL = int(os.environ.get("ELITELAB_CACHE_TTL", "600"))             # seconds for Spansh/EDSM responses
POLL_SECONDS = float(os.environ.get("ELITELAB_POLL_SECONDS", "1.0"))     # journal tail interval
DISABLED_MODULES = {m.strip() for m in os.environ.get("ELITELAB_DISABLE", "").split(",") if m.strip()}
OFFLINE = os.environ.get("ELITELAB_OFFLINE", "") not in ("", "0", "false")   # tests/CI: never call Spansh or EDSM
