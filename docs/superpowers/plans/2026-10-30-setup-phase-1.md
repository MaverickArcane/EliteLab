# Setup Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A settings file the server reads, journal folder detection, a first-run setup page with a reserved Connections section, and a restart path that the start scripts honour, so source and Docker users get configuration without environment variables.

**Architecture:** `elitelab/core/config.py` keeps its module constants but fills them from CLI flag, then environment, then a JSON settings file, then defaults, and records where each value came from. A new pure module `elitelab/core/journals.py` lists journal folder candidates. A new `setup` module exposes `get_setup`, `save_setup` and `restart_elitelab` tools and serves the setup page as static files under `/setup/`. Restart is cooperative: the server exits with status 75 and whoever started it (scripts now, the tray later) starts it again.

**Tech Stack:** Python 3.10+ standard library only, vanilla JS, unittest, the existing headless-Chrome `tests/browser.mjs` harness.

**Spec:** `docs/superpowers/specs/2026-10-30-installers-and-tray-app-design.md`, components 1, 2 and 3, phase 1.

## Global Constraints

- Standard library only in `elitelab/`, `modules/` and `web/`. No new dependencies, no build step.
- Precedence for every setting: CLI flag, then environment variable, then settings file, then default. Environment variables keep overriding so Docker is unchanged.
- Settings file location: Windows `%APPDATA%\EliteLab\settings.json`; otherwise `$XDG_CONFIG_HOME/elitelab/settings.json` with `~/.config` as the default; `ELITELAB_SETTINGS` or `--settings PATH` override.
- Keys: `journal_dir`, `port`, `host`, `data_dir`, `browser`, `connections` (object, reserved, preserved verbatim). Unknown keys are preserved on save. A missing or unreadable file is not an error: one log line, defaults apply.
- Saving writes only the keys the user changed. Journal folder, port, host and data folder are restart-required; nothing is applied live.
- Restart exit status is 75. `start.sh` and `Start EliteLab.cmd` restart the server on 75 and stop on anything else.
- Every route gets a `tool=` name and a model-facing description. `esc()` anything from the file system or the API before it reaches HTML. ASCII only in code, docs and UI copy, no emojis, no em or en dashes.
- Tests run offline with `python -m unittest discover -s tests` and must not read the developer's real settings file.
- Branch from `origin/development` as `feat/setup`; one PR against `development`. Commits end with `Co-Authored-By: Claude <noreply@anthropic.com>`.

## Review Focus

1. A settings file that is valid JSON but not an object (a list, a string) must be treated like an unreadable file: log once, use defaults, and `save_setup` must still be able to write a fresh object. Test in Task 1.
2. `port` saved as the string "8767" by hand must load as the integer 8767, and a port outside 1024..65535 in the file must fall back to the default with a `sources` entry of `default`, not crash the import. Test in Task 1.
3. A journal folder path with a trailing slash or `~` must be normalised before comparison and saving, or the candidate list shows the chosen folder as "not selected". Test in Task 2 and Task 4.
4. `save_setup` with a port equal to the current one must not set `restart_required`; only real changes do. Test in Task 4.
5. The dashboard banner must not appear during the first seconds after start when the watcher has not replayed yet: `journal_found` is computed from the folder listing, not from replayed events, so the banner reflects the folder, and the setup link must survive the 30 second refresh. Test in Task 6.

---

### Task 1: Settings file in `config.py`

**Files:**
- Modify: `elitelab/core/config.py`
- Modify: `tests/test_elitelab.py:17-21` (environment set before importing `elitelab.core`)
- Create: `tests/test_settings.py`

**Interfaces:**
- Produces: `config.settings_path() -> str`; `config.load_settings(path: str) -> dict` (returns `{}` when missing, invalid or not an object, and logs one `warning` in that case); `config.save_settings(changes: dict, path: str) -> dict` (reads the current file, merges `changes` on top, preserves unknown keys and `connections`, writes atomically via a `.tmp` file and `os.replace`, creates parent folders, returns the merged object); module constants `HOST`, `PORT`, `JOURNAL_DIR`, `DATA_DIR`, `BROWSER` (new, default `""`), `SETTINGS_PATH`, `RESTART_EXIT_CODE = 75`, and `SOURCES: dict[str, str]` mapping each of `host`, `port`, `journal_dir`, `data_dir`, `browser` to one of `"flag"`, `"env"`, `"file"`, `"default"`.
- Consumes: nothing new.

