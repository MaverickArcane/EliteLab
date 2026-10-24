# State reference

Every namespace in the store, every key, its type, who writes it and who reads it. The browser mirrors all of this in `Lab.state[ns][key]` via SSE. Client-only namespaces (never on the server) are marked.

Conventions: `null` means unknown/not yet seen. Timestamps are the journal's ISO strings (`2026-10-23T02:14:28Z`). Credits are integers. Distances are light-years, floats.

## journal (module: journal)

| Key | Type | Source | Readers |
|---|---|---|---|
| `cmdr` | str | `Commander`, `LoadGame` | header, tools |
| `credits` | int | `LoadGame`, then `Status.json.Balance` | header, ship |
| `ship` | str display name | `LoadGame`, `Loadout`, `ShipyardSwap` (+ learned names) | header, ship card |
| `ship_name`, `ship_ident` | str | `LoadGame`, `Loadout` | header |
| `cargo_capacity` | int | `Loadout.CargoCapacity` | cargo card, targets (not yet) |
| `jump_range` | float | `Loadout.MaxJumpRange` (unladen) | fallback for jump estimates |
| `jump_range_now`, `jump_range_laden` | float or null | computed from the FSD (EDSY table: max fuel per jump, fuel multiplier and power, optimal mass from the `FSDOptimalMass` engineering modifier) and the ship mass: `now` = unladen + current fuel + current cargo (`Status.json`), burning at most the fuel in the tank; `laden` = unladen + full tank + full hold; plus a Guardian FSD booster's bonus. `jump_range_now` falls back to `jump_range` when the FSD is unknown, so it is the one key consumers read | targets, combat, farming, wishlist traders (jumps), ship card |
| `ship_info` | dict | `Loadout` | ship card |
| `ship_info.*` | `type, internal, id, name, ident, hull_value, modules_value, rebuy, hull_health (0..1), unladen_mass, cargo_capacity, max_jump_range, fuel_main, fuel_reserve, hot, module_count, core[{slot,item,engineering,level}], hardpoints[{slot,item}], modules[{slot, item (lower case), on, priority, health, engineering{blueprint, level, quality, experimental, engineer} | null}]` (cosmetic slots dropped) | | build module reads `modules` |
| `ship_internal` | str lower-case hull id (`smallcombat01_nx`) | `Loadout` | build module (same ship as the pinned build?) |
| `system` | str | `Location`, `FSDJump`, `CarrierJump`, `Docked` | everything |
| `star_pos` | [x,y,z] | `Location`, `FSDJump`, `CarrierJump` | loop distances, map ship marker |
| `station`, `station_type` | str or null | `Docked`, `Undocked`, `Location.Docked` | location card |
| `docked` | bool | same | loop `docked_here` |
| `system_power` | str or null | `ControllingPower` on jump/location | location, powerplay status |
| `system_power_state` | str or null | `PowerplayState` (Unoccupied/Exploited/Fortified/Stronghold) | location |
| `system_powers` | [str] | `Powers` | location |
| `carrier` | dict or null | `CarrierStats`, `CarrierLocation`, `CarrierJump`, backfill | carrier card, map carrier marker |
| `carrier.*` | `name, callsign, fuel (tritium), balance, free_space, cargo, docking, system, stats_time, services[str]` | | |
| `cargo` | `{count, items[{name, key, count, stolen, rare}], timestamp}` | `Cargo.json` | cargo card, loop, targets refusal check, merits |
| `market` | `{station, system, timestamp, rares_in_stock[{name, buy, stock}]}` | `Market.json` | market card |
| `status` | `{docked_flag, landed, supercruise, fsd_charging, fuel, cargo_tons, legal, timestamp}` | `Status.json` | location, ship |
| `feed` | `[{ts, event, text}]` newest first, max 40 | `FEED` table in the module | feed card |
| `last_event_time` | str | every event | header live pill |
| `game_version` | str | `Fileheader` | header |

## carrier (module: carrier)

