"""Open the portable Windows dashboard in a dedicated browser window."""
import logging
import os
from pathlib import Path
import subprocess
import webbrowser

log = logging.getLogger(__name__)


def browser_candidates(configured=""):
    """Configured executable first; then known Chromium installations on Windows."""
    if configured:
        return [configured]
    candidates = []
    for rel in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe",
                r"BraveSoftware\Brave-Browser\Application\brave.exe", r"Chromium\Application\chrome.exe"):
        for key in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
            base = os.environ.get(key)
            if base:
                path = os.path.join(base, rel)
                if os.path.isfile(path) and path not in candidates:
                    candidates.append(path)
    return candidates


def portable_windows(root):
    return os.name == "nt" and (Path(root) / ".windows-bundle").is_file()


def open_dashboard(url, config):
    """Use app mode for a Windows bundle; otherwise open the usual browser tab."""
    bundled = portable_windows(config.ROOT)
    if bundled:
        profile = str(Path(config.DATA_DIR) / "browser")
        for executable in browser_candidates(config.BROWSER):
            try:
                subprocess.Popen([executable, "--app=" + url, "--user-data-dir=" + profile,
                                  "--window-size=1440,1000", "--no-first-run", "--no-default-browser-check"],
                                 close_fds=True)
                return True
            except OSError as error:
                log.warning("Could not open app window with %s: %s", executable, error)
        log.warning("No compatible app browser was found; opening the dashboard in a browser tab.")
    return webbrowser.open(url)
