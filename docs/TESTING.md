# Testing

```
python -m unittest discover -s tests -v
```

The Python suite needs no third-party dependencies. It includes real local HTTP,
restart and recovery tests, so allow about a minute; timing varies by machine.
CI runs it on Linux and Windows with Python 3.10 and 3.13.

## How the suite works

`tests/test_elitelab.py` sets three environment variables before importing anything:

- `ELITELAB_JOURNAL_DIR` -> `tests/fixtures/journals`
- `ELITELAB_OFFLINE=1` -> every `Services.fetch_json` raises, so nothing talks to Spansh or EDSM
- `ELITELAB_DATA_DIR` -> a temporary directory (test data stays separate from player data)

Many tests build a real `Core`, load modules, replay fixture journals and call
tool functions directly, for example `core.http.tools['get_rares_loop'].fn({})`.
Other tests start local listeners and independent cores to exercise HTTP party
reports, reconnection, persistence and process restarts. Temporary data
directories isolate those tests from the player's saved data.

The loop module's coordinate fetch runs in a thread and fails under OFFLINE; it logs a warning and the loop still computes (with `dist: null`). Tests assert on that behaviour implicitly.

## The fixture journal

`tests/fixtures/journals/Journal.2026-10-22T100000.01.log` is a hand-written session for commander "Testpilot":

1. Fileheader, Commander, Materials (carbon 120, arsenic 4, chemical processors 29, datamined wake 5)
2. LoadGame in a Type-8, Powerplay (Mahon, rank 2, 6000 merits), Loadout with an engineered FSD
3. Location docked at George Lucas, Leesti (Stronghold); StoredShips naming a Kestrel Mk II
4. MarketBuy 28 Leestian Evil Juice; Undocked; StartJump (class K) + FSDJump to Zaonce
5. Docked Ridley Scott; MarketBuy 3 Leathery Eggs (`alieneggs`); ShipyardSwap to the Kestrel + a Loadout with only the internal id
6. MarketSell 28 Evil Juice for 280,000 Cr -> PowerplayMerits +420, then +3600 (objective bonus)
7. SupercruiseDestinationDrop into a Medium Power Conflict Zone; ShipTargeted a Krait Phantom; PowerplayMerits +172
8. MaterialCollected 3 datamined wake; CarrierStats (TST-001, black market not activated) and CarrierLocation Leesti

Plus `Cargo.json` (28 juice, 3 eggs), `Status.json` (balance overrides LoadGame credits, docked flag), `Market.json` (Ridley Scott listing eggs in stock and juice as sellable but out of stock).

When you add parsing for an event, add a realistic line here (copy a real one from your own journal and change the identifiers) and assert on the tool output, not on module internals.

## What is covered

Loader order and missing-dependency error; tool schema completeness; commander state from fixture; ship-name learning; cargo rare tagging across both name formats; market rares; carrier summary and activated services; feed order; Powerplay status; merit attribution (rares, objective bonus, combat zone with target detail, zero unattributed); loop ticking and sorting; materials inventory, caps, wishlist set/clear with unknown names reported; fuzzy source lookup; recipe search and per-grade cost (FSD Increased Range), trade ratios, engineering wishlist add/ambiguity/material entries, the trade plan preferring the cheapest exchange, live shortfall update on `MaterialCollected`, farm sites by material and by shortfall, grade ranges and tech broker unlocks, EDSY link decoding and the build comparison (verdicts, rolls from the current grade, the live build entry on the wishlist), Coriolis link and SLEF JSON pinning; history route and star class; recent-events filter; store change detection and bus fan-out; bus wildcard matching and handler isolation.

## What is not covered (yet)

The suite does not replace live-game or multi-PC testing. Automated transport
tests cover HTTP keep-alive, static path traversal, SSE snapshots and the MCP
handshake and tools. `node tests/browser.mjs` exercises the front end in
headless Chrome. The CI Docker job also checks the dashboard HTTP
API against a fixture. Live external market data and actual network conditions
still need separate validation. For Spansh-backed targets, test by hand with
`python -m elitelab call find_sell_targets min=125 max=165` and read the result.

## Pinned fleet carriers