| Key | Type | Meaning |
|---|---|---|
| `pinned` | object or null | Selected visitor carrier; null means show the existing owned-carrier view |
| `pinned.*` | `market_id, callsign, system, star_pos, services, docking, source, observed_at, last_seen, distance` | `distance` in Ly; `source` is `journal` or `Spansh`; unknown coordinates, distance and docking access are null |
| `visited` | list | Up to 50 `{market_id, callsign, system, last_seen}` choices from journal visits, newest visits first; includes the pin |
| `checked_at` | ISO string or null | Last completed remote check, including failures; not the observation time |
| `error` | string or null | Remote lookup failed; cached information remains visible |
| `refreshing` | bool | Remote request in progress |
| `offline` | bool | External lookups disabled by configuration |

Selection and observations persist in `data/carrier.json`. `last_seen` is the latest local visit; `observed_at` dates the displayed location report. Remote reports replace observations only when strictly newer. Owner data remains in `journal.carrier`; the visitor namespace never writes it. Docked, docked Location and docked CarrierJump events are matched by MarketID, not station name. The map card receives a `pinned-carrier` layer from the carrier card script.

## history (module: history)

| Key | Type | Notes |
|---|---|---|
| `version` | int | bumps on live jumps; the map refetches `/api/history` when it changes |

The data itself is not in the store (it can be thousands of rows). `GET /api/history?days=N` returns `{days, systems[{name, pos, visits, first, last, star_class, carrier}], route[{name, ts, event, dist}], total_ly, jumps}`.

## powerplay (module: powerplay)

| Key | Type | Notes |
|---|---|---|
| `power` | str or null | null = unpledged |
| `merits` | int or null | `TotalMerits` from the latest event |
| `rank` | int or null | |
| `time_pledged` | int seconds | from `Powerplay` at load |
| `session_merits` | int | sum of `MeritsGained` since `LoadGame` |
| `merit_log` | `[{ts, gained, total}]` last 20 | |
| `cycle_end` | ISO str | next Thursday 07:00 UTC |
| `cycle_hours_left` | float | |
| `powers` | [str] | the 12 powers, for dropdowns |

## merits (module: merits)

| Key | Type |
|---|---|
| `session_start` | ISO or null |
| `session_merits` | int |
| `hours` | float or null |
| `per_hour` | int or null |
| `last_hour` | int |
| `by_activity` | `{activity: {merits, events, per_event, share}}` |
| `best` | activity name or null |
| `unattributed` | int |
| `recent` | `[{ts, gained, activity, detail, total}]` newest first, 15 |
| `note` | str |

Activity names: `rares`, `trade`, `bounty hunting`, `combat zone`, `pvp`, `hauling`, `exploration`, `exobiology`, `missions`, `search and rescue`, `scans`, `odyssey trade`, `objective bonus`, `unattributed`.

## targets (module: targets)

| Key | Type |
|---|---|
| `last` | the last `find_sell_targets` response or null |

Response shape: `{count, results[{system, station, dist, jumps, ls, type, pad, pop, updated, government, x, y, z, economy, refuses[str] or null, accepts_all bool or null}], ref, power, min, max, pad, jump_range, hold_rares, jumps_note, refuses_note}`.

The card renders from `last` (so a search made by an AI tool call appears in the UI too). The only client-only key is `selected` (the selected row object, used by the map layer to draw the leg).

Materials totals are not in `journal`; see the `materials` namespace.

## combat (module: combat)

| Key | Type |
|---|---|
| `last` | the last `find_combat_systems` response or null |

Response: `{power, ref, kind, radius, jump_range, results[{kind, system, dist, jumps, state, controlling_power, security, population, allegiance, my_progress, zone_likely, conflict[{power, progress}], x, y, z}], hints{kind: text}, conflict_threshold, note}`.

## loop (module: loop)

| Key | Type |
|---|---|
| `id`, `name`, `note`, `origin` | loop identity |
| `stations` | `[{system, station, type, ls, rares[{name,key}], keys[str], tons, in_hold, dist, docked_here, done, coords{x,y,z} or null}]` sorted (done, dist) |
| `done_count`, `tons_total` | ints |
| `next` | `{system, station, dist}` or null |
| `complete` | bool |
| `available` | `[{id, name, origin}]` |

Client-side manual overrides live in `localStorage.loopManual` as `{system: {done, tons}}` and apply only while `tons` matches.

## materials (module: materials)