- [ ] **Step 1: Isolate tests from the developer's settings file**

In `tests/test_elitelab.py`, next to the other `os.environ[...]` lines that run before `from elitelab.core import ...`, add:

```python
os.environ["ELITELAB_SETTINGS"] = os.path.join(tempfile.mkdtemp(prefix="elitelab-test-settings-"), "settings.json")
```

- [ ] **Step 2: Write the failing tests**

`tests/test_settings.py`, importing `config` from `test_elitelab`:

```python
def test_settings_path_prefers_env_override(self):          # ELITELAB_SETTINGS set -> exactly that path
def test_settings_path_windows_and_xdg(self):               # patch os.name/APPDATA -> %APPDATA%\EliteLab\settings.json; patch XDG_CONFIG_HOME -> that/elitelab/settings.json; unset -> ~/.config/elitelab/settings.json
def test_missing_file_loads_empty(self):                    # load_settings(nonexistent) == {}
def test_invalid_json_and_non_object_load_empty_with_one_warning(self):  # '{bad' and '[1,2]' -> {} and exactly one logging warning each (assertLogs)
def test_save_merges_preserves_unknown_keys_and_connections(self):  # file {"port": 8766, "future": 1, "connections": {"inara": {"k": "v"}}}; save_settings({"port": 8767}) -> all three kept, port 8767, file on disk identical to return value, parent dir created
def test_precedence_flag_env_file_default(self):            # importlib.reload(config) under patched env/file: env ELITELAB_PORT=9000 beats file 8767 -> PORT 9000, SOURCES["port"] == "env"; file only -> 8767, "file"; neither -> 8766, "default"
def test_string_port_in_file_is_cast_and_bad_port_falls_back(self):  # file {"port": "8767"} -> 8767; {"port": 80} -> 8766 and SOURCES["port"] == "default"
def test_data_dir_and_journal_dir_expand_user(self):        # file {"journal_dir": "~/j", "data_dir": "~/d"} -> expanded absolute paths
```

