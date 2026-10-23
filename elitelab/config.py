"""Runtime configuration. Everything can be overridden with environment variables."""
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


def _default_journal_dir() -> str:
    # Explicit override wins (also what the Docker image sets).
    env = os.environ.get("ELITELAB_JOURNAL_DIR")
    if env:
        return env
    # Docker convention: journals mounted at /journals.
    if os.path.isdir("/journals"):
        return "/journals"
    # Native Windows default.
    return os.path.join(os.path.expanduser("~"), "Saved Games", "Frontier Developments", "Elite Dangerous")


HOST = os.environ.get("ELITELAB_HOST", "127.0.0.1")
PORT = int(os.environ.get("ELITELAB_PORT", "8766"))
JOURNAL_DIR = _default_journal_dir()
WEB_DIR = os.environ.get("ELITELAB_WEB_DIR", os.path.join(_ROOT, "web"))
USER_AGENT = "EliteLab/0.3 (+https://github.com/ELITELAB_REPO)"

# How many recent journal files to scan for live state. Older files are only
# touched when something (like carrier stats) is missing from the recent ones.
RECENT_JOURNALS = int(os.environ.get("ELITELAB_RECENT_JOURNALS", "3"))

# Seconds to cache Spansh / EDSM responses.
CACHE_TTL = int(os.environ.get("ELITELAB_CACHE_TTL", "600"))
