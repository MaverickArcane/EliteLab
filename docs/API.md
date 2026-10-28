# API / AI tools

Generated from `GET /api/schema` (EliteLab 0.5.0). Every tool is an HTTP route: `GET` with query parameters or `POST` with a JSON body. Responses are JSON; errors are `{"error": "..."}`. `GET /events` streams state changes as Server-Sent Events (`snapshot` then `state` events).

## `health`  -  `GET /api/health`  -  module: core

Server health, version, journal folder and loaded modules.

## `stop_elitelab`  -  `POST /api/shutdown`  -  module: core

Stop this local EliteLab instance, close its party and release its ports. Does not change saved jobs or inventories.

Replies `{"stopping": true}` first; the server stops about 100 ms later and leaves any party during shutdown.

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

## `get_followed_carrier`  -  `GET /api/carrier`  -  module: carrier

Pinned fleet carrier's last reported system, services, source and observation time; also up to 50 visited carriers available to pin. Remote reports may be stale. Owner-only fuel and finance remain in get_commander_state.

## `pin_fleet_carrier`  -  `POST /api/carrier/pin`  -  module: carrier

Persistently follow one visited fleet carrier. Choose its market_id from get_followed_carrier.visited. Replaces the previous pin; does not imply ownership.

| Parameter | Type | Description |
|---|---|---|
| `market_id` | integer | Market ID of a visited fleet carrier. (**required**) |

## `unpin_fleet_carrier`  -  `POST /api/carrier/unpin`  -  module: carrier

Remove the pinned fleet carrier. Keeps visited carriers and restores the owned-carrier card if available.

## `refresh_followed_carrier`  -  `POST /api/carrier/refresh`  -  module: carrier

Check Spansh for the pinned carrier's last reported location and services. Cached for five minutes; older reports never replace newer journal observations. Offline mode keeps cached data.

## `get_powerplay_status`  -  `GET /api/powerplay`  -  module: powerplay

Pledged power, rank, total merits, merits earned this session with a log of recent gains, days pledged, when the weekly cycle ends, and who controls the current system.

## `get_carrier_price_reference`  -  `GET /api/trade/price-reference`  -  module: trade

Retrieve the newest commodity meanPrice from local journals or Ardent/EDDN reports within 24 hours. This is a reported reference for the carrier 100% setting, not the average of station buy/sell prices. Live in-game prices take precedence.

Returns `commodity`, `mean_price`, `observed_at` and `source` (`Local market journal` or `Ardent / EDDN`) for the newest report; an error when no report is under 24 hours old.

| Parameter | Type | Description |
|---|---|---|
| `commodity` | string | Commodity journal key, letters and digits only, e.g. tritium (**required**) |

## `correct_hauling_delivery`  -  `POST /api/trade/correct`  -  module: trade

Owner corrects a commander's credited loading/unloading total with a reason. Preserves raw cumulative reports, survives retries/reconnects, and records a visible audit entry. Requires current credited and reported totals; stale edits are rejected. Does not change in-game cargo.

Owner only. Returns the updated operation view (reports, history, loaded and unloaded totals).

| Parameter | Type | Description |
|---|---|---|
| `id` | string | Current operation id from get_carrier_trade.operation (**required**) |
| `member` | string | Party member id of the commander being corrected, from the operation's reports or the party roster (**required**) |
| `phase` | string | loading or unloading (**required**) |
| `tonnes` | integer | New credited total for that commander and phase; cannot exceed the job size (**required**) |
| `expected` | integer | Credited total currently shown for that commander and phase (**required**) |
| `expected_reported` | integer | Raw reported total currently shown; the correction is rejected if either total has changed since (**required**) |
| `reason` | string | Why the total is being changed, 1-300 characters (**required**) |
| `request_id` | string | Unique id of 16-80 characters; repeating it with the same values returns the existing result, with different values is rejected (**required**) |

## `export_hauling_diagnostics`  -  `GET /api/trade/diagnostics`  -  module: trade

Export local hauling diagnostics for the current or most recent job. Includes credited/raw totals, corrections, quotas and retained history; anonymizes commanders and omits credentials, addresses, notes, reasons, full journals, credits and file paths. Members export only their latest shared history. Nothing is uploaded.