Reloading `config` in tests: patch `os.environ` with `patch.dict`, point `ELITELAB_SETTINGS` at a temp file, call `importlib.reload(config)`, and reload once more in `addCleanup` with the original environment so later tests see the normal constants.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m unittest discover -s tests -p test_settings.py -v`
Expected: FAIL with `AttributeError: module 'elitelab.core.config' has no attribute 'settings_path'` (and similar).

- [ ] **Step 4: Implement in `elitelab/core/config.py`**

Add `settings_path()`, `load_settings(path)`, `save_settings(changes, path)` and a private `_pick(key, env_name, default, cast)` that returns `(value, source)` applying the precedence (flags are applied later by `__main__`, which also sets `SOURCES[key] = "flag"`). Replace the direct `os.environ.get` lines for `HOST`, `PORT`, `JOURNAL_DIR`, `DATA_DIR` with `_pick`, add `BROWSER`, `SETTINGS_PATH`, `SETTINGS = load_settings(SETTINGS_PATH)`, `SOURCES`, `RESTART_EXIT_CODE = 75`. Port validation: integer in 1024..65535 after `int()`; anything else falls back to the default with source `"default"`. Paths: `os.path.abspath(os.path.expanduser(value))`. Keep `_default_journal_dir()` for now; Task 2 replaces its body.

- [ ] **Step 5: Run the tests to verify they pass, then the whole suite**

Run: `python -m unittest discover -s tests -p test_settings.py -v` then `python -m unittest discover -s tests`
Expected: all PASS, same count as before plus the new tests.

- [ ] **Step 6: Commit**

```bash
git add elitelab/core/config.py tests/test_elitelab.py tests/test_settings.py
git commit -m "Read a settings file behind environment variables"
```

---

### Task 2: Journal folder candidates

**Files:**
- Create: `elitelab/core/journals.py`
- Modify: `elitelab/core/config.py` (`_default_journal_dir` uses the candidates)
- Create: `tests/test_journals.py`
- Create: `tests/fixtures/steam/libraryfolders.vdf` (two libraries, one with `"path" "/mnt/games"`)

**Interfaces:**
- Produces: `journals.steam_libraries(home: str) -> list[str]` (Steam roots that exist among `~/.steam/steam`, `~/.local/share/Steam`, `~/.var/app/com.valvesoftware.Steam/.local/share/Steam`, plus every `"path"` in each root's `steamapps/libraryfolders.vdf`); `journals.candidates(home: str, platform: str = os.name, extra: list[str] = ()) -> list[dict]` where each dict is `{"path": str, "exists": bool, "journals": int, "newest": str | None, "source": "saved" | "windows" | "steam" | "mac" | "docker"}`; `journals.describe(path: str) -> dict` (the `exists`, `journals`, `newest` triple for one folder, counting `Journal.*.log` files and taking the newest by name). Paths are returned normalised with `os.path.normpath(os.path.expanduser(...))` and no trailing separator.
- Consumes: Task 1 constants only inside `config._default_journal_dir()`.

- [ ] **Step 1: Write the failing tests**

`tests/test_journals.py`, building fake trees with `tempfile.TemporaryDirectory` as `home`:

```python
def test_windows_candidate_first_on_nt(self):               # platform="nt": first path endswith "Saved Games/Frontier Developments/Elite Dangerous", source "windows"
def test_proton_paths_under_every_steam_root(self):         # create ~/.steam/steam/steamapps/compatdata/359320/pfx/.../Elite Dangerous with one Journal.2026-10-30T100000.01.log -> candidate exists, journals 1, newest "2026-10-30T100000.01", source "steam"
def test_libraryfolders_vdf_adds_libraries(self):           # copy fixture vdf under ~/.steam/steam/steamapps; "/mnt/games" root appears as a candidate path
def test_flatpak_steam_root(self):                          # ~/.var/app/com.valvesoftware.Steam/.local/share/Steam present -> candidate
def test_mac_candidate_on_posix(self):                      # "Library/Application Support/Frontier Developments/Elite Dangerous" present with source "mac"
def test_extra_paths_first_and_normalised(self):            # extra=["~/custom/", ...] -> first entry path == normpath(expanduser("~/custom")), source "saved", no duplicates when the same folder also comes from detection
def test_default_journal_dir_prefers_existing_with_journals(self):  # patch config.os.path.expanduser home and reload config: a Proton folder with journals beats the Saved Games default that does not exist
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest discover -s tests -p test_journals.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'elitelab.core.journals'`.

- [ ] **Step 3: Implement `elitelab/core/journals.py` and update `config._default_journal_dir()`**

`libraryfolders.vdf` parsing: a regex for `"path"\s+"([^"]+)"` is enough; unescape `\\` to `\`. `_default_journal_dir()` returns the environment or settings value when present, else `/journals` when it is a directory, else the first candidate with `journals > 0`, else the first candidate that exists, else the Windows-style default under the home folder.

- [ ] **Step 4: Run the tests to verify they pass, then the whole suite**

Run: `python -m unittest discover -s tests -p test_journals.py -v` then `python -m unittest discover -s tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add elitelab/core/journals.py elitelab/core/config.py tests/test_journals.py tests/fixtures/steam/libraryfolders.vdf
git commit -m "Detect journal folders for Windows, Steam Proton and Mac"
```

---

### Task 3: Cooperative restart with exit status 75

**Files:**
- Modify: `elitelab/core/__init__.py` (`start()` and a new `request_restart()`)
- Modify: `elitelab/__main__.py` (`--settings`, flag provenance, exit status)
- Modify: `start.sh`
- Modify: `Start EliteLab.cmd`
- Create: `scripts/serve-loop.cmd`
- Create: `tests/test_restart.py`

**Interfaces:**
- Produces: `Core.request_restart() -> None` (sets `self.restart_requested = True` and stops the HTTP server 0.1 s later on a daemon `threading.Timer`, the same shape as the shutdown timer on the hauling branch so the two merge cleanly); `Core.start(host=None, port=None) -> int` returns `config.RESTART_EXIT_CODE` when a restart was requested and `0` otherwise; `python -m elitelab --settings PATH serve ...` sets `ELITELAB_SETTINGS` before `elitelab.core` is imported; `main()` returns the exit status and `__main__` calls `sys.exit(main())`.
- Consumes: `config.RESTART_EXIT_CODE` from Task 1.

