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

Game facts shared by modules (modules may not import each other, so shared facts live in core): `POWERS` (the 12 powers, Spansh spelling), `RARES` (journal key -> display name for all 142 rare goods, from EDCD FDevIDs `rare_commodity.csv`), `RARE_MARKETS` (key -> origin station market id), `KNOWN_RARES`, `RARE_NAMES`, `norm(name)` (strip `$`/`_name;`, lowercase), `is_rare(key_or_name)`.

Engineering, loaded from `engineering.json` next to it: `MATERIALS` / `MATERIAL_BY_KEY` / `MATERIAL_BY_NAME` (`key, name, category, grade, family`; family is the trader group, null for Guardian/Thargoid), `MATERIAL_CAPS` (grade -> 300/250/200/150/100), `BLUEPRINTS` / `BLUEPRINT_BY_KEY` (`key` like `FSD_LongRange`, `name`, `module`, `aliases`, `max_grade`, `grades{"1".."5": {material key: count}}`, `engineers{name: max grade}`), `EXPERIMENTALS` / `EXPERIMENTAL_BY_KEY` (`key` like `special_fsd_heavy`, `name`, `modules`, `ingredients`), `ROLLS_PER_GRADE`, `TRADE`.

- `tokens(text)`: query words minus filler ('engineered', 'blueprint', 'for').
- `resolve_material(name)`: key, exact name, or a loose all-words match that hits exactly one material.
- `find_recipes(query, kind, module, engineer, limit)`: every query word must prefix-match a word of the recipe's module, name, key or aliases; exact words score 2, prefixes 1; ties go to blueprints, then fewer words. `engineer` matches engineer-name words and adds `engineer_grade`. `module` is exact when it is a known module name (so "Frame shift drive" excludes the interdictor) and word-prefix otherwise. `RECIPE_MODULES` and `ENGINEERS` are the distinct lists for UI filters. `resolve_recipe()` returns `{"match"}` only for a single hit or a strict top score, else `{"candidates"}`; an exact key always matches.
- `recipe_cost(key, grade, from_grade, rolls, qty)`: sums `grades[g] * rolls[g]` for `g` in `from_grade+1..grade` (blueprint) or `ingredients * qty` (experimental).
- `trade_ratio(give, get)`: `(give, get)` in lowest terms: same family 1->3 per grade down, 6->1 per grade up; a different family multiplies the give side by 6; `None` across categories or without a family.

`UNLOCKS` / `UNLOCK_BY_KEY` are technology broker recipes (`{key, name, module, broker (Guardian | Human), ingredients{material key: n}, commodities{name: n}}`); they take part in `find_recipes` (kind `unlock`) and `recipe_cost` (materials only). `BLUEPRINT_BY_LOWER` / `EXPERIMENTAL_BY_LOWER` map journal and EDSY spellings to keys.

`engineering.json` was generated from EDCD coriolis-data (blueprints, specials, modules), EDCD FDevIDs `material.csv` (families, Thargoid and Guardian materials) and a community tech broker table; see docs/DECISIONS.md. Edit it by hand when the game changes; keep keys as journal names.

## elitelab/core/edsy.py

Decoder for EDSY build links (`#/L=<hash>`, hash versions 15 to 20), with EDSY's tables in `edsy.json` (ships, modules, module types with their blueprint and effect index lists, blueprints, effects; extracted from EDSY's `eddb.js`). `extract_hash(text)` accepts a URL, fragment or bare hash. `decode(text)` returns `{version, ship{id, fdname, name}, name, tag, hash, slots[{group, index, slot, module{id, fdname, name, class, rating, mount, mtype, cost}, blueprint{fdname, name} | None, grade, roll, experimental{fdname, name} | None, preengineered, powered, priority}]}`. Modified-attribute values are skipped (only the blueprint, grade and effect matter for materials). `slot_name()` reconstructs journal-style slot names (`LargeHardpoint2`, `Slot03_Size6`...) for display; the build module never relies on them outside the core slots. Hull (bulkhead) module ids have ship-specific fdnames and are resolved through the ship's module table.

`MODULE_BY_FDNAME` (journal item -> EDSY module incl. ship-specific bulkheads) and `SHIP_BY_FDNAME` serve the other build sources. FSD entries also carry `fsdoptmass, maxfuel, fuelmul, fuelpower` and Guardian boosters `jumpbst`; `jump_range(fsd_item, optmass, mass, booster_item)` is the single-jump range formula `(maxfuel / fuelmul) ** (1 / fuelpower) * optmass / mass + boost`, which reproduces the journal's `MaxJumpRange` when mass is unladen plus one jump's fuel.

