"""Open packaged dashboards in a dedicated browser window where supported."""
import logging
import os
from pathlib import Path
import subprocess
import shutil
import sys
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


def linux_browsers(configured=""):
    if configured:
        return [configured]
    return [found for name in ('google-chrome', 'chromium', 'chromium-browser', 'brave-browser', 'microsoft-edge')
            if (found := shutil.which(name))]


def macos_browsers(configured="", applications=None):
    if configured:
        return [configured]
    roots = applications if applications is not None else (Path.home() / 'Applications', Path('/Applications'))
    names = ('Google Chrome', 'Chromium', 'Brave Browser', 'Microsoft Edge')
    return [str(path) for name in names for root in roots
            if (path := Path(root) / (name + '.app') / 'Contents' / 'MacOS' / name).is_file()]


def open_dashboard(url, config):
    """Use app mode for desktop packages, with the usual browser fallback."""
    linux = sys.platform.startswith('linux') and (Path(config.ROOT) / '.linux-package').is_file()
    macos = sys.platform == 'darwin' and (Path(config.ROOT) / '.macos-bundle').is_file()
    bundled = portable_windows(config.ROOT) or linux or macos
    if bundled:
        profile = str(Path(config.DATA_DIR) / "browser")
        discover = macos_browsers if macos else linux_browsers if linux else browser_candidates
        for executable in discover(config.BROWSER):
            try:
                subprocess.Popen([executable, "--app=" + url, "--user-data-dir=" + profile,
                                  "--window-size=1440,1000", "--no-first-run", "--no-default-browser-check"],
                                 close_fds=True)
                return True
            except OSError as error:
                log.warning("Could not open app window with %s: %s", executable, error)
        log.warning("No compatible app browser was found; opening the dashboard in a browser tab.")
    return webbrowser.open(url)