`tests/test_carrier.py` uses `tests/fixtures/journals/carriers/` and a separate temporary data directory per test. It checks visited-carrier discovery, persistent pin/unpin, ownership separation, live and replayed location/jump observations, identity matching, remote freshness, missing optional fields, failed lookups, offline behavior, and pin changes during an in-flight request. External reports are mocked; no network is required.

For a manual check, enable the Fleet carrier card in Layout, pin a previously visited carrier, refresh, restart EliteLab, and verify the selection and observation survive. Check that the map marks the reported location and that docking at a different carrier does not change the pin. Unpin to restore owned-carrier details if present. Remote reports are last known observations, not live telemetry.

## Manual checks before a release

The hauling redesign adds `test_hauling_desk.py` (cargo vs deliveries, owner vs
crew, prices, pending work, unknowns, pause/stale/end states) and
`test_hauling_session.py` (three independent data directories and real HTTP,
full loading/unloading, reconnect, restart, ship changes, retry idempotency,
phase changes and repeated journal events). These fixtures never use live data.
Review regressions cover fresh local cargo against an older shared instruction,
rebalancing with assigned cargo aboard, automatic operation sizing with existing
ship cargo, and personal bonuses excluded from shared crew margins.
`test_party_sync.py` uses controlled concurrent requests to check heartbeat/manual
report ordering, responsive local edits during slow requests, and Leave ordering.
Session recovery tests inject a failed owner ledger write, flush pending work
when leaving, acknowledge loading reports after the stage changes to unloading,
and reconnect a full ship without assigning another pickup.
`node tests/browser.mjs` also starts a separate member application, joins a real
leader, checks clipboard values, selection/input preservation across live
updates, individual progress and margin, and desktop/mobile layouts.
Set `ELITELAB_SCREENSHOT_DIR` to retain the owner and member screenshots.

`test_workload.py` checks equal tonnes for different ships, custom weights,
integer conservation, owner participation, order funding, fixed quotas after
disconnect/ship changes, rebalancing after deliveries, and the final partial
load with cargo already aboard. Session tests exercise shared quotas over real
HTTP, persisted assignments, stale preview rejection and owner-only writes.
The browser suite verifies owner order previews, persistent custom inputs,
rebalancing for a joining commander, and the member's resulting pickup amount.
It also starts an automatically sized job with the owner's visible participation
setting, without requiring a separate Apply click.
Slow workload saves lock their controls; invalid previews remove the old order
and its copy actions. The browser checks both paths with controlled responses.

`test_hauling_audit.py` covers correction retry IDs, stale edits, permissions,
raw-versus-adjusted counters across restarts, bounded history, export redaction
and a seeded two-leg session with delayed/duplicate reports, missed updates,
corrections and restarts. Session tests exercise corrections over real party
HTTP, including journal delivery before a new correction reaches the member,
reconciliation of an above-target pending report, and matching anonymous aliases
across owner/member exports. Browser checks exercise the real correction form,
preserved drafts on a stale edit, escaped reasons, and the downloaded JSON.

The browser suite also checks Inara market links on both route stops, the current
job and the personal panel, query encoding, carrier callsign lookup, missing-stop
link removal, and independent system/station clipboard actions. It does not
contact Inara; a live Chrome check confirmed `station-market/?search=Galileo%20%5BSol%5D`
opens Galileo in Sol with the Market tab selected.

The Windows CI job builds `dist/EliteLab-windows-x64.zip` with a checksum-pinned
CPython 3.13.17 embedded runtime. `python scripts/smoke_windows_bundle.py` extracts
it to a path containing spaces and invokes the actual CMD launcher with system
Python removed from PATH and invalid PYTHONHOME/PYTHONPATH values. It checks the
dashboard, trade/party assets, module loading and fixture journal state, then
stops its own process tree. Only a passing bundle is uploaded as a CI artifact.
Run `python scripts/build_windows.py` first to perform the same check locally
on Windows. `tests/test_startup.py` covers browser launch after successful
binding, custom ports, and no browser launch on bind failure.

