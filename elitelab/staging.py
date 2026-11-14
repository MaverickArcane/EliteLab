"""Isolated private playtests and bounded, redacted support ZIPs (stdlib only)."""
import argparse
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import uuid
import zipfile

from . import __version__
from .instance import InstanceGuard, fingerprint

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 1024 * 1024


def redact(text):
    text = text.replace(str(Path.home()), '<home>').replace(str(Path.home()).replace('\\', '/'), '<home>')
    text = re.sub(r'(?i)Bearer\s+[^\s\"\'<>]+', 'Bearer <redacted>', text)
    text = re.sub(r'(?i)((?:token|secret|password|code|authorization|cookie)[\"\']?\s*[:=]\s*)[^\r\n,}]+', r'\1<redacted>', text)
    text = re.sub(r'https?://[^\s\"\'<>]+', '<url>', text)
    # Party codes and device secrets, including unlabelled copies in notes/errors.
    return re.sub(r'(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{24,}(?![A-Za-z0-9_-])', '<redacted-id>', text)


def environment(directory, journals=None, offline=False):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('ELITELAB_')}
    env.update(ELITELAB_SETTINGS=str(directory / 'settings.json'),
               ELITELAB_DATA_DIR=str(directory / 'data'),
               ELITELAB_INSTANCE_DIR=str(directory / 'instance'),
               ELITELAB_HOST='127.0.0.1', ELITELAB_PORT='18766',
               PYTHONUNBUFFERED='1')
    if journals:
        env['ELITELAB_JOURNAL_DIR'] = str(journals)
    if offline:
        env['ELITELAB_OFFLINE'] = '1'
    return env


def metadata():
    return dict(version=__version__, build=fingerprint(ROOT), python=platform.python_version(),
                platform=platform.system(), architecture=platform.machine(),
                collected_utc=datetime.now(timezone.utc).isoformat())


def collect(directory, note=''):
    if not directory.is_dir():
        raise ValueError('No staging profile exists yet. Start staging first.')
    destination = directory / 'reports'
    destination.mkdir(exist_ok=True)
    path = destination / ('EliteLab-staging-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                          + '-' + uuid.uuid4().hex[:8] + '.zip')
    # Exact allowlist: never traverse runtime data, journals, settings or locks.
    with zipfile.ZipFile(path, 'x', zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr('collector.json', json.dumps(metadata(), indent=2))
        bundle.writestr('problem.txt', redact(note[:8000]))
        bundle.writestr('READ-ME.txt', 'Review these files before sharing. Logs may contain commander/system names.\n'
                         'Settings, journal files, saved state and credentials are excluded.\n'
                         'Only the latest bounded logs are included; browser console logs are not captured.\n')
        for name in ('run.json', 'staging.log', 'staging.log.1', 'staging.log.2'):
            source = directory / name
            if source.is_symlink() or not source.is_file():
                continue
            with source.open('rb') as stream:
                stream.seek(max(0, source.stat().st_size - LIMIT))
                content = stream.read(LIMIT).decode('utf-8', errors='replace')
            # Build fingerprints in the generated manifest must remain comparable.
            if name == 'run.json':
                try:
                    value = json.loads(content)
                    value = {key: value[key] for key in ('version', 'build', 'python', 'platform', 'architecture', 'collected_utc') if key in value}
                    content = json.dumps(value, indent=2)
                except ValueError:
                    content = '{}'
            else:
                content = redact(content)
            bundle.writestr(name, content)
    return path


def run(directory, args):
    directory.mkdir(parents=True, exist_ok=True)
    guard = InstanceGuard(directory / 'supervisor')
    if not guard.acquire():
        guard.close()
        raise ValueError('This staging profile is already running. Use its existing window.')
    handler = RotatingFileHandler(directory / 'staging.log', maxBytes=LIMIT, backupCount=2, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    try:
        (directory / 'run.json').write_text(json.dumps(metadata(), indent=2), encoding='utf-8')
        env = environment(directory, args.journals, args.offline)
        command = [sys.executable, '-m', 'elitelab', 'serve', '--host', '127.0.0.1', '--port', str(args.port)]
        if not args.no_browser:
            command += ['--open-browser', '--setup']
        print(f'STAGING: http://127.0.0.1:{args.port}/ | profile: {directory}', flush=True)
        print('Keep this window open. Collect staging logs after a problem.', flush=True)
        while True:
            child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
            try:
                for line in child.stdout:
                    safe = redact(line.rstrip())
                    handler.emit(logging.LogRecord('staging', logging.INFO, '', 0, safe, (), None))
                    print(safe, flush=True)
                code = child.wait()
            except KeyboardInterrupt:
                # Ctrl+C also reaches the console child. Terminate only our child if needed.
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.terminate()
                    child.wait(timeout=10)
                return 0
            finally:
                child.stdout.close()
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=10)
            if code != 75:
                return code
    finally:
        handler.close()
        guard.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='friends', help='Separate staging profile name')
    sub = parser.add_subparsers(dest='action', required=True)
    start = sub.add_parser('run')
    start.add_argument('--journals', type=Path, help='Optional journal directory; otherwise choose in staging setup')
    start.add_argument('--port', type=int, default=18766)
    start.add_argument('--offline', action='store_true')
    start.add_argument('--no-browser', action='store_true')
    report = sub.add_parser('collect')
    report.add_argument('--note', default='')
    report.add_argument('--prompt', action='store_true')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,39}', args.profile):
        parser.error('Use a profile name of 1-40 letters, digits, underscores or hyphens.')
    directory = Path.home() / '.elitelab-staging' / args.profile
    try:
        if args.action == 'collect':
            note = input('What happened? Include time, expected result and steps (no codes):\n') if args.prompt else args.note
            path = collect(directory, note)
            print(f'Send this ZIP after reviewing its contents:\n{path}')
            if args.prompt and os.name == 'nt':
                os.startfile(path.parent)
            return 0
        if not 1024 <= args.port <= 65535:
            parser.error('Port must be between 1024 and 65535.')
        if args.journals:
            args.journals = args.journals.expanduser().resolve()
            if not args.journals.is_dir():
                parser.error('Journal directory does not exist.')
        return run(directory, args)
    except (OSError, ValueError) as error:
        print(redact(str(error)), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
