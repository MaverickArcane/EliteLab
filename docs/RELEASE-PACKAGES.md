# Package release procedure

The release workflow builds a draft release from a version tag after the full CI
workflow passes. It attaches the Windows installer, Debian package, source
archive and SHA-256 files. It does not publish the draft automatically.

1. Finish review and merge the intended release changes.
2. Update `elitelab.__version__` and release notes in that release commit.
3. Tag that exact commit as `v<version>`. The workflow rejects a tag that differs
   from the application version. Manual runs must select that tag, not a branch.
4. Check the draft's package names, checksums, CI results and supported platforms.
5. Complete the manual desktop checks below, then publish the reviewed draft.

The source archive is generated from Git's committed tree. Runtime journals,
settings and local work are excluded. Builds are unsigned; checksums detect
corruption and do not provide code signing.

## Debian validation

CI exercises both extracted and system-installed packages on a disposable Ubuntu
runner. It checks the desktop-entry syntax, fixture replay, a saved trade plan,
restart, reinstall over itself, and uninstall. Settings and a user-data sentinel
must retain their exact bytes. The lifecycle script refuses its system-install
mode outside a GitHub Linux runner.

These checks do not demonstrate the graphical launcher or error dialog. Before
publishing, install on a supported graphical Linux desktop and verify launching
from the applications menu, first-run setup, browser opening, a startup error,
restart and Quit. Record the desktop/distribution and results on PR #97.
Linux tray and login startup remain separate unfinished portions of #9.

## Remaining platforms and validation

Windows uses the existing isolated installer smoke test and embedded-runtime
launcher test. macOS packaging (#55) is not implemented by this workflow and is
not advertised as a release asset. Do not close #9 or #55 based on the existence
of this workflow alone. Mining #3 additionally requires the outstanding real-game
checks listed on that issue; fixture tests cannot establish current game rules.
