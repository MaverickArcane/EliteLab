"""Open packaged dashboards in a dedicated browser window where supported."""
import logging
import os
from pathlib import Path
import subprocess
import shutil
import sys
import webbrowser

log = logging.getLogger(__name__)

BROWSER_NAMES = {'default': 'System default', 'chrome': 'Google Chrome', 'firefox': 'Mozilla Firefox',
                 'edge': 'Microsoft Edge', 'brave': 'Brave', 'chromium': 'Chromium', 'safari': 'Safari'}


def installed_browsers():
    """Resolve fixed browser IDs locally; never accept an executable from HTTP."""
    found = {}
    if os.name == 'nt':
        paths = {'chrome': r'Google\Chrome\Application\chrome.exe', 'firefox': r'Mozilla Firefox\firefox.exe',
                 'edge': r'Microsoft\Edge\Application\msedge.exe',
                 'brave': r'BraveSoftware\Brave-Browser\Application\brave.exe',
                 'chromium': r'Chromium\Application\chrome.exe'}
        for name, relative in paths.items():
            for key in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
                base = os.environ.get(key)
                if base:
                    path = os.path.join(base, relative)
                    if os.path.isfile(path):
                        found[name] = path
                        break
    elif sys.platform == 'darwin':
        names = {'chrome': ('Google Chrome', 'Google Chrome'), 'firefox': ('Firefox', 'firefox'),
                 'edge': ('Microsoft Edge', 'Microsoft Edge'), 'brave': ('Brave Browser', 'Brave Browser'),
                 'chromium': ('Chromium', 'Chromium'), 'safari': ('Safari', 'Safari')}
        for name, (app, binary) in names.items():
            for root in (Path.home() / 'Applications', Path('/Applications')):
                path = root / (app + '.app') / 'Contents' / 'MacOS' / binary
                if path.is_file():
                    found[name] = str(path)
                    break
    else:
        names = {'chrome': ('google-chrome', 'google-chrome-stable'), 'firefox': ('firefox',),
                 'edge': ('microsoft-edge',), 'brave': ('brave-browser',),
                 'chromium': ('chromium', 'chromium-browser')}
        for name, binaries in names.items():
            for binary in binaries:
                path = shutil.which(binary)
                if path:
                    found[name] = path
                    break
    return found


def browser_options():
    default = 'Windows default' if os.name == 'nt' else 'System default'
    return [{'id': 'default', 'label': default}] + [
        {'id': name, 'label': BROWSER_NAMES[name]} for name in installed_browsers()]


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
    """Respect the saved browser choice; custom app windows require an override."""
    if not config.BROWSER:
        choice = getattr(config, 'BROWSER_CHOICE', 'default')
        if choice != 'default':
            executable = installed_browsers().get(choice)
            if executable:
                try:
                    subprocess.Popen([executable, url], close_fds=True)
                    return True
                except OSError as error:
                    log.warning('Could not open the selected browser: %s', error)
            log.warning('Selected browser is unavailable; opening the system default browser.')
        return webbrowser.open(url)
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
