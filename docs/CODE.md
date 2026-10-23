# Code reference

File by file, function by function. Line-level details change; the shapes below are the contract. When you change a signature, change it here.

## elitelab/__init__.py

`__version__` only. Imported by core and mcp for `/api/health` and `serverInfo`.

## elitelab/__main__.py

`main(argv=None)`: argparse with subcommands.

- `serve` (default): `--host`, `--port`, `--journals`, `-v`. Sets `config.JOURNAL_DIR` if `--journals` given, configures logging to stderr, builds `Core()` and calls `start()`.
- `mcp`: runs `elitelab.mcp.serve()` (stdio JSON-RPC).
- `modules`: prints `loader.resolve_order(loader.discover())` without starting anything.
- `tools`: prints the tool list from a running lab (`mcp._tools()`).
- `call TOOL k=v ...`: calls a tool on a running lab via HTTP; values are parsed as JSON when possible, else strings.

## elitelab/core/config.py

Module-level constants read from environment at import time. Tests override `config.JOURNAL_DIR` etc. after import, which works because every consumer reads `config.X` at call time, not at import.

| Name | Env | Default |
|---|---|---|
| `ROOT` | | repo root (two levels up from this file) |
| `HOST`, `PORT` | `ELITELAB_HOST`, `ELITELAB_PORT` | `127.0.0.1`, `8766` |
| `JOURNAL_DIR` | `ELITELAB_JOURNAL_DIR` | `/journals` if it exists, else `~/Saved Games/Frontier Developments/Elite Dangerous` |
| `WEB_DIR`, `MODULES_DIR`, `DATA_DIR` | `ELITELAB_WEB_DIR`, `ELITELAB_MODULES_DIR`, `ELITELAB_DATA_DIR` | `web/`, `modules/`, `data/` under ROOT |
| `USER_AGENT` | | sent to Spansh/EDSM |
| `RECENT_JOURNALS` | `ELITELAB_RECENT_JOURNALS` | 3 files replayed at startup |
| `CACHE_TTL` | `ELITELAB_CACHE_TTL` | 600 s |
| `POLL_SECONDS` | `ELITELAB_POLL_SECONDS` | 1.0 s journal tail interval |
| `DISABLED_MODULES` | `ELITELAB_DISABLE` | comma list |
| `OFFLINE` | `ELITELAB_OFFLINE` | truthy = `Services.fetch_json` raises instead of calling out |

## elitelab/core/gamedata.py

Game facts shared by modules (modules may not import each other, so shared facts live in core): `POWERS` (the 12 powers, Spansh spelling), `RARES` (internal key -> display name; observed keys are marked, the rest are community slugs), `KNOWN_RARES`, `RARE_NAMES`, `norm(name)` (strip `$`/`_name;`, lowercase), `is_rare(key_or_name)`. Add a rare's key only after seeing it in a real journal.

## elitelab/core/bus.py

`EventBus`:

- `on(pattern, fn) -> off()`: `fn(name, payload)`. Pattern is an exact name, `*`, or an `fnmatch` glob like `journal.*` or `state.journal.cargo`. Returns an unsubscribe callable.
- `emit(name, payload=None)`: synchronous, in the caller's thread. Each handler runs in its own try/except; a failure is logged with `log.exception` and does not stop the others. Subscribers are snapshotted under a lock before iterating, so handlers may subscribe/unsubscribe during emit.

Event names in use: `journal.<Event>` (any journal event), `journal.file.<Name>` (snapshot files: Status, Cargo, Market, ModulesInfo, ShipLocker, Backpack, NavRoute, Shipyard, Outfitting), `journal.replay.done` (payload: int count), `state.<ns>.<key>` (payload: the new value).

## elitelab/core/store.py

`Store(bus)`: dict of namespaces, each a dict of keys.

