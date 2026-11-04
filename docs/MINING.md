# Mining desk

The Mining card connects finding a ring, tracking production and selling the
haul. Use the Mining & trade layout for the full-width desk, or enable Mining
in the Layout menu. Journal tracking works offline; community searches require
Spansh. The forms retain edits during live updates and save filters in this browser.

## Workflow

**Mining for merits:** start with [MeritMiner](https://meritminer.cc/). Set your
reference system, power, power goal and mineral there to plan the run. The Mining
card's **Open MeritMiner** link opens the site in a new tab. Use EliteLab to track
the haul, sales and recorded merit gains during the run.

1. Search near your current system. Filter ring type, reserve level, optional
   reported hotspot, and optional power owning the mining source.
2. Compare distance, approximate jumps, arrival distance, reserves and dated
   hotspot reports. Select mining spot highlights it on the map and prefills
   the buyer search origin; copy the system into the game's navigation search.
3. Prospect and refine. Composition bars, produced tons, tracked unsold units,
   tons/hour and the session ledger update from journals.
4. Open Sell your haul and choose Credits only or a Powerplay goal. Use tracked haul fills the largest remaining commodity
   and its quantity. Search buyers with a radius, minimum pad and market-age
   limit. Quotes require positive prices and enough reported demand.
5. Use a credit quote to estimate the tracked unsold value of that commodity. Actual
   journal sales update the ledger; a quote never becomes realized income.

## Powerplay and MCP

The buyer form offers Credits only - any market, Acquisition candidates and Reinforcement
candidates. The power defaults to My pledged power; an unknown pledge requires
an explicit selection. Credit mode explicitly does not validate merit eligibility,
both above the form and on every quote. A high sale price is not a merit forecast.
Acquisition selects provider-reported Unoccupied systems listing that power;
reinforcement requires its actual controlling power in Exploited, Fortified or
Stronghold systems. A power being present is not ownership: Spansh's
`system_power` can list many powers while `system_controlling_power` names one.
The same ownership requirement applies to mining source discovery and pairing.

For merit searches, the browser requires **Cargo mined in**, separate from
**Travel from system**. Selecting a ring prefills this source for confirmation;
it is a user assertion, not verified cargo history. Reinforcement excludes
different-system sales. Acquisition makes one source-system lookup, checks its
controlling power, Fortified/Stronghold state and 20/30 Ly reach, and excludes
known incompatible routes. Missing source/control/coordinates stay unknown.
The API allows an omitted source but explicitly reports unknown route eligibility.
These are candidate searches: local activities, actual cargo provenance and other
game requirements must still be checked in game. Transferring cargo through a
carrier can remove mining origin. Use MeritMiner to plan a new merit run.
Nearby rings > Merit opportunities remains available for comparing EliteLab's
reported source and market candidates.
There is no forecast of merits from sale value.

The card and `get_mining_status` expose `powerplay`: `power`, `total_merits`,
`session_merits`, `sale_associated_merits`, `unassociated_merits`,
`association_estimated`, the latest 12 `recent` gain records, and `note`.
`PowerplayMerits.MeritsGained` supplies the observed counter. The first gain
within 0-12 seconds after a wholly tracked mined sale may be associated with
that sale only when cargo history is known and unmixed, and no known intervening
earning/travel event breaks the association. Negative time differences, missing
timestamps, other sales, ambiguous cargo and power changes cannot create a link.
The journal provides no sale identifier: association is always estimated and can
include bonuses. Additional gains remain unassociated rather than being split
or forecast. Counters reset on game session, commander or pledge changes and
freeze at Shutdown. Credits and merits are separate.

All three mining tools are listed by MCP. `find_mining_buyers` accepts
`powerplay_mode` (`none`, `acquisition`, `reinforcement`) and `power` (`pledged`
or a known power), and optional `mined_in`. Results include purpose/purpose_note,
selected power/mode, reported powers/controller/state, excluded route count,
per-quote `merit_route` status/reason, `merit_eligibility: unverified` and
`merit_estimate: null`. The `mining_run` MCP
prompt recommends MeritMiner for merit route planning and reads commander,
pledge and mining status for context. EliteLab's ring and buyer searches support
local comparisons while preserving these evidence limits. `elitelab://state/mining` exposes the same
atomic summary used by the browser. Searches are returned to the caller;
browser form selections and map pins remain client-local.

## Full sales and attributed profit

The headline is **Recorded sale proceeds**: full `MarketSell.TotalSale` receipts
this game session, including cargo already held when the game was reloaded.
`SellPrice * Count` is a fallback when TotalSale is absent. Invalid prices remain
unknown, with the missing quantity disclosed. These are gross commodity sales,
including non-mining cargo, not net mining profit or lifetime earnings.

**Attributed mining net** remains conservative: only refinery units tracked in
this session contribute, other cargo is consumed first, and recorded operating
costs are subtracted. After reloading with 114 tons, refining 54 more and selling
168 tons for 44,328,984 Cr, the headline shows all 44,328,984 Cr. The separate
attributed proceeds are 14,248,602 Cr for 54 tons before costs. Prior-session
costs/provenance are not reconstructed or silently assumed.

The API adds `profit.market_sale_proceeds`, `market_sold_tons` and
`unknown_market_sale_tons`. Existing `sale_proceeds`, `sold_tons` and `net_profit`
retain their attributed meanings. Sale transactions now show full `credits` and
`tons` with separate `tracked_credits` and `tracked_tons`. Receipts, attributed
profit, unsold quotes and recorded merits are distinct; no sale creates merits.
All counters still reset on LoadGame or changed commander.

References checked 2026-11-02: [Frontier Journal manual, MarketSell section 7.6](https://hosting.zaonce.net/community/journal/v34/Journal_Manual_v34.pdf),
[mining route conditions](https://elitecheatsheet.com/powerplay-2), and live
Spansh station fields. The live Elysian Fields response showed Felicia Winters
as controller while its power-presence list included Edmund Mahon and others.

Ring discovery uses [Spansh bodies](https://www.spansh.co.uk/bodies); buyers use
[Spansh stations](https://www.spansh.co.uk/stations). The nested ring and market
filters were checked against Spansh's own UI and live API. The station catalogue
resolves capitalization and the LowTemperatureDiamond journal alias.
Each search fetches at most four pages of 25 matching bodies/stations (five-minute
cache), retaining the shared 8 MiB per-response limit. The catalogue is cached
for a day. At most 30 rings or 20 buyers are displayed. A failed later page is
explicitly marked partial. Ranking is within this bounded search, not the galaxy.

Hotspot counts do not establish overlaps, yields or mining method. DSS-scan and
prospect on arrival. Unknown permit status is visible. Acquisition filtering is
provider-reported, not a guarantee that a sale earns merits. Jump estimates use
straight-line distance/current range, not a plotted route. Markets exclude
carriers and surface ports; old/future/undated quotes and inadequate demand are
excluded. Prices and demand can change, including with sale size.

Each `MiningRefined` event adds one ton. Output is grouped by normalized
commodity key; localized journal names are used for display. Buying, selling,
ejecting or transferring cargo never changes production totals. Unknown
commodity types appear in Other / unknown. Production is separate from current
cargo, attributed sales, and quote estimates. Conditional planning forecasts never change recorded merits.

## Ship range and merit opportunities

Mining searches default to `min(jump_range_laden, jump_range_now, 200)` Ly.
The laden calculation uses a full hold and tank; the current calculation can
reduce it for low fuel or current mass. No neutron/synthesis boost is assumed.
A supplied smaller radius is honored; a larger valid radius is clamped by the
same backend used by HTTP and MCP. Missing reliable loadout data or zero range
blocks the search. Ship swaps and LoadGame clear old range data until Loadout.
The journal publishes current fuel/cargo range updates; the UI clears stale
results and pending responses when ship, cargo, fuel, pledge or location changes.
A search whose context changes during provider I/O fails with a retry message.
A manual reference system still uses this cap but explicitly represents a
planning origin, not a destination reachable from the current ship location.

For a candidate comparison within EliteLab, choose **Merit opportunities**, your
hotspot commodity, power or current pledge, goal, planned load, pad and market age.
`find_mining_spots` exposes the same `sort=merits`, `hotspot`, `power`,
`powerplay_mode`, `quantity`, `pad` and `hours` parameters. It compares the nearest
30 matching rings from at most 100 bodies with at most 100 orbital markets:

- Reinforcement: a reported owned mining system and market in that same system.
- Acquisition: an owned Fortified or Stronghold source, with an Unoccupied
  destination reporting the selected power within 20 or 30 Ly respectively.
  Missing coordinates cannot establish the cross-system link.
- Both: a matching commodity, adequate reported demand/pad and a fresh quote.
  These are reported candidates; local activities, current system control,
  pledge prerequisites and actual cargo provenance remain in-game checks.

The planner makes one shared bounded market search, not a request for each
ring: at most nine provider calls including the catalogue. The market radius
can include acquisition destinations up to 30 Ly beyond the mining search,
within the provider's existing 200 Ly cap. It never widens the mining radius.
`buyer.from_ring_ly` is source-to-sale distance; `buyer.distance` is from the
search origin. Partial market coverage is disclosed with the data limits.

Numerical forecasts require a sale-associated merit event within 24 hours in
the current session and pledge, matching commodity, mining source and its
reported state, sell system/station/state, and the exact reported unit price.
The source must be consistently known from refinery events. Mixed origins or
carrier transfers invalidate reusable origin evidence. Forecasts scale that
sample's merits per ton to the planned load and disclose sample size/time.
They remain conditional: temporal association is not causation, and bonuses,
bulk effects or cycle changes may alter the result. Unknown yield is `null`,
not zero. A candidate without such evidence still shows its market and price.
Conditional forecasts rank first by merits; unknowns follow with compatible
markets first, then price and distance as an explicitly labeled fallback.
No extraction-rate or merits/hour claim is made from hotspot counts.

Selecting a spot, including through the map, highlights it and updates the buyer
origin, commodity/load/goal when present, and clears stale buyer results/quotes.
It does not plot a route in Elite Dangerous. Copy system remains available for
both the source and proposed sell destination.

### Research basis (reviewed 2026-11-02 UTC)

[Merit Miner's own search guide](https://meritminer.cc/templates/how_to.html)
describes same-system reinforcement and the 20/30 Ly acquisition source rules.
Its search uses market prices as a practical comparison, not a published
universal numerical conversion. We apply these as candidate rules and preserve
unknown eligibility where evidence is absent.

The [EDC Academy laser-mining guide, January 2026](https://siriuscorp.cc/guides/laser-mining.html)
recommends platinum and explains that yield depends on equipment, technique and
market conditions. [First-hand player reports, July 2026](https://www.reddit.com/r/EliteDangerous/comments/1uxf6ds/how_are_people_getting_to_1m_merits_what_am_i/)
show materially different merit returns at similar prices and point to acquisition
versus reinforcement, source geography and market conditions. These support
platinum as a candidate, not a universal fastest-method or per-ton guarantee.

Frontier's [Dodec update, November 2025](https://store.steampowered.com/news/posts/?appids=359320&enddate=1763037221&feed=steam_community_announcements)
changed single-unit/bulk commodity merit behavior; its
[Caspian Explorer update, December 2025](https://store.steampowered.com/news/posts/?enddate=1764670144&feed=steam_community_announcements)
fixed under-rewarded trade activities. Consequently this planner does not reuse
old community conversion constants or EliteLab's unrelated rare-goods rate.
Current game validation remains under #3; synthetic browser sales are never
presented as measurements of actual game merit yields.

## Profit accounting

`summary.profit` contains attributed `sale_proceeds`, `sold_tons`,
`operating_costs`, `cost_breakdown`, `net_profit`, `net_per_hour`, `estimated`,
`unknown_sale_tons`, `removed_tons`, `remaining` (commodity key -> tons), the
latest 12 `transactions`, and an explanation in `note`.

An initial Cargo inventory establishes other cargo. Refinery events add mined
units. Buying, collecting or transferring into the ship adds other units;
sales consume those first, then tracked mined units. The attributed share of
`MarketSell.TotalSale` is revenue (SellPrice is a fallback). Missing initial
cargo or mixing mined/other units marks attribution estimated. The journal does
not identify individual cargo units, so this allocation is a conservative
assumption, not proof of provenance. Missing sale prices are disclosed separately.

Ejection, outward carrier/SRV transfers and mission deliveries remove tracked
units without inventing income. Returning cargo remains other cargo, so a
transfer cannot create a second mining sale. Death clears inventory. Dated
Cargo snapshots reconcile losses without adding mined units; older snapshots
cannot overwrite later inventory events.

Net subtracts this game session's recorded limpet purchases (less refunds),
fuel, repairs and ammunition, including spending before the first mining event
and spending on other activities. Equipment, rebuy and every possible expense
are not inferred. These are tracked operating costs, not total commander profit.
No credits or commodities are changed in game; no ledger file is written.

Prospector reports show composition, material content, remaining percentage,
and a core material when the journal supplies it. Zero remaining is valid;
missing or invalid percentages show unknown. The journal supplies no asteroid
identifier, so the report counter does not claim to count unique asteroids.
The latest report stays visible with its recorded timestamp after travel.

## Sessions and rate

- Every `LoadGame` resets the session. A changed Commander name or FID also
  clears totals. Journal file continuation alone does not reset them.
- Replay rebuilds the session using the same events as live tracking. If the
  loaded journal window has no `LoadGame`, partial history is explicitly shown.
  No separate mining file is written. Adjust `ELITELAB_RECENT_JOURNALS` if a
  long session's beginning falls outside the replay window.
- The rate is refined tons divided by hours from the first mining event to
  the latest recorded journal timestamp. Travel and idle gaps are included.
  It becomes available after 60 recorded seconds; missing/invalid mining
  timestamps suppress it. Older timestamps cannot move the end time backward.
- `Shutdown` freezes the session. The card shows the journal's `as_of` time;
  a silent or disconnected game does not keep changing the displayed rate.
  This is a recorded-session average, not an instantaneous mining speed.
- Two refinery events in the same second both count. There is no deduplication
  by timestamp, because those can represent two legitimate units.

Event semantics come from Frontier's [Player Journal manual v34, sections
7.7 and 13.33](https://hosting.zaonce.net/community/journal/v34/Journal_Manual_v34.pdf).
The tests use synthetic records matching those fields, not a recorded mining run.
In-game validation should compare a fresh session's prospector composition,
refined units and timestamps with the journal, then reload the game and verify
the reset. Repeat with mixed purchased/mined cargo, sales, ejection and carrier
transfers. Actual in-game validation remains under #3.

## State and input limits

`mining.summary` is one atomic store snapshot. It includes `commander`,
`partial`, `ended`, `started_at`, `as_of`, `elapsed_seconds`,
`timing_incomplete`, `tons_per_hour`, `prospector_reports`, `last_prospect`,
`refined_tons`, `commodities`, `other_tons`, `profit`, `powerplay`, and `rate_note`.
The API returns the same snapshot. It is read-only and uses the existing
HTTP authentication and host checks. The two discovery tools make explicit,
bounded requests to fixed Spansh endpoints; journal handlers never do network I/O.
`mining.spots` and `mining.selected` are client-only map state. Selected quotes
are card-local, dated estimates; they never modify the ledger.

The latest composition is limited to 32 entries, text fields to 160 characters,
and named output to 256 commodity keys. Additional distinct keys accumulate in
Other / unknown so the total remains correct. Percentages must be finite numbers
between 0 and 100. The browser escapes journal text before rendering it.

## Validation

`python -m unittest discover -s tests -p test_mining.py -v` covers replay/live
equivalence, session boundaries, duplicate-second output, rate timing, malformed
and bounded input, and separation from cargo transactions.

`node tests/mining-browser.mjs` (Node 22+, Chrome) starts the real CLI against a
temporary journal directory, appends records, checks API and SSE results, tests
HTML escaping, reloads a saved layout, and checks desktop/390px layouts. Set
`ELITELAB_SCREENSHOT_DIR` to save screenshots in a chosen directory. It never
uses the player's journal or data directory. Its provider boundary uses synthetic
Spansh fixtures by default; parsing, HTTP handlers, CLI and watcher remain real.
`ELITELAB_MINING_LIVE=1` enables the same smoke flow against live Spansh, with
unrelated community requests blocked. Both modes were run locally. Live market
prices are transient; screenshots label whether provider data is real or fixture.

`test_mining_desk.py` covers monetary attribution, mixed cargo, transfers,
snapshot reconciliation, missing prices, aliases, actual nested provider filters,
freshness/pad/demand/radius checks, bounded pagination and partial failures.

`test_mining_powerplay.py` covers observed versus associated merits, ambiguous
cargo, chronology, competing events, power/session resets, malformed numbers,
bounded history, replay and provider power/state validation. Its authenticated
MCP subprocess test exercises tool schemas/calls, native boolean query encoding,
state resources, the planning prompt, validation errors and wrong-token denial.

`test_mining_options.py` covers range caps and boundaries, live loadout/status changes,
missing range, source/destination eligibility, unknown yields, matching sale evidence
and changed price/state/pledge/freshness. The browser flow also tests map selection,
conditional versus recorded merits, ship-swap invalidation and stale responses.

`test_mining_guidance.py` covers partial attribution after reload, full sale
receipts, malformed amounts, controller-versus-presence, separate travel/mining
origins, acquisition boundaries and unknown evidence. The browser reproduces
the 168-ton sale, checks credit-only guidance and source exclusions, captures
desktop/mobile views, and rejects late buyer responses after journal changes.
