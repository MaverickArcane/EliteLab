# Testing

```
python -m unittest discover -s tests -v
```

No dependencies. Runs in well under a second. CI runs it on Linux and Windows with Python 3.10 and 3.13.

## How the suite works

`tests/test_elitelab.py` sets three environment variables before importing anything:

- `ELITELAB_JOURNAL_DIR` -> `tests/fixtures/journals`
- `ELITELAB_OFFLINE=1` -> every `Services.fetch_json` raises, so nothing talks to Spansh or EDSM
- `ELITELAB_DATA_DIR` -> `tests/.data` (gitignored; wishlist writes go there)

`make_core()` builds a real `Core`, loads every module through the loader, and calls `core.watcher.replay()` synchronously (no thread, no HTTP server). Tests then call tool functions directly: `core.http.tools['get_rares_loop'].fn({})`. That exercises the exact code the HTTP and MCP paths use, minus the transport.

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

The HTTP transport itself (SSE framing, static path guard), the MCP server, the front end, and anything that needs Spansh (targets, combat). The CI Docker job does an end-to-end check of the HTTP path against the fixture. For Spansh-backed modules, test by hand with `python -m elitelab call find_sell_targets min=125 max=165` and read the result.

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