Format summary: EDSY base-64 alphabet `0-9A-Za-z_-`, 6 bits per character. Build: version (1), ship id (1), hull discount (1), hull cost bits (1) + cost (2-5), crew (1), distributor (2), cargo hatch module; then one comma-separated chunk per group (hardpoint, utility, component, military, internal). Per fitted slot: module id (3), slot bits (1: 0x20 costed, 0x10 engineered, 0x08 unpowered, 0x07 priority), cost bits + cost or discount (1), and when engineered: engineering bits (2: 0x800 pre-engineered, 0x780 blueprint index, 0x070 grade, 0x00F effect index), roll (2), modifier count (1), modifiers (4 each). A module id >= 199900 is a gap of that many empty slots. Chunks 6 and 7 are the build name and tag in EDSY's text encoding.

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

## elitelab/core/coords.py

`CoordCache(core, label, cache_file=None, on_update=None)`: EDSM coordinates for a set of system names, shared by loop and farming. `request(names)` adds names and starts one daemon-thread fetch unless one is running or nothing is missing (no-op under `ELITELAB_OFFLINE`); `get(name)` returns `{x,y,z}` or None; `ready` is true once anything is known. After an answer, names EDSM did not return are stored as None so they are never asked again; a failed call retries with back-off (5 s doubling to 300 s). `cache_file` persists the dict under the data dir; `on_update()` runs after every fetch (loop's `recompute`, farming's `publish`).

## elitelab/core/coriolis.py

