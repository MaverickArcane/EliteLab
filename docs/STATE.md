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
| `jump_range` | float | `Loadout.MaxJumpRange` (unladen) | targets/combat jump estimates |
| `ship_info` | dict | `Loadout` | ship card |
| `ship_info.*` | `type, internal, id, name, ident, hull_value, modules_value, rebuy, hull_health (0..1), unladen_mass, cargo_capacity, max_jump_range, fuel_main, fuel_reserve, hot, module_count, core[{slot,item,engineering,level}], hardpoints[{slot,item}]` | | |
| `system` | str | `Location`, `FSDJump`, `CarrierJump`, `Docked` | everything |
| `star_pos` | [x,y,z] | `Location`, `FSDJump`, `CarrierJump` | loop distances, map ship marker |
| `station`, `station_type` | str or null | `Docked`, `Undocked`, `Location.Docked` | location card |
| `docked` | bool | same | loop `docked_here` |
| `system_power` | str or null | `ControllingPower` on jump/location | location, powerplay status |
| `system_power_state` | str or null | `PowerplayState` (Unoccupied/Exploited/Fortified/Stronghold) | location |
| `system_powers` | [str] | `Powers` | location |
| `materials` | `{Raw, Manufactured, Encoded}` totals | `Materials`, `MaterialCollected` | (materials module has the detailed one) |
| `materials_detail` | `{cat: [[name, count], ...]}` | `Materials` | |
| `carrier` | dict or null | `CarrierStats`, `CarrierLocation`, `CarrierJump`, backfill | carrier card, map carrier marker |
| `carrier.*` | `name, callsign, fuel (tritium), balance, free_space, cargo, docking, system, stats_time, services[str]` | | |
| `cargo` | `{count, items[{name, key, count, stolen, rare}], timestamp}` | `Cargo.json` | cargo card, loop, targets refusal check, merits |
| `market` | `{station, system, timestamp, rares_in_stock[{name, buy, stock}]}` | `Market.json` | market card |
| `status` | `{docked_flag, landed, supercruise, fsd_charging, fuel, cargo_tons, legal, timestamp}` | `Status.json` | location, ship |
| `feed` | `[{ts, event, text}]` newest first, max 40 | `FEED` table in the module | feed card |
| `last_event_time` | str | every event | header live pill |
| `game_version` | str | `Fileheader` | header |

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

Client-only keys written by the card: `results, ref, power, count, selected` (the selected row object, used by the map layer to draw the leg).

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

`GET /api/materials` returns rows for every material in inventory or on the wishlist with the same row shape.

## map (module: map)

| Key | Type |
|---|---|
| `ready` | true |

## Client-only runtime state (web/app.js)

- `Lab.coords`: `{systemName: {x,y,z}}` fetched for the carrier system and loop systems.
- `localStorage.layout.v1`: `{order[ids], spans{id: n}, hidden[ids], collapsed[ids], locked}`.
- `localStorage.layouts.v1`: `{name: layout}` saved layouts.
- `localStorage.loopManual`: see loop.