- `set(ns, key, value) -> bool`: deep-copies dict/list values. Returns False and does nothing if equal to the current value. On change: bumps `_version`, calls subscribers `(ns, key, value, version)`, emits `state.<ns>.<key>`.
- `update(ns, mapping) -> [changed keys]`.
- `get(ns, key=None, default=None)`: deep copy; without `key` returns the whole namespace dict.
- `snapshot()`: all namespaces plus `_version`.
- `subscribe(fn) -> off()`: used by the SSE handler (one subscription per connected browser).
- `delete_ns(ns)`.

Thread safety: a single RLock around the data. Subscriber callbacks run outside the lock. The SSE subscriber puts into a bounded queue (`http._put`, drops on full).

## elitelab/core/services.py

`Services`: one shared cache for all modules.

- `fetch_json(url, body=None, ttl=None, method=None)`: GET, or POST JSON if `body` given. Cached by `(url, body)` for `ttl` seconds (default `config.CACHE_TTL`). Expired entries are evicted on insert and the cache is capped at `CACHE_MAX_ENTRIES` (400, oldest first). Raises `RuntimeError` immediately if `config.OFFLINE`. 40 s timeout.
- `spansh_stations(filters, ref, size=40, sort="distance", ttl=None)`: POST to `https://spansh.co.uk/api/stations/search` with `{filters, sort:[{sort:{direction:asc}}], size, page:0, reference_system}`. Returns the raw Spansh response (`count`, `results`). Station result fields used across modules: `name, system_name, distance, distance_to_arrival, type, has_large_pad, medium_pads, system_population, market_updated_at, system_x/y/z, system_primary_economy, government, market[{commodity, category, buy_price, sell_price, supply, demand}]`.
- `spansh_system(name)`: POST to the systems search with `{"filters":{"name":{"value":name}}}`; returns a trimmed dict. Systems result fields used: `name, x, y, z, population, security, allegiance, controlling_power, power (list of powers present), power_state (Unoccupied|Exploited|Fortified|Stronghold), power_conflict_progress [{power, progress}]`.
- `pad(station)`: `L` if `has_large_pad`, `M` if `medium_pads > 0`, else `S`.
- `edsm_coords(names) -> {name: {x,y,z}}`: GET `https://www.edsm.net/api-v1/systems?systemName[]=...&showCoordinates=1`, cached 24 h.

Constants: `STARPORT_TYPES` (Coriolis, Orbis, Ocellus, Asteroid base, Planetary Port), `MEDIUM_TYPES` (plus Outpost, Planetary Outpost), `POWERS` (12 Powerplay powers, exact Spansh spelling: `A. Lavigny-Duval`, `Li Yong-Rui`...).

## elitelab/core/http.py

- `Route(path, fn, tool, description, params, method, module)` with `schema()` producing `{tool, path, method, module, description, input_schema}`; `params` is `{name: {type, description, default?, required?, enum?}}` and becomes JSON Schema properties. Keys with `required: True` and no `default` are listed in `required`.
- `Router`: `route(path, fn, *, tool=None, description="", params=None, method="GET", module="core")` stores by `(METHOD, path)`; the same path may have both GET and POST (materials wishlist does). `mount(prefix, directory)` serves static files under a URL prefix (used for `/modules/<name>/`).
- `make_handler(core)` builds the `BaseHTTPRequestHandler` subclass:
  - `_dispatch(method)`: percent-decodes the path; for POST reads the body first (always, so keep-alive connections stay in sync even on a 404; bodies over `MAX_BODY` = 1 MB are rejected with 400); `/events` -> SSE; else exact route match on `(method, path)`; handler is called as `fn(q)` where `q` is the query dict merged with the JSON body for POST (body wins). `ValueError` -> 400, other exceptions -> 500 with `{"error"}` and a logged traceback. Unknown `/api/*` -> 404. Everything else is static: mounted prefixes first, then `config.WEB_DIR`. `_static` normalises the path and refuses anything outside the directory (404).
  - No CORS headers, deliberately: the API has no auth, so a third-party page in the user's browser must not be able to read state or POST a wishlist. Same-origin dashboard, MCP and CLI are unaffected.
  - `_sse()`: writes `event: snapshot` with the full store, then one `event: state` per change `{ns, key, value, v}`, and a `: ping` comment every 15 s. The per-client queue holds 1000 messages and drops on overflow; the browser detects the gap in `v` and refetches `/api/state`. Subscription is removed in `finally` when the client disconnects. `protocol_version = HTTP/1.1` so keep-alive works.
