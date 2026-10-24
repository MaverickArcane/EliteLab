# API / AI tools

Generated from `GET /api/schema` (EliteLab 0.4.0). Every tool is an HTTP route: `GET` with query parameters or `POST` with a JSON body. Responses are JSON; errors are `{"error": "..."}`. `GET /events` streams state changes as Server-Sent Events (`snapshot` then `state` events).

## `health`  -  `GET /api/health`  -  module: core

Server health, version, journal folder and loaded modules.

## `get_state`  -  `GET /api/state`  -  module: core

Full live state snapshot: every module namespace (journal, powerplay, loop, materials...). Large; prefer the specific tools when you only need one thing.

## `list_modules`  -  `GET /api/modules`  -  module: core

Loaded modules with what they require/provide and their UI cards.

## `list_tools`  -  `GET /api/schema`  -  module: core

Every API route that is exposed as an AI tool, with parameter schemas.

## `get_recent_events`  -  `GET /api/events`  -  module: core

Most recent raw journal events (newest first). Useful to see exactly what the game just did.

| Parameter | Type | Description |
|---|---|---|
| `limit` | integer | How many events (max 200) (default `30`) |
| `event` | string | Only this event type, e.g. MarketSell |

## `get_commander_state`  -  `GET /api/journal`  -  module: journal

Live commander state from the journal: name, credits, ship (with loadout summary), cargo capacity and jump range, current system/station, docked flag, Powerplay control of the current system, cargo with rare goods tagged, rares in stock at the last market opened, fleet carrier summary, and the recent event feed. Materials live in get_materials.

## `get_travel_history`  -  `GET /api/history`  -  module: history

Systems visited and the chronological route, with star class, visit counts, coordinates, total jumps and light-years.

| Parameter | Type | Description |
|---|---|---|
| `days` | integer | Look back this many days; 0 = all time (default `30`) |

## `get_powerplay_status`  -  `GET /api/powerplay`  -  module: powerplay

Pledged power, rank, total merits, merits earned this session with a log of recent gains, days pledged, when the weekly cycle ends, and who controls the current system.

## `get_merits_summary`  -  `GET /api/merits`  -  module: merits

Where this session's Powerplay merits came from (rares, trade, bounty hunting, combat zone bonds, hauling, exploration, missions, objective bonuses), merits per hour overall and in the last hour, merits per event, and a recent log. Use it to compare activities with real numbers.

## `find_sell_targets`  -  `GET /api/targets`  -  module: targets

Stations with a market in Unoccupied systems that a power can acquire (where Powerplay trade and rare goods sales earn merits), nearest the reference system first. Rare goods pay best 125-165 Ly from where they were bought. Includes market data age so stale stations can be avoided.

| Parameter | Type | Description |
|---|---|---|
| `power` | string | Power name; default = the pledged power (one of `Edmund Mahon`, `Li Yong-Rui`, `Aisling Duval`, `Pranav Antal`, `Denton Patreus`, `Nakato Kaine`, `Felicia Winters`, `Jerome Archer`, `Zemina Torval`, `Yuri Grom`, `A. Lavigny-Duval`, `Archon Delaine`) |
| `ref` | string | Reference system; default = current system |
| `min` | number | Minimum distance in Ly |
| `max` | number | Maximum distance in Ly |
| `pad` | string | L = large starports only (default), M = include outposts (default `L`; one of `L`, `M`) |
| `limit` | integer | Max results (<=100) (default `40`) |

## `compare_powers`  -  `GET /api/powers`  -  module: targets

For every Powerplay power: how many large-pad acquisition starports exist and the three nearest to the reference system. Use it to choose a power to pledge to. Slow on first call (~20 s).

| Parameter | Type | Description |
|---|---|---|
| `ref` | string | Reference system; default = current system |

## `get_system_info`  -  `GET /api/system`  -  module: targets

Spansh summary of a system: controlling power, Powerplay state, powers present, population, allegiance, coordinates.

| Parameter | Type | Description |
|---|---|---|
| `name` | string | System name; default = current system |

## `find_combat_systems`  -  `GET /api/combat`  -  module: combat

