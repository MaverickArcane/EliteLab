"""Build an unsigned Debian package for the current-user EliteLab dashboard."""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from elitelab import __version__

# The package contains only executable source and UI assets, never local data,
# settings, journals, logs, credentials, bytecode or arbitrary checkout files.
ALLOWED = {'.py', '.json', '.js', '.css', '.html'}


def stage(source, target):
    source, target = Path(source), Path(target)
    app = target/'usr'/'lib'/'elitelab'
    manifest = source/'installer'/'debian'/'manifest.txt'
    seen = set()
    for name in manifest.read_text(encoding='ascii').splitlines():
        path = PurePosixPath(name)
        if (not name or '\\' in name or path.is_absolute() or len(path.parts) < 2 or
                path.parts[0] not in ('elitelab','modules','web') or
                any(part in ('', '.', '..') for part in name.split('/')) or path.suffix not in ALLOWED or name in seen):
            raise ValueError('unsafe or duplicate package manifest entry')
        seen.add(name)
        origin = source.joinpath(*path.parts)
        if origin.is_symlink() or any((source/parent).is_symlink() for parent in Path(*path.parts).parents if parent != Path('.')):
            raise ValueError('symlink in package manifest')
        if not origin.is_file():
            raise ValueError('missing package manifest file: ' + name)
        dest = app.joinpath(*path.parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, dest)
    for required in ('elitelab/__main__.py','elitelab/desktop.py','modules/setup/module.json','web/index.html'):
        if not (app/required).is_file():
            raise ValueError('missing required application file')
    (app/'.linux-package').write_text('Debian package\n', encoding='ascii', newline='\n')
    bindir=target/'usr'/'bin'; bindir.mkdir(parents=True, exist_ok=True)
    for name, module in (('elitelab','elitelab'),('elitelab-desktop','elitelab.desktop')):
        script=bindir/name
        script.write_text('#!/bin/sh\ncd /usr/lib/elitelab || exit 1\nexec /usr/bin/python3 -m '+module+' "$@"\n', encoding='ascii', newline='\n')
        script.chmod(0o755)
    desktop=target/'usr'/'share'/'applications'/'elitelab.desktop'; desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text('[Desktop Entry]\nType=Application\nName=EliteLab\nComment=Elite Dangerous dashboard\nExec=/usr/bin/elitelab-desktop\nIcon=applications-games\nTerminal=false\nCategories=Game;Utility;\n',encoding='ascii', newline='\n')
    copyright_file=target/'usr'/'share'/'doc'/'elitelab'/'copyright'; copyright_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source/'LICENSE', copyright_file)
    size=sum(p.stat().st_size for p in (target/'usr').rglob('*') if p.is_file())
    control=target/'DEBIAN'/'control'; control.parent.mkdir(parents=True, exist_ok=True)
    control.write_text('Package: elitelab\nVersion: '+__version__+'\nArchitecture: all\nMaintainer: EliteLab contributors <noreply@github.com>\nDepends: python3 (>= 3.10), zenity\nInstalled-Size: '+str((size+1023)//1024)+'\nSection: games\nPriority: optional\nDescription: Local Elite Dangerous dashboard\n A local dashboard and API for game journal data.\n', encoding='ascii', newline='\n')
    for path in target.rglob('*'):
        if path.is_dir():
            path.chmod(0o755)
        elif path.is_file():
            path.chmod(0o755 if path.parent == bindir else 0o644)


def build(output):
    output = Path(output).resolve()
    if output.suffix != '.deb':
        raise ValueError('output must end in .deb')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='elitelab-deb-stage-') as tmp:
        stage(ROOT, Path(tmp)/'package')
        subprocess.run(['dpkg-deb','--root-owner-group','--build',str(Path(tmp)/'package'),str(output)],check=True)
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix+'.sha256').write_text(f'{digest}  {output.name}\n',encoding='ascii')
    return output


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'dist'/f'elitelab_{__version__}_all.deb')
    build(parser.parse_args().output)
