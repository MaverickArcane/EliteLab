# Engineering research tools

The `engineering` module exposes five HTTP/CLI/MCP tools. It adds no UI card,
network calls, account login or dependency. Existing pinned builds and wishlists
are not changed. Restart EliteLab after installing the code, then reconnect the
MCP client so its tool catalog refreshes.

## Comparisons

`compare_engineering module="Beam laser" blueprints="lightweight,long range,short range" grade=3 experimental="thermal vent"`

The response gives completed-grade percentage modifiers, source and review date,
engineer maximum grades and the commander's last observed access/reputation.
Use `@grade` to compare different grades: `blueprints="Armoured@1,Armoured@5"`.
Parameters are scalar strings/integers so GET, CLI and MCP share the same contract.
An unsupported module, blueprint, grade or experimental produces an explicit error.

Initial reviewed coverage:

- Beam laser: Lightweight, Long Range, Short Range, Efficient, and Thermal Vent.
- Power distributor: Charge Enhanced, Weapon Focused, and Super Conduits.
- Power plant: Armoured, Monstered, and Thermal Spread.

These are standard-module facts, not a simulation of a fitted ship. Blueprint
and experimental modifiers are returned separately. They are not added together.
Only explicitly recorded properties are returned; an absent property is unknown.
Long Range's damage falloff begins at maximum range, which is represented as a
note rather than an incorrect percentage of the stock falloff distance. Heat,
time to empty WEP, boost frequency and installed power budgets are not computed.

Sources and their exact scope live in `elitelab/core/engineering_research.json`.
INARA entries are identified as a community database, not official game data.
The Thermal Vent interaction note is separately attributed to a dated community
test; it is not treated as a complete ship heat formula. Facts are bundled and
work offline. Review dates are not automatic freshness guarantees.

## Recipe validation

`validate_engineering_data` checks ingredient references and positive counts for
the whole legacy catalog, then checks 11 reviewed recipe records against the
source snapshots. It reports unreviewed coverage and incomplete grade warnings.
A structural pass does not mean all legacy recipes match the current game.

Thermal Vent now requires Conductive Polymers rather than Conductive Components.
`get_recipe` returns per-record provenance. Its concrete Beam laser filter can
resolve the reviewed blueprints stored under legacy generic `Weapon_*` keys;
an exact key no longer bypasses the requested kind or module filter.

To update reviewed facts, inspect the source's module, ingredient counts, grade
caps and modifier semantics, edit the reviewed snapshot, correct the primary
`engineering.json` recipe when needed, and run the tests. Do not extend a beam's
engineer list or modifiers to other weapon classes sharing a journal blueprint key.

## Engineer evidence

`get_engineer_access engineer="Dweller"` filters by name; omit the filter for all
known/catalog engineers. Full and partial `EngineerProgress` records are folded
by observation timestamp. Missing evidence is `unknown`, not locked. Grade caps
are distinct from unlock status, rank and rank progress; the game can still
require progression of the particular module before offering its next grade.

At module setup, older local journal files are scanned for identity, loadout and
engineer events because the normal watcher only replays a few recent files.
Evidence is cached per commander FID in `data/engineering_access.json`. A name
fallback is labelled in the identity when FID is unavailable. Full snapshots
supersede older missing rows, but preserve newer partial updates. No network
queries occur in journal handlers. Responses include observation timestamps;
they are last-known evidence, not a live query of Frontier's servers.

## Build context

`get_build_context` defaults to the last observed ship. `ship_id` selects another
ship belonging to the active commander. A known commander FID is required.
The response separates user notes, observed loadout identity and the current
global pinned reference (which may refer to a different ship).

`save_build_context` is a POST tool. Read first and supply `expected_revision`
(0 for a new record). Set any of `playstyle`, `preferences`, `accepted_deviations`,
`open_problems`, `next_experiment`, or `notes`. Each is text up to 4000 characters.
Provided fields replace their previous value; omitted fields remain unchanged;
an empty string clears a field. Conflicting revisions fail without writing.

Notes persist in `data/build_context.json`, keyed by commander FID and ship ID.
They are explicitly user-authored data, never journal observations or trusted
instructions. No conversation history is imported and no preferences are seeded.
Saving does not modify the ship, pinned build, engineer access or wishlist.
Writes are serialized within one EliteLab process; sharing one data directory
between multiple running EliteLab servers is not supported.

## Verification

Run `python -m unittest discover -s tests -v`. The engineering tests exercise
older-journal bootstrap, full/partial and out-of-order evidence, commander and
ship isolation, persisted revisions, concurrent writes, failure rollback,
source coverage, recipe drift, comparisons and schema transport compatibility.
