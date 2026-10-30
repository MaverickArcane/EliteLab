# Testing

```
python -m unittest discover -s tests -v
```

No dependencies. Runs in well under a second. CI runs it on Linux and Windows with Python 3.10 and 3.13.

## How the suite works

`tests/test_elitelab.py` sets three environment variables before importing anything:

- `ELITELAB_JOURNAL_DIR` -> `tests/fixtures/journals`
- `ELITELAB_OFFLINE=1` -> every `Services.fetch_json` raises, so nothing talks to Spansh or EDSM
- `ELITELAB_DATA_DIR` -> `tests/.data` (gitignored; wishlist writes go there)

`make_core()` builds a real `Core`, loads every module through the loader, and calls `core.watcher.replay()` synchronously (no thread, no HTTP server). Tests then call tool functions directly: `core.http.tools['get_rares_loop'].fn({})`. That exercises the exact code the HTTP and MCP paths use, minus the transport.

The loop module's coordinate fetch runs in a thread and fails under OFFLINE; it logs a warning and the loop still computes (with `dist: null`). Tests assert on that behaviour implicitly.

## The fixture journal

`tests/fixtures/journals/Journal.2026-10-22T100000.01.log` is a hand-written session for commander "Testpilot":

1. Fileheader, Commander, Materials (carbon 120, arsenic 4, chemical processors 29, datamined wake 5)
2. LoadGame in a Type-8, Powerplay (Mahon, rank 2, 6000 merits), Loadout with an engineered FSD
3. Location docked at George Lucas, Leesti (Stronghold); StoredShips naming a Kestrel Mk II
4. MarketBuy 28 Leestian Evil Juice; Undocked; StartJump (class K) + FSDJump to Zaonce
5. Docked Ridley Scott; MarketBuy 3 Leathery Eggs (`alieneggs`); ShipyardSwap to the Kestrel + a Loadout with only the internal id
6. MarketSell 28 Evil Juice for 280,000 Cr -> PowerplayMerits +420, then +3600 (objective bonus)
7. SupercruiseDestinationDrop into a Medium Power Conflict Zone; ShipTargeted a Krait Phantom; PowerplayMerits +172
8. MaterialCollected 3 datamined wake; CarrierStats (TST-001, black market not activated) and CarrierLocation Leesti

Plus `Cargo.json` (28 juice, 3 eggs), `Status.json` (balance overrides LoadGame credits, docked flag), `Market.json` (Ridley Scott listing eggs in stock and juice as sellable but out of stock).

When you add parsing for an event, add a realistic line here (copy a real one from your own journal and change the identifiers) and assert on the tool output, not on module internals.

## What is covered

Loader order and missing-dependency error; tool schema completeness; commander state from fixture; ship-name learning; cargo rare tagging across both name formats; market rares; carrier summary and activated services; feed order; Powerplay status; merit attribution (rares, objective bonus, combat zone with target detail, zero unattributed); loop ticking and sorting; materials inventory, caps, wishlist set/clear with unknown names reported; fuzzy source lookup; recipe search and per-grade cost (FSD Increased Range), trade ratios, engineering wishlist add/ambiguity/material entries, the trade plan preferring the cheapest exchange, live shortfall update on `MaterialCollected`, farm sites by material and by shortfall, grade ranges and tech broker unlocks, EDSY link decoding and the build comparison (verdicts, rolls from the current grade, the live build entry on the wishlist), Coriolis link and SLEF JSON pinning; history route and star class; recent-events filter; store change detection and bus fan-out; bus wildcard matching and handler isolation.

## What is not covered (yet)

The HTTP transport itself (SSE framing, static path guard), the MCP server, the front end, and anything that needs Spansh (targets, combat). The CI Docker job does an end-to-end check of the HTTP path against the fixture. For Spansh-backed modules, test by hand with `python -m elitelab call find_sell_targets min=125 max=165` and read the result.

## Pinned fleet carriers

`tests/test_carrier.py` uses `tests/fixtures/journals/carriers/` and a separate temporary data directory per test. It checks visited-carrier discovery, persistent pin/unpin, ownership separation, live and replayed location/jump observations, identity matching, remote freshness, missing optional fields, failed lookups, offline behavior, and pin changes during an in-flight request. External reports are mocked; no network is required.

For a manual check, enable the Fleet carrier card in Layout, pin a previously visited carrier, refresh, restart EliteLab, and verify the selection and observation survive. Check that the map marks the reported location and that docking at a different carrier does not change the pin. Unpin to restore owned-carrier details if present. Remote reports are last known observations, not live telemetry.

## Setup, settings and restart

`tests/test_settings.py` covers the settings file: the platform path and the `ELITELAB_SETTINGS` override, a missing or invalid file loading as empty with one warning, saving that keeps unknown keys and connections and creates the folder, precedence (flag, environment, file, default), casting a string port and falling back from a bad one, and `~` expansion for folders. `tests/test_journals.py` builds fake home folders and checks the candidate folders: Windows first on `nt`, Proton under every Steam root, extra libraries from `libraryfolders.vdf`, Flatpak Steam, the Mac path, saved paths first, one entry for a symlinked root, a bare `Journal.log` ignored, and the default journal folder choice. `tests/test_restart.py` checks that `start()` returns 75 after `request_restart` (including one requested before the start) and 0 on a normal stop, that `--settings` is applied before the config is imported, and that `start.sh` loops on 75 and stops on anything else (POSIX only). `tests/test_setup.py` calls `get_setup`, `save_setup` and `restart_elitelab` directly (what is reported, what is written, restart flagging, rejected values, `browser` refused, unknown keys kept), refused hosts and ports (IPv6, a port in use, an address not on this machine), env and flag warnings, the launcher warning on a port change, an unwritable settings file, and `inspect_journal_folder`), starts a real server for the mutation Host rule (an unknown name gets 403 on a 0.0.0.0 bind and writes nothing; IP literals, `[::1]`, this machine's name, the bind host and `ELITELAB_ALLOWED_HOSTS` names are accepted; any Host with a valid token; GET is unaffected), the `/setup` redirect and the page being served, and runs `main()` with `--host` and `--port` to check they reach `get_setup` and the Host rule. `test_settings.py` also covers concurrent saves, the `.bad` backup of an unparseable file, an invalid `host` falling back, and `ELITELAB_ALLOWED_HOSTS`. `test_restart.py` also checks the one-line message and non-zero status when the port is taken, and the Windows launcher's relative loop path. `test_setup.py` and `test_journals.py` import `test_elitelab` first and assert that config was imported with the temporary settings file, so either file run alone never reads your real one.

`tests/browser.mjs` drives the setup page in Chrome: the candidate list and the selected fixture folder, typing a path clearing the radio choice, saving a port change showing Restart and writing the file, `waitForRestart` against a fake `fetch` and clock (up after a gap, timeout, bad or non-JSON replies, a new port with `no-cors`), and the journal banner linking to `/setup/`. It never clicks Restart.

## Manual checks before a release

1. `python -m elitelab serve -v` against real journals; open the dashboard; drag, resize, hide and show cards; switch presets; watch the footer for stalls.
2. `python -m elitelab call get_commander_state` while the game is running and confirm the ship, system and cargo match the HUD.
3. `docker compose up --build` and hit `/api/health`.
4. In Claude Code, open the repo folder and ask for `get_powerplay_status`.