- `HttpServer(core).serve(host, port)`: `ThreadingHTTPServer` with daemon threads.

## elitelab/core/loader.py

- `ModuleInfo(name, path, manifest)`: `requires`, `provides`, `cards`, `order` (default 100), `web_dir`, `instance`. `to_json()` rewrites each card's `script` to `/modules/<name>/<script>`.
- `discover(modules_dir=None)`: folders containing both `module.json` and `module.py`, minus `config.DISABLED_MODULES`.
- `resolve_order(mods)`: topological sort on `requires` resolved through `provides`. Raises `RuntimeError` on a missing provider or a cycle. Ties broken by `(order, name)`.
- `load_all(core)`: for each module in order, `importlib` the file as `elitelab_modules.<name>`, call `setup(core, module_info)`, mount `web/` if present, register in `core.modules`.

## elitelab/core/watcher.py

- `journal_files(newest_first=False)`: `Journal.*.log` sorted by mtime.
- `JournalWatcher(bus)` thread:
  - `replay()`: reads the last `RECENT_JOURNALS` files fully, emits each event with `_replay=True`, records the newest file and its size as the tail position, forces a snapshot-file pass, then emits `journal.replay.done`.
  - `run()`: `replay()` then loop `_tick()` every `POLL_SECONDS`.
  - `_tick()`: if a newer journal file appeared, switch to it at offset 0; if the file shrank, reset to 0; read new complete lines only (`_read_lines` stops at the last newline so a half-written line is retried next tick); then `_check_snapshots()`.
  - `_check_snapshots(force=False)`: for each name in `SNAPSHOT_FILES`, compare mtime; on change parse JSON and emit `journal.file.<Name>`. A parse failure (mid-write) clears the stored mtime so it is retried.

## elitelab/core/__init__.py

`Core`: owns `config, log, bus, store, services, http, modules, watcher`. Helpers for modules: `data_path(*parts)`, `read_data(*parts, default)`, `write_data(value, *parts)` (atomic via temp file + `os.replace`).

Built-in routes (`module="core"`): `/api/health` (`health`), `/api/state` (`get_state`), `/api/modules` (`list_modules`), `/api/schema` (`list_tools`), `/api/events` (`get_recent_events`, params `limit` <= 200, `event`). `_remember_event` keeps a ring of the last 500 journal events for `/api/events`.

`start(host, port)`: `load_all`, start watcher thread, print banner, serve forever; stops the watcher on exit.

## elitelab/mcp.py

