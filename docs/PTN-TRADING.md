# PTN trade desk

The `ptn` module is a dedicated affiliate trade planner. It reads `journal` and
`trade`, writes only `ptn`, and persists its independent operation in `ptn.json`.
It never places game orders, moves a carrier, posts Discord messages, or changes
the existing Carrier job. Cancelling a local plan does not cancel those actions.

## Offer and discovery

Defaults: up to 18,000 t, a preferred public payout of 20,000 Cr/t, minimum public
payouts of 10,000 Cr/t, 1,000 Cr/t minimum carrier margin before costs, a
5,000,000 Cr fuel/fee reserve, and 450 Ly radius and carrier leg. Common and active
commodities are included; explicit exclusion controls remain available. Smaller
orders down to 2,000 t are allowed when supply or demand cannot cover the maximum.
Report age is at most 24 hours and station approach at most 10,000 Ls.

The preferred payout is a ranking target, not a rejection threshold. All profitable
routes are visible by default; "At target" filters them explicitly. Minimum public
payouts remain hard limits. These preferences are not PTN rules or promises of
turnout. The board shortcut changes the preferred target, never those hard limits.

Three hauling modes are available: public haulers on both legs, owner loads and
haulers unload, or haulers load and owner unloads. A self-hauled leg has no public
payout or advert; its purchase cost or sale proceeds come from the station. The
owner records the actual average price and remaining tonnes during that phase.
The full order still requires hauling; self-hauling does not make those trips free.

Surplus-sharing mode maximizes the weaker public payout, then combined public
payout, over the available carrier price settings. It reserves the larger of the
owner's per-tonne margin and `floor(cost_reserve / actual_quantity) + 1`. Thus every
qualified result retains a strictly positive total after the reserve, including
smaller orders and a zero owner-margin preference. Switch sharing off to retain
the spread above the public payout minimums instead. On a self-hauled leg, the
unpaid payout is zero and excluded from the optimization objective.

The whole-percent model uses 5%-1000% and `(mean * percent + 50) // 100`.
Suggested prices must support public payout minimums and the owner margin. Unknown
references and impossible settings stay unqualified. Actual displayed in-game
prices are entered and checked before an advert is generated. Income remains
estimated: fuel, price changes and remaining market volumes are not guaranteed.

Sources:

- Ardent/EDDN: `https://api.ardent-insight.com/v2/commodities` and
  `/system/name/{system}/commodity/name/{commodity}/nearby/exports` or `imports`.
  Up to 1,000 nearby reports per side and 15 eligible stations per side for each
  of at most 48 catalog candidates; default 32. The old global best-100 endpoints
  could discard local stations before local filters ran. It is not an
  exhaustive route search and is not Inara market data.
- Public PTN missions: `https://pilotstradenetwork.com/wp-json/ptn/v1/missions`.
  Only official adverts are covered. Affiliate adverts and unadvertised carriers
  are unknown. Board snapshots older than 15 minutes are unavailable. Displayed
  medians are comparisons, not market requirements or predictions of turnout.

Discovery excludes surface stations, carriers, unknown station types, missing
large pads, missing coordinates/arrival distances and stale reports. Both stops
must be within the selected radius of the carrier and within the selected
carrier leg of each other. Zero demand is not assumed unlimited.

Common cargo exclusions are optional through the common-cargo toggle and custom
list: agronomic treatment, gold, silver, bertrandite, indite, gallite, palladium,
and tritium. The public-board exclusion optionally skips commodities with an
official advert. Failure of that feed is shown as unknown competition. Known
same-station, same-commodity loading adverts reduce the available supply buffer
and optional smaller-order size. The current carrier is not counted as its own
competitor. Common-cargo status and known source competition are visible on results.
Profitable routes are the default results. Rejected candidates are shown only when
requested, with the available spread, required spread and shortfall instead of
projected profits or hauler earnings. Payout floors are not silently reduced.

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
3. Open loading after both scouts and the economic checks pass. On a public leg,
   confirm proximity
   to the station body, docking access, market funding/service and competition.
   Enter the actual carrier buy price and remaining order, rather than inferring
   that a suggested percentage was applied in game. On an owner-hauled leg, record
   the actual average station cost/proceeds and remaining tonnes instead. Public
   advertising is disabled for that leg.
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

