# Flight context and upgrade budgets

Five additional read-only MCP tools support work across play sessions:

| Tool | Purpose |
|---|---|
| `get_navigation_context(limit=20)` | Ship route destination, next system, remaining hops and geometric distance |
| `get_ship_modules(slot, item)` | Actual fitted modules, engineering modifiers and matching reported module power |
| `get_data_freshness(max_age_seconds=300)` | Ages and missing observations for the current commander session |
| `plan_engineering_upgrade(...)` | Explicit material budget, inventory shortfalls, optional experimental and engineer caps |
| `list_engineer_unlocks(engineer)` | Reviewed engineer locations, referral chains, observed access and next actions |

## Ship and route evidence

The `flight` module folds the normal journal replay/live stream. It depends on
the progression module's active commander and session timestamp, discards older
session events, and clears session observations when identity/session changes.
It has no persistent cache. `flight` store state contains commander, session
start and observation timestamps; detailed reports are served by the tools.

`NavRoute.json` supplies the plotted route. The tool finds the current system in
that route and returns the remaining legs, capped by `limit` (1-100). Distances
come from successive `StarPos` coordinates; missing coordinates remain unknown.
If the current system is absent, status is `off_route`. Repeated occurrences of
the current system yield `ambiguous_position`, without an invented next jump.
`NavRouteClear` prevents older snapshot files from resurrecting a cleared route.
A plotted route is neither a permit confirmation nor a carrier jump plan.
The tool does not simulate fuel needs, neutron boosts or jump feasibility.

`get_ship_modules` uses actual `Loadout.Modules`, including raw engineering
modifiers and experimental effects. Optional slot/item filters match substrings.
`ModulesInfo.json` is joined only when its timestamp is at least as new as the
loadout and every reported slot/item matches. Module changes, ship swaps and
engineering events mark the loadout as changed until a new Loadout arrives.
Reported module power is not instantaneous power draw. Neither the pinned build
nor an assumed heat simulation substitutes for observed modules.

Snapshot files lack commander identity. A snapshot predating the active session
is excluded. The freshness tool reports missing/recent/older-than-threshold
observations; an old event-driven loadout is not automatically incorrect.
Shutdown is reported separately and does not claim to monitor the game process.

## Small engineering steps

For one G3 Lightweight beam roll plus Thermal Vent:

```json
{
  "blueprint": "Lightweight", "module": "Beam laser",
  "grade": 3, "from_grade": 2, "mode": "single_roll",
  "experimental": "Thermal Vent", "quantity": 1
}
```

`single_roll` budgets one roll at the requested grade. It does not establish
that the grade is available. `estimate` walks from `from_grade + 1` to `grade`
using the catalog planning hint; optional `rolls="1,2,3,4,5"` supplies explicit
counts for all five grades. Quantity is 1-20. Equal start/target grades allow an
experimental-only plan. Missing recipe grades are errors, never free upgrades.

`from_grade` means completed grades of the same blueprint. A blueprint change
starts from zero. Custom roll estimates do not predict engineer reputation gain
or guarantee a completed grade. Experimental costs apply once per module; omit
an already retained effect. Effect compatibility requires a concrete module.

Inventory affordability requires a Materials snapshot for the active session;
otherwise have/short/affordable are unknown. Current inventory is read through
the materials module's tool. Blueprint and effect provenance are returned
separately. Reviewed concrete-module engineer caps are preferred. Generic Weapon
rows cannot lend their beam-centric engineer caps to cannons or other weapons;
those caps remain unavailable until reviewed. Legacy non-generic caps are
explicitly labeled. Affordability does not establish engineer access.

No tool here changes a wishlist, build pin, inventory or user notes.
The `resume_ship_work` MCP prompt combines saved build context, actual modules,
freshness, access and a small budget, preserving accepted build deviations.

## Unlock coverage

`get_engineer_unlock_progress` now covers Farseer, Martuuk, Qwent, Palin,
Dweller, Ryder, Tani, Tarquin, Nemo and Cheung. The catalog in
`elitelab/core/unlock_research.json` contains each source URL and a review date.
`Rank`/`Promotion` observations and selected `Statistics` sections supply
timestamped meeting evidence. A met threshold never becomes an inferred
invitation. Already-unlocked access suppresses further donation advice.

Palin and Martuuk use `Exploration.Greatest_Distance_From_Start`, not accumulated
hyperspace distance. Dweller uses `Smuggling.Black_Markets_Traded_With`; Cheung
uses `Trading.Markets_Traded_With`. Cumulative contributions support commodities,
materials and credits. Missing contribution history remains unknown, and cargo
is separate from donations. Qwent's existing response fields remain compatible.

Rank encodings and statistics fields are documented in
[Frontier's journal manual](https://hosting.zaonce.net/community/journal/v18/Journal_Manual_v18.pdf).
The remaining session/snapshot fields follow the
[journal manual](https://hosting.zaonce.net/community/journal/v34/Journal_Manual_v34.pdf).
Tests use `tests/fixtures/journals/flight` and `tests/test_future_research.py`.
