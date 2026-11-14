"""Publication refuses incomplete, unexpected or corrupted release packages."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.prepare_beta import prepare
from elitelab import __version__, __native_version__, __debian_version__


class BetaReleaseTests(unittest.TestCase):
    def packages(self, root):
        names = ['EliteLab-windows-x64.zip', 'EliteLab-Setup-x64.exe',
                 'elitelab_0.6.0-beta.1_all.deb', 'EliteLab-0.6.0-beta.1-macos-arm64.pkg',
                 'EliteLab-0.6.0-beta.1-macos-x86_64.pkg']
        for name in names:
            (root / name).write_bytes(b'package fixture')
            (root / (name + '.sha256')).write_text(hashlib.sha256(b'package fixture').hexdigest() + '  ' + name + '\n')
        return names

    def test_verified_windows_assets_get_versioned_names_and_matching_checksums(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.packages(root)
            prepare(root, 'v0.6.0-beta.1')
            self.assertFalse((root / 'EliteLab-windows-x64.zip').exists())
            for file in root.glob('*.sha256'):
                digest, name = file.read_text().split()
                self.assertEqual(digest, hashlib.sha256((root / name).read_bytes()).hexdigest())
            self.assertTrue((root / 'EliteLab-0.6.0-beta.1-windows-x64.zip').exists())

    def test_bad_assets_are_rejected_before_renaming(self):
        for failure in ('missing', 'extra', 'corrupt', 'checksum-name'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                names = self.packages(root)
                if failure == 'missing':
                    (root / names[-1]).unlink()
                elif failure == 'extra':
                    (root / 'settings.json').write_text('private')
                elif failure == 'corrupt':
                    (root / names[-1]).write_bytes(b'changed')
                else:
                    (root / (names[-1] + '.sha256')).write_text('0' * 64 + '  ../other-file')
                with self.assertRaises(ValueError):
                    prepare(root, 'v0.6.0-beta.1')
                self.assertTrue((root / names[0]).exists())

    def test_stable_tag_cannot_publish_as_beta(self):
        with self.assertRaises(ValueError):
            prepare('.', 'v0.6.0')

    def test_platform_versions_keep_beta_identity_and_ordering(self):
        self.assertEqual(__native_version__, __version__.split('-', 1)[0])
        self.assertEqual(__debian_version__, __version__.replace('-beta.', '~beta.'))


if __name__ == '__main__':
    unittest.main()
