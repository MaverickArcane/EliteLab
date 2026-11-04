# Package release procedure

The release workflow builds a draft release from a version tag after the full CI
workflow passes. It attaches the Windows installer, Debian package, macOS installers, source
archive and SHA-256 files. It does not publish the draft automatically.

1. Finish review and merge the intended release changes.
2. Update `elitelab.__version__` and review `docs/releases/<version>.md` in that
   release commit. The workflow requires this file and uses it as the draft body.
3. Tag that exact commit as `v<version>`. The workflow rejects a tag that differs
   from the application version. Manual runs must select that tag, not a branch.
4. Check the draft's package names, checksums, CI results and supported platforms.
5. Complete the manual desktop checks below, then publish the reviewed draft.

The prepared version is **0.6.0**. It has not been tagged or published by the
preparation changes. Review the candidate notes, merge the intended changes,
then create `v0.6.0` on that exact merged commit to run the release workflow.
Remove candidate-only wording from the draft body after completing validation.

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

Windows CI creates a Start Menu shortcut in a unique test folder, verifies its
target/arguments/working directory, launches through the shortcut and exercises
dashboard and Quit through native window messages. A separate embedded-runtime
check drives the tray's native menu commands, verifies login check/disabled
states and ownership, simulates icon loss and taskbar recreation, and checks
restart followed by Quit. Tests use fixture journals, temporary settings/data,
a browser recorder, and unique test registry values. They do not manipulate an
existing EliteLab installation or its sign-in entry. Manual checks still cover
a real browser, pointer interaction with the notification-area menu and a real
Windows sign-in. The installer also checks browser selection, rejects invalid
browser/profile options and preserves choices on upgrade. Manually verify the
App window browser and profile pages, the chosen browser's standalone frame,
Guest mode and its browser-preference reset, and persistent-mode behavior.
Do not close #9 based on the existence of CI alone.
Mining #3 additionally requires the outstanding real-game
checks listed on that issue; fixture tests cannot establish current game rules.
