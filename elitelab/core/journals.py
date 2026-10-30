"""Find Elite Dangerous journal folders. Pure: reads only under the given home and paths."""
import os
import re

_PROTON_TAIL = ("steamapps", "compatdata", "359320", "pfx", "drive_c", "users", "steamuser",
                "Saved Games", "Frontier Developments", "Elite Dangerous")
_STEAM_ROOTS = (
    (".steam", "steam"),
    (".local", "share", "Steam"),
    (".var", "app", "com.valvesoftware.Steam", ".local", "share", "Steam"),
)
_VDF_PATH = re.compile(r'"path"\s+"([^"]+)"')


def _norm(path: str) -> str:
    return os.path.normpath(os.path.expanduser(path))


def steam_libraries(home: str) -> list:
    """Steam roots that exist, plus every library listed in each root's libraryfolders.vdf."""
    found, seen = [], set()
    for parts in _STEAM_ROOTS:
        root = _norm(os.path.join(home, *parts))
        if not os.path.isdir(root):
            continue
        if os.path.realpath(root) not in seen:
            seen.add(os.path.realpath(root))
            found.append(root)
        try:
            with open(os.path.join(root, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        for raw in _VDF_PATH.findall(text):
            lib = _norm(raw.replace("\\\\", "\\"))
            if os.path.realpath(lib) not in seen:
                seen.add(os.path.realpath(lib))
                found.append(lib)
    return found


def describe(path: str) -> dict:
    """exists / journals / newest for one folder. newest is the latest journal name without Journal. and .log."""
    try:
        names = [n for n in os.listdir(path) if n.startswith("Journal.") and n.endswith(".log") and len(n) > len("Journal..log")]
    except OSError:
        return {"exists": os.path.isdir(path), "journals": 0, "newest": None}
    newest = max(names)[len("Journal."):-len(".log")] if names else None
    return {"exists": True, "journals": len(names), "newest": newest}


def candidates(home: str, platform: str = os.name, extra=()) -> list:
    """Likely journal folders, most trusted first: saved/extra paths, Windows, Steam Proton, Mac."""
    listed = [(p, "saved") for p in extra if p]
    if platform == "nt":
        listed.append((os.path.join(home, "Saved Games", "Frontier Developments", "Elite Dangerous"), "windows"))
    for lib in steam_libraries(home):
        listed.append((os.path.join(lib, *_PROTON_TAIL), "steam"))
    if platform != "nt":
        listed.append((os.path.join(home, "Library", "Application Support", "Frontier Developments",
                                    "Elite Dangerous"), "mac"))
    out, seen = [], set()
    for path, source in listed:
        path = _norm(path)
        key = os.path.realpath(path)
        if key in seen:
            continue
        seen.add(key)
        out.append({"path": path, "source": source, **describe(path)})
    return out
