# API / AI tools

Generated from `GET /api/schema` (EliteLab 0.4.0). Every tool is an HTTP route: `GET` with query parameters or `POST` with a JSON body. Responses are JSON; errors are `{"error": "..."}`. `GET /events` streams state changes as Server-Sent Events (`snapshot` then `state` events).

## `health`  ·  `GET /api/health`  ·  module: core

Server health, version, journal folder and loaded modules.

## `get_state`  ·  `GET /api/state`  ·  module: core

Full live state snapshot: every module namespace (journal, powerplay, loop, materials...). Large; prefer the specific tools when you only need one thing.

## `list_modules`  ·  `GET /api/modules`  ·  module: core

Loaded modules with what they require/provide and their UI cards.

## `list_tools`  ·  `GET /api/schema`  ·  module: core

Every API route that is exposed as an AI tool, with parameter schemas.

## `get_recent_events`  ·  `GET /api/events`  ·  module: core

Most recent raw journal events (newest first). Useful to see exactly what the game just did.

| Parameter | Type | Description |
|---|---|---|
| `limit` | integer | How many events (max 200) (default `30`) |
| `event` | string | Only this event type, e.g. MarketSell |

## `get_commander_state`  ·  `GET /api/journal`  ·  module: journal

Live commander state from the journal: name, credits, ship, cargo capacity and jump range, current system/station, docked flag, Powerplay control of the current system, cargo with rare goods tagged, rares in stock at the last market opened, fleet carrier summary, materials totals, and the recent event feed.

## `get_travel_history`  ·  `GET /api/history`  ·  module: history

Systems visited and the chronological route, with star class, visit counts, coordinates, total jumps and light-years.

| Parameter | Type | Description |
|---|---|---|
| `days` | integer | Look back this many days; 0 = all time (default `30`) |

## `get_powerplay_status`  ·  `GET /api/powerplay`  ·  module: powerplay

Pledged power, rank, total merits, merits earned this session with a log of recent gains, days pledged, when the weekly cycle ends, and who controls the current system.

## `get_merits_summary`  ·  `GET /api/merits`  ·  module: merits

Where this session's Powerplay merits came from (rares, trade, bounty hunting, combat zone bonds, hauling, exploration, missions, objective bonuses), merits per hour overall and in the last hour, merits per event, and a recent log. Use it to compare activities with real numbers.

## `find_sell_targets`  ·  `GET /api/targets`  ·  module: targets

Stations with a market in Unoccupied systems that a power can acquire (where Powerplay trade and rare goods sales earn merits), nearest the reference system first. Rare goods pay best 125-165 Ly from where they were bought. Includes market data age so stale stations can be avoided.

| Parameter | Type | Description |
|---|---|---|
| `power` | string | Power name; default = the pledged power (one of `Edmund Mahon`, `Li Yong-Rui`, `Aisling Duval`, `Pranav Antal`, `Denton Patreus`, `Nakato Kaine`, `Felicia Winters`, `Jerome Archer`, `Zemina Torval`, `Yuri Grom`, `A. Lavigny-Duval`, `Archon Delaine`) |
| `ref` | string | Reference system; default = current system |
| `min` | number | Minimum distance in Ly |
| `max` | number | Maximum distance in Ly |
| `pad` | string | L = large starports only (default), M = include outposts (default `L`; one of `L`, `M`) |
| `limit` | integer | Max results (<=100) (default `40`) |

## `compare_powers`  ·  `GET /api/powers`  ·  module: targets

For every Powerplay power: how many large-pad acquisition starports exist and the three nearest to the reference system. Use it to choose a power to pledge to. Slow on first call (~20 s).

| Parameter | Type | Description |
|---|---|---|
| `ref` | string | Reference system; default = current system |

## `get_system_info`  ·  `GET /api/system`  ·  module: targets

Spansh summary of a system: controlling power, Powerplay state, powers present, population, allegiance, coordinates.

| Parameter | Type | Description |
|---|---|---|
| `name` | string | System name; default = current system |

## `find_combat_systems`  ·  `GET /api/combat`  ·  module: combat

Systems near the reference where combat earns Powerplay merits for the pledged power. kind=contested: acquisition systems two or more powers are fighting over (Powerplay combat zones); acquisition: bounty hunting pays +5%; undermining: rival-controlled systems where killing the controlling power's ships pays; reinforcement: your own systems (-35%). Includes security, population, conflict progress per power, distance and jumps.

| Parameter | Type | Description |
|---|---|---|
| `kind` | string | contested (default), acquisition, undermining, reinforcement or all (default `contested`; one of `contested`, `acquisition`, `undermining`, `reinforcement`, `all`) |
| `ref` | string | Reference system; default = current system |
| `power` | string | Power; default = pledged power |
| `max` | number | Search radius in Ly (default `60`) |
| `limit` | integer | Max results (<=100) (default `25`) |

## `get_rares_loop`  ·  `GET /api/loop`  ·  module: loop

The active rare goods loop: each station with its rares, tons already in the hold, distance from the ship, whether docked there, and the recommended next stop. Stations tick done when their rare is aboard.

## `select_rares_loop`  ·  `POST /api/loop/select`  ·  module: loop

Switch the active rare goods loop.

| Parameter | Type | Description |
|---|---|---|
| `id` | string | Loop id, see get_rares_loop.available (**required**) |

## `get_materials`  ·  `GET /api/materials`  ·  module: materials

Engineering materials inventory with grade, cap (300/250/200/150/100 for G1-G5), wishlist need and shortfall per material.

| Parameter | Type | Description |
|---|---|---|
| `category` | string | Raw, Manufactured or Encoded (one of `Raw`, `Manufactured`, `Encoded`) |
| `grade` | integer | 1-5 |
| `only_wishlist` | boolean | Only materials on the wishlist (default `False`) |
| `only_short` | boolean | Only materials where need exceeds stock (default `False`) |

## `get_wishlist`  ·  `GET /api/materials/wishlist`  ·  module: materials

The materials wishlist with have/need/short for each entry.

## `set_wishlist`  ·  `POST /api/materials/wishlist`  ·  module: materials

Set the materials wishlist, e.g. everything needed for a blueprint. Names may be display names ('Datamined Wake Exceptions') or journal keys. The dashboard then shows shortfalls live as materials are collected.

| Parameter | Type | Description |
|---|---|---|
| `items` | object | Map of material name -> quantity needed (**required**) |
| `mode` | string | replace (default), add (increase needs), remove (drop these), clear (empty the list first) (default `replace`; one of `replace`, `add`, `remove`, `clear`) |
| `label` | string | What this is for, e.g. 'FSD G5 Increased Range x3' |

## `material_sources`  ·  `GET /api/materials/sources`  ·  module: materials

Where to farm a material: community-known sites and the general approach, plus current stock and cap.

| Parameter | Type | Description |
|---|---|---|
| `name` | string | Material display name or key (**required**) |

## `get_system_coords`  ·  `GET /api/coords`  ·  module: map

Galactic coordinates for one or more systems (EDSM).

| Parameter | Type | Description |
|---|---|---|
| `names` | string | System names separated by a pipe character (**required**) |

