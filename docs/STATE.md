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
| `ship_info.*` | `type, internal, id, name, ident, hull_value, modules_value, rebuy, hull_health (0..1), unladen_mass, cargo_capacity, max_jump_range, fuel_main, fuel_reserve, hot, module_count, modules[{slot, group (component/hardpoint/utility/military/internal), item (lower case), name, class, rating, mount, on, priority, health, engineering{blueprint, blueprint_name, level, quality, experimental, experimental_name, engineer} | null}]` (cosmetic slots dropped; names from the EDSY table and gamedata, a prettified journal id for modules the table lacks; the old `core` and `hardpoints` lists are gone, filter `modules` by `group`) | | build module and the ship card read `modules` |
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
| `status` | Docking/flight flags, vehicle, shield up/down, fuel/reservoir/fuel_at, body/destination, low fuel/heat/danger/interdiction flags, cargo_tons, legal, timestamp | `Status.json`; omitted fuel retains its own observation time, reset on vehicle changes | location, ship, party |
| `game_running`, `hull_health`, `hull_at` | bool/null, fraction/null, timestamp/null | LoadGame/Shutdown; Loadout and player-piloted non-fighter HullDamage. Hull is last-reported, not continuous | party |
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
| `per_hour` | int or null, session merits over elapsed hours since login |
| `active_hours`, `per_hour_active`, `breaks`, `idle` | hours with journal activity (any event keeps the clock running; a silence longer than 10 min counts as 10 min and as one break), the rate over that (null until 5 min of activity), the break count (an ongoing silence counts), and whether a break is in progress |
| `earning_hours`, `per_hour_earning` | hours between merit gains with each gap capped at 20 min, and the rate over that: the activity's own pace (a combat session's rate, undisturbed by the engineering you did afterwards); the card's headline |
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

## Carrier trade and party additions

`trade` owns `carrier_id`, `inventory` (commodity -> stock or null, evidence and
timestamp), `orders` (side, active, remaining quantity, price and timestamp),
`plan`, `calculation`, `market_count`, `inventory_scan`, and `buy_commitment`. `trade.json` also
persists up to 100 observed markets and 10,000 event fingerprints for replay
deduplication. Physical counts and orders are separate. Carrier ownership is
established by CarrierStats/CarrierTradeOrder, never by pinning a visitor carrier.
Counts are partial evidence; unreported external trades require reconciliation.
Private `baselines` preserve manual counts during the chronological archive scan.
`inventory_scan` reports reading/ready/unavailable/carrier changed. Archive rows
only replace older evidence. Historical totals exceeding a newer CarrierStats
cargo total require reconciliation before a selected opportunity can become a plan.

`plan.price_basis` is known/unknown acquisition/unknown resale;
`carrier_price_known` prevents treating an absent carrier price as zero cost.
Unknown margins and estimated profits remain null. Personal Powerplay bonuses
store their confirmed pledge/rank context and never inflate carrier profit.

`trade/market.py` caches at most twelve paired-route queries for five minutes. Query
IDs bind prices to the inventory, orders, capacity and Powerplay context;
selection rejects changed context or queries older than ten minutes. Reports
are Ardent/EDDN observations, filtered by age, pad and radius, not Inara data.
`localStorage.trade.routes.v1` retains route search settings. The mounted
card preserves unsaved operation fields during live updates and clears its
refresh timer on unmount.

`party` owns mode (`idle`, `leader`, `member`), local member identity, listener
port, leader-only invitation code, remote URL, last error, shared plan and member
reports. Connections and invitation codes are memory-only; local identity and
cumulative delivery reports persist in `party-local.json`. The remote listener exposes only `/report`; the
management routes remain on the local dashboard. Reports older than 30 seconds
are stale, and members expire after 300 seconds. Client disconnects retain the
last evidence marked stale rather than turning cargo into zero. Party reports
never modify the trade ledger.

