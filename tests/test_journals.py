"""Journal folder detection, run against fake home folders in a temp directory."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

import test_elitelab  # noqa: F401  (first: sets ELITELAB_SETTINGS and the fixtures before config is imported)
from elitelab.core import config, journals  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
VDF = os.path.join(HERE, "fixtures", "steam", "libraryfolders.vdf")
TAIL = os.path.join("steamapps", "compatdata", "359320", "pfx", "drive_c", "users", "steamuser",
                    "Saved Games", "Frontier Developments", "Elite Dangerous")


def touch(*parts):
    path = os.path.join(*parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("")
    return path


IMPORT_SETTINGS_PATH = config.SETTINGS_PATH      # what config read when this module imported it


class HermeticImportTests(unittest.TestCase):
    def test_config_was_first_imported_with_the_test_settings_file(self):
        self.assertTrue(os.path.realpath(IMPORT_SETTINGS_PATH).startswith(os.path.realpath(tempfile.gettempdir())),
                        IMPORT_SETTINGS_PATH)

class JournalCandidates(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = self._tmp.name

    def by_source(self, cands, source):
        return [c for c in cands if c["source"] == source]

    def test_windows_candidate_first_on_nt(self):
        cands = journals.candidates(self.home, platform="nt")
        self.assertEqual(cands[0]["source"], "windows")
        self.assertTrue(cands[0]["path"].replace("\\", "/").endswith(
            "Saved Games/Frontier Developments/Elite Dangerous"))
        self.assertFalse(cands[0]["exists"])
        self.assertEqual(self.by_source(journals.candidates(self.home, platform="posix"), "windows"), [])

    def test_proton_paths_under_every_steam_root(self):
        root = os.path.join(self.home, ".steam", "steam")
        touch(root, TAIL, "Journal.2026-10-30T100000.01.log")
        touch(root, TAIL, "Journal.2026-10-29T090000.01.log")
        steam = self.by_source(journals.candidates(self.home, platform="posix"), "steam")
        self.assertEqual(len(steam), 1)
        self.assertTrue(steam[0]["exists"])
        self.assertEqual(steam[0]["journals"], 2)
        self.assertEqual(steam[0]["newest"], "2026-10-30T100000.01")

    def test_libraryfolders_vdf_adds_libraries(self):
        root = os.path.join(self.home, ".steam", "steam")
        os.makedirs(os.path.join(root, "steamapps"))
        shutil.copy(VDF, os.path.join(root, "steamapps", "libraryfolders.vdf"))
        self.assertIn("/mnt/games", journals.steam_libraries(self.home))
        paths = [c["path"] for c in journals.candidates(self.home, platform="posix")]
        self.assertIn(os.path.normpath(os.path.join("/mnt/games", TAIL)), paths)

    def test_flatpak_steam_root(self):
        root = os.path.join(self.home, ".var", "app", "com.valvesoftware.Steam", ".local", "share", "Steam")
        os.makedirs(root)
        paths = [c["path"] for c in journals.candidates(self.home, platform="posix")]
        self.assertIn(os.path.join(root, TAIL), paths)

    def test_mac_candidate_on_posix(self):
        folder = os.path.join(self.home, "Library", "Application Support", "Frontier Developments", "Elite Dangerous")
        touch(folder, "Journal.2026-10-30T100000.01.log")
        mac = self.by_source(journals.candidates(self.home, platform="posix"), "mac")
        self.assertEqual([c["path"] for c in mac], [folder])
        self.assertEqual(mac[0]["journals"], 1)

    def test_extra_paths_first_and_normalised(self):
        folder = os.path.join(self.home, "Library", "Application Support", "Frontier Developments", "Elite Dangerous")
        os.makedirs(folder)
        with mock.patch.dict(os.environ, {"HOME": self.home}):
            cands = journals.candidates(self.home, platform="posix",
                                        extra=["~/custom/", folder + os.sep])
            expected = os.path.normpath(os.path.expanduser("~/custom"))
        self.assertEqual(cands[0]["path"], expected)
        self.assertEqual(cands[0]["source"], "saved")
        paths = [c["path"] for c in cands]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(paths.count(folder), 1)
        self.assertEqual(cands[1]["path"], folder)
        self.assertEqual(cands[1]["source"], "saved")
        self.assertTrue(all(not p.endswith(os.sep) for p in paths))

    def test_symlinked_steam_root_listed_once(self):
        real = os.path.join(self.home, ".local", "share", "Steam")
        touch(real, TAIL, "Journal.2026-10-30T100000.01.log")
        os.makedirs(os.path.join(self.home, ".steam"))
        try:
            os.symlink(real, os.path.join(self.home, ".steam", "steam"))
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("symlinks not supported")
        steam = self.by_source(journals.candidates(self.home, platform="posix"), "steam")
        self.assertEqual(len(steam), 1)
        self.assertEqual(len(journals.steam_libraries(self.home)), 1)

    def test_describe_ignores_bare_journal_log(self):
        touch(self.home, "Journal.log")
        self.assertEqual(journals.describe(self.home)["journals"], 0)

    def test_describe_empty_and_missing(self):
        self.assertEqual(journals.describe(os.path.join(self.home, "nope")),
                         {"exists": False, "journals": 0, "newest": None})
        self.assertEqual(journals.describe(self.home), {"exists": True, "journals": 0, "newest": None})

    @unittest.skipIf(os.path.isdir("/journals"), "Docker folder present on this host")
    def test_default_journal_dir_prefers_existing_with_journals(self):
        proton = os.path.join(self.home, ".local", "share", "Steam", TAIL)
        touch(proton, "Journal.2026-10-30T100000.01.log")
        with mock.patch.object(config.os.path, "expanduser", lambda p: p.replace("~", self.home, 1)):
            self.assertEqual(config._default_journal_dir(), proton)

    @unittest.skipIf(os.path.isdir("/journals"), "Docker folder present on this host")
    def test_default_journal_dir_falls_back_to_saved_games(self):
        with mock.patch.object(config.os.path, "expanduser", lambda p: p.replace("~", self.home, 1)):
            self.assertEqual(config._default_journal_dir(),
                             os.path.join(self.home, "Saved Games", "Frontier Developments", "Elite Dangerous"))


if __name__ == "__main__":
    unittest.main()