- [ ] **Step 1: Write the failing tests**

`tests/test_restart.py`:

```python
def test_start_returns_75_after_request_restart(self):      # Core(); thread runs start("127.0.0.1", 0) with patch.object(config, "DATA_DIR", tmp); poll until core.ready is True (add `self.ready` if absent, set True after watcher start); core.request_restart(); thread result == 75 within 5 s
def test_start_returns_0_on_normal_stop(self):              # same, but core._server.stop() -> 0
def test_main_settings_flag_sets_env_before_import(self):   # subprocess: python -m elitelab --settings <tmp.json with port 8799> modules  -> exit 0; then python -c that imports config with the same env -> PORT 8799 (proves the flag is honoured before import)
def test_start_sh_restarts_on_75_and_stops_otherwise(self): # skipUnless posix; temp dir with a fake `python3` script on PATH that appends to a log and exits 75 on first call, 0 on second; run start.sh; log has two lines; a fake that exits 1 gives one line and start.sh exits 1
```

For the first two tests `HttpServer.serve` must accept port `0`: check `elitelab/core/http.py:239` and pass the bound port through unchanged.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest discover -s tests -p test_restart.py -v`
Expected: FAIL with `AttributeError: 'Core' object has no attribute 'request_restart'` and the shell test failing because `start.sh` runs once.

- [ ] **Step 3: Implement**

`Core.request_restart()` and the return value of `start()` in `elitelab/core/__init__.py`. In `elitelab/__main__.py`: add `--settings` to the top-level parser, and before `from .core import Core, config` do `if args.settings: os.environ["ELITELAB_SETTINGS"] = args.settings`; when `--journals` is given set `config.SOURCES["journal_dir"] = "flag"` as well as `config.JOURNAL_DIR`; `return Core().start(...)`; change the guard to `sys.exit(main())`.

`start.sh`:

```sh
#!/usr/bin/env sh
# Run natively on Linux/macOS. Exit status 75 means "restart me" (Settings saved).
cd "$(dirname "$0")"
while :; do
  python3 -m elitelab "$@"
  status=$?
  [ "$status" -eq 75 ] || exit "$status"
done
```

`scripts/serve-loop.cmd`:

```bat
@echo off
cd /d "%~dp0.."
:again
python -m elitelab serve
if errorlevel 76 goto done
if errorlevel 75 goto again
:done
pause
```

`Start EliteLab.cmd`: replace the `start "EliteLab server" /min cmd /c "python -m elitelab serve & pause"` line with `start "EliteLab server" /min cmd /c "%~dp0scripts\serve-loop.cmd"`. Keep the rest.

- [ ] **Step 4: Run the tests to verify they pass, then the whole suite**

Run: `python -m unittest discover -s tests -p test_restart.py -v` then `python -m unittest discover -s tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add elitelab/core/__init__.py elitelab/__main__.py start.sh "Start EliteLab.cmd" scripts/serve-loop.cmd tests/test_restart.py
git commit -m "Exit with status 75 to request a restart and loop in the start scripts"
```

---

### Task 4: Setup module API

**Files:**
- Create: `modules/setup/module.json`
- Create: `modules/setup/module.py`
- Create: `tests/test_setup.py`

**Interfaces:**
- Produces: store namespace `setup` with keys `journal_found: bool`, `journal_dir: str`, `restart_required: bool`, `settings_path: str`, published at load and after every save; tools `get_setup` (`GET /api/setup`), `save_setup` (`POST /api/setup`), `restart_elitelab` (`POST /api/restart`). Response shape of `get_setup` and `save_setup`:

```json
{"path": "...settings.json", "exists": true,
 "values": {"journal_dir": "...", "port": 8766, "host": "127.0.0.1", "data_dir": "...", "browser": ""},
 "sources": {"journal_dir": "file", "port": "default", "host": "default", "data_dir": "default", "browser": "default"},
 "pending": {"port": 8767},
 "restart_required": true,
 "journal_found": false,
 "journal_candidates": [{"path": "...", "exists": true, "journals": 3, "newest": "2026-10-30T100000.01", "source": "steam", "selected": true}],
 "saved": ["port"], "warnings": ["Folder does not exist yet: ..."]}
