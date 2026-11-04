# Package release procedure

The release workflow builds a draft release from a version tag after the full CI
workflow passes. It attaches the Windows installer, Debian package, macOS installers, source
archive and SHA-256 files. It does not publish the draft automatically.

1. Finish review and merge the intended release changes.
2. Update `elitelab.__version__` and release notes in that release commit.
3. Tag that exact commit as `v<version>`. The workflow rejects a tag that differs
   from the application version. Manual runs must select that tag, not a branch.
4. Check the draft's package names, checksums, CI results and supported platforms.
5. Complete the manual desktop checks below, then publish the reviewed draft.

The source archive is generated from Git's committed tree. Runtime journals,
settings and local work are excluded. Builds are unsigned; checksums detect
corruption and do not provide developer identity. The macOS app is ad-hoc signed
for local integrity; the installer is unsigned and neither is notarized.

## Debian validation

CI exercises both extracted and system-installed packages on a disposable Ubuntu
runner. It checks the desktop-entry syntax, fixture replay, a saved trade plan,
restart, reinstall over itself, and uninstall. Settings and a user-data sentinel
must retain their exact bytes. The lifecycle script refuses its system-install
mode outside a GitHub Linux runner.

Native GTK checks run under Xvfb against an extracted package. They exercise the
fallback control window, login opt-in and ownership, Open setup browser arguments,
verified server shutdown, and indicator connection/loss through a simulated D-Bus
host. The Linux-desktop-screenshots artifact contains the fallback window.

These checks do not demonstrate a full desktop session's launcher or error dialog. Before
publishing, install on a supported graphical Linux desktop and verify launching
from the applications menu, first-run setup, browser opening, a startup error,
restart and Quit. Record the desktop/distribution and results on the current
Linux desktop PR. The browser recorder in the automated GTK test validates
launch arguments, not a real browser window or a real login cycle.

## macOS validation

Build on a Mac with Python 3.13+ and Xcode command-line tools:

```sh
python3 scripts/build_macos.py
```

The architecture follows the build host. Python 3.13.18 comes from the pinned
[python-build-standalone 20261026 release](https://github.com/astral-sh/python-build-standalone/releases/tag/20261026),
with a separate SHA-256 for each architecture. The complete runtime, including
its license files, is retained. The application uses the same explicit source
manifest as the Debian package; user data and checkout extras are excluded.
Swift/AppKit supplies native controls without adding Python dependencies.

CI builds on Apple Silicon and Intel macOS runners, installs into Applications,
runs the native executable's `--check` using its bundled Python with no system
Python on PATH, verifies journal replay, saves a trade plan, restarts the server,
upgrades over itself and removes the app. It also drives the actual AppKit menu
targets to enable/disable login startup, open dashboard/setup and Quit. The
browser recorder verifies launch arguments and the separate profile. Settings
and a saved-data sentinel must retain their exact bytes across upgrade/removal.
The install/remove smoke script refuses to run outside a disposable GitHub
macOS runner or over an existing EliteLab.app.

Before publishing, test a quarantined download on each supported architecture:
Gatekeeper guidance, Applications launch, first-run setup, a real Chromium
app window and Safari fallback, login startup after logout/login, a startup
error, restart and Quit. CI does not reproduce a downloaded file's quarantine
or an actual user login. Record the macOS version and results on the macOS PR.

## Remaining validation

Windows uses the existing isolated installer smoke test and embedded-runtime
launcher test. Do not close #9 based on the existence of this workflow alone.
Mining #3 additionally requires the outstanding real-game
checks listed on that issue; fixture tests cannot establish current game rules.