Systems near the reference where combat earns Powerplay merits for the pledged power. kind=contested: systems where your power AND a rival are both past the ~29% conflict threshold and nobody is past 100%, the only place Powerplay combat zones exist (zone_likely=true), sorted by closest race; acquisition: bounty hunting pays +5%; undermining: rival-controlled systems where killing the controlling power's ships pays; reinforcement: your own systems (-35%). Includes Spansh data age, security, population, conflict progress per power, distance, jumps, and any zones your own journal has recorded there.

| Parameter | Type | Description |
|---|---|---|
| `kind` | string | contested (default), acquisition, undermining, reinforcement or all (default `contested`; one of `contested`, `acquisition`, `undermining`, `reinforcement`, `all`) |
| `ref` | string | Reference system; default = current system |
| `power` | string | Power; default = pledged power |
| `max` | number | Search radius in Ly (default `60`) |
| `limit` | integer | Max results (<=100) (default `25`) |

## `get_conflict_zones_seen`  -  `GET /api/combat/zones`  -  module: combat

Powerplay conflict zones recorded from your own journal: the zones (by intensity and count) in the current system right now, and every system where zones were seen with when and how hot. This is live and exact, unlike Spansh-derived guesses; scout a candidate system and this tells you what is there.

## `get_rares_loop`  -  `GET /api/loop`  -  module: loop

The active rare goods loop: each station with its rares, tons already in the hold, distance from the ship, whether docked there, and the recommended next stop. Stations tick done when their rare is aboard.

## `select_rares_loop`  -  `POST /api/loop/select`  -  module: loop

Switch the active rare goods loop.

| Parameter | Type | Description |
|---|---|---|
| `id` | string | Loop id, see get_rares_loop.available (**required**) |

## `get_materials`  -  `GET /api/materials`  -  module: materials

Engineering materials inventory with grade, cap (300/250/200/150/100 for G1-G5), wishlist need and shortfall per material.

| Parameter | Type | Description |
|---|---|---|
| `category` | string | Raw, Manufactured or Encoded (one of `Raw`, `Manufactured`, `Encoded`) |
| `grade` | integer | 1-5 |
| `only_wishlist` | boolean | Only materials on the wishlist (default `False`) |
| `only_short` | boolean | Only materials where need exceeds stock (default `False`) |

## `get_material_inventory`  -  `GET /api/materials/inventory`  -  module: materials

The raw inventory as {journal key: count} for every material ever seen, plus a version that changes on every update. Small and fast; get_materials has names, grades and caps.

## `get_wishlist`  -  `GET /api/materials/wishlist`  -  module: materials

The materials wishlist with have/need/short for each entry.

## `set_wishlist`  -  `POST /api/materials/wishlist`  -  module: materials

Set the materials wishlist, e.g. everything needed for a blueprint. Names may be display names ('Datamined Wake Exceptions') or journal keys. The dashboard then shows shortfalls live as materials are collected.

| Parameter | Type | Description |
|---|---|---|
| `items` | object | Map of material name -> quantity needed (**required**) |
| `mode` | string | replace (default), add (increase needs), remove (drop these), clear (empty the list first) (default `replace`; one of `replace`, `add`, `remove`, `clear`) |
| `label` | string | What this is for, e.g. 'FSD G5 Increased Range x3' |

## `material_sources`  -  `GET /api/materials/sources`  -  module: materials

Where to farm a material: community-known sites and the general approach, plus current stock and cap.

| Parameter | Type | Description |
|---|---|---|
| `name` | string | Material display name or key (**required**) |

## `list_recipes`  -  `GET /api/recipes`  -  module: recipes

Search engineering blueprints, experimental effects and technology broker unlocks (Guardian modules and weapons, human broker items) by free text ('fsd range', 'dirty drives', 'guardian fsd booster', 'mass manager'). Returns compact hits with keys; call get_recipe for materials.

