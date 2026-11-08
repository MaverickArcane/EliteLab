# Sell the cargo aboard

Open **Trading**. **Sell cargo** starts from your latest complete cargo snapshot.
Choose radius, minimum pad and maximum report age, then **Find buyers for my cargo**.
More filters contains station breadth, arrival limit and surface-station access.
Search runs in the background; changing tabs does not cancel it.

The default search checks up to 100 reported eligible stations within 80 Ly,
requires large pads, excludes surface stations, limits approach to 10,000 Ls,
and accepts reports up to 24 hours old. Requests use 25-station pages to keep
full provider records below the shared download limit. Maximums are 300 stations, 500 Ly and
72 hours. Server filtering reduces wasted candidates; every result is checked
again locally against coordinates, pad, freshness, station type and commodity.
Carriers, stronghold carriers, prohibited offers, invalid prices and unknown
demand are excluded. Zero demand is not treated as unlimited without explicit
consumer evidence. Mission and stolen cargo are excluded from this legal-market
planner. A partial cargo snapshot cannot start a search.

| Strategy | Allocation | Tradeoff |
| --- | --- | --- |
| Highest prices found | Each commodity goes to the highest reported prices, capped by demand | May split cargo across more stops |
| Nearby stops | Favors remaining sale value divided by distance plus 10 Ly | A travel/value heuristic, not maximum profit per hour |
| One stop | Chooses the station taking most tonnes, then highest proceeds | Simplifies travel but can leave cargo unsold |

All strategies use the same returned eligible markets. There are at most 20
stops. Goods assigned to the same station are consolidated; travel order uses
nearest next stop. Distances are straight lines, not plotted fuel-safe jumps. Permit access is
unverified; confirm that you can reach each destination.
This is not a galaxy-wide optimum or a travelling-salesman solver. Unallocated
cargo and incomplete provider coverage remain visible. A later-page provider
failure keeps usable earlier results and marks them partial; an initial failure
shows an error with retry.

**Track this route** saves the selected plan for the current commander. It rejects
changed cargo/location and searches older than 30 minutes. Copy each destination
system and plot in game. Spansh market links open the specific reported market.
Only matching MarketSell receipts after selection advance a stop; transfers,
ejections and mere arrival do not. Replayed duplicates do not count twice.
Saved plans survive restarts and stay visible offline. Quotes over 24 hours old
and cargo that differs from the remaining plan are flagged; refresh buyers to
plan against the current hold. The receipt history stops accepting new progress
at 2,000 distinct sales without evicting deduplication evidence; start a fresh
route for the remaining cargo if that limit is reached.

Figures are **estimated proceeds**, not net profit. Whole-hold acquisition costs,
travel expenses, bulk-sale reductions and future demand are unknown. The Cargo
panel adds best-found price from the last search and last observed purchase price
when available. Last paid is a receipt, not weighted cost for the current hold.
No galaxy average is invented when the provider has not supplied one.

Use **Plan a round trip** for the existing personal route finder and Inara handoff.
Carrier loading, party membership and stock accounting live in **Carrier ops**.
These planners never buy, sell, move the ship or interact with the game controls.

Tools: `find_cargo_buyers` starts work and returns a job; poll
`get_cargo_sale_plan` about every two seconds. Use `select_cargo_sale_plan` with a
returned ID, or `clear_cargo_sale_plan`. Routes use the same HTTP/session/bearer
authorization as other tools. State is in `selling`; persistence is `selling.json`.
Quotes come from [Spansh](https://spansh.co.uk/stations), using community EDDN reports.