| Key | Type |
|---|---|
| `totals` | `{Raw, Manufactured, Encoded}` |
| `wishlist` | `{key: {name, need, label}}` |
| `shortfalls` | rows for wishlist entries: `{key, name, category, grade, cap, count, need, label, short}` |
| `inventory_count` | int distinct materials |
| `inventory_version` | int, bumped on every inventory change; wishlist and build recompute on `state.materials.inventory_version` and read the counts through the `get_material_inventory` tool (the dict itself stays out of the store so it is not sent over SSE on every pickup) |

`GET /api/materials` returns rows for every material in inventory or on the wishlist with the same row shape.

## recipes (module: recipes)

| Key | Type |
|---|---|
| `blueprints`, `experimentals` | int counts of the tables in `elitelab/core/engineering.json` |
| `rolls_per_grade` | `{1: 1, 2: 2, 3: 3, 4: 4, 5: 5}` planning hint |
| `modules`, `engineers` | sorted distinct names, for the card's filter selects |

The tables themselves are served by `/api/recipes` and `/api/recipes/get`, never pushed over SSE.

## wishlist (module: wishlist)

| Key | Type |
|---|---|
| `entries` | `[{id, kind (blueprint/experimental/unlock/material/build), key, name, module, grade, from_grade, qty, rolls, label, added, commodities?, broker?, materials, units, short, complete}]`; a `build` entry's needs are `build.progress.materials` |
| `needs` | `[{key, name, category, grade, family, cap, have, need, short}]`, short first |
| `summary` | `{entries, materials, short, units_short, complete}` |
| `trades` | `{trades[{category, ratio, same_family, give{key,name,grade,qty}, get{...}}], by_trader{type: {trades, give, get}}, unresolved[{key,name,grade,category,short,note?}], covered, reserve, note}` |
| `updated` | ISO timestamp of the last recompute |

Raw entries persist in `data/engineering_wishlist.json`; everything else is recomputed from the materials inventory (via `get_material_inventory`) on `state.materials.inventory_version` and `state.build.progress`. The card keeps a client-only `wishlist_ui.traders` with the last `find_material_traders` result.

## farming (module: farming)

| Key | Type |
|---|---|
| `sites` | `[{id, name, system, body, type, category, materials[keys], material_names[], surface[lat, lon], how, notes, coords{x,y,z}, dist, jumps, covers[names]}]`, nearest first; entries without a system are methods |
| `coords_ready` | bool, EDSM coordinates cached in `data/farm_coords.json` |

Recomputed on `state.journal.star_pos` (distances) and `state.wishlist.needs` (`covers` = wishlist shortfalls the site supplies).

## build (module: build)

| Key | Type |
|---|---|
| `pinned` | `{url, source (edsy | coriolis | slef), hash, name, ship, ship_fdname, slots, pinned_at}` or null; persisted in `data/build.json` |
| `progress` | null, or `{same_ship, current_ship, target_ship, slots[...], totals{slots, ok, fitted, to_buy, to_engineer, engineering_total, engineering_done, credits}, percent{fitted, engineered, materials, overall}, materials[{key, name, category, grade, have, need, short}], materials_short, wishlist_items[{item, grade, from_grade, qty}], not_in_build[{slot, item}], note}` |

`progress.slots[]`: `{group, slot, item, target, blueprint, grade, experimental, status (ok | engineer | buy), todo[], materials[{key, name, count}], current{slot, item, blueprint, level, experimental} | null, credits}`. Recomputed on `state.journal.ship_info` and `state.materials.inventory_version`.

## map (module: map)

| Key | Type |
|---|---|
| `ready` | true |

## Client-only runtime state (web/app.js)

- `Lab.coords`: `{systemName: {x,y,z}}` fetched for the carrier system and loop systems.
- `localStorage.layout.v1`: `{order[ids], spans{id: n}, heights{id: px}, hidden[ids], collapsed[ids], locked, pack}` (`pack` = dense packing, default true; `heights` caps a card's body height).
- `localStorage.farming.filter`: the farm sites card's filter, category and shortfall checkbox.
- `wishlist_ui` (client-only): `{traders, preselect{key, kind, module, at}}`.
- `farming_ui` (client-only): `{systems{site id: 'loading' | find_hge_systems result | {error}}}`.
- `localStorage.layouts.v1`: `{name: layout}` saved layouts.
- `localStorage.loopManual`: see loop.
