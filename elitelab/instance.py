"""One CLI dashboard per desktop user, across folders and requested ports."""
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request
import webbrowser


class InstanceGuard:
    def __init__(self, directory=None):
        self.directory = Path(directory or os.environ.get("ELITELAB_INSTANCE_DIR") or Path.home() / ".elitelab")
        self.file = None
        self.owned = False

    def acquire(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.directory / "instance.lock", os.O_RDWR | os.O_CREAT, 0o600)
        self.file = os.fdopen(fd, "r+b", buffering=0)
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        self.owned = True
        if os.fstat(fd).st_size == 0:
            self.file.seek(0)
            self.file.write(b" ")
        return True

    def read(self):
        try:
            self.file.seek(1)
            return json.loads(self.file.read(16384))
        except (OSError, ValueError):
            return {}

    def write(self, data):
        if not self.owned:
            raise RuntimeError("Instance lock is not owned")
        self.file.seek(1)
        self.file.write(json.dumps(data).encode("utf-8"))
        self.file.truncate()

    def close(self):
        if self.file:
            if self.owned:
                self.file.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
            self.file.close()
            self.file = None
            self.owned = False


def fingerprint(root):
    digest = hashlib.sha256()
    for directory in ("elitelab", "modules", "web"):
        for path in sorted((root / directory).rglob("*")):
            if path.is_file() and path.suffix in (".py", ".js", ".css", ".html", ".json"):
                digest.update(str(path.relative_to(root)).replace("\\", "/").encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()[:20]


def health(url, token=""):
    try:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        request = urllib.request.Request(url + "api/health", headers={"Authorization":"Bearer "+token} if token else {})
        with opener.open(request, timeout=.5) as response:
            result = json.loads(response.read(65536))
        if result.get("ok") and result.get("version") and isinstance(result.get("modules"), list) and "journal_dir" in result:
            return result
    except (OSError, ValueError):
        pass
    return None


def serve(args):
    from .core import Core, config
    root = Path(config.ROOT).resolve()
    build = fingerprint(root)
    host, port = args.host or config.HOST, args.port or config.PORT
    browser_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{browser_host}:{port}/"
    guard = InstanceGuard()
    try:
        if not guard.acquire():
            deadline = time.monotonic() + 3
            existing = guard.read()
            while time.monotonic() < deadline and not existing.get("url"):
                time.sleep(.05)
                existing = guard.read()
            if existing.get("source") != os.path.normcase(str(root)) or existing.get("build") != build:
                raise RuntimeError(f"Another EliteLab copy or build is already running at {existing.get('url', 'an existing dashboard')} "
                                   f"from {existing.get('source', 'another folder')}. Stop that instance before starting this copy.")
            while time.monotonic() < deadline:
                state = health(existing["url"], config.AUTH_TOKEN)
                if state and state.get("ready") and state.get("pid") == existing.get("pid"):
                    print(f"EliteLab is already running at {existing['url']} (PID {existing.get('pid')}). Reusing it.")
                    if args.open_browser:
                        webbrowser.open(existing["url"])
                    return
                time.sleep(.1)
            raise RuntimeError("EliteLab is already starting or stopping. Wait a moment and try again.")
        # Older versions do not hold the guard. Detect their normal dashboard
        # ports before loading modules, replaying journals, or writing any data.
        for candidate in dict.fromkeys((url,) if os.environ.get("ELITELAB_INSTANCE_DIR") else (url, "http://127.0.0.1:8766/", "http://127.0.0.1:8776/")):
            if health(candidate):
                raise RuntimeError(f"An older EliteLab instance is already running at {candidate}. Stop it before starting this copy. "
                                   "Closing a browser tab does not stop the server.")
        guard.write({"pid": os.getpid(), "url": url, "source": os.path.normcase(str(root)), "build": build})
        print(f"EliteLab folder: {root}")
        print("Keep this terminal open. Ctrl+C stops EliteLab and closes its party.")
        if args.journals:
            config.JOURNAL_DIR = args.journals
        Core().start(host, port, open_browser=args.open_browser)
    finally:
        guard.close()