Decoder for Coriolis links (`/outfit/<ship>?code=<code>&bn=<name>`), tables in `coriolis.json` (from EDCD/coriolis-data: ships with slot layouts and bulkheads, modules by 2-char id per group, blueprint and special ids). `parse_link()` also accepts the older `/outfit/<ship>/<code>` path. `decode()` returns the EDSY shape. The code is `<version letter><bulkhead index><2 chars per slot or '-'>` over standard (pp, t, fsd, ls, pd, s, ft), then hardpoints (utility mounts are size 0), then internals (Military slots and the planetary approach suite are typed entries in the ship's slot list). The fourth dot-separated part is the modifications blob: gzip of int8 slot id, then int8 record id + 4-byte value until -1, where -2/-3/-4 carry blueprint id, grade and special id; slot ids count bulkheads as 0. Ship-specific armour fdnames come from the EDSY ship table (grade order 40131, 40122, 40113, 40114, 40115). Module display names fall back to EDSY's table (coriolis-data has none for most weapons).

## elitelab/core/builds.py

`parse(text)`: the one entry point for `pin_build`. JSON (SLEF `[{header, data}]` or a bare Loadout event) -> `from_loadout()`; `L=<hash>` -> `edsy.decode`; `/outfit/` -> `coriolis.decode`; otherwise EDSY again for its error message. Adds `source` (`edsy`, `coriolis`, `slef`). `group_of(slot)` maps journal slot names to EDSY groups (used by the build module too). `from_loadout()` drops cosmetic slots and resolves blueprint and effect display names through `gamedata`.

## elitelab/mcp.py (prompts and resources)

Besides tools, the stdio server advertises `resources` and `prompts`. `resources/list` returns `elitelab://state` (the whole snapshot) and `elitelab://state/<ns>` per namespace (from `/api/state`); `resources/read` returns the JSON; `resources/templates/list` has the namespace template. `PROMPTS` holds three prompt recipes (`plan_rares_run`, `engineering_plan` with a `goal` argument, `where_am_i`), each a user message that tells the model which tools to call and what to produce.

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

`Loop(core)`: loads `loops.json` (`{id: {name, origin, note, stations[{system, station, type, ls, rares[{name, key}]}]}}`), selected loop persisted in `data/loop.json`. Station coordinates come from a `CoordCache` (core/coords.py) requested at startup and on `select`, so the bus handler never blocks. `recompute()` on `state.journal.cargo|system|docked|star_pos` and on replay done: per station, `tons` = cargo items whose key is in the station's rare keys or whose display name matches (case-insensitive), `dist` from `journal.star_pos` to the station's coords, `docked_here`, `done = tons > 0`; stations sorted by `(done, dist)`; `next` = first not done.

Routes: `/api/loop` -> `get_rares_loop`; `POST /api/loop/select` -> `select_rares_loop` (`id` required).

## modules/materials/module.py

`Materials(core)`: catalog and caps come from `gamedata` (`MATERIAL_BY_KEY`, `MATERIAL_CAPS`); `data.json` only has `sources` hints keyed by material key plus `_general`. The inventory dict is not published to the store (it would ride SSE on every pickup); instead `inventory_version` is bumped on each publish and other modules call the `get_material_inventory` tool (`/api/materials/inventory`, `{inventory{key: count}, version}`) through `core.http.tools`. `resolve(name)` delegates to `gamedata.resolve_material` first, then names seen in the journal, then a loose match. Inventory `inv{key: count}` is rebuilt from `Materials` and adjusted by `MaterialCollected`, `MaterialDiscarded`, `MaterialTrade` (Paid/Received), `EngineerCraft`/`Synthesis`/`TechnologyBroker`/`ScientificResearch` ingredients, `EngineerContribution` of type Materials, and `MissionCompleted.MaterialsReward`. `resolve(name)` accepts a journal key, an exact display name, a name seen in the journal, or a loose all-words match. Wishlist persisted in `data/wishlist.json` as `{key: {name, need, label}}`.

Routes: `/api/materials` (`get_materials`; `category`, `grade`, `only_wishlist`, `only_short`), `GET/POST /api/materials/wishlist` (`get_wishlist`, `set_wishlist` with `items`, `mode` replace|add|remove|clear, `label`), `/api/materials/sources?name=` (`material_sources`).

`web/card.js`: totals per category, distinct count, and a filterable inventory list (text + category) fetched from `/api/materials`; counts at cap are highlighted. The flat wishlist is API-only now (the engineering wishlist card is the one people use).

## modules/recipes/module.py

Read-only view of the `gamedata` engineering tables; state only carries counts so the tables never go over SSE. `mats(ingredients)` turns `{key: n}` into named rows sorted by category and grade; `detail(hit, grade, from_grade, qty)` builds the blueprint response (`grades` per roll, `engineers`, `total` via `recipe_cost`) or the experimental one.

Routes: `/api/recipes` -> `list_recipes` (`query`, `kind`, `module`, `engineer`, `limit`; `engineer` keeps only blueprints that engineer offers and adds `engineer_grade`); `/api/recipes/get` -> `get_recipe` (`key` or free text, `grade`, `from_grade`, `qty`, `kind`, `module`; an ambiguous query returns `{error, candidates}`).

`web/card.js`: reference only. Search box with a 250 ms debounce plus module, kind (blueprints, effects, unlocks) and engineer selects (filled from `recipes.modules` / `recipes.engineers`); any filter alone lists everything that matches, up to 60 rows. A row expands to the per-grade materials (or an unlock's materials and cargo); "+ wishlist" hands the recipe to the wishlist card's picker through `wishlist_ui.preselect`, where grades and quantity are chosen.

## modules/wishlist/module.py

`Wishlist(core)`: `entries` persisted raw in `data/engineering_wishlist.json`; everything else is recomputed by `compute()` on every `state.materials.inventory` change and on every edit. `parse_item(text)` pulls quantity (`2x`, `x2`, leading number) and grade (`g5`, `grade 5`, trailing 1-5) out of free text. `_add()` resolves in this order: exact recipe key, exact material name, recipe search (`resolve_recipe`); a tie returns `status: ambiguous` with candidates and adds nothing. Blueprints default to `max_grade` from `from_grade` 0; `rolls` can override the per-grade roll counts.

`plan_trades(rows, inv, reserve)`: surplus = have - need - reserve for every material with a trader family; every (donor, shortfall) pair that `trade_ratio` allows is sorted by cost (give/get), then higher target grade, then bigger surplus, and filled greedily so a 6:1 same-family trade is never starved by a 36:1 cross-family one. Receives are capped at `cap - have`. Output: `trades`, `by_trader` (per Raw/Manufactured/Encoded), `unresolved` (still short, or not tradeable), `covered`.

`traders(q)`: Spansh station search with `material_trader: [type]` (values `Raw`, `Manufactured`, `Encoded`), one thread per type, `ttl=1800`; default types are the ones in the current trade plan.

`parse_item` also understands grade ranges: `2-5`, `g2 to g5`, `from g2` set `from_grade` (the module's current grade) and the target. `kind: unlock` entries carry `commodities` (cargo the broker also wants; not tracked) and `broker`. `kind: build` (item `build`) is the pinned build as one entry: `entry_needs` reads `build.progress.materials` at compute time and the module recomputes on `state.build.progress`, so the entry shrinks as the ship gets fitted and engineered; only one build entry exists at a time.

Routes: `/api/wishlist` -> `get_engineering_wishlist` (`reserve`); `POST /api/wishlist/add` -> `wishlist_add` (`item` required, `qty`, `grade`, `from_grade`, `kind`, `module`, `rolls`, `label`); `POST /api/wishlist/remove` -> `wishlist_remove` (`id` comma-separated or `all`); `/api/wishlist/trades` -> `plan_material_trades`; `/api/wishlist/traders` -> `find_material_traders` (`types`, `ref`, `limit`, `pad`); `/api/wishlist/options` -> `wishlist_options` (pick-lists: modules with blueprint and effect keys, unlocks, materials by category).

`web/card.js`: no free text for people. A structured picker: kind (blueprint, experimental effect, tech broker unlock, material, pinned build) -> module or category -> blueprint/effect/unlock/material -> from grade and to grade (blueprints only; "to" defaults to the max) -> quantity. Posts exact keys to `wishlist_add`, so nothing is ambiguous. The recipes card's "+ wishlist" sets `wishlist_ui.preselect` and this card selects that recipe in the picker. Then entries with ready/short tags and remove buttons, the materials table (short by default, "all" toggle), the trader plan, and a "nearest traders" button that stores its result in the client-only `wishlist_ui` namespace. Free text remains for the AI tool path only.

## modules/farming/module.py

`Farming(core)`: `sites.json` (`{sites: [{id, name, system, body, type, category, materials[keys], surface, how, notes}]}`; sites with `system: null` are methods such as High Grade Emissions by state). System coordinates come from a `CoordCache` (see core/coords.py) cached in `data/farm_coords.json`. `rows(material, category, type_, max_dist, for_wishlist)` filters, adds `dist`/`jumps` from `journal.star_pos` and `covers` (wishlist shortfalls the site supplies, from `wishlist.needs`), nearest first with method entries last. Publishes on `state.journal.star_pos`, `state.wishlist.needs` and replay done.

Routes: `/api/farming` -> `find_farm_sites` (`material`, `category`, `type`, `max_dist`, `for_wishlist`, `limit`); `/api/farming/systems` -> `find_hge_systems` (`site` = an HGE entry id whose `spansh` query in sites.json gives the controlling-faction states and/or allegiance, or `state` / `allegiance` directly; `ref`, `min_pop` default 1,000,000, `limit`). Uses `services.spansh_systems()` (population, `controlling_minor_faction_state`, `allegiance` filters, nearest first, 30 min cache).

`web/card.js`: text filter, category select and an "only my shortfalls" checkbox (remembered in `localStorage.farming.filter`), expandable how-to per site, copy/Inara buttons, a "find systems" button on HGE entries (result kept per site in the client-only `farming_ui.systems`), and a `farming` map layer (off by default) with sites that cover a shortfall drawn red.

## modules/build/module.py

`Build(core)`: `pin(url)` decodes an EDSY link, a Coriolis link or SLEF/Loadout JSON with `elitelab.core.builds.parse()` and persists `{url, source, hash, name, ship, ...}` in `data/build.json` (the raw text is re-parsed at startup). `compute()` compares the target slots with `journal.ship_info.modules`: core slots by journal slot name, every other group as a multiset by item (`group_of(slot)` maps journal slot names to EDSY groups; the best candidate is the one sharing the blueprint, grade and effect). Verdicts: `buy` (item not aboard; `credits` = EDSY list price), `engineer` (same item, blueprint missing or below the target grade, or effect missing), `ok`. Materials per row come from `gamedata.recipe_cost(blueprint, grade, from_grade)` where `from_grade` is the current level when the module already carries the same blueprint, plus the effect's cost; `wishlist_items` aggregates them. Blueprint and effect names are matched case-insensitively through `BLUEPRINT_BY_LOWER` / `EXPERIMENTAL_BY_LOWER` (journal `BlueprintName` and EDSY `fdname` share the spelling).

`to_wishlist()` calls the wishlist module's tools through `core.http.tools` (never an import): `wishlist_add item=build kind=build`, which the wishlist stores as one entry whose needs are read live from `build.progress.materials` (and it removes older per-blueprint entries labelled `build: <name>`). Raises when the wishlist module is not loaded.

Routes: `/api/build` -> `get_build_progress`; `POST /api/build/pin` -> `pin_build` (`url`); `POST /api/build/unpin` -> `unpin_build`; `POST /api/build/wishlist` -> `build_to_wishlist`.

`web/card.js`: link/JSON input, four progress bars (overall, fitted, engineered, materials), a one-line-per-slot table (to-do rows by default, "all" toggle; the full to-do text is the row tooltip), the materials table (short by default), and header buttons "track in wishlist" and "unpin". View toggles live in a closure so renders keep them.

## modules/map/module.py

Only `/api/coords?names=a|b` -> `get_system_coords` and a `map.ready` flag. The drawing is in `web/card.js` (see docs/FRONTEND.md).

## web/app.js

See docs/FRONTEND.md. Exposes `window.Lab`, mounts cards from `/api/modules`, connects to `/events`, owns the layout engine (drag, resize, collapse, hide, presets, saved layouts) and the UI stall indicator.

## tests/test_elitelab.py

Builds a real `Core`, loads all modules, replays `tests/fixtures/journals/`, and calls tool functions directly (`core.http.tools[name].fn(q)`). `ELITELAB_OFFLINE=1` makes every network call raise; the loop module logs the failure and carries on without coordinates. See docs/TESTING.md.