Reports now include optional `telemetry`: bounded fuel/fuel_reservoir/fuel_capacity
and hull_health numbers; nullable booleans for shield, flight and warning flags;
vehicle, body, destination, legal, game_running and status_at/fuel_at/hull_at.
Old reports without telemetry remain valid. No credits, raw journal or loadout
modules cross the party connection. Fuel capacity is only applied in the main
ship, never to SRV/fighter readings. Hull values describe the main ship and are
hidden in other vehicles. Fuel omitted in station menus keeps its original
observation time. One-second worker reports keep network I/O off journal callbacks;
leader status changes publish immediately. Receipt freshness and game observation
times are distinct, since Status.json only changes when the game writes it.

Route results pair the cheapest eligible supplier with each buyer above the
configured reported-high threshold, rank by spread per ton, and expose
`route_distance`, `reported_high`, `sell_percent`, `purchase_cost`, and `order`.
Unknown inter-stop coordinates are excluded. `radius` applies to both stops;
`route_distance` caps the buy-to-sell leg. Catalog spread chooses a bounded
24/48/96-commodity shortlist; fresh quotes determine all displayed prices.
`min_volume=0` (default) derives the supply/demand minimum from reported free
space on every query; `settings.volume_mode` identifies carrier/manual mode.
Unknown/full free capacity requires an explicit positive minimum to browse;
`quantity` then stays null/zero, respectively. Selection requires known stock and positive capacity. Runs are per leg.

Crew profit accounting:
`plan.crew_enabled`, `crew_load_percent`, `crew_unload_percent` and
`planned_quantity` persist with the plan. `crew_split` contains both suggested
order prices and per-ton rewards, recomputed server-side on save. Selection
uses the route quantity; manually supplied quantity 0 uses remaining hauling
quantity for calculated totals. `calculation.profit_split` includes gross,
carrier, loading and unloading profit totals. Carrier profit deducts BOTH legs.
Unknown quantity remains null; personal Powerplay bonuses are excluded.
Legacy plans default to crew disabled. Switching phase on an enabled plan sets
carrier_price to its buy/sell order price. Party snapshots include the saved split.
`localStorage.trade.crew.v1` stores preview percentages independently of search
filters. Preview changes do not requery markets or alter the saved operation.

Team operation lifecycle:
`trade.operation` persists id, stage (loading/transit/unloading/complete/cancelled),
paused, quantity, baseline_stock, notes, timestamps and reports keyed by stable
party identity. Public views add loaded/unloaded and remaining totals. The
owner-only manage_carrier_operation route controls stages; active operation
plans are frozen. Unloading sets target to baseline_stock and switches price.
Manual stage confirmation never synthesises inventory or crew deliveries.
`party.operation` and `party.carrier` are the leader's shared snapshot. Reports
include activity and cumulative `work{operation_id,loading,unloading}`. Party
emits `party.work`; trade validates operation/phase/bounds and merges monotonic
per-member totals into its own namespace. Delivery reports never modify inventory.
`party-local.json` holds identity, cumulative work, event fingerprints, manual
retry receipts and job recovery boundaries (no invitation code or address).
Heartbeat retries and reconnects deduplicate by identity and cumulative counters.
Late loading reports can arrive after departure; unloading cannot be reported
before that phase. Cancelled/other-operation reports are ignored. Crew UI marks
unacknowledged local counts as pending and disables delivery entry on stale links.

Inventory reset and journal delivery tracking:
`trade.history_since` is the persistent reset cutoff. CarrierTradeOrder, local
trades and transfers at/before it cannot modify the ledger. Carrier ownership
and docking context still replay. Archive scans capture the cutoff and discard
results if it changes mid-scan. `trade-ledger-before-reset.json` saves the prior
ledger. Kept tritium is an unknown-count baseline; plans/operations are unchanged.
Saved route plans now include source_market_id, destination_market_id and
carrier_market_id. The party journal listener matches MarketSell commodity and
market ID against the active loading/unloading leg; owner CargoTransfer to the
correct docked carrier can record loading. No cargo-delta inference. Replays and
events predating the operation are ignored. `party-local.json` persists auto_seen
fingerprints and last_auto with cumulative totals atomically. Heartbeats send
those totals, including after a temporary disconnect. `party.auto_tracking`
reports whether each leg has its required market ID; missing IDs require manual
fallback. Manual entry of an already detected delivery would count twice.

