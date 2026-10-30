# Installers, tray app and first-run setup

Design for roadmap items #40 (setup scripts) and #9 (standalone app), merged into one
deliverable. Written 2026-10-30 from a conversation with the owner. Decisions marked
"owner" were made by him; decisions marked "builder call" were made while writing this
document and can be overruled.

## Intent

EliteLab should feel like an application a friend can install, not a Python project.
The owner wants to point people at the GitHub Releases page, have them download the
installer for their operating system, and be playing with a working dashboard a minute
later without opening a terminal. Starting and stopping the lab must be a click in a
tray or menu bar, the dashboard must open in its own window, and first-run setup must
find the journal folder and configure what EliteLab has today while leaving room for
connections (Inara and others) that do not exist yet.

The current state: `start.sh` and `Start EliteLab.cmd` assume Python is installed and
configured, the only configuration is environment variables, and the dashboard opens
in a browser tab. The carrier branch (#48 / #52) already builds a portable Windows zip
with an embedded CPython; that build logic is the seed for the Windows installer.

## Goals

1. The Releases page carries one installer per supported platform plus the source.
   First release: Windows and Linux (owner). Mac follows in its own issue; nobody in
   the first group of players uses a Mac (owner).
2. A GUI tray (Windows) or indicator (Linux) app starts, stops and opens the lab,
   opens Settings, toggles start-at-login and quits. No console window ever appears
   (owner).
3. The dashboard opens in its own window, with EliteLab's title and icon and no tabs
   or address bar, by launching the user's installed Chromium-family browser in app
   mode (owner chose this over shipping a web engine).
4. First-run setup finds the journal folder, lets the user confirm or pick another,
   confirms the port and data folder, and shows a Connections section that is empty
   today but is where future integrations plug in (owner).
5. Settings persist in one file that the server reads at startup, so `python -m
   elitelab`, the scripts, Docker and the installed app all honour the same choices.
   Environment variables keep overriding, so Docker is unchanged.
6. Running setup again, or installing a newer version over an older one, preserves
   settings, wishlists, layouts and trade state.
7. Missing or too-old Python on Linux, a journal folder that does not exist, and an
   occupied port each produce a plain message with the next step.

## Non-goals

- Mac installer, code signing and notarization. Tracked separately; the design below
  must not make them harder.
- Inara (or any) account connection or event upload. Only the empty Connections
  section is in scope.
- Auto-update. Installing the next installer over the old one is the update path.
- Multiplayer or shared servers (#42).
- A tray app for the Docker image.

## Anti-goals

- Adding any dependency to the server, the modules or the web shell. The source
  checkout, `start.sh`, `Start EliteLab.cmd` and Docker must keep running with the
  standard library only. The tray app is the only component allowed a dependency,
  and it ships only inside installers.
- A second configuration system. Settings must flow through `elitelab/core/config.py`
  so every module keeps reading `config.X` as today.
- Breaking `python -m elitelab serve --journals DIR --port N`; the CLI flags stay
  and win over the settings file.

## Constraints

- Repository rules in `CLAUDE.md`: standard library, modules never import each other,
  every route gets a `tool=` name and a model-facing description, `esc()` before HTML,
  ASCII only, tests before and after, a new feature is a new module.
- Builds run on GitHub-hosted runners (`windows-latest`, `ubuntu-latest`). No paid
  signing certificates. Inno Setup is preinstalled on the Windows runner image;
  `dpkg-deb` is standard on Ubuntu.
- Python 3.10 or newer, matching the rest of the project. Windows installs bundle
  CPython 3.13 (already pinned and checksum-verified in `scripts/build_windows.py`);
  Linux uses the distribution's `python3`.
- The owner develops on Ubuntu; the first players are on Windows.

## Components

### 1. Settings file (core change, builder call)

A JSON file, one object, read once at import time by `elitelab/core/config.py` after
environment variables are consulted, so the precedence is: CLI flag, then environment
variable, then settings file, then built-in default.

Location is fixed per platform so the file can be found before any other setting is
known:

- Windows: `%APPDATA%\EliteLab\settings.json`
- Linux and Mac: `$XDG_CONFIG_HOME/elitelab/settings.json`, default
  `~/.config/elitelab/settings.json`
- Override for tests and odd setups: `ELITELAB_SETTINGS` environment variable or
  `python -m elitelab --settings PATH`.

Keys, all optional: `journal_dir`, `port`, `host`, `data_dir`, `browser` (explicit
browser executable for the app window), `connections` (object, reserved, empty by
default and preserved verbatim). Unknown keys are preserved on save so older and newer
versions can share a file. A missing or unreadable file is not an error; the server
logs one line and uses defaults.

Default data directory when installed: Windows `%LOCALAPPDATA%\EliteLab\data`, Linux
`~/.local/share/elitelab`. A source checkout keeps `ROOT/data` as today. The
single-instance lock directory introduced on #52 follows the data directory.

### 2. Journal folder detection (extend existing, builder call)

`config._default_journal_dir()` grows into a `journal_candidates()` function that
returns an ordered list of `{path, exists, newest_journal}` entries:

- Windows: `%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous`.
- Linux (Steam Proton, app id 359320) under each Steam library found in
  `libraryfolders.vdf`, for native Steam (`~/.steam/steam`, `~/.local/share/Steam`)
  and Flatpak Steam (`~/.var/app/com.valvesoftware.Steam/...`):
  `steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier
  Developments/Elite Dangerous`.
- Mac: `~/Library/Application Support/Frontier Developments/Elite Dangerous` for the
  day a Mac build exists; harmless to include now.
- Whatever the settings file or environment already names, first.

The first existing candidate with journals is the default. The function is pure and
unit-tested with fabricated directory trees.

### 3. Setup module (new module `setup`, builder call)

A module, per the repository rule, with:

- `GET /api/setup` (`tool=get_setup`): current effective settings, where each value
  came from (flag, environment, file, default), journal candidates, whether journals
  were found, and `restart_required` flags per key.
- `POST /api/setup` (`tool=save_setup`): validates and writes only the keys the
  user changed, then reports `restart_required: true` when journal folder, port,
  host or data folder changed. Nothing is applied live: the watcher is a thread
  that cannot be restarted, and replaying another folder over the current store
  would layer one commander's history on another. Instead the page offers Restart,
  which calls `POST /api/restart` (`tool=restart_elitelab`): the server exits with
  status 75, which means "start me again". The tray, `start.sh` and `Start
  EliteLab.cmd` all restart the server on status 75, so installed and source users
  get the same "Save, Restart, Open dashboard" flow without a store reset path. The
  page polls `/api/health` and redirects when the server is back. Only loopback
  peers may call `save_setup` and `restart_elitelab` (peer address check) unless the
  existing auth token is set.
- A web page at `/setup` (served by the module's static files through the existing
  shell) with three sections: Journals (candidate list with "found N journals, newest
  DATE", a custom path field, a Test button), Server (port, data folder), and
  Connections (text: "Nothing to connect yet. Inara and other services will appear
  here."). Save, then "Open dashboard".
- A dashboard banner (shell change in `web/app.js`): when `journal_found` is false
  the header shows "No journals found. Open setup." linking to `/setup`.

First run is "no settings file exists". The tray opens `/setup` in that case and `/`
otherwise. Source users get the same page by visiting `/setup`.

### 4. Tray app (new package `tray/`, ships only in installers, builder call)

A small Python program, `elitelab-tray`, kept outside the `elitelab` package so the
server stays dependency-free. It uses `pystray` for the icon and menu and `Pillow`
for the icon image. Both are vendored into the installers; a developer runs it from a
checkout with `pip install -r tray/requirements.txt`. No other dependency.

Responsibilities:

- Start the server as a child process (`python -m elitelab serve`, using the bundled
  interpreter on Windows and `/usr/bin/python3` on Linux), capture its stderr to
  `DATA_DIR/logs/elitelab.log` with rotation, and poll `/api/health` until ready.
- Menu: Open dashboard, Start lab / Stop lab (one item, label follows state),
  Settings, Start with Windows / Start at login (checkbox), Open logs folder, Quit.
- Icon states: grey (stopped), amber (starting or error), green (running). Errors
  surface as a system notification with the first line of the problem and a hint
  ("Port 8766 is in use. Change it in Settings.").
- Open dashboard launches the window (component 5). Stopping the lab does not try to
  close a borrowed browser window; the page shows the existing disconnected state.
  Quit stops the server and exits.
- If the configured port already answers `/api/health` from an EliteLab of the same
  version, the tray adopts it instead of starting a second one. If the port is held
  by anything else, the tray starts the server with `--port 0` (the server gains
  that option: bind an OS-chosen port and print it on the first stdout line), opens
  the setup page on that port with the message "Port 8766 is in use. Pick another
  port and save.", and the saved port applies on the restart that follows. This
  keeps Settings reachable when the configured port is the problem. The
  single-instance lock on #52 guards the rest.
- A `--check` mode for CI: start the server, wait for health, print the browser
  command it would run, stop, exit 0. It never creates an icon, so it runs headless.

### 5. Dashboard window (function in the tray app, builder call)

Launch the first available Chromium-family browser in app mode:

- Windows search order: Edge (always present), Chrome, Brave, Chromium.
- Linux search order: `google-chrome`, `chromium`, `chromium-browser`, `brave`,
  `microsoft-edge`, then Flatpak ids for Chrome and Chromium.
- `browser` in the settings file overrides the search.

Command: `BROWSER --app=http://127.0.0.1:PORT/ --user-data-dir=DATA_DIR/browser
--window-size=1440,1000 --class=EliteLab --no-first-run --no-default-browser-check`.
The dedicated profile gives the window its own taskbar entry and icon and keeps it
out of the user's normal browser session. If no such browser exists, fall back to
`webbrowser.open` and notify once per run that the dashboard opened in a tab.

The window layer is one function with one job so a future shipped engine can replace
it without touching the server, setup or tray menu.

### 6. Windows installer (builder call)

Inno Setup script `installer/windows/EliteLab.iss`, built in CI on `windows-latest`
from a staging folder produced by extending `scripts/build_windows.py` (embedded
CPython, `elitelab/`, `modules/`, `web/`, `tray/`, vendored wheels unpacked into a
`vendor/` folder on `sys.path`).

- Per-user install, no administrator prompt (`PrivilegesRequired=lowest`), into
  `%LOCALAPPDATA%\Programs\EliteLab`.
- Start menu entry "EliteLab" that runs `pythonw.exe -m tray` (no console); optional
  desktop shortcut; optional "Start EliteLab when I sign in" that writes a shortcut
  into the user's Startup folder. The tray's checkbox toggles the same shortcut.
- Installer runs the tray at the end if the user leaves "Launch EliteLab" ticked.
- Uninstall removes the program folder and shortcuts and asks whether to delete
  settings and data (default: keep).
- Output: `EliteLab-Setup-x64.exe` plus a `.sha256` file.

### 7. Linux package (builder call)

A `.deb` for Ubuntu 22.04 and newer and Debian 12 and newer, built with `dpkg-deb` on
`ubuntu-latest` from `installer/debian/`.

- Installs to `/usr/lib/elitelab` with `/usr/bin/elitelab` (the CLI) and
  `/usr/bin/elitelab-tray`, a `.desktop` file for the tray under
  `/usr/share/applications`, and a hicolor icon.
- `Depends: python3 (>= 3.10), python3-gi, gir1.2-ayatanaappindicator3-0.1,
  python3-pil`. `pystray` is pure Python and is vendored under
  `/usr/lib/elitelab/vendor`. On desktops without an indicator extension the tray
  falls back to a plain window with the same actions, so the lab is still usable.
- Start at login writes `~/.config/autostart/elitelab-tray.desktop`; the tray's
  checkbox toggles it.
- Output: `elitelab_VERSION_all.deb` plus `.sha256`.

### 8. Release workflow (builder call)

A new `release.yml` runs on tags `v*`: builds the Windows installer, the `.deb` and a
source tarball, runs the smoke checks below, and attaches all assets with checksums to
the GitHub Release. The existing portable zip remains a CI artifact for debugging but
is no longer a release asset.

Smoke checks, all in CI:

- Windows: run the installer with `/VERYSILENT /DIR=...` into a temporary folder, run
  `pythonw -m tray --check`, assert exit 0 and that the printed browser command names
  Edge. Then run the uninstaller silently and assert the folder is gone.
- Linux: `apt install ./elitelab_*.deb`, run `elitelab-tray --check` with a fake
  `HOME` and a fixture journal folder in `settings.json`, assert exit 0 and that
  health reported `journal_found: true`.
- Both: install over itself (upgrade path) and assert `settings.json` and a seeded
  `data/wishlist.json` survive.

### 9. Documentation

README gains an "Install" section per platform (download, run, first-run setup,
where settings and data live, how to update, how to uninstall, how to find logs) and
keeps the source and Docker sections. `docs/STATE.md` documents the settings file and
`docs/MODULES.md` the setup module. A GitHub issue is opened for the Mac installer
with the Gatekeeper note and the detection path above.

## Where the code starts from

Phase 1 depends only on `development`. Phases 2 and 3 depend on pieces that exist
today only on PR #52 (`feat/hauling-desk-v2`): `scripts/build_windows.py`,
`elitelab/instance.py` (single-instance lock), the `--open-browser` flags and the
`ready`, `pid` and `source_dir` fields in `/api/health`. Decision (owner): phase 1
starts now; phases 2 and 3 start after #52 has merged into `development`. Copying
those files onto an installer branch is ruled out because it guarantees conflicts in
`__main__.py`, `core/__init__.py` and the health route. Whatever `instance.py`
finally does is canonical for the tray's adopt-or-report behaviour.

## Delivery order

Each phase is useful on its own and lands as its own pull request against
`development`.

1. Settings file, journal detection, setup module and banner. Source users and
   Docker users already benefit; this alone closes most of #40.
2. Tray app and app-mode window, runnable from a checkout for development.
3. Windows installer and the release workflow.
4. Linux `.deb`.
5. README and docs, Mac issue.

## Left to the builder

- Exact versions of `pystray` and `Pillow` to vendor and how the wheels are fetched
  and checksum-pinned in CI, following the pattern already used for CPython.
- Icon artwork: one SVG source in the repository rendered to `.ico` and PNG sizes at
  build time.
- Inno Setup wording, page order and the uninstall prompt text.
- Log rotation policy and the exact health polling cadence.
- How `--check` fakes a display-free environment on Linux.
- Test layout for the tray app (unit tests for process management and browser
  detection with fake filesystems; no GUI tests).

## Notes from the builder review (settled, builder calls)

- `/setup` is a small core addition: routes return JSON today and module static
  files live under `/modules/<name>/`, so the shell needs one HTML route for the
  setup page.
- `config.py` tells an installed copy from a checkout by a marker file the installer
  writes next to the program, which selects the installed data directory default.
- The Windows installer declares an `AppMutex` so it can stop a running tray before
  replacing files.
- `save_setup` writes only the keys the user changed, so a source checkout and an
  installed `.deb` on the same machine never silently share one data folder.
- No existing release has binary assets (v0.5.0 is source only), so there is no
  portable-zip data migration to design for.

## Open questions for the owner

None. The one question from the builder review (where phases 2 and 3 start) was
answered: after #52 merges.