```

  `saved` and `warnings` appear only on `save_setup`. `pending` holds values saved in this process that differ from the running `config` values. `restart_elitelab` returns `{"restarting": true, "exit_code": 75}`.
- Consumes: Task 1 `config.load_settings`, `config.save_settings`, `config.SETTINGS_PATH`, `config.SOURCES`; Task 2 `journals.candidates`, `journals.describe`; Task 3 `core.request_restart()`.

- [ ] **Step 1: Write the manifest**

`modules/setup/module.json`: name `setup`, version `1.0.0`, description "First-run setup: journal folder, port, data folder and future connections, saved to the settings file.", `requires: []`, `provides: ["setup"]`, `order: 5`, `cards: []`. Confirm `ModuleInfo` tolerates an empty `cards` list (`elitelab/core/loader.py:19-33`); if it does not, make `cards` default to `[]` there.

- [ ] **Step 2: Write the failing tests**

`tests/test_setup.py` with a temp `ELITELAB_SETTINGS` file, temp `DATA_DIR`, `config` reloaded as in Task 1, and `core = make_core()`; call tools through `core.http.tools[name].fn(q)`:

```python
def test_get_setup_reports_values_sources_candidates_and_path(self):  # values match config, sources present for all five keys, exists False before any save, journal_found True with the fixture journals, the fixture folder is in candidates with selected True
def test_save_port_writes_only_that_key_and_flags_restart(self):      # save {"port": 8767} -> file == {"port": 8767}; saved == ["port"]; pending == {"port": 8767}; restart_required True; store setup.restart_required True
def test_save_same_port_is_not_a_restart(self):                        # save {"port": config.PORT} -> saved == [], restart_required False
def test_save_journal_dir_normalises_and_warns_when_missing(self):     # save {"journal_dir": tmp + "/nope/"} -> file value normpath without slash; warnings has one entry mentioning the folder; restart_required True
def test_save_rejects_bad_values(self):                                # port 80, port "x", host "example.com", journal_dir "" each raise ValueError with a plain message naming the field
def test_connections_and_unknown_keys_survive_a_save(self):            # pre-write {"connections": {"inara": {}}, "future": 1}; save {"port": 8767}; both still in the file; connections not writable: save {"connections": {...}} raises ValueError
def test_restart_tool_requests_restart(self):                          # patch core.request_restart; tool returns {"restarting": True, "exit_code": 75}; mock called once
def test_tools_have_descriptions(self):                                # /api/schema lists get_setup, save_setup, restart_elitelab with non-empty descriptions
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m unittest discover -s tests -p test_setup.py -v`
Expected: FAIL with `KeyError: 'get_setup'`.

- [ ] **Step 4: Implement `modules/setup/module.py`**

Class `Setup(core)` with `status(q) -> dict`, `save(q) -> dict`, `restart(q) -> dict`, `publish()` (writes the `setup` namespace). Validation in `save`: `port` integer 1024..65535; `host` one of `127.0.0.1`, `0.0.0.0`, `localhost` or an `ipaddress`-parsable address; `journal_dir` and `data_dir` non-empty strings, expanded and normalised, warning (not error) when the folder does not exist; `browser` string, may be empty; any other key, including `connections`, raises `ValueError("Only journal_dir, port, host, data_dir and browser can be saved here.")`. `restart_required` is true when any saved value differs from the running `config` value for that key. `setup(core, module)` registers the three routes with `method="POST"` for the two mutations, `module=module.name`, and model-facing descriptions that say what is saved, that nothing applies until restart, and that `restart_elitelab` exits with status 75 for the supervisor to restart.

- [ ] **Step 5: Run the tests to verify they pass, then the whole suite and the module check**

Run: `python -m unittest discover -s tests -p test_setup.py -v`, `python -m unittest discover -s tests`, `python -m elitelab modules`
Expected: PASS; `setup` listed with `requires=[] provides=['setup'] cards=[]`.

- [ ] **Step 6: Commit**

```bash
git add modules/setup/module.json modules/setup/module.py tests/test_setup.py
git commit -m "Add the setup module: read, save and restart"
```

---

### Task 5: Setup page

**Files:**
- Create: `modules/setup/web/page/index.html`
- Create: `modules/setup/web/page/setup.js`
- Modify: `modules/setup/module.py` (`core.http.mount("/setup/", <module>/web/page)` in `setup()`)
- Modify: `web/style.css` (one `.setup` block: max-width 720px, 16px gutter, stacked labels on narrow screens)
- Modify: `tests/test_setup.py` (HTTP test)
- Modify: `tests/browser.mjs` (setup page checks)

**Interfaces:**
- Produces: `GET /setup/` returns the page (200, `text/html; charset=utf-8`); the page uses only `GET /api/setup`, `POST /api/setup`, `POST /api/restart` and `GET /api/health` from Task 4 and the core.
- Consumes: Task 4 response shape.

- [ ] **Step 1: Write the failing HTTP test**

Append to `tests/test_setup.py`:

```python
def test_setup_page_is_served(self):   # ThreadingHTTPServer(("127.0.0.1", 0), make_handler(core)) in a daemon thread; GET /setup/ -> 200, Content-Type starts with text/html, body contains 'data-setup-form' and 'Connections'; GET /setup/../module.py -> 404
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m unittest discover -s tests -p test_setup.py -k page -v`
Expected: FAIL with status 404.

- [ ] **Step 3: Build the page**

`index.html` links `/style.css`, has a `<form data-setup-form>` with three `<section>`s titled Journals, Server and Connections, a `<ul data-candidates>` the script fills with radio inputs (label: path, then "N journals, newest DATE" or "not found"), a custom path `<input name="journal_dir_custom">`, `<input name="port" type="number" min="1024" max="65535">`, `<input name="data_dir">`, the Connections copy exactly: "Nothing to connect yet. Inara and other services will appear here.", a Save button, a hidden `<button data-restart>Restart EliteLab</button>`, a `<p data-status role="status">` and a link "Open dashboard" to `/`.

`setup.js`: on load `GET /api/setup`, render candidates (`selected` checks the radio; a value not in the list goes into the custom field), fill port and data folder, show `sources` as a muted hint per field ("from environment variable", "from settings file", "default"). On submit, POST only fields whose value differs from the loaded `values`; show `warnings`; when `restart_required`, show the Restart button. Restart: POST `/api/restart`, then poll `GET /api/health` every 500 ms for up to 30 s on the saved port (same origin if the port did not change, otherwise `http://HOST:NEWPORT/api/health`) and redirect to that dashboard URL; after 30 s show "EliteLab did not come back. Start it again from your launcher." Escape every value with a local `esc()` before `innerHTML`, or use `textContent`.

