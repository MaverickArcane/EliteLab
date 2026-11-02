# Rare-goods buying workflow

Open **Trading** for commodity routes and the rare-goods panels, or choose
**Layout > Rare goods** to arrange the buy loop, cargo, local stock, sell targets
and map together. Choosing a workspace preserves the custom layout; applying a
layout preset deliberately replaces its arrangement.

The workflows serve different purposes:

| Workflow | Start here | Evidence to check |
|---|---|---|
| General trading | Personal trade planner | Commodity quotes, supply, demand and quote age |
| Rare run | Rares loop, then Cargo and Rares at this market | Exact buy station, observed cargo and stock recorded during this visit |
| Powerplay sale | Rare sell targets and Powerplay | Eligible activity, pledge and system control; confirm an actual merit event after selling |

The next buy stop is the nearest unmarked stop when coordinates are available.
Offline or unavailable coordinates leave distances unknown and retain listed
order. Select a stop to highlight it on the map; Copy system puts its name on
the clipboard. Neither action plots a route in Elite Dangerous. The map cannot
draw a stop without coordinates, but the station list and copy action still work.

Docked status requires both the system and the exact station. A cargo snapshot
marks a stop when its rares are aboard; it does not prove a purchase at that stop.
Unknown or inconsistent cargo is distinct from an observed empty hold. Cargo
from before a new game session or commander is unverified until a new snapshot
arrives. Free capacity also requires a recorded capacity.

Manual visit marks are local to this browser, commander and loop. They survive
reload with unchanged cargo, reset when that cargo snapshot changes, and can be
cleared with **Reset my visit marks**. Other browsers and MCP clients see only
cargo-based progress. A marker is not a purchase, profit or merit receipt.

Open the commodities market in game to refresh local rare stock. Its card labels
the station, observation time, buy prices and positive stock in that snapshot:

| `workflow.market.status` | Meaning |
|---|---|
| `not_recorded` | No station market snapshot was observed |
| `previous_station` | Not docked at the snapshot's exact system and station |
| `undated` | Timestamp is missing, invalid or in the future |
| `previous_visit` | Snapshot predates arrival, or arrival time is unknown |
| `current_snapshot` | Snapshot was recorded during this station visit; stock can still change |

Missing stock is not a zero-stock claim. Buy prices are not sell quotes. The
loop's static station list is a planning aid; check access and stock in game.
Distance alone does not establish Powerplay eligibility or guarantee merits.

## API and MCP

`GET /api/loop` and `get_rares_loop` return the same state. Station `tons` and
`tons_total` are null when cargo is unknown. `workflow` adds `cargo_known`,
`free_capacity` and the market status/source/time/rare rows above. `docked_here`
requires an exact station match. `done_count`, `complete` and `next` use observed
cargo, not browser marks or map selection.

`POST /api/loop/select` and `select_rares_loop` accept only an advertised loop ID;
invalid selection or a failed save preserves the prior choice. Existing token,
Host, Origin and JSON request protections apply. No new network service or MCP
tool is added. Journal callbacks compute state without disk or network work;
coordinates remain asynchronous. The browser escapes market-derived text.

## Validation and remaining work

`python -m unittest discover -s tests -p test_rares_workflow.py -v` checks journal
transitions, unknown/empty cargo, exact station identity, invalid evidence,
selection failures, authentication and real stdio MCP parity.

`node tests/rares-browser.mjs` starts an isolated real CLI and headless Chrome,
writes synthetic game files, observes API/SSE updates, tests reload/manual marks,
market refresh, HTML escaping, failed-request recovery and navigation, and saves
desktop/mobile screenshots. Set `ELITELAB_SCREENSHOT_DIR` to choose their folder.
Network providers are offline in this test; it does not establish current game
stock, prices or merit rewards. CI runs the test and retains the screenshots.

This closes the focused buying-workflow issue #71. Parent #41 remains open for
the other panel workflows and any remaining mockup/acceptance work. Rare-price
curves and merits-per-jump changes remain tracked separately by #2 / PR #69.