Returns an `elitelab-hauling-diagnostics-v1` document: `client`, `operation`, `route`, `carrier_prices`, `totals`, `checks`, `reports`, `assignments`, `crew` and `history`, with the applied `redactions` listed.

## `configure_trade_workload`  -  `POST /api/trade/workload`  -  module: trade

Owner chooses live loads, equal-tonnage quotas or custom weights. Live mode updates from acknowledged deliveries, free holds and available crew, with the final pickup assigned to one ship when it fits. Owner participation excludes estimated direct transfers from carrier market orders. Apply requires the current preview basis. No in-game orders are placed.

Owner only. Returns the workload view: per-member targets, done/remaining and run estimates per phase, totals, carrier prices and crew economics. Nothing is saved until action=apply.

| Parameter | Type | Description |
|---|---|---|
| `action` | string | preview computes the split; apply saves it (default `preview`) |
| `mode` | string | live, equal or custom (default `equal`) |
| `owner_hauls` | boolean | Whether the carrier owner takes a share of the hauling (default `True`) |
| `shares` | object | custom mode only: map of party member id -> whole-number weight 0-10000 |
| `basis` | string | Token from the preview's basis field; apply is rejected when the job or crew changed since |

## `preview_trade_profit`  -  `POST /api/trade/profit`  -  module: trade

Preview crew splits and carrier prices for up to 100 route price rows using the same rules as saved operations. No state changes. Quantity null means unknown.

Returns `splits`, one per row in order: carrier buy/sell prices and percentage settings, per-ton and total pay for loading, unloading and the owner; a row that cannot be priced gets `error` instead.

| Parameter | Type | Description |
|---|---|---|
| `rows` | array | Up to 100 objects with buy and sell (Cr/t, whole numbers), quantity (tonnes or null) and optional mean_price (the carrier 100% price) (**required**) |
| `loading` | integer | Percent of the route spread paid to loading haulers (default `25`) |
| `unloading` | integer | Percent paid to unloading haulers; both shares together must not exceed 100 (default `25`) |

## `manage_carrier_operation`  -  `POST /api/trade/operation`  -  module: trade

Owner controls the saved team trade: start, pause, resume, depart, unload, complete, cancel, notes. Depart/unload/complete are explicit owner stage confirmations; reported counts remain evidence, never invented inventory. Existing operation actions require its id. Only the local carrier owner can control stages.

Owner only. start needs a complete load plan and opens a new operation in the loading stage; depart, unload and complete move it through transit, unloading and complete in that order; pause, resume, cancel and notes act on the active operation. Returns the trade state.

| Parameter | Type | Description |
|---|---|---|
| `action` | string | start, pause, resume, depart, unload, complete, cancel or notes (**required**) |
| `id` | string | Current operation id; required for every action except start |
| `notes` | string | notes action: crew instructions, up to 500 characters |

## `get_trade_profiles`  -  `GET /api/trade/profiles`  -  module: trade

Trade profiles and their live carrier context: observed inventory, buy orders, free space, ship capacity and reference system. Inventory is partial journal evidence.

Returns `profiles` (currently the single buy/sell route profile) and `context`: carrier name, callsign, system, free/unreserved/reserved space, reported cargo, ship capacity, inventory, orders, inventory_conflict, power and rank.

## `find_carrier_opportunities`  -  `GET /api/trade/opportunities`  -  module: trade

Find paired buy/sell routes from Ardent/EDDN reports. For each high-paying buyer, choose the cheapest supplier within route_distance Ly, then rank by spread per ton. Radius limits BOTH stops from the carrier reference system. Unknown route distances are excluded. Broad search screens up to breadth catalog candidates; commodity selects one. Reports are capped at 100 quotes per side, not an exhaustive galaxy search. Unreserved plus buy-order-reserved capacity sizes replacement loads; cancel old orders in game. Unknown/full capacity still permits browsing. Cached five minutes.

Unavailable offline. Returns up to 18 `rows`, each with an `id` for select_carrier_opportunity, the buy and sell stops, route distance, per-ton spread, suggested quantity and runs; plus `commodities`, `warnings`, `settings` and `outdated` (true when the carrier context changed since the query). The filters accept only the listed values.