- [ ] **Step 4: Add browser checks**

In `tests/browser.mjs`, after the dashboard checks and before the party section (or at the end if the harness has none): navigate to `/setup/`, wait for `[data-candidates] input`, assert at least one candidate is listed and the fixture folder is selected, assert the Connections sentence is present, set port to `8799`, submit, wait for `[data-restart]` to be visible and assert the status text contains "restart", then read the temp settings file the server was started with (set `ELITELAB_SETTINGS` in `tests/browser_server.py` to a temp path and print it alongside the port) and assert it equals `{"port": 8799}`. Do not click Restart in the browser suite.

- [ ] **Step 5: Run the checks**

Run: `python -m unittest discover -s tests -p test_setup.py -v`, `node --input-type=module --check < modules/setup/web/page/setup.js`, `PYTHON=python3 CHROME_BIN=/usr/bin/google-chrome node tests/browser.mjs`
Expected: PASS; browser exit 0 with `"browserExceptions": []`.

- [ ] **Step 6: Commit**

```bash
git add modules/setup/module.py modules/setup/web/page/index.html modules/setup/web/page/setup.js web/style.css tests/test_setup.py tests/browser.mjs tests/browser_server.py
git commit -m "Serve the first-run setup page at /setup/"
```

---

### Task 6: Dashboard banner links to setup

**Files:**
- Modify: `web/app.js:405-417` (`checkHealth`)
- Modify: `web/style.css` (`.journal-warning a` colour)
- Modify: `tests/browser.mjs`