| Parameter | Type | Description |
|---|---|---|
| `query` | string | Words to match against module, blueprint/effect/unlock name and aliases; empty lists all |
| `kind` | string | Only blueprints, experimental effects or unlocks (one of `blueprint`, `experimental`, `unlock`) |
| `module` | string | Restrict to a module, e.g. 'frame shift drive' or 'shield booster' |
| `engineer` | string | Only blueprints this engineer offers (e.g. 'Farseer'); adds engineer_grade, the highest grade they do |
| `limit` | integer | Max hits (<=200) (default `20`) |

## `get_recipe`  -  `GET /api/recipes/get`  -  module: recipes

One blueprint with the materials for each grade, which engineers offer which grade, and the total to take a module from from_grade to grade (default: unengineered to max grade, with the rolls-per-grade hint); or one experimental effect with its materials. Accepts a key from list_recipes or free text.

| Parameter | Type | Description |
|---|---|---|
| `key` | string | Recipe key (e.g. FSD_LongRange, special_fsd_heavy) or free text (**required**) |
| `grade` | integer | Target grade 1-5; default = the blueprint's max |
| `from_grade` | integer | Grade the module already has; default 0 (default `0`) |
| `qty` | integer | How many modules (default `1`) |
| `kind` | string | Disambiguate free text (one of `blueprint`, `experimental`, `unlock`) |
| `module` | string | Disambiguate free text by module |

## `wishlist_options`  -  `GET /api/wishlist/options`  -  module: wishlist

Pick-lists behind the wishlist card: every module with its blueprint keys (and max grade) and experimental effect keys, every technology broker unlock key, and every material key by category. Use the keys with wishlist_add when free text is ambiguous.

## `get_engineering_wishlist`  -  `GET /api/wishlist`  -  module: wishlist

The engineering wishlist: every entry (blueprint to a grade, experimental effect, or material) with its completeness, the per-material needs vs live inventory (have/need/short), a summary, and a material trader plan for the shortfalls. Use wishlist_add / wishlist_remove to change it.

| Parameter | Type | Description |
|---|---|---|
| `reserve` | integer | Units of each material to keep back when planning trades (default `0`) |

## `wishlist_add`  -  `POST /api/wishlist/add`  -  module: wishlist

Add an entry. item is free text or a recipe key: '2x g5 fsd increased range', 'dirty drives 2-5', 'mass manager', '50 tellurium', 'FSD_LongRange', 'unlock_guardian_fsd_booster', or 'build' to track the pinned EDSY build as one entry whose needs follow the build's progress. Quantity, grade and a grade range ('2-5', 'g2 to g5' = the module already has G2, buy the rolls for G3, G4 and G5) can be in the text or as parameters. Blueprints default to the max grade from an unengineered module. If the text matches several recipes the reply has status 'ambiguous' and candidates instead of adding anything.

| Parameter | Type | Description |
|---|---|---|
| `item` | string | What to track (free text, key, or 'build') (**required**) |
| `qty` | integer | How many modules / units (default `1`) |
| `grade` | integer | Target grade 1-5 for a blueprint; default = max |
| `from_grade` | integer | Grade the module already has (0 = unengineered) (default `0`) |
| `kind` | string | Force the kind when the text is ambiguous (one of `blueprint`, `experimental`, `unlock`, `material`, `build`) |
| `module` | string | Restrict the recipe search to a module |
| `rolls` | string | Override rolls per grade as a list, e.g. [1,2,3,4,6]; default is the rolls_per_grade hint |
| `label` | string | Free note, e.g. the ship this is for |

## `wishlist_remove`  -  `POST /api/wishlist/remove`  -  module: wishlist

Remove entries by id (comma-separated) or everything with all=true.

| Parameter | Type | Description |
|---|---|---|
| `id` | string | Entry id(s) from get_engineering_wishlist |
| `all` | boolean | Clear the whole list (default `False`) |

## `plan_material_trades`  -  `GET /api/wishlist/trades`  -  module: wishlist

Estimate which material trader exchanges would cover the wishlist shortfalls from current surplus: a list of give/get trades with ratios, totals per trader type (Raw/Manufactured/Encoded), and what stays short. Ratios: same family 1->3 per grade down and 6->1 per grade up, other families cost 6x more.

| Parameter | Type | Description |
|---|---|---|
| `reserve` | integer | Units of each material to keep back (default `0`) |