| Parameter | Type | Description |
|---|---|---|
| `commodity` | string | Commodity key from the result's commodities list or the carrier inventory; empty screens the broadest catalog candidates |
| `hours` | integer | Maximum report age in hours: 3, 6, 12, 24 or 72 (default `6`) |
| `radius` | integer | Maximum distance of both stops from the carrier reference system in Ly: 0 (any), 25, 50, 100, 250, 500 or 1000 (default `100`) |
| `route_distance` | integer | Maximum distance between the buy and sell systems in Ly: 25, 50, 100, 250 or 500 (default `100`) |
| `min_volume` | integer | 0 automatically requires supply and demand for all reported carrier free space; a positive value overrides the minimum tons. (default `0`) |
| `sell_percent` | integer | Only buyers paying at least this percent of the highest reported sell price: 0, 80, 90 or 95 (default `80`) |
| `breadth` | integer | Catalog commodities screened when no commodity is given: 24, 48 or 96 (default `24`) |
| `arrival` | integer | Maximum distance to arrival in Ls for both stations: 0 (any), 2000, 10000 or 50000 (default `10000`) |
| `pad` | string | Minimum landing pad size: L, M or S (default `L`) |

## `select_carrier_opportunity`  -  `POST /api/trade/select`  -  module: trade

Save a trade operation from a fresh opportunity ID using observed quantities and prices. Rechecks inventory context and rejects unknown stock or expired results. Does not place in-game orders.

Owner only. Saves a load plan from the chosen row (as plan_carrier_trade does) and returns the trade state. Results older than ten minutes, or made against a different carrier context, are rejected; when the commodity's stock is unknown, pass stock to reconcile it first.

| Parameter | Type | Description |
|---|---|---|
| `id` | string | Row id from find_carrier_opportunities (**required**) |
| `stock` | integer | Explicit current physical count when existing stock is unknown or conflicting. |
| `crew_enabled` | boolean | Derive the carrier order prices from the station prices and the crew shares (default `False`) |
| `crew_load_percent` | integer | Percent of route spread paid to loading haulers (default `25`) |
| `crew_unload_percent` | integer | Percent paid to unloading haulers; both shares together must not exceed 100 (default `25`) |

## `get_carrier_trade`  -  `GET /api/trade`  -  module: trade

Carrier stock evidence, outstanding market orders, persisted operation plan and run calculations. Unknown stock stays null; orders are not inventory.

The trade state: `carrier_id`, `inventory`, `orders`, `plan`, `operation` (with history and loaded/unloaded totals), `workload`, `previous_operation`, `calculation` (remaining, to_haul, runs, margins, profit_split), `buy_commitment`, `market_count`, `inventory_scan`, and a `job` block that carries plan, operation, workload and calculation together.

## `plan_carrier_trade`  -  `POST /api/trade/plan`  -  module: trade

Save a load/unload plan. Target is desired stock remaining aboard the carrier. Prices are Cr/t estimates, excluding expenses; capacity 0 uses your ship. Does not place in-game orders.

Not allowed while a party member, or while an operation is loading, in transit or unloading. Saving a plan clears the workload and moves any ended operation to previous_operation. Returns the trade state.

| Parameter | Type | Description |
|---|---|---|
| `commodity` | string | Commodity name or journal key (**required**) |
| `source` | string | Where the cargo is bought, e.g. 'Station / System' |
| `destination` | string | Where the cargo is sold |
| `mode` | string | load (fill the carrier) or unload (empty it); default load |
| `target` | integer | Desired stock remaining aboard the carrier after the operation (default `0`) |
| `ship_capacity` | integer | Cargo capacity used for run counts; 0 uses your ship (default `0`) |
| `source_price` | integer | Station buy price, Cr/t (default `0`) |
| `carrier_price` | integer | Carrier order price, Cr/t; derived automatically when crew_enabled (default `0`) |
| `destination_price` | integer | Station sell price, Cr/t (default `0`) |
| `bonus_per_ton` | integer | Personal Powerplay bonus per ton at the destination, Cr/t (default `0`) |
| `source_market_id` | integer | Verified market ID for automatic crew delivery matching; 0 is unknown. (default `0`) |
| `destination_market_id` | integer | Verified market ID for automatic crew delivery matching; 0 is unknown. (default `0`) |
| `carrier_market_id` | integer | Verified market ID for automatic crew delivery matching; 0 is unknown. (default `0`) |
| `carrier_mean_price` | integer | Current commodity price at the carrier's 100% setting; 0 means unknown. Used for whole-percentage carrier prices. (default `0`) |
| `carrier_mean_source` | string | Source of the 100% price reference. |
| `carrier_mean_at` | string | Observation time for the 100% price reference. |
| `crew_enabled` | boolean | Derive both carrier order prices from station prices and the crew shares. Excludes personal bonuses. (default `False`) |
| `crew_load_percent` | integer | Percent of route spread paid to loading haulers. (default `25`) |
| `crew_unload_percent` | integer | Percent paid to unloading haulers; both shares together must not exceed 100. (default `25`) |
| `planned_quantity` | integer | Full operation tonnage for profit totals; 0 uses remaining hauling quantity. (default `0`) |
| `price_basis` | string | Which station prices are known; crew pricing needs known (default `known`; one of `known`, `unknown acquisition`, `unknown resale`) |
| `carrier_price_known` | boolean | False hides the hauler and carrier margins until the carrier order price is set (default `True`) |
| `bonus_confirmed` | boolean | Only enable after verifying your personal bonus for the power, rank, commodity and destination. (default `False`) |
| `price_includes_bonus` | boolean | True if the sell price already includes the personal bonus; prevents adding it twice. (default `False`) |
| `use_ship_cargo` | boolean | Deduct your matching cargo from new loading work; does not deduct it from outstanding orders. (default `False`) |