**Interfaces:**
- Produces: `Lab.checkHealth()` is exposed on the global `Lab` object so tests can trigger it; the banner reads "No journal files found in FOLDER. Open setup to choose your journal folder." with "Open setup" as a link to `/setup/`, and keeps the Docker sentence.
- Consumes: `GET /api/health` fields `journal_found` and `journal_dir` (unchanged).

- [ ] **Step 1: Write the failing browser check**

In `tests/browser.mjs`, on the dashboard page: override `Lab.api` for `/api/health` to return `{journal_found:false, journal_dir:'<dir>&'}`, call `await Lab.checkHealth()`, assert `#journal-warning a[href="/setup/"]` exists and the banner text contains `<dir>&` as text (no `<dir>` element created); restore `Lab.api`, return `journal_found:true`, call again, assert the banner is gone.

- [ ] **Step 2: Run it to verify it fails**

Run: `PYTHON=python3 CHROME_BIN=/usr/bin/google-chrome node tests/browser.mjs`
Expected: AssertionError because `Lab.checkHealth` is undefined.

- [ ] **Step 3: Implement**

In `web/app.js` build the banner with `textContent` for the folder and a created `<a>` element for the link (no `innerHTML` with the folder in it), and set `Lab.checkHealth = checkHealth` next to the `setInterval`.

- [ ] **Step 4: Run the checks**

Run: `node --input-type=module --check < web/app.js` then the browser suite.
Expected: PASS, exit 0.

- [ ] **Step 5: Commit**

```bash
git add web/app.js web/style.css tests/browser.mjs
git commit -m "Point the no-journals banner at the setup page"
```

---

### Task 7: Documentation and changelog

**Files:**
- Modify: `README.md` (Quick start: a "First run" paragraph after the Windows and Linux sections; Configuration table: a row for the settings file and `--settings`, a row for `ELITELAB_BROWSER`)
- Modify: `docs/STATE.md` (new section `## setup (module: setup)` describing the four keys)
- Modify: `docs/MODULES.md` (one sentence: a module may have `cards: []` and may mount extra static folders with `core.http.mount`)
- Modify: `docs/TESTING.md` (one paragraph on `test_settings.py`, `test_journals.py`, `test_restart.py`, `test_setup.py` and the browser setup checks)
- Modify: `docs/API.md` (entries for `get_setup`, `save_setup`, `restart_elitelab` in the existing heading format, in load order)
- Modify: `CHANGELOG.md` (Unreleased bullet)

- [ ] **Step 1: Write the docs**

README "First run": open `http://localhost:8766/setup/`, pick the journal folder, save, click Restart; settings live in the settings file (both platform paths); environment variables still win; Docker unchanged. Changelog bullet: "Setup: a settings file read by the server, journal folder detection for Windows, Steam Proton and Mac, a first-run page at /setup/ with a reserved Connections section, and a restart that the start scripts honour (exit status 75)."

- [ ] **Step 2: Verify**

Run: `python - <<'EOF'` scanning the changed files for non-ASCII characters (expect 0), `git diff --check`, and `python -m unittest discover -s tests` once more.
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/STATE.md docs/MODULES.md docs/TESTING.md docs/API.md CHANGELOG.md
git commit -m "Document the settings file, setup page and restart status"
```

---

## Self-review notes

- Spec coverage: component 1 (Task 1), component 2 (Task 2), component 3 routes and page (Tasks 4 and 5), banner (Task 6), restart semantics and start scripts (Task 3), docs (Task 7). The installed-copy data directory default and the loopback peer check are deferred to phase 2 and 3 by the spec's "Notes from the builder review"; the tray and installers are later phases.
- Names used across tasks: `config.load_settings`, `config.save_settings`, `config.SETTINGS_PATH`, `config.SOURCES`, `config.RESTART_EXIT_CODE`, `journals.candidates`, `journals.describe`, `Core.request_restart`, tools `get_setup`, `save_setup`, `restart_elitelab`, store namespace `setup`.
- Review Focus lines 1 and 2 are tested in Task 1, line 3 in Tasks 2 and 4, line 4 in Task 4, line 5 in Task 6.