## `find_material_traders`  -  `GET /api/wishlist/traders`  -  module: wishlist

Nearest material traders by type (Spansh), default from the current system and only for the types the trade plan needs. Includes distance, jump estimate, pad size and station type.

| Parameter | Type | Description |
|---|---|---|
| `types` | string | Comma-separated subset of Raw, Manufactured, Encoded; default = types in the trade plan, else all |
| `ref` | string | Reference system; default = current system |
| `limit` | integer | Traders per type (<=10) (default `3`) |
| `pad` | string | L = large pads only (one of `L`) |

## `find_hge_systems`  -  `GET /api/farming/systems`  -  module: farming

Nearest populated systems where High Grade Emissions for a material would spawn: pass the HGE site id from find_farm_sites (hge-boom, hge-war, hge-empire...) or a state/allegiance directly. Returns systems with distance, jumps, population, controlling faction state and allegiance (Spansh data).

| Parameter | Type | Description |
|---|---|---|
| `site` | string | HGE site id from find_farm_sites, e.g. hge-boom |
| `state` | string | Controlling faction state(s), comma-separated (one of `Boom`, `Civil Unrest`, `War`, `Civil War`, `Outbreak`, `Expansion`, `Election`, `Investment`, `None`) |
| `allegiance` | string | Superpower allegiance (one of `Empire`, `Federation`, `Alliance`, `Independent`) |
| `ref` | string | Reference system; default = current system |
| `min_pop` | integer | Minimum population (default `1000000`) |
| `limit` | integer | Max systems (<=30) (default `8`) |

## `find_farm_sites`  -  `GET /api/farming`  -  module: farming

Where to farm engineering materials: community-known sites (crystalline shards and brain trees for G4 raw, Dav's Hope for manufactured, Jameson Crash Site for encoded, Guardian structures) and methods (High Grade Emissions by system state, wake and ship scans), with system, body, surface coordinates and how-to, nearest to the ship first. Filter by material to answer 'where do I get X'; for_wishlist=true returns only sites that supply a current wishlist shortfall.

| Parameter | Type | Description |
|---|---|---|
| `material` | string | Material name or key, e.g. 'tellurium' or 'Adaptive Encryptors Capture' |
| `category` | string | Raw, Manufactured, Encoded or Guardian (one of `Raw`, `Manufactured`, `Encoded`, `Guardian`) |
| `type` | string | Site type substring: crystal, brain, crash, settlement, guardian, emissions, wake, scan, prospecting |
| `max_dist` | number | Only sites within this many Ly (drops sites without a system) |
| `for_wishlist` | boolean | Only sites that supply a current engineering wishlist shortfall (default `False`) |
| `limit` | integer | Max sites (<=100) (default `30`) |

## `get_build_progress`  -  `GET /api/build`  -  module: build

Progress of the current ship toward the pinned EDSY build: per target slot the verdict (ok, engineer, buy) with what to do, the blueprint rolls still needed from the module's current grade, experimental effects, credits for modules to buy, and every material summed against the live inventory (have/need/short). Percentages: fitted, engineered, materials, overall.

## `pin_build`  -  `POST /api/build/pin`  -  module: build

Pin a build as the target for the current ship: an EDSY link (https://edsy.org/#/L=...), a Coriolis link (https://coriolis.io/outfit/<ship>?code=...), or SLEF / journal Loadout JSON (what both sites export). Replaces any pinned build.

| Parameter | Type | Description |
|---|---|---|
| `url` | string | EDSY link, Coriolis link, or SLEF/Loadout JSON text (**required**) |

## `unpin_build`  -  `POST /api/build/unpin`  -  module: build

Remove the pinned build.

## `build_to_wishlist`  -  `POST /api/build/wishlist`  -  module: build

Track the pinned build on the engineering wishlist as a single entry whose material needs follow the build's progress. Then the wishlist card, trade plan and farm sites all work from the build.

## `get_system_coords`  -  `GET /api/coords`  -  module: map

Galactic coordinates for one or more systems (EDSM).

| Parameter | Type | Description |
|---|---|---|
| `names` | string | System names separated by | (**required**) |