`journal.carrier.reserved_space` reads CargoSpaceReserved. Market planning capacity
is unreserved plus reserved space, explicitly conditional on replacing existing
buy orders in game. Raw free_space remains unchanged. Unknown/full capacity
allows browsing with a 1 t minimum and no executable load.

`party.load_suggestion` carries remaining tonnes, eligible onboard tonnes, full
crew-round capacity, an advisory rounded total and proportional next-pickup
amounts. It is recomputed from shared member reports, never persisted to plans
or interpreted as a reservation/delivery. Stale leader connections suppress it.

Saving a plan after cancellation/completion moves the ended operation and its
plan into `trade.previous_operation` (one retained snapshot) and clears the
current operation. The new plan is ready to start with a fresh operation id;
late reports for the previous id cannot enter its totals. Physical stock is unchanged.

Hauling desk:
`trade.job` publishes plan, operation and calculation as one coherent object.
Party sharing reads that object so a new plan cannot be paired with an old
operation during the store's individual-key notifications.
`party.desk` is a read-only projection for the local identity: next action,
quantity, structured pickup/delivery stops, prices, per-tonne/run estimates,
acknowledged personal progress, pending local counts, and the crew roster.
Disconnected contributors are reconstructed from persisted operation reports.
Idle mode projects the owner's local job and tracks their transfers without
opening a party listener. Nonblocking refresh callbacks update this solo view
after cargo and job changes without reversing the party/ledger lock order.
Reports now retain an owner flag so direct transfers are not priced as crew work.
Paused, stale, ended, away or unsupported-vehicle states suppress new pickups.
Ship cargo never creates delivery credit. Over-target reports are flagged.

`party-local.json.receipts` persists manual delivery request IDs and their
operation/phase/tonnes atomically with work totals. Repeating a request returns
the same cumulative work; reusing its ID with different contents fails.
The optional expected phase rejects a form submitted after a stage transition.
Legacy callers without request_id retain additive semantics. Automatic journal
fingerprints remain separate; manually reporting an automatically tracked load
is still a duplicate and must be avoided.

`POST /api/trade/profit` previews bounded batches of route prices using the same
Python calculation as saved plans. The browser discards outdated preview replies
when the route results or crew shares change.

Workload quotas:
`trade.workload` persists mode (live/equal/custom), owner_hauls, custom share weights,
and stable-identity member loading_target/unloading_target quantities. Equal
means tonnes, using largest remainders for whole-tonne conservation. Capacity
never weights equal-mode quotas. Applying a split requires the preview basis hash to match
the current plan, phase, deliveries, cargo and roster. Rebalancing adds portions
of remaining work to each member's existing credited deliveries. Assigned cargo
already aboard sets a minimum for that member's current leg, even if they opt out
of future runs. Other shares stay proportional where those minimums allow.
Zero-weight, away or stale members receive no new pickups. The owner flag is preserved.
Starting an operation creates a default equal split if none is saved. Replacing
the plan clears its split; previous_operation retains the previous workload.
During active equal splits, `party.roster` includes ready newcomers once, after
their incoming delivery report is reconciled and before the shared response.
The saved split is rebuilt from remaining work, protecting assigned onboard cargo
and the full outstanding quotas of absent/away members. Loading targets stay fixed
after departure. New away members wait until ready; reconnects keep assignments.
Custom splits require the owner to choose newcomer weights. Automatic changes
record a workload history entry with action `join`; persistence/validation errors
keep the old split, populate `trade.workload_join_error`, and retry on a later poll.
Automatic sizing uses tonnes still to deliver to the carrier, including existing
ship cargo. Only the new-purchase calculation deducts matching ship cargo.

