"""Build a macOS .pkg with a pinned, relocatable Python runtime (Python 3.13+)."""
import argparse
import hashlib
from pathlib import Path
import platform
import plistlib
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

from build_debian import ROOT, copy_application
from elitelab import __version__, __native_version__

RELEASE = '20261026'
PYTHON = '3.13.18'
RUNTIMES = {
    'arm64': ('aarch64', 'e5af2fde6a937a0e0c795a0c595c4efb70578d57463a2657c819992b9b9acbac'),
    'x86_64': ('x86_64', '708be9e7df297f68bdae589ea9e62a621db5abe7708f79e851c41410347452d1'),
}
IDENTIFIER = 'net.elitelab.desktop'


def extract_runtime(archive, target, expected):
    if hashlib.sha256(Path(archive).read_bytes()).hexdigest() != expected:
        raise ValueError('Bundled Python checksum mismatch')
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        if any(not member.name.startswith('python/') and member.name != 'python' for member in members):
            raise ValueError('Unexpected runtime archive layout')
        # Keep internal runtime symlinks, reject traversal, devices and external links.
        tar.extractall(target, members=members, filter='data')
    (target / 'python').rename(target / 'runtime')
    if not (target / 'runtime/bin/python3').is_file():
        raise ValueError('Runtime is missing python3')


def build(output, runtime_archive=None):
    if sys.platform != 'darwin' or sys.version_info < (3, 13):
        raise RuntimeError('Build on macOS using Python 3.13 or newer')
    arch = platform.machine()
    triple, checksum = RUNTIMES[arch]
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    package = output / f'EliteLab-{__version__}-macos-{arch}.pkg'
    with tempfile.TemporaryDirectory(prefix='elitelab-macos-build-') as tmp:
        work = Path(tmp)
        archive = Path(runtime_archive).resolve() if runtime_archive else work / 'python.tar.gz'
        if not runtime_archive:
            url = (f'https://github.com/astral-sh/python-build-standalone/releases/download/{RELEASE}/'
                   f'cpython-{PYTHON}%2B{RELEASE}-{triple}-apple-darwin-install_only.tar.gz')
            urllib.request.urlretrieve(url, archive)
        app = work / 'payload/EliteLab.app'
        contents = app / 'Contents'
        source = contents / 'Resources/app'
        copy_application(ROOT, source)
        (source / '.macos-bundle').write_text('macOS package\n', encoding='ascii')
        extract_runtime(archive, source, checksum)
        # Preserve upstream runtime licenses and ship the application's license too.
        (contents / 'Resources/LICENSE').write_bytes((ROOT / 'LICENSE').read_bytes())
        binary = contents / 'MacOS/EliteLab'
        binary.parent.mkdir(parents=True)
        subprocess.run(['/usr/bin/xcrun', 'swiftc', '-swift-version', '5', '-O', '-target',
                        arch + '-apple-macosx12.0', str(ROOT / 'installer/macos/EliteLab.swift'),
                        '-framework', 'AppKit', '-o', str(binary)], check=True)
        info = {'CFBundleIdentifier': IDENTIFIER, 'CFBundleName': 'EliteLab',
                'CFBundleDisplayName': 'EliteLab', 'CFBundleExecutable': 'EliteLab',
                'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': __native_version__,
                'CFBundleVersion': __native_version__, 'LSMinimumSystemVersion': '12.0',
                'LSUIElement': True, 'NSHighResolutionCapable': True}
        (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
        # Ad-hoc signing satisfies local code integrity, not Gatekeeper trust.
        subprocess.run(['/usr/bin/codesign', '--force', '--deep', '--sign', '-', str(app)], check=True)
        component = work / 'component.plist'
        component.write_bytes(plistlib.dumps([{'RootRelativeBundlePath': 'EliteLab.app',
            'BundleIsRelocatable': False, 'BundleIsVersionChecked': True,
            'BundleOverwriteAction': 'upgrade', 'BundleHasStrictIdentifier': True}]))
        subprocess.run(['/usr/bin/pkgbuild', '--root', str(work / 'payload'), '--identifier', IDENTIFIER,
                        '--version', __native_version__, '--install-location', '/Applications',
                        '--component-plist', str(component), str(package)], check=True)
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    package.with_suffix('.pkg.sha256').write_text(digest + '  ' + package.name + '\n', encoding='ascii')
    print(package)
    return package


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(ROOT / 'dist'))
    parser.add_argument('--runtime-archive', help='Local runtime archive (same pinned checksum required)')
    args = parser.parse_args()
    build(args.output, args.runtime_archive)