Stdio JSON-RPC 2.0, newline-delimited. `BASE` from `ELITELAB_URL`. Handles `initialize` (returns `protocolVersion 2024-11-05`, `capabilities.tools`, `serverInfo`, an `instructions` string that tells the model which tools to start with), `notifications/*` (ignored), `ping`, `tools/list` (from `/api/schema`), `tools/call` (GET with query params or POST with JSON body depending on the route's method; result wrapped as one `text` content block with pretty JSON; errors return `isError: true`). Unknown methods -> `-32601`.

## modules/journal/module.py

`Journal(core)`: holds `self.st` (the namespace dict), `self.feed` (last 40 feed lines), `_market_rares` (keys flagged `Rare` in the last `Market.json`), `_cargo_raw` (last `Cargo.json`, re-tagged when a new market arrives), `_learned_ships` (internal id -> display name), `_ship_internal`. Cargo items are tagged rare when the key is in the last market's rare set, or `gamedata.is_rare()` matches the key or the display name. Materials are not tracked here (the materials module owns them). The carrier backfill runs in a thread so the watcher is never blocked.

- `on_event(name, ev)`: routes `journal.file.*` to `on_file`; otherwise folds the event (see docs/EVENTS.md) and pushes only the changed keys.
- `_learn(internal, display)` / `ship_name(internal)`: learned names first, then `SHIP_NAMES`, then a prettified internal id (`smallcombat01_nx` -> `Smallcombat01`).
- `_carrier(ev, prev)`: shapes `CarrierStats` into the carrier dict, keeping `system` from the previous value.
- `on_replay_done`: if no carrier name was seen in the replayed files, `_backfill_carrier()` scans older journals (files 4..60 newest-first) for the last `CarrierStats` line.
- `on_file(name, data)`: `Status` -> `status` dict and `credits`; `Market` -> `market` dict and the rare key set (then re-tags cargo); `Cargo` -> `cargo.items` with `rare` = key in market rares or `KNOWN_RARES`.
- `norm(name)`: strips `$` prefix and `_name;` suffix, lowercases.

Route: `/api/journal` -> `get_commander_state` (the whole namespace).

## modules/history/module.py

`History(core)`: `version` counter bumped on live (non-replay) `FSDJump`, `CarrierJump`, `Location`, `StartJump`, and on `replay.done`; published as `history.version` so the UI knows to refetch. `compute(days)`: scans every journal file newer than `days` (0 = all) for lines containing `"StarPos"` or `"StartJump"`; builds `systems{name: {pos, visits, first, last, star_class, carrier}}` and `route[{name, ts, event, dist}]` with consecutive duplicates collapsed; star classes come from `StartJump.StarClass` keyed by system name. Cached on `(days, tuple of (file, mtime))`.

Route: `/api/history?days=` -> `get_travel_history`.

## modules/powerplay/module.py

`Powerplay(core)`: `power, merits, rank, time_pledged, session_merits, merit_log (last 20 gains)`, plus `cycle_end` (next Thursday 07:00 UTC) and `cycle_hours_left` recomputed on every `push()`. `LoadGame` resets the session counters; `PowerplayJoin/Defect/Leave` reset everything.

Route: `/api/powerplay` -> `get_powerplay_status` (adds `current_system` from the journal namespace).

## modules/merits/module.py

`Merits(core)`: attribution engine.

- `causes`: last 50 `(ts, activity, detail, credits)` from the `CAUSES` table (MarketSell -> rares or trade by `KNOWN_RARES`, Bounty, FactionKillBond, PVPKill, PowerplayDeliver/Collect, exploration sales, SellOrganicData, MissionCompleted, SearchAndRescue, DatalinkScan, DataScanned, SellMicroResources).
- `zone`: set by `SupercruiseDestinationDrop` whose `Type` contains `Warzone_Powerplay`; cleared by `SupercruiseEntry`, `FSDJump`, `Docked`.
- `last_target`: last `ShipTargeted` that had a `Ship` field.
- On `PowerplayMerits`: blame the newest cause within `WINDOW_S` (12 s). If the cause is a sale and the gain is more than 2.5x the expected `credits / RARE_RATE` and at least 500, relabel as `objective bonus`. Else if `zone` is set, label `combat zone` with the last target in the detail. Else `unattributed`.
- `summary()`: totals, `hours` since session start (or first gain), `per_hour`, `last_hour`, `by_activity{merits, events, per_event, share}`, `best`, `recent` (last 15, newest first).

Route: `/api/merits` -> `get_merits_summary`.

## modules/targets/module.py

- `find(q)`: defaults `power` to the pledged power and `ref` to the current system. Spansh station filters: `system_power`, `system_power_state: Unoccupied`, `has_market`, `type` (starports, or plus outposts when `pad=M`), `has_large_pad` when `pad=L`, `distance{min,max}`. Adds `jumps = ceil(distance / journal.jump_range)` and `refuses` = rares in the hold whose display name is not in the station's Spansh `market` list (None when the station has no market data). Stores the result in `targets.last`.
- `compare(q)`: for each of `POWERS`, the count and 3 nearest large-pad acquisition starports (cached 30 min).
- `/api/system?name=` -> `spansh_system`.

Routes: `find_sell_targets`, `compare_powers`, `get_system_info`.

## modules/combat/module.py

`find(q)`: `kind` in `contested | acquisition | undermining | reinforcement | all`, `ref`, `power`, `max` (radius, default 60), `limit`. Spansh systems filters per kind: contested/acquisition -> `power_state: Unoccupied` and `power: [power]`; undermining -> `power_state` in Exploited/Fortified/Stronghold (then drops systems controlled by `power`); reinforcement -> `controlling_power: [power]`. Contested pages through up to 25 x 100 results because qualifying systems are rare. A row is `zone_likely` when the power's `power_conflict_progress` >= `CONFLICT_THRESHOLD` (0.29) and at least one rival is too; `kind=contested` keeps only those. Unpopulated systems are skipped. Sort: kind order, then liveliest conflict, then distance.

Route: `/api/combat` -> `find_combat_systems`.

## modules/loop/module.py

`Loop(core)`: loads `loops.json` (`{id: {name, origin, note, stations[{system, station, type, ls, rares[{name, key}]}]}}`), selected loop persisted in `data/loop.json`. Fetches station coordinates from EDSM in a daemon thread at startup (so the bus handler never blocks). `recompute()` on `state.journal.cargo|system|docked|star_pos` and on replay done: per station, `tons` = cargo items whose key is in the station's rare keys or whose display name matches (case-insensitive), `dist` from `journal.star_pos` to the station's coords, `docked_here`, `done = tons > 0`; stations sorted by `(done, dist)`; `next` = first not done.

Routes: `/api/loop` -> `get_rares_loop`; `POST /api/loop/select` -> `select_rares_loop` (`id` required).

## modules/materials/module.py

`Materials(core)`: `data.json` has `caps` by grade (300/250/200/150/100), a `materials` catalog (`key, name, category, grade`), and `sources` hints keyed by material key plus `_general`. Inventory `inv{key: count}` is rebuilt from `Materials` and adjusted by `MaterialCollected`, `MaterialDiscarded`, `MaterialTrade` (Paid/Received), `EngineerCraft`/`Synthesis`/`TechnologyBroker`/`ScientificResearch` ingredients, `EngineerContribution` of type Materials, and `MissionCompleted.MaterialsReward`. `resolve(name)` accepts a journal key, an exact display name, a name seen in the journal, or a loose all-words match. Wishlist persisted in `data/wishlist.json` as `{key: {name, need, label}}`.

Routes: `/api/materials` (`get_materials`; `category`, `grade`, `only_wishlist`, `only_short`), `GET/POST /api/materials/wishlist` (`get_wishlist`, `set_wishlist` with `items`, `mode` replace|add|remove|clear, `label`), `/api/materials/sources?name=` (`material_sources`).

## modules/map/module.py

Only `/api/coords?names=a|b` -> `get_system_coords` and a `map.ready` flag. The drawing is in `web/card.js` (see docs/FRONTEND.md).

## web/app.js

See docs/FRONTEND.md. Exposes `window.Lab`, mounts cards from `/api/modules`, connects to `/events`, owns the layout engine (drag, resize, collapse, hide, presets, saved layouts) and the UI stall indicator.

## tests/test_elitelab.py

Builds a real `Core`, loads all modules, replays `tests/fixtures/journals/`, and calls tool functions directly (`core.http.tools[name].fn(q)`). `ELITELAB_OFFLINE=1` makes every network call raise; the loop module logs the failure and carries on without coordinates. See docs/TESTING.md.
