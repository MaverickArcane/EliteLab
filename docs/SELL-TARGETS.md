# Rare sell targets

The Powerplay sell targets panel compares destinations for rare goods currently
aboard. Choose a travel origin, distance band, pad and maximum quote age, then
search. Each result shows travel effort, load value, conditional merits and the
price/source distance for each rare. Select a result to highlight it on EliteLab's
map; copy its system to plan the route in game. Selection does not plot a route.

## Price evidence and distance

Fresh Spansh market quotes take precedence. A usable quote must list the rare,
have a positive finite sale price, not mark it prohibited, and report demand
covering the quantity aboard. Missing listings do not establish refusal or
acceptance. Stale, future-dated and undated quotes cannot seed estimates.

Each rare's source comes from a journal MarketBuy at a known non-carrier station,
or the active rare-loop catalogue. Unknown/conflicting purchase locations stay
unknown. Search origin affects travel distance only; moving the search origin
does not move a rare's source. Quotes may still give a sale estimate when source
distance is unknown, but origin-dependent eligibility is unverified.

The chart groups reported prices by source distance, takes the median at each
distance, and joins observations linearly. It describes the searched markets,
not a universal game formula. Market conditions also affect prices. Optional
interpolation fills a missing price only for an explicitly listed legal good with
adequate demand and a distance between two observed points. It never extrapolates,
fills an absent listing, or replaces a reported price. Without enough evidence,
the price remains unknown.

Research checked 2026-11-02: [Rare Trading Distances Calculator](https://edtools.cc/rares?a=about)
describes increasing rare value with source distance and a plateau around
160-170 Ly. This supports tracking source distance; it does not supply verified
current per-commodity pricing coefficients. The planner therefore uses observed
quotes and explicitly optional interpolation, not hard-coded historical curves.
The default 125-200 Ly search band is a travel filter, not a promise of peak value.

## Merit assumptions

The default rate is unknown. The optional Mahon setting uses the owner's
October 2026 observation in [issue #2](https://github.com/MaverickArcane/EliteLab/issues/2):
approximately 667 Cr of sale value per merit with Mahon's bonus. Selecting it
assumes those bonus and eligibility conditions apply; it is rejected for other
powers. Custom rates are also user assumptions. Neither setting is a verified
current game-wide conversion law.

Estimated merits = complete estimated sale value / selected Cr-per-merit rate.
Any missing cargo price leaves the full load and merit totals unknown; a known
subtotal is shown separately. Known stolen, carrier-exposed or same-origin goods
block the merit forecast. Carrier-transfer/purchase flags conservatively persist
for that rare until a new LoadGame or changed commander; mixed batches cannot be
reliably separated here. All other eligibility remains unverified. Check local
Powerplay activities, origin rules and current bonuses before selling.

Jumps = ceiling(travel distance / minimum of unboosted laden and current range).
This is a straight-line lower bound, not a plotted route or a time estimate.
Merits per jump is consequently optimistic. Unknown range and zero-jump targets
have no finite merits-per-jump estimate. Planning never writes recorded merits.

## Coverage, MCP and boundaries

The search reads at most four pages of 25 orbital markets from a fixed Spansh
endpoint. It rechecks power, Unoccupied state, pad and distance locally, then
sorts by estimated merits per jump, total estimated merits, or travel distance.
Unknown metrics follow complete estimates. It shows up to 40 results by default
(100 maximum), reports coverage/partial errors, and does not claim a galaxy-wide
optimum. Planetary ports and carriers are excluded. Community data can lag.

`find_sell_targets` and `GET /api/targets` share the same handler. Parameters:
`power`, `ref`, `min`, `max`, `pad`, `limit`, `hours`, `sort`, `rate_mode`,
`credits_per_merit`, and `interpolate`. Native MCP booleans work. Results,
per-good evidence and curves are available in `elitelab://state/targets` and
`targets.last`. The `plan_rares_run` prompt preserves unknown rates and requires
explicit choice before interpolation. MCP searches appear in the panel when the
user has not edited its filters or started another search.

The planner writes only its own namespace. Journal handlers perform no network
or disk operations. Cargo, ship range, location, source catalogue and pledge
changes invalidate forecasts; commander changes reset purchase evidence. Newer
requests supersede older requests, including late browser/SSE responses. Existing
HTTP/MCP authentication applies. No new network destination, credentials or
write-to-game capability is introduced. Provider error details are not returned.

## Validation

`python -m unittest discover -s tests -p test_merit_targets.py` covers ranking,
per-rare origins, incomplete loads, bounds, invalid provider data, interpolation,
freshness, cargo restrictions, session boundaries, invalidation and authenticated
MCP schema/calls/resources/prompts with wrong-token denial.

`node tests/targets-browser.mjs` starts the real CLI in temporary directories,
drives Chrome through the actual HTTP/SSE flow, and checks result selection,
stale responses, ship changes, HTML escaping, retry and saved filters. Set
`ELITELAB_SCREENSHOT_DIR` to capture desktop and 390px layouts. Its journal,
coordinates and market responses are synthetic; it never uses the player's
journal or data directory. `ELITELAB_TARGETS_LIVE=1` enables live Spansh quotes
with a synthetic commander/cargo and unknown source coordinates. This can test
provider compatibility, not actual rewards or an in-game sale.
