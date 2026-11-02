# Mining desk

The Mining card connects finding a ring, tracking production and selling the
haul. Use the Mining & trade layout for the full-width desk, or enable Mining
in the Layout menu. Journal tracking works offline; community searches require
Spansh. The forms retain edits during live updates and save filters in this browser.

## Find, mine, sell

1. Search near your current system. Filter ring type, reserve level, optional
   reported hotspot, and optional Powerplay acquisition candidate for a power.
2. Compare distance, approximate jumps, arrival distance, reserves and dated
   hotspot reports. Set a destination to highlight it on the map and prefill
   the buyer search origin; copy the system into the game's navigation search.
3. Prospect and refine. Composition bars, produced tons, tracked unsold units,
   tons/hour and the session ledger update from journals.
4. Open Sell your haul. Use tracked haul fills the largest remaining commodity
   and its quantity. Search buyers with a radius, minimum pad and market-age
   limit. Quotes require positive prices and enough reported demand.
5. Use a quote to estimate the tracked unsold value of that commodity. Actual
   journal sales update the ledger; a quote never becomes realized income.

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
cargo, attributed sales, and quote estimates. There is no Powerplay merit estimate.

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
`refined_tons`, `commodities`, `other_tons`, `profit`, and `rate_note`.
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