## `reset_carrier_inventory`  -  `POST /api/trade/reset-inventory`  -  module: trade

Forget carrier commodity counts and market orders, retaining a backup and a cutoff so older journal history cannot recreate them. Does not change the game, saved plans or operations. Optionally retain tritium with an unknown quantity.

Writes the previous ledger to trade-ledger-before-reset.json in the data folder and returns the trade state.

| Parameter | Type | Description |
|---|---|---|
| `keep_tritium` | boolean | Keep a Tritium row with unknown stock instead of forgetting it (default `False`) |

## `reconcile_carrier_stock`  -  `POST /api/trade/reconcile`  -  module: trade

Set the current physical stock of ONE commodity after checking the carrier in game. Never enter outstanding buy orders as stock. Replaces older stock evidence.

Records the count as a manual baseline and, if an active sell order exists for the commodity, sets that order's quantity to the same count. Returns the trade state.

| Parameter | Type | Description |
|---|---|---|
| `commodity` | string | Commodity name or journal key (**required**) |
| `stock` | integer | Tonnes physically aboard the carrier now, 0 to 1000000 (**required**) |
| `name` | string | Display name to store for the commodity; default = the key |

## `find_trade_spots`  -  `GET /api/trade/spots`  -  module: trade

Find buy/sell stops using remembered local markets (default source=observed) or Ardent/EDDN community reports (source=community). Community mode filters by pad, age and volume, excludes fleet carriers, and returns up to 15 per side from the best 100 quotes. Prices are observations, not live guarantees.

Returns `buy` and `sell` lists (up to 15 each), a `source` note, `warnings` in community mode, and up to 8 paired `routes` sorted by profit per ton with margin, volume, gross profit and distance. Community mode is unavailable offline.

| Parameter | Type | Description |
|---|---|---|
| `commodity` | string | Commodity name or journal key (**required**) |
| `source` | string | observed = markets this commander has opened; community = Ardent/EDDN reports (default `observed`; one of `observed`, `community`) |
| `pad` | string | Minimum landing pad size, community mode only (default `L`; one of `L`, `M`, `S`) |
| `min_volume` | integer | Minimum stock or demand in tonnes, community mode only (default `1`) |
| `max_days` | integer | Maximum report age in days, up to 30, community mode only (default `3`) |
| `max_route_distance` | integer | Maximum distance between paired buy/sell systems in Ly. 0 is unlimited; unknown distances remain explicitly unknown. (default `500`) |

## `get_hauling_party`  -  `GET /api/party`  -  module: party

Local hauling party status, commander cargo/location and telemetry (shield up/down, fuel, flight mode, alerts, last-reported hull), observation timestamps and shared leader plan. Party codes appear only on the leader's local dashboard.

