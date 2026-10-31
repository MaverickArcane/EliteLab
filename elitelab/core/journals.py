"""Journal discovery without reading or modifying journal contents."""
import glob
import os
import re


def normalize(path):
    return os.path.abspath(os.path.expanduser(path))


def describe(path):
    path = normalize(path)
    files = sorted(p for p in glob.glob(os.path.join(path, 'Journal.*.log')) if os.path.isfile(p))
    return {'exists': os.path.isdir(path), 'journals': len(files),
            'newest': os.path.basename(files[-1])[8:-4] if files else None}


def steam_libraries(home):
    roots = [os.path.join(home, p) for p in ('.steam/steam', '.local/share/Steam',
             '.var/app/com.valvesoftware.Steam/.local/share/Steam')]
    found = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        found.append(root)
        try:
            with open(os.path.join(root, 'steamapps', 'libraryfolders.vdf'), encoding='utf-8') as stream:
                found.extend(value.replace('\\\\', '\\') for value in re.findall(r'"path"\s+"([^"]+)"', stream.read()))
        except (OSError, UnicodeError):
            pass
    return list(dict.fromkeys(normalize(p) for p in found))


def candidates(home, platform=os.name, extra=()):
    paths = [(p, 'saved') for p in extra if p]
    windows = os.path.join(home, 'Saved Games', 'Frontier Developments', 'Elite Dangerous')
    paths.append((windows, 'windows'))
    if platform != 'nt':
        for root in steam_libraries(home):
            paths.append((os.path.join(root, 'steamapps', 'compatdata', '359320', 'pfx', 'drive_c',
                          'users', 'steamuser', 'Saved Games', 'Frontier Developments', 'Elite Dangerous'), 'steam'))
        paths.append((os.path.join(home, 'Library', 'Application Support', 'Frontier Developments', 'Elite Dangerous'), 'mac'))
    if os.path.isdir('/journals'):
        paths.append(('/journals', 'docker'))
    seen, result = set(), []
    for path, source in paths:
        path = normalize(path)
        key = os.path.normcase(path)
        if key not in seen:
            seen.add(key)
            result.append({'path': path, 'source': source, **describe(path)})
    return result
