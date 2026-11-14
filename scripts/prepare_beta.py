"""Require and verify every expected beta package before GitHub publication."""
import hashlib
from pathlib import Path
import re
import sys


def prepare(directory, tag):
    if not re.fullmatch(r'v\d+\.\d+\.\d+-beta\.[1-9]\d*', tag):
        raise ValueError('Invalid beta tag')
    directory = Path(directory)
    version = tag[1:]
    packages = ['EliteLab-windows-x64.zip', 'EliteLab-Setup-x64.exe',
                f'elitelab_{version}_all.deb',
                f'EliteLab-{version}-macos-arm64.pkg',
                f'EliteLab-{version}-macos-x86_64.pkg']
    expected = {name + suffix for name in packages for suffix in ('', '.sha256')}
    actual = {p.name for p in directory.iterdir()}
    if actual != expected:
        raise ValueError(f'Unexpected package set: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}')
    for name in packages:
        package = directory / name
        if package.is_symlink() or not package.is_file():
            raise ValueError('Expected a regular package file')
        fields = (directory / (name + '.sha256')).read_text().strip().split()
        if fields != [hashlib.sha256(package.read_bytes()).hexdigest(), name]:
            raise ValueError('Package checksum mismatch: ' + name)
    # Version the two Windows assets, whose CI names are intentionally fixed.
    for old, new in [('EliteLab-windows-x64.zip', f'EliteLab-{version}-windows-x64.zip'),
                     ('EliteLab-Setup-x64.exe', f'EliteLab-{version}-Setup-x64.exe')]:
        (directory / old).rename(directory / new)
        checksum = directory / (old + '.sha256')
        digest = checksum.read_text().split()[0]
        checksum.unlink()
        (directory / (new + '.sha256')).write_text(f'{digest}  {new}\n', encoding='ascii')


if __name__ == '__main__':
    prepare(sys.argv[1], sys.argv[2])
