"""Build a per-user Windows installer from the checksum-verified portable bundle."""
import argparse
import hashlib
import hmac
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tempfile
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from elitelab import __version__
MAX_FILES = 50000
MAX_TOTAL = 1024 * 1024 * 1024


def verify_bundle(bundle):
    """Check the builder's digest for corruption; this is not a signature."""
    bundle = Path(bundle)
    digest_file = bundle.with_suffix(bundle.suffix + '.sha256')
    parts = digest_file.read_text(encoding='ascii').strip().split(maxsplit=1)
    if len(parts) != 2 or parts[1] != bundle.name or len(parts[0]) != 64:
        raise ValueError('invalid portable bundle checksum file')
    actual = hashlib.sha256(bundle.read_bytes()).hexdigest()
    if not hmac.compare_digest(actual, parts[0].lower()):
        raise ValueError('portable bundle checksum mismatch')



def stage_bundle(bundle, destination):
    """Extract only the expected bundle tree; reject unsafe and ambiguous names."""
    destination = Path(destination)
    seen = set()
    total = 0
    with zipfile.ZipFile(bundle) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_FILES:
            raise ValueError('bundle has too many entries')
        for entry in entries:
            name = entry.orig_filename
            directory = entry.is_dir()
            if directory and name.endswith('/'):
                name = name[:-1]
            if directory and name == 'EliteLab':
                continue
            path = PurePosixPath(name)
            if ('\\' in name or path.is_absolute() or not path.parts or path.parts[0] != 'EliteLab'
                    or len(path.parts) < 2 or any(part in ('', '.', '..') or ':' in part or part.endswith((' ', '.'))
                                                      or any(ord(c) < 32 for c in part)
                                                      or part.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
                                                      for part in name.split('/'))
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError('unsafe bundle entry')
            relative = PurePosixPath(*path.parts[1:])
            key = relative.as_posix().casefold()
            if key in seen:
                raise ValueError('duplicate bundle entry')
            seen.add(key)
            total += entry.file_size
            if total > MAX_TOTAL:
                raise ValueError('bundle too large')
            target = destination.joinpath(*relative.parts)
            if directory:
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output)
    for required in ('.windows-bundle', 'Launch EliteLab.vbs', 'runtime/pythonw.exe', 'elitelab/desktop.py'):
        if not (destination / required).is_file():
            raise ValueError('bundle is missing required application files')


def build(bundle, compiler, output, app_id='MaverickArcane.EliteLab'):
    output = Path(output).resolve()
    if output.suffix.lower() != '.exe':
        raise ValueError('installer output must end in .exe')
    if not app_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-' for c in app_id):
        raise ValueError('invalid application ID')
    if not Path(compiler).is_file():
        raise ValueError('Inno Setup compiler not found')
    verify_bundle(bundle)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='elitelab-installer-stage-') as temporary:
        stage = Path(temporary) / 'EliteLab'
        stage_bundle(bundle, stage)
        subprocess.run([str(compiler), '/Qp', '/DStagingDir=' + str(stage), '/DAppVersion=' + __version__,
                        '/DAppIdValue=' + app_id, '/O' + str(output.parent), '/F' + output.stem,
                        str(ROOT / 'installer' / 'windows' / 'EliteLab.iss')], check=True)
    if not output.is_file():
        raise RuntimeError('Inno Setup did not produce the expected installer')
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + '.sha256').write_text(f'{digest}  {output.name}\n', encoding='ascii')
    output.with_suffix(output.suffix + '.build.json').write_text(json.dumps({'app_id': app_id, 'sha256': digest}) + '\n', encoding='ascii')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=ROOT/'dist'/'EliteLab-windows-x64.zip')
    parser.add_argument('--compiler', type=Path, required=True, help='Path to Inno Setup ISCC.exe')
    parser.add_argument('--output', type=Path, default=ROOT/'dist'/'EliteLab-Setup-x64.exe')
    parser.add_argument('--app-id', default='MaverickArcane.EliteLab', help='Override for isolated installer tests')
    args = parser.parse_args()
    build(args.bundle, args.compiler, args.output, args.app_id)
