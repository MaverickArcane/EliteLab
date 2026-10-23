# JSON API

All endpoints are `GET`, return JSON, and send `Cache-Control: no-store`. Errors are `{"error": "message"}` with status 500 (or 404 for unknown paths).

## `GET /api/health`

```json
{"ok": true, "version": "0.3.0", "journal_dir": "...", "journal_found": true}
```

## `GET /api/state`

The whole live picture. Key fields:

| Field | Type | Source |
|---|---|---|
| `cmdr`, `credits`, `ship`, `ship_name`, `ship_ident` | str / int | `LoadGame`, `Loadout`, `Status.json` |
| `cargo_capacity`, `jump_range` | int / float | `Loadout` |
| `system`, `star_pos` (`[x,y,z]`), `station`, `station_type`, `docked` | | `Location`, `FSDJump`, `Docked`, `Undocked` |
| `system_power`, `system_power_state`, `system_powers` | | Powerplay fields on `Location` / `FSDJump` |
| `power`, `merits`, `rank`, `time_pledged` (s) | | `Powerplay*` events; `null` when unpledged |
| `materials` `{Raw, Manufactured, Encoded}` totals, `materials_detail` | | `Materials`, `MaterialCollected` |
| `carrier` `{name, callsign, system, fuel, balance, free_space, cargo, docking, services, stats_time}` | | `CarrierStats`, `CarrierLocation`, `CarrierJump` |
| `cargo` `{count, items[{name,key,count,stolen,rare}]}` | | `Cargo.json` |
| `market` `{station, system, timestamp, rares_in_stock[{name,buy,stock}]}` | | `Market.json` |
| `status` `{docked_flag, landed, supercruise, fsd_charging, fuel, cargo_tons, legal}` | | `Status.json` flags |
| `feed` `[{ts, event, text}]` newest first, max 30 | | see `FEED_EVENTS` in `journal.py` |
| `powers` | list | the Powerplay powers, for UI dropdowns |
| `last_event_time`, `game_version`, `generated`, `journal_dir`, `journal_ok` | | |

## `GET /api/history?days=30`

Visited systems and the route between them, from every journal newer than `days` (`0` = all time). Cached until a journal file changes.

```json
{"days": 30, "jumps": 212, "total_ly": 6130.4,
 "systems": [{"name": "Leesti", "pos": [72.75, 48.75, 68.25], "visits": 9, "first": "...", "last": "...", "star_class": "K", "carrier": false}],
 "route":   [{"name": "Leesti", "ts": "...", "event": "FSDJump", "dist": 5.2}]}
```

`route` is chronological with consecutive duplicates collapsed; `event` is `FSDJump`, `CarrierJump` or `Location`.

## `GET /api/targets?power=&ref=&min=&max=&pad=`

Stations with a market in **Unoccupied** systems that `power` can acquire, nearest `ref` first.

- `power`: exact power name (default `Edmund Mahon`)
- `ref`: reference system (default `Leesti`)
- `min`, `max`: distance band in Ly (optional)
- `pad`: `L` for large starports only (default) or `M` to include outposts

```json
{"count": 386, "ref": "Leesti", "power": "Edmund Mahon",
 "results": [{"system": "...", "station": "...", "dist": 125.2, "ls": 1143, "type": "Orbis Starport",
              "pad": "L", "pop": 107263894, "updated": "2026-10-19T10:28:50Z", "x": .., "y": .., "z": .., "economy": "..."}]}
```

## `GET /api/powers?ref=`

For every power: number of large-pad acquisition starports and the three nearest to `ref`. First call takes ~20 s (12 Spansh queries), cached 30 min.

## `GET /api/system?name=`

Spansh summary for one system: `power_state`, `controlling_power`, `powers`, `population`, `allegiance`, coordinates.

## `GET /api/coords?names=A|B|C`

EDSM coordinates, pipe-separated names. Returns `{name: {x, y, z}}` for systems EDSM knows.