`trade.job.workload` shares the saved quotas coherently with the job. Party
projects them into `party.workload`: live run estimates, full/partial remaining
loads, separate owner-transfer and market-order balances, buy-order budget and
profit adjusted for owner participation. Disconnects and ship swaps do not
rewrite fixed-mode targets. `party.desk.assignment` supplies personal target/remaining/run
figures. `load_suggestion` caps each pickup at that member's remaining quota,
less matching onboard cargo, and also applies the overall job bound. The desk
can recommend topping up a partial hold before delivery. Estimated runs include
the current load; they are not a count of observed docking visits.
Local cargo updates consume any pickup allowance from an older leader snapshot;
they never authorize buying beyond the remaining assignment. Unassigned surplus
cargo does not block other members' assigned pickups.

Live allocation uses `core.live_hauling`: it reserves observed commodity cargo,
then fills current free holds, minimizing ships used for a partial final pickup.
Later rounds are estimates using usable ship capacities. A full ship can retain
future work; a faster returning ship can pick up more without a fixed quota cap.
`unassigned` records work with no eligible ship; `reserved` records cargo held by
unavailable commanders. Per-member `cargo_snapshot` retains the last material
cargo observation and corresponding raw `reported` delivery counters. Later deliveries consume
that observation until a new cargo snapshot arrives, including on disconnect.
`party.roster` also fires on leader heartbeats and explicitly carries a leaving
member's last report. Only material changes write the saved live workload.
`party.workload.members[].next_pickup` and `pickup_phase` come from the shared
load suggestion used by personal instructions. `party.desk.allocation_mode`
distinguishes live estimates from fixed shares. Completed jobs keep saved targets.
New dashboard plans default to live; existing/API default equal settings remain
compatible. Active operation totals use acknowledged work, not inventory estimates.

Member heartbeats and manual report exchanges are serialized through response
application. Queued sends capture fresh local state; network I/O never holds the
party state lock. Leave follows any in-flight report, and its generation change
prevents that report's response from restoring the departed party.
The Leave message includes the final cumulative work report, so locally saved
deliveries can be acknowledged even when the previous heartbeat failed. At
startup, the owner reconciles saved local work into the matching operation;
repeated starts use cumulative counts and do not double-credit deliveries.

Delivery audit and corrections:
`operation.reports[id].reported` stores acknowledged raw cumulative totals;
`adjustments` stores signed owner corrections. Existing loading/unloading fields
remain credited totals (raw + adjustment), so quotas and margins share one basis.
Legacy reports without `reported` use their existing totals as the raw baseline.
`party.desk.pending` compares local raw work to acknowledged raw work, never to
adjusted credit. The personal panel exposes signed adjustments separately.

`POST /api/trade/correct` requires owner mode, the current operation ID, member,
phase, corrected total, expected credited and latest reported totals, a reason,
and a unique request ID. It rejects stale edits and mismatched retry payloads.
Correction receipts are persisted atomically with the ledger (up to 1,000 per
job). An above-target pending report can be explicitly reconciled by correcting
against the latest raw report; the resulting raw baseline prevents re-crediting
it on the next heartbeat. Credited totals cannot be corrected outside 0..job size.
Local journal observations are retained even if the client's correction view is
outdated. Above-target counts remain pending until reconciled. Raw work counters
are bounded at 1,000,000,000; cargo and each manual delivery remain bounded at
1,000,000. Manual additions still enforce the known credited job limit.

`work.last_entry` records the latest local entry's kind (manual, MarketSell or
CargoTransfer), phase, tonnes and timestamp. This is reported context, not proof
that every tonne in a batched cumulative report came from that one entry.
The persisted operation audit logs accepted raw increments, credited changes,
corrections, stage actions and workload changes. It retains the latest 2,000
entries with a monotonic count. Public operation views share only the latest 20
and omit correction retry receipts. Starting a replacement job retains the
previous operation, as does replacing the plan.