1. `python -m elitelab serve -v` against real journals; open the dashboard; drag, resize, hide and show cards; switch presets; watch the footer for stalls.
2. `python -m elitelab call get_commander_state` while the game is running and confirm the ship, system and cargo match the HUD.
3. `docker compose up --build` and hit `/api/health`.
4. In Claude Code, open the repo folder and ask for `get_powerplay_status`.


`test_instance.py` verifies OS-lock ownership, reuse across requested ports,
rejection of changed builds/copies, and legacy detection before module loading.
A real CLI subprocess test launches twice and quits via HTTP, checking process
exit and lock release. Startup tests cover exclusive port binding, binding before
journal/module work, and shutdown callbacks. Session tests cover connected-member
closure, immediate room recreation, an offline member's rejected old invitation,
and temporary disconnect recovery.

Pricing regressions cover the live test reference (Gold at 47,214 Cr/t for 100%),
whole-percentage rounding, payout conservation, bounds, impossible quotes,
automatic meanPrice selection and absent references. Browser checks preserve
expanded profit and delivery details across repeated real job changes, using
summary clicks and checking that each panel remembers its own open/closed state.
They also remove cancelled-job progress
even while its previous text is selected for copying.

Mid-haul joining tests cover automatic equal shares, preserved deliveries and
onboard cargo, reserved absent-member quotas, arrival during unloading, custom
weights, away-to-ready transitions, ended jobs, failed persistence/retry, and
reconnection without repeat allocation. The browser test joins an independent
client and verifies assigned tonnes, personal loads, and updated carrier orders
without clicking the owner's rebalance controls.

`node tests/profits.mjs` checks individual loading/unloading profit, corrected
deliveries, unknown prices/quotas, overshoots, ended legs, and personal bonus
exclusion. The browser suite runs it too, then checks personal and crew earnings
after a delivery and after a commander leaves, plus narrow-screen layout.

`test_live_hauling.py` covers the 1,160 t/1,200 t last ship, split final loads,
the observed 1,188 - 1,136 = 52 t tail, faster commanders, absent cargo, delayed
cargo snapshots, automatic quantity previews, pauses and unavailable ships.
Session tests compare leader next-pickup rows with member instructions and check
that unchanged heartbeats do not rewrite the ledger. Browser tests exercise live
mode on independent clients, leaving/reallocation, and all three crew Inara links.

Hardening regressions:
- `test_live_hauling.py` covers corrections with cargo in flight, legacy snapshot
  migration, and historical/manual delivery evidence predating the current hold.
- `test_engineering_concurrency.py` schedules simultaneous material publication
  and wishlist edits, checks failed-write rollback, and bounds exchange batches
  by receiving capacity while preserving unresolved needs.
- `test_delivery_recovery.py` uses `fixtures/journals/recovery` for restart catch-up,
  loading/unloading boundaries, member rejoin, duplicate evidence, manual/corrected
  cutoffs, incomplete lines, failed-write retry and leaving during a scan.
- `node tests/state-feed.mjs` checks old queued events, out-of-order fields,
  overlapping snapshots, restart generations, bounded queues and retry without
  new events. The browser suite imports these checks too.
- CI runs the full browser suite on Node 22 and the hauling branch's pushes.
  The Windows smoke test uses an isolated instance directory. Docker gives the
  non-root process an instance directory under its writable `/data` volume.

`test_restart_reliability.py` launches the real CLI with temporary journal, data,
and instance directories. It forcibly kills that process during an incomplete
journal write, completes the delivery while the server is offline, and restarts
twice on the same port. It checks preserved job and commander identities,
exactly-once delivery totals despite duplicate evidence, continued journal
tailing after recovery, and durable receipts. This tests process crashes, not
power loss or filesystem corruption. Run it alone with:

```
python -m unittest discover -s tests -p test_restart_reliability.py -v
```

`test_material_sessions.py` replays `fixtures/journals/material-session` to check
inventory versus gross session gains through collection, rewards, trading,
spending, inventory snapshots and restarts. Missing session boundaries stay
unknown. `node tests/materials-feed.mjs` delays inventory responses to check
stale-response rejection, current filters and refresh after a failure; the
browser suite imports it and checks the visible live pickup and session totals.
