# Trading workflows

This is the target workflow for EliteLab's trading panels (#41). It names the
workflows the dashboard supports, the order they matter in, the panels each one
uses, and what the player should be able to do without reading a table twice.
The rare-goods buying loop is documented in [RARE-GOODS.md](RARE-GOODS.md).

## Workflows and priority

| Priority | Workflow | Start here | Then | Evidence that counts |
|---|---|---|---|---|
| 1 | General commodity trading | Trading: find routes, select one | Cargo, Star map | Observed cargo, exact docking, recorded MarketBuy/MarketSell at the planned station |
| 2 | Rare-goods run | Rares loop | Cargo, Local market, Rare sell targets | Exact station, cargo snapshot, current-visit market snapshot |
| 3 | Powerplay selling | Powerplay sell targets, Powerplay | Trading or Rares loop for the goods | Pledge, system control, a PowerplayMerits event after the sale |

General trading comes first because it is the workflow the most commanders run
most often and the one with the least connected support before this work. The
rares run already has its buying loop (#71). Powerplay selling depends on the
expected-merit estimates tracked in #2 and keeps using the sell-target finder.

## The flow: choose, buy, travel, sell

1. **Choose.** Search from the current system with the current ship. The
   comparison table ranks routes by estimated profit and shows, per route:
   combined profit, profit per tonne of hold, straight-line distance per leg,
   estimated laden jumps, return on purchase costs, starting credits needed, the
   age of the oldest market report and the landing pads. Details expand the
   full outbound and return legs with copy buttons and Inara links. The top
   route is expanded by default; the table shows ten and can show all thirty.
2. **Select.** One route is the active plan. It is stored by the server
   (`data/personal.json`), so it survives restarts, shows the same way in every
   browser and to MCP clients, and is drawn on the map as the trade route layer.
3. **Buy.** The selected-route panel names the next action: travel to the buy
   station or, once docked there exactly, buy the planned tonnes (less what is
   already aboard). It shows the straight-line distance, tonnes of the planned
   goods aboard, the report age, and whether reported credits cover the purchase.
4. **Travel.** When the planned goods are aboard, the next stop becomes the sell
   station. Show on map draws a dashed line from the ship to that stop. Copy
   system and Copy station put names on the clipboard; nothing plots an in-game
   route.
5. **Sell.** Docked at the sell station exactly, the action is to sell what is
   aboard. A leg counts as sold only from MarketSell events at the planned
   market ID after the route was selected; a partial sale shows tonnes sold so
   far and completes when the hold is observed empty of those goods. Round trips
   then move to the return leg at the same station. Complete routes report the
   recorded sale total.

## Evidence states

| Signal | Shown as | Never implies |
|---|---|---|
| Cargo snapshot consistent | `N t aboard`, buy quantity reduced | A purchase at the planned station |
| Cargo unknown or inconsistent | `Cargo unknown`; stage from docking and recorded purchases | An empty hold |
| Docked at exact system and station | `Docked at ...`, stage buy/sell | Stock, demand or price |
| MarketBuy/MarketSell at the planned market ID since selection | bought/sold tonnes, recorded sale total | Profit (purchase price is in the journal history) |
| Report age under 12 h / under 48 h / older | fresh / aging / stale | Current prices |
| Reported credits below the purchase | `Credits short for this purchase` | Exact affordability (fees, insurance) |
| Journal commander differs from the selector | Warning to clear or reselect | Anything about the other commander's cargo |

Spansh quotes are community reports. Distances are straight lines. Profit
excludes fuel, fees and bonuses. The browser escapes every station, system and
commodity name; market text can be hostile.

## Comparisons the table supports

Profit for the route, profit per tonne, distance and estimated laden jumps per
leg, return on purchase costs, starting credits, report age and landing pads.
Missing values show as `-` or `unknown`, never as zero. Expected merits per
sale belong to the Powerplay workflow and #2, not to this table.

## Panels and handoffs

| Panel | Role in general trading |
|---|---|
| Trading | Search, compare, select; the selected route and its next action |
| Cargo | What is aboard; the Trading panel links to it |
| Star map | `trade route` layer: buy stop in gold, sell stop in blue, next stop larger, dashed line when shown on map |
| Ship | Capacity and laden range that the search defaults use |
| Location | Exact docking that the stages depend on |

The Trading layout preset arranges these together. The selected-route panel
updates live from the journal without rebuilding the search form, so typed
filters survive docking, cargo and credit updates.

## States

- Loading: the Find routes button disables and the status line says what is being compared.
- Empty: the table explains why no routes matched and what to loosen.
- Error or offline: the server's message replaces the status line; the previous plan stays.
- No plan: the panel says how to select one.
- Narrow screens: the comparison table scrolls sideways inside the card; stops stack in one column.

## API and MCP

`find_personal_trade_routes` rows now carry `id` and each stop carries `pos`.
`select_trade_route` (`POST /api/personal/plan`, `id` from the latest search)
sets the plan; `clear_trade_route` (`POST /api/personal/plan/clear`) removes it;
`get_trade_plan` (`GET /api/personal/plan`) returns `plan` and `progress`, the
same object the browser receives over SSE. See [API.md](API.md) and
[STATE.md](STATE.md) for the fields.

## Validation

`python -m unittest discover -s tests -p test_trade_plan.py -v` covers route
ids, persistence and validation of the saved plan, failed saves, stage
transitions from docking, cargo and recorded sales, partial sales, events before
selection or at other markets, unknown cargo, report age, credits and commander
changes, and that journal handlers never write files or fetch.

`node tests/browser.mjs` drives the real card in headless Chrome: comparison
table and details toggle, a rejected selection, a fixture plan arriving over SSE,
the next action changing on dock and cargo updates while typed filters survive,
hostile station names, the map layer and its selection, the narrow-screen table,
and clearing the route. Spansh is offline in these tests; nothing here claims
current game prices.

## Status under #41

- Expected merits per rare sell target and merit-first comparisons are covered by merged #69 (issue #2). Forecasts remain conditional on game and market evidence.
- The explicit destination handoff is covered by merged #75 (issue #74); see [TRADE-POWERPLAY.md](TRADE-POWERPLAY.md). Sale acceptance and merit rewards still require game evidence.
- The default-panel audit and before/after mockups are in [PANEL-AUDIT.md](PANEL-AUDIT.md). The implementation follow-ups are #77 for cargo and local market evidence, #78 for merit context, and #79 for the live feed.

## Selected trade in Cargo and Market (#77)

Cargo highlights the active leg's commodity, observed tonnes aboard and amount
left to buy while retaining every other cargo row. The Market card shows a local
buy or sell quote only when Market.json has the active stop's exact market ID,
the ship is docked there and the snapshot was taken during this visit. Missing,
old, mismatched or truncated entries are labeled as unknown, never zero stock.
The community route quote in Trading remains a separate estimate. The local
snapshot is available to HTTP and MCP clients in `get_commander_state.market`.

## Combined panel validation (#41)

The browser regression uses one synthetic trade to exercise the selected route,
observed cargo, exact-stop market quote, partial sale and filtered live feed.
A nearby synthetic PowerplayMerits event appears as a recorded amount with an
uncertain association to the sale. The scenario checks the corresponding
HTTP tool responses and desktop and narrow layouts. It does not establish
in-game sale eligibility, merit rates or the freshness of live market data.