`GET /api/trade/diagnostics` exports an allowlisted snapshot of the current job
(or the previous job when there is no current operation). Owner exports use the
retained local audit; member exports use the shared tail and local pending totals.
Commander aliases are salted by operation ID so owner/member exports correlate
within a job. Names/identities, credentials, addresses, free-text notes/reasons,
unrelated journals, credit balances and filesystem paths are not exported.
Saved local raw work remains exportable after leaving. If its job is unavailable
or differs from the exported job, pending acknowledgement is null (unknown),
not a claim that those deliveries were accepted.


Party closure and process ownership:
`party.closing` is true during the bounded close handshake. Authenticated reports
then receive `{closed: true, members: [], plan: null, operation: null}`. The leader
waits for connected members or three seconds before releasing its listener.
`exchange` raises a terminal exception for closure or a rejected invitation;
`synchronize` clears membership/remote data and advances the generation, preserving
local work. Temporary network failures retain retryable stale state. Older clients
must update to understand the close response.

The CLI holds a user-wide OS file lock under `~/.elitelab/instance.lock` through
startup and shutdown. Its metadata identifies PID, dashboard URL, source folder
and source fingerprint. Repeat launches reuse the same ready process; changed
folders/builds are rejected. `ELITELAB_INSTANCE_DIR` explicitly isolates an
independent profile, primarily for tests. Legacy dashboard ports are checked for
the default profile. Windows HTTP listeners use SO_EXCLUSIVEADDRUSE. Core binds
before module loading or journal replay and runs shutdown callbacks on exit.
Health includes `application`, `ready`, `pid` and `source_dir` for diagnosis.
`POST /api/shutdown` stops the dashboard and closes its party; saved data remains.

Carrier percentage pricing:
Plans persist `carrier_mean_price`, `carrier_mean_source`, `carrier_mean_at`.
Market snapshots and paired quotes retain `mean_price`; the newest qualifying
report supplies the route reference. `GET /api/trade/price-reference` considers
local market snapshots and Ardent/EDDN import/export reports within 24 hours.
The reference is not an average of station buy/sell quotes.
`crew_split` includes target carrier prices, actual percentage settings, rounded
carrier prices, the reference and `carrier_prices_valid`. Percentage settings are
chosen within 5..1000 and the station spread, preserving nonnegative leg/owner
margins. Profit totals and quotas use the resulting prices. Without a reference,
preview values are explicitly targets and starting automatic crew pricing is
rejected. Active job prices are frozen; refresh/override requires ending the job.

Delivery recovery and physical cargo:
Operations persist `phase_started_at` and `ended_at`. Reports retain per-leg
`delivery_evidence{kind,at,tonnes}` and `correction_at`; local work sends the same bounded
delivery evidence. Raw totals and credited totals remain separate. Live cargo
snapshots use raw-counter baselines; corrections, manual accounting, and journal
evidence older than the cargo observation do not consume the current hold.
Legacy snapshots preserve their observed cargo until new evidence arrives.

`party-local.json.tracking` contains `operation_id`, `since`, `owner`, and
per-leg `manual_through` cutoffs. First observation establishes the recovery
boundary; installing this version never guesses older missing contributions.
`party.recovery` is `{running,recovered,error}`. Restart/rejoin/phase changes
schedule a background scan of complete journal lines using separate docking
context. Members require the matching shared job. Event fingerprints deduplicate
live and recovered deliveries. Cancelled jobs, post-completion events, and
evidence covered by manual entries/corrections are excluded. Missing legacy
phase boundaries and full fingerprint history require manual review.
`shared.recovering` pauses crew pickup suggestions during the owner's scan;
local scans also pause the personal desk and new manual entries. Leave/new jobs
invalidate scans by generation and identity. No credentials are persisted.

Materials publication serializes writers separately from inventory reads and
releases its inventory lock before synchronous callbacks. Build edits are
serialized. Build and wishlist edits publish only after their disk write succeeds.