The party state: `mode` (idle, leader or member), `code` (leader only), `port`, `url`, `error`, `members` with their telemetry and work totals, `plan`, `operation`, `workload`, `load_suggestion`, `recovery`, `activity`, `work` (this client's cumulative deliveries), `auto_tracking`, `last_auto_delivery`, `stale`, `closing`, `local_id` and the personal `desk`.

## `host_hauling_party`  -  `POST /api/party/host`  -  module: party

Start an opt-in private LAN/tailnet party listener, separate from the dashboard. Returns a random party code. Members share location, ship, cargo and status telemetry; restart or Leave stops sharing.

Fails when already in a party or when the address and port cannot be bound. Returns the party state, including the `code` to give members.

| Parameter | Type | Description |
|---|---|---|
| `port` | integer | Listener port, 1024-65535; separate from the dashboard port (default `8767`) |
| `bind` | string | Local IPv4 address to listen on; use your Tailscale IPv4 to restrict the listener to the tailnet. (default `0.0.0.0`) |

## `join_hauling_party`  -  `POST /api/party/join`  -  module: party

Connect this EliteLab to a leader over LAN/Tailscale. Reports commander name, location, ship, cargo and status telemetry every second until Leave or shutdown; never sends credits or the full journal. Shields are up/down; hull is last-reported, not continuous.

Fails when already in a party or when the leader cannot be reached. Returns the party state with the leader's shared plan, operation and roster.

| Parameter | Type | Description |
|---|---|---|
| `url` | string | Leader's address and party port, e.g. 100.64.0.5:8767; http:// is added when missing (**required**) |
| `code` | string | Party code shown on the leader's dashboard (**required**) |

## `report_hauling_work`  -  `POST /api/party/work`  -  module: party

Set your crew activity (ready/hauling/away) or add actually delivered tonnes for the current shared operation id. Cumulative local totals survive reconnect/restart and are retried without double counting. Delivery reports do not change physical inventory.

Pass activity alone to change status, or id and tonnes (with phase and request_id) to record a manual delivery; both may be sent together. Deliveries are accepted only while the operation is loading or unloading, and a member needs a fresh leader connection. Returns the party state.

| Parameter | Type | Description |
|---|---|---|
| `activity` | string | ready, hauling or away |
| `id` | string | Current shared operation id from get_hauling_party.operation |
| `tonnes` | integer | Tonnes actually delivered in this report, added to your cumulative total for the current phase |
| `phase` | string | Expected loading/unloading phase; rejects a stale form after a stage change. |
| `request_id` | string | Unique delivery request id, retained on retries to prevent duplicate manual reports. |

## `leave_hauling_party`  -  `POST /api/party/leave`  -  module: party

Stop sharing immediately. Members leave the party; leaders close the listener and invalidate its code. Saved trade plans remain.

Returns the party state.

## `get_merits_summary`  -  `GET /api/merits`  -  module: merits

Where this session's Powerplay merits came from (rares, trade, bounty hunting, combat zone bonds, hauling, exploration, missions, objective bonuses), merits per event, and a recent log. Rates: per_hour_earning is the activity's own pace (time between merit gains, a gap over 20 min counts as 20 min), per_hour_active is over time with any journal activity (a silence over 10 min is a break), per_hour is over elapsed time since login, last_hour is the last 60 minutes; breaks and idle say why they differ.

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

## Trading routes

`find_personal_trade_routes` / `/api/personal/routes` retains its existing tool
and URL for compatibility. It now uses Spansh station market snapshots.
`route_type=round_trip` (default) builds exact station A-B-A loops; `one_way`
returns a single leg. `origin` defaults to the journal system, `station` is an
optional starting station, and `destination` is an optional system name.
`quantity` defaults to ship capacity. `distance` is a per-leg radius (max 500 Ly),
or `distance_mode=jumps` uses `jumps * jump_range_laden` as an estimate.
`pad` is S/M/L; `hours` defaults to 24 (max 72); `arrival` defaults to 10000 Ls
(0 means any); `surface` is "0" or "1". Fleet carriers are always excluded.
`breadth` now counts nearest eligible stations (default 100, max 300), not goods.
`commodity` is an outbound selection key returned in `commodities[{key,name}]`;
it never restricts the return cargo. The result includes up to 30 routes with
`legs`, `profit`, combined `cost`, `required_credits`, `return_on_cost` (percent),
`distance` per leg, `total_distance`, and `estimated_jumps` per leg.
`screened`/`available` count nearby stations; coverage/errors appear in `warnings`.
Reports are cached five minutes. No game action is performed.