Confirmed station prices expire after one hour, independently of the broader
discovery report-age setting; order confirmations and carrier management stats
also expire after one hour. Re-capturing markets clears affected checks while retaining
historical loading cost after departure. Mutations require the current revision;
failed disk writes leave the previous plan intact. A party member cannot mutate
the owner's plan. No remote network calls occur in bus handlers or at startup.

The UI uses `ptn.preferences.v2`; old browser preferences remain stored under v1
but do not reapply the old restrictive defaults. Saved operations retain their
explicit route settings. "Restore normal search settings" resets only the search
form. Search settings and result lists scroll independently on desktop; open
details, focused fields and scroll positions survive live state updates.
Revision, plan identity and stage markers keep queued SSE fields from replacing
a newer POST response or displaying mismatched operation details. A revision
conflict refreshes the plan without replaying the rejected mutation.

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
The nearby query shape and response limits follow the
[Ardent API documentation](https://github.com/iaincollins/ardent-api/blob/main/README.md).
The affiliate formatting follows the owner's provided Discord instructions.

## Security review (2026-11-07)

Reviewed the PTN routes, pricing, persisted-plan mutations, provider ingestion,
journal capture, HTML rendering and shared HTTP protections. Changes from this
review:

- Provider reports must match the requested commodity. Station/body names,
  prices, volumes, market IDs and mean prices are validated and bounded. Rare
  catalog entries are excluded even when absent from the local rare-goods list.
- Advert text rejects Unicode controls, invisible formatting controls and line
  separators, as well as mentions and backticks. HTML values remain escaped.
  Discord links must be exact numeric message URLs, without suffixes or controls.
- Route selection is tied to the carrier owner and location that produced the
  scan. An owner/location change during scanning discards that result. Existing
  revision checks, owner checks and atomic writes remain in place.
- A raw journal mean price must belong to the same timestamp and market as the
  captured normalized market. Discovery's 24-hour window cannot authorize a
  24-hour-old posting scout. Expired board snapshots no longer supply benchmarks.
- Provider exception details are not returned in public-board errors. Searches
  allow only one active scan, four provider workers, at most 48 commodities,
  1,000 reports per side and 15 eligible stations per side. After a 90-second
  report deadline queued work is cancelled and completed reports are returned
  with a coverage warning. In-flight requests may take the shared 40-second
  socket timeout to finish. Catalog/board requests precede that report deadline.
  The shared network layer bounds each response at 8 MiB and caches requests.

Real HTTP tests verify configured-token authentication, hostile Origin rejection,
DNS-rebinding Host rejection, JSON-only mutations, cross-site API rejection,
forged route IDs, party-member restrictions, CSP and nosniff headers. Browser
tests put malicious HTML in station and public-board names and verify it stays
text. These checks found no remaining reproducible bypass in the tested paths;
they are not an audit of the entire application or external providers.

Scope and limits: PTN inherits the app's network access policy. An installation
without a token trusts clients that can reach its permitted HTTP address. Market
feeds and local game journals are reports, not authoritative transaction receipts.
The owner still verifies the in-game price and order. There are no Discord tokens,
shell execution, user-selected network destinations, or automated game actions in
this module. Unknown/zero demand remains unqualified; this can omit legitimate
buyers and is not interpreted as unlimited demand without additional evidence.

## Validation

`python -m unittest discover -s tests -p 'test_ptn*.py' -v` exercises currency
conservation, payout floors and rounding, commodity/market filters, board
exclusions and failures, journal scouting, stale data, capacity reservations,
partial orders, historical purchase costs, actual prices, owner scope, revision
checks, atomic persistence, advert injection protection, normal-search defaults,
both self-hauling modes, nearby-report coverage, deadlines and
real HTTP security boundaries.

`node tests/ptn-browser.mjs` uses real HTTP/SSE and offline provider/journal
fixtures for discovery, scout rejection/retry, both trading phases, posting
readiness, exact Markdown, soft board targets, smaller orders, owner loading,
provider HTML injection and reload persistence. Captures and
viewport bounds cover 3440x1440, 1920x1080, 1366x768, 1280x720 and 390x844.
CI preserves these images. Fixtures are illustrative, not live opportunities.
