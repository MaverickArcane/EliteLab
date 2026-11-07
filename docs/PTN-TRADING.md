# PTN trade desk

The `ptn` module is a dedicated affiliate trade planner. It reads `journal` and
`trade`, writes only `ptn`, and persists its independent operation in `ptn.json`.
It never places game orders, moves a carrier, posts Discord messages, or changes
the existing Carrier job. Cancelling a local plan does not cancel those actions.

## Offer and discovery

Defaults: 18,000 t, 20,000 Cr/t minimum for loading and unloading, 2,500 Cr/t
minimum carrier margin, a 5,000,000 Cr fuel/fee reserve, and 450 Ly radius and
carrier leg. These are adjustable preferences, not PTN rules. Hauler-first mode
shares surplus spread after the owner's minimum: it maximizes the weaker hauler
payout, then combined hauler payout, over the available carrier price settings.
Switch it off to retain the spread above the two payout floors instead.

The whole-percent model uses 5%-1000% and `(mean * percent + 50) // 100`.
Suggested prices must support both payout floors and the owner margin. Unknown
references and impossible settings stay unqualified. Actual displayed in-game
prices are entered and checked before an advert is generated. Income remains
estimated: fuel, price changes and remaining market volumes are not guaranteed.

Sources:

- Ardent/EDDN: `https://api.ardent-insight.com/v2/commodities` and commodity
  `exports`/`imports`. Up to 100 reports per side and 15 eligible stations per
  side for each of at most 48 catalog candidates; default 24. It is not an
  exhaustive route search and is not Inara market data.
- Public PTN missions: `https://pilotstradenetwork.com/wp-json/ptn/v1/missions`.
  Only official adverts are covered. Affiliate adverts and unadvertised carriers
  are unknown. Board snapshots older than 15 minutes are unavailable. Displayed
  medians are comparisons, not market requirements or predictions of turnout.

Discovery excludes surface stations, carriers, unknown station types, missing
large pads, missing coordinates/arrival distances and stale reports. Both stops
must be within the selected radius of the carrier and within the selected
carrier leg of each other. Zero demand is not assumed unlimited.

Common cargo exclusions are editable through the common-cargo toggle and custom
list: agronomic treatment, gold, silver, bertrandite, indite, gallite, palladium,
and tritium. The public-board exclusion optionally skips commodities with an
official advert. Failure of that feed is shown as unknown competition. Known
same-station, same-commodity loading adverts reduce the available supply buffer.
The desk shows near misses without silently reducing payout floors.

The hauler credits/hour and operation-time figures are explicit scenarios using
an editable example hold, round-trip time and number of haulers. They do not
measure or guarantee actual traffic, completion times or a competitive offer.

## Scout, operate, advertise

1. Select a candidate; this saves a scouting plan with a revision and immutable
   carrier/commander identity. Choosing a new plan replaces only the PTN draft.
2. Dock at each selected orbital station and open its market. Capture the current
   visit's journal snapshot. The server requires matching market ID, station,
   system, station type and a snapshot no older than 15 minutes. The recorded
   price, volume, source and observation time remain visible.
3. Open loading after both scouts and the economic checks pass. Confirm proximity
   to the station body, docking access, market funding/service and competition.
   Enter the actual carrier buy price and remaining order, rather than inferring
   that a suggested percentage was applied in game.
4. Generate the affiliate advert. The server checks readiness every time, including
   quote age, volume, owner scope, location, order price and capacity. Other buy
   orders' reserved space is not available capacity. Matching recent reservations
   belonging to this confirmed order can cover its own remaining tonnes.
5. Use `/aco trade`, review its generated message, paste into
   `affiliate-trade-alerts` without role pings, and review/confirm Roomba. The
   optional separate note is `SCO FSD recommended.` Exact profits and quantities
   use up to three decimal places in `k` notation, never rounded up.
6. Record posting locally only after posting and confirming in Discord. The
   optional message link and 48-hour timeout are local reminders. Update the
   original message using `/aco stock_update`; Roomba reactions close it.
7. Confirm zero remaining before departure; move the carrier, open unloading,
   confirm the sell order and generate the unloading advert. The actual price
   paid during loading remains the purchase-cost basis after departure.

Owner-entered remaining counts are timestamped. A newer matching journal carrier
order updates the advert quantity. Newer changed order prices/sides require a
fresh confirmation. Stage changes themselves are explicit owner declarations,
not inferred delivery receipts. No archive of individual public haulers is kept.

Confirmed station prices expire at the selected market age; order confirmations
and carrier management stats expire after one hour. Re-capturing markets clears affected checks while retaining
historical loading cost after departure. Mutations require the current revision;
failed disk writes leave the previous plan intact. A party member cannot mutate
the owner's plan. No remote network calls occur in bus handlers or at startup.

## Tools

| Tool | Route | Purpose |
|---|---|---|
| `get_ptn_desk` | GET `/api/ptn` | Current plan, context, readiness, last scan and board |
| `get_ptn_public_board` | GET `/api/ptn/board` | Refresh official missions and median payouts |
| `find_ptn_routes` | GET `/api/ptn/search` | Bounded route scan with explicit filters |
| `select_ptn_route` | POST `/api/ptn/select` | Save a recent route by id and revision |
| `capture_ptn_market` | POST `/api/ptn/capture` | Capture current journal market, side buy/sell |
| `update_ptn_plan` | POST `/api/ptn/update` | Stage, confirm, remaining or posted actions |
| `prepare_ptn_advert` | GET `/api/ptn/advert` | Recheck and generate exact affiliate Markdown |

See PTN's [carrier trading guide](https://pilotstradenetwork.com/guides/fleet-carrier-trading/)
and [hauler guide](https://pilotstradenetwork.com/guides/ptn-trade-alerts/).
The affiliate formatting follows the owner's provided Discord instructions.

## Validation

`python -m unittest discover -s tests -p test_ptn.py -v` exercises currency
conservation, payout floors and rounding, commodity/market filters, board
exclusions and failures, journal scouting, stale data, capacity reservations,
partial orders, historical purchase costs, actual prices, owner scope, revision
checks, atomic persistence and advert injection protection.

`node tests/ptn-browser.mjs` uses real HTTP/SSE and offline provider/journal
fixtures for discovery, scout rejection/retry, both trading phases, posting
readiness, exact Markdown, board targeting and reload persistence. Captures and
viewport bounds cover 3440x1440, 1920x1080, 1366x768, 1280x720 and 390x844.
CI preserves these images. Fixtures are illustrative, not live opportunities.
