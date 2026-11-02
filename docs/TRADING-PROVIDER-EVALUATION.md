# Trading provider evaluation

Tested 2026-10-28. Recommendation: Spansh for embedded discovery and market
data; Inara for preferred external route/market views. This is a recommendation,
not an implemented provider switch.

## Live checks

Origin: Raleigh's Inheritance, Col 285 Sector GG-D a42-4. Cargo 720 t,
large pad, no fleet carriers, no surface stations, market age at most 24 hours,
station approach at most 10,000 Ls. Latest discovery comparison used 60 Ly.
Spansh used 100 million Cr starting capital and two hops, with repeated stations
allowed. Inara supply/demand filters were checked both at 720 and at the
standard 1,000 dropdown setting; its demand filter explicitly includes
unlimited/zero demand, unlike a strictly positive-volume check.

| Check | Inara | Spansh |
|---|---|---|
| Plain HTTP access | Repeated HTTP 503 responses in this environment | Form POST and JSON GET worked |
| Browser access | Installed Chrome, isolated profile, no login, worked repeatedly | Not required for tested API calls |
| Specified station pair | 40 visible round-trip combinations with standard filters | Station JSON supplies quotes for either direction |
| Discovery without destination | 41 results before filtering; zero visible after Round trips with standard filters | Found Muppet Enterprise and returned to Raleigh's |
| Timing samples | Broad page ready in 2.57-2.67 s; specified pair in 1.76 s | Submission 0.91 s; completed result retrieved by 3.62 s |

Timings are a few observations, not a performance or uptime benchmark. Inara
timings exclude browser startup and the subsequent filter wait. The discovery
result is specific to this search; its cause is unproven. Do not infer that
Inara generally cannot discover loops.

The matched round trip is 47.76 Ly each way:

- HN Shock Mount outbound: buy 1,828, sell 2,492 Cr/t; 478,080 Cr per load.
- Palladium return: buy 47,776, sell 71,482 Cr/t; 17,068,320 Cr per load.
- Total: 17,546,400 Cr. Both sources match for this pair.
- Return on combined purchase costs: 49.13%; profit/sales margin: 32.94%.

Inara showed market reports from 07:03 and 03:49 UTC that day. Spansh's route
job used an older Raleigh snapshot (03:54 UTC) than its station endpoint
(07:03 UTC), although the prices matched. Revalidate selected routes against
station market data and display observation times.

Spansh job: https://www.spansh.co.uk/trade/results/E9342CF8-D2A1-11F1-93DB-CE90DB26783F

## Integration implications

Inara's official developer guide explicitly excludes market and station data
from its API: https://inara.cz/elite/inara-api-devguide/
The working route interface is HTML and needs browser automation in this
environment. That adds browser discovery, process management, timeouts and
HTML parsing to a standard-library Python app. Browser success does not
establish an officially supported market API.

Spansh's website uses POST /api/trade/route with form-encoded parameters and
GET /api/results/{job} for asynchronous results. These were exercised live;
this is not a claim of a versioned API stability guarantee. EliteLab already
has Spansh JSON services in elitelab/core/services.py. Its current generic
POST helper sends JSON, so the planner requires a small form-POST adapter.
Station search and station market JSON offer a route to local loop ranking.

Do not equate two hops with a round trip. A previous Sol test returned A-B-C;
Raleigh happened to return A-B-A. Guaranteed loops must be explicitly
constructed/validated with station IDs, independent commodities per direction,
load limits, purchase affordability, freshness and carrier exclusions.

Keep the proposed Trading name, existing ship-aware inputs, and clear
outbound/return cards. Make Inara the preferred external destination with
prefilled station pairs and supported filters. Inara's tested distance
dropdown supports 10/20/30/40/60/80 Ly, not 50; do not silently misrepresent
an unsupported external filter. Provide a selected-route workflow independently
of which website supplied the quotes.

Only diagnostic scripts/results under ignored data/ were used. No application
code or provider setting changed during this evaluation.

## Implementation follow-up

Trading now uses Spansh station-search JSON directly and constructs exact loops
locally. It does not depend on the asynchronous two-hop planner. Live checks
found the Raleigh/Muppet loop at 17,546,400 Cr, both with an explicit destination
(2.3 s) and automatic discovery across 66 eligible stations (3.49 s). No browser
runtime or third-party package was added to the application. Inara remains the
preferred external station-market and route-pair view.
