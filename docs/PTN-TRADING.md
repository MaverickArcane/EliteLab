# PTN trade desk

Discovery now returns a background `search_job` immediately. Poll
`get_ptn_desk` (about every two seconds) for completion or failure; duplicate
searches are rejected while a job runs. The browser follows the same contract.
Newer matching contradictory journal markets revoke the affected scout and
posting confirmations, including missing items, invalid prices and lost
producer/consumer evidence. Recapture valid evidence and reconfirm to recover.
See [Carrier ops handoff and mining limits](GROUP-MINING.md#working-with-ptn).

The `ptn` module is a dedicated affiliate trade planner. It reads `journal` and
`trade`, writes only `ptn`, and persists its independent operation in `ptn.json`.
It never places game orders, moves a carrier, posts Discord messages, or implicitly changes the existing Carrier job. The explicit
`handoff_ptn_to_carrier` action copies a freshly scouted loading route into a
separate Carrier ops draft; it rejects stale revisions and active carrier jobs. Cancelling a local plan does not cancel those actions.

## Offer and discovery

Defaults: up to 18,000 t, a preferred public payout of 20,000 Cr/t, minimum public
payouts of 20,000 Cr/t, 1,000 Cr/t minimum carrier margin before costs, a
5,000,000 Cr fuel/fee reserve, and 1,500 Ly to the loading source and from there
to the buyer. Common and active
commodities are included; explicit exclusion controls remain available. Smaller
orders down to 2,000 t are allowed when supply or demand cannot cover the maximum.
Report age is at most 24 hours. The optional station approach limit defaults to
0 (no cutoff): a carrier parked near the station body can make hauling practical
even when that station is far from the main star. Arrival distance remains visible.
Loading and unloading are orbital by default. Surface loading is an explicit
option; unloading remains orbital. Large pads are required in both cases.
Valid zero-demand buyers are included as unlimited demand. Their reported price
still needs scouting; missing demand and zero loading stock do not qualify.

All non-rare catalog commodities are searched by default (`breadth=0`, safety
cap 500), after explicit exclusions. Stale catalog prices and stock only prioritize
requests; they cannot exclude a commodity. Completion counts distinguish checked
commodities from missing feeds and optional commodity limits. Up to six candidates
per commodity and 200 total are returned, with alternate loading sources included
before filling every slot with buyers for one source, ranked by carrier return after reserve,
then hauler payout and minimum jumps. These remain bounded market reports, not an
exhaustive list of every station.

The preferred payout is a comparison target, not a rejection threshold. Profitable
routes are visible by default; "At target" filters them explicitly. Minimum public
payouts remain hard limits. These preferences are not PTN rules or promises of
turnout. The board shortcut changes the preferred target, never those hard limits.

Three hauling modes are available: public haulers on both legs, owner loads and
haulers unload, or haulers load and owner unloads. A self-hauled leg has no public
payout or advert; its purchase cost or sale proceeds come from the station. The
owner records the actual average price and remaining tonnes during that phase.
The full order still requires hauling; self-hauling does not make those trips free.

By default, the carrier retains the spread above both public payout minimums.
Optional surplus-sharing mode maximizes the weaker public payout, then combined public
payout, over the available carrier price settings. It reserves the larger of the
owner's per-tonne margin and `floor(cost_reserve / actual_quantity) + 1`. Thus every
qualified result retains a strictly positive total after the reserve, including
smaller orders and a zero owner-margin preference. Switch sharing off to retain
the spread above the public payout minimums instead. On a self-hauled leg, the
unpaid payout is zero and excluded from the optimization objective.
Loading and unloading minimums and surplus sharing are visible in the main form.
The 20k/20k and 30k/20k presets set independent minimums, use public haulers on
both legs, and turn sharing off so the carrier keeps the remainder. They leave
station filters, order size and the preferred comparison target unchanged.

The whole-percent model uses 5%-1000% and `(mean * percent + 50) // 100`.
Suggested prices must support public payout minimums and the owner margin. Unknown
references and impossible settings stay unqualified. Actual displayed in-game
prices are entered and checked before an advert is generated. Income remains
estimated: fuel, price changes and remaining market volumes are not guaranteed.

Sources:

- Ardent/EDDN: `https://api.ardent-insight.com/v2/commodities` and
  `/system/name/{system}/commodity/name/{commodity}/nearby/exports` or `imports`.
  Nearby also excludes the reference system. Two bulk current-system
  `/system/name/{system}/commodities/exports` or `imports` calls restore those
  markets, bounded to 10,000 orders per side with explicit coverage warnings.
  Nearby endpoints silently cap distance at 500 Ly and return up to 1,000 reports.
  Wider searches add `/commodity/name/{commodity}/exports` or `imports` for up to
  100 global price leaders per side. Coordinates then enforce the requested bounds.
  Date-based provider requests include one extra UTC date; local timestamp checks
  enforce the exact selected hours, including quotes from before midnight.
  Global price leaders supplement nearby reports; they do not replace them.
  Newest reports win per market before validation. Up to 50 eligible orbital
  stops per side and 50 surface sources survive for pairing. Missing or capped
  feeds are counted. Coverage beyond 500 Ly can miss stations outside the global
  top 100; this is not exhaustive market coverage and is not Inara data.
- Public PTN missions: `https://pilotstradenetwork.com/wp-json/ptn/v1/missions`.
  Only official adverts are covered. Affiliate adverts and unadvertised carriers
  are unknown. Board snapshots older than 15 minutes are unavailable. Displayed
  medians are comparisons, not market requirements or predictions of turnout.

Discovery excludes surface unloading, carriers, unknown station types, missing
large pads, missing coordinates/arrival distances and stale reports. The loading
source must be within the selected starting radius; the buyer must be within the
selected leg distance from that source, even if beyond the starting radius.
Controls allow one to five 500 Ly carrier jumps per leg. Displayed counts use
unrounded straight-line distances and are lower bounds, not plotted routes.
Check intermediate systems and include all travel in the editable cost reserve;
fuel usage and tritium cost are not simulated. Zero demand is not assumed unlimited.
Known surface types are CraterOutpost, CraterPort and OnFootSettlement, plus
their Planetary Outpost, Planetary Port and Odyssey Settlement aliases. Surface
loading remains excluded until enabled. A summary counts distinct commodity/source
pairs that otherwise have a profitable route to an orbital buyer, using the same
payout, reserve, volume, competition, age and distance checks. It shows up to three
examples and an explicit button to enable surface loading and search again.
These counts cover only the bounded scan and are estimates, not scouted offers.
Separate station buckets keep cheap surface stock from displacing orbital options.

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
2. Dock at each selected station and open its market. Capture the current
   visit's journal snapshot. The server requires matching market ID, station,
   system, station type and a snapshot no older than 15 minutes. The recorded
   price, volume, source and observation time remain visible.
   Surface capture requires the saved surface-loading option, a loading stop and
   a matching surface station category; enabling it cannot permit surface buyers.
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
   Surface loading adds a brief surface-port note; Odyssey is named only for a
   known Odyssey station type. The journal determines the captured station type.
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

The UI uses `ptn.preferences.v3`. Migration from v2 widens both legs to 1,500 Ly,
removes the star-approach cutoff, checks all commodities, uses public haulers on
both legs and retains surplus.
Custom payout minimums and order size are retained; old default 10k minimums
become 20k. The form explains the migration before searching. Saved operations
retain their explicit route settings. "Restore normal search settings" resets only the search
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
  allow only one active scan, four provider workers, at most 500 commodities,
  1,000 nearby and 100 global reports per side, 50 orbital stops per side and 50
  surface sources. After a 300-second
  report deadline queued work is cancelled and completed reports are returned
  with a coverage warning. In-flight requests may take the shared 40-second
  socket timeout per request to finish (up to two sequential feeds per running
  job). Catalog/board and current-system requests precede that report deadline.
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
this module. A valid Ardent buyer report with an explicit integer demand of zero
and positive sell price is treated as unlimited demand, following Ardent's import
query and PTN's trading guide. Stops retain `volume: 0` and set
`demand_unlimited: true`; the UI labels this "Unlimited demand (reported 0)".
Missing, invalid or negative demand is rejected; zero loading supply remains empty.
Unlimited demand does not cap the order quantity, but requested quantity, loading
supply and competition still do. Finite demand continues to limit partial orders.
Local zero-demand capture requires matching raw journal evidence with explicit
zero `Demand` and a positive `SellPrice`; an explicit `Consumer: false` is rejected.
Old saved zero-demand scouts without that evidence require recapture. Rechecks
replace the flag, invalidate affected confirmations and still expire after an hour.
Unlimited demand does not guarantee that the price will remain unchanged.

## Validation

`python -m unittest discover -s tests -p 'test_ptn*.py' -v` exercises currency
conservation, payout floors and rounding, commodity/market filters, board
exclusions and failures, journal scouting, stale data, capacity reservations,
partial orders, historical purchase costs, actual prices, owner scope, revision
checks, atomic persistence, advert injection protection, normal-search defaults,
both self-hauling modes, nearby-report coverage, deadlines and
real HTTP security boundaries. Surface tests cover opt-in, hidden profitable
source counts, station and pad restrictions, legacy plans, scouting and adverts.
Wider-search tests cover more than 48 commodities, stale catalog totals, separate
source/buyer bounds, multi-jump distances, retained-profit ranking, deduplication,
missing global feeds, current-system markets, distant station approaches,
alternate loading sources and honest partial coverage.
Zero-demand tests cover full and partial orders, source competition, invalid and
missing reports, matching journal evidence, persistence, recapture, expiry and
both adverts without bypassing remaining-order or loading-supply checks.

`node tests/ptn-browser.mjs` uses real HTTP/SSE and offline provider/journal
fixtures for discovery, scout rejection/retry, both trading phases, posting
readiness, exact Markdown, soft board targets, smaller orders, owner loading,
provider HTML injection, asymmetric payout presets, surface loading and reload persistence. Captures and
viewport bounds cover 3440x1440, 1920x1080, 1366x768, 1280x720 and 390x844.
CI preserves these images. Fixtures are illustrative, not live opportunities.
