"""Open packaged dashboards in a dedicated browser window where supported."""
import logging
import configparser
import os
from pathlib import Path
import subprocess
import shutil
import sys
import webbrowser

log = logging.getLogger(__name__)

WINDOWS_BROWSERS = {
    'chrome': ('Google Chrome', r'Google\Chrome\Application\chrome.exe'),
    'edge': ('Microsoft Edge', r'Microsoft\Edge\Application\msedge.exe'),
    'brave': ('Brave', r'BraveSoftware\Brave-Browser\Application\brave.exe'),
    'chromium': ('Chromium', r'Chromium\Application\chrome.exe'),
}


def installed_windows_browsers():
    found = {}
    for name, (_, relative) in WINDOWS_BROWSERS.items():
        for key in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            base = os.environ.get(key)
            if base:
                path = os.path.join(base, relative)
                if os.path.isfile(path):
                    found[name] = path
                    break
    return found


def default_windows_browser():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice') as key:
            progid = winreg.QueryValueEx(key, 'ProgId')[0].lower()
        for prefix, name in (('chromehtml', 'chrome'), ('msedgehtm', 'edge'),
                             ('bravehtml', 'brave'), ('chromiumhtm', 'chromium')):
            if progid.startswith(prefix):
                return name
    except (OSError, AttributeError):
        pass
    return ''


def windows_browser(config):
    """Read the installer's fixed browser ID and profile mode, never a command."""
    settings = configparser.ConfigParser(interpolation=None)
    path = Path(config.ROOT) / 'desktop-browser.ini'
    try:
        if path.is_file():
            with path.open(encoding='utf-8-sig') as source:
                settings.read_string(source.read(4096))
        choice = settings.get('Desktop', 'Browser', fallback='')
        profile = settings.get('Desktop', 'Profile', fallback='guest')
        if choice not in ('', *WINDOWS_BROWSERS) or profile not in ('guest', 'persistent'):
            raise ValueError('Unknown browser or profile mode')
    except (OSError, ValueError, configparser.Error) as error:
        raise OSError('The app browser setting is invalid. Run the EliteLab installer again.') from error
    if config.BROWSER:
        return 'custom', config.BROWSER, profile == 'guest'
    installed = installed_windows_browsers()
    if not choice:
        preferred = default_windows_browser()
        choice = preferred if preferred in installed else next(iter(installed), '')
    if choice not in installed:
        raise OSError('The selected app browser is unavailable. Run the EliteLab installer again and choose an installed Chrome, Edge, Brave or Chromium.')
    return choice, installed[choice], profile == 'guest'


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
    if portable_windows(config.ROOT):
        name, executable, guest = windows_browser(config)
        profile = Path(config.DATA_DIR) / ('browser' if name == 'custom' else 'browser-' + name)
        args = [executable, '--app=' + url, '--user-data-dir=' + str(profile),
                '--window-size=1440,1000', '--no-first-run', '--no-default-browser-check', '--disable-sync']
        if guest:
            args.append('--guest')
        # A missing app browser is an error, not permission to open a normal tab.
        subprocess.Popen(args, close_fds=True)
        return True
    linux = sys.platform.startswith('linux') and (Path(config.ROOT) / '.linux-package').is_file()
    macos = sys.platform == 'darwin' and (Path(config.ROOT) / '.macos-bundle').is_file()
    bundled = linux or macos
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
