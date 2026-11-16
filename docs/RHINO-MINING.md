# Rhino surface mining

Open **Mining > Rhino surface mining**. The **Mining** tab combines a selected
destination, automatic collection progress, hold space and useful next-step
instructions. **Locations** groups confirmed visits and unconfirmed leads;
**How to mine** contains the
full sourced guide. Forms and long explanations open only when needed.
The existing Materials panel appears alongside it for visual
progress; when first opened from Mining it selects **gained this session**.
Those gains include pickups, mission rewards and trader receipts since game
login, not only Rhino output.

## Watch a deployment

Launching a player-controlled `mev_rhino` starts a new deployment. Each
`MiningRefined` event adds one tonne, including separate receipts with the same
timestamp. The total, commodity breakdown and cumulative chart survive cargo
transfers. Run details show gross unloaded tonnes, unload count and the observed
average, including setup, driving and idle time through the last recorded event.
This is collection throughput, not a rig production estimate. Boarding, shutdown,
death, ship departure or another controlled SRV ends the run. Login already in a
Rhino begins a clearly marked partial run. Replay reconstructs the same totals.

Cargo bars use timestamped `Cargo` reports for Ship and SRV separately, never
subtracting a transfer twice or treating unknown inventory as empty. The Rhino
has a 72 t hold; ship capacity comes from Loadout. An older report cannot replace
a newer one. The equipment hint checks observed DSS and large-hangar module IDs;
missing Loadout means unknown, and outfitting changes invalidate the checks.
It does not prove which vehicle is installed. Low reported free space links
directly to the unloading procedure. Guide shortcuts cover the whole loop.

## Save and revisit a spot

The Locations tab combines the bundled [catalog](../modules/rhino/sites.json)
with your personal notebook. Each entry has coordinates, navigation, evidence,
a recording date and source links. Confirmation and depletion are separate:

- **Confirmed**: a field report by the catalog contributor or current commander
  supports the location. It does not prove current reserves or every rig claim.
- **Unconfirmed**: a research lead or bookmark awaiting that field confirmation.
  Survey-reported and modeled rig counts stay labeled as such.
- **Reported depleted**: an observation of depletion, which can coexist with
  confirmation. Unknown reserves never imply a stocked deposit.

Click **Mark confirmed** directly on an unconfirmed location after verifying it
in game. This records a dated confirmation and moves it into Confirmed in one
click, retaining the complete existing report, its original date and any
depletion flag. A separate date records the confirmation. It does not confirm
an estimated rig count, and confirming an already-confirmed entry changes nothing.
Open **Evidence and notes > Update report** to add details, change the status
back to Unconfirmed, or report depletion.
Describe what was actually checked and include the visit date when it differs
from the recording date. Reports are local to your commander, retain the original
catalog evidence, and do not change the selected destination. Merely saving GPS
coordinates starts an unconfirmed bookmark. Moving a personal bookmark to another
system/body/coordinate or changing its commodity clears its old report; editing
the name or notes preserves it.

The initial catalog has two confirmed locations and six unconfirmed leads:

| Location | Evidence retained |
| --- | --- |
| Wregoe JC-Y b57-0 A 1, PML 4 | Owner visited and subsequently deployed six rigs, reproducing the survey's placement claim |
| Shinrarta Dezhra AB 2 j | Three working rigs reproduced; later reported depleted |
| Wregoe GW-Y c28-2 A 1, PML 4 / Spot 31 and PML 3 / Spot 33 | Six survey-reported rigs each; not reproduced by the contributor |
| HIP 63920 AB 4 b, 35.3958 / 110.2640 | Large Tritium patch reported; exact link to six-rig test unresolved |
| HIP 39418 5 b, A11 / A25 / B40 | Mapped Monazite/Serendibite positions; five-rig estimates, not placement tests |

The Wregoe entries were extracted from the original Surface Mining v0.3 FileMaker
archive linked in Tessa R. Act's [release post](https://www.forum.stellanebula.de/viewtopic.php?p=36652#p36652).
SHA-256: `0631289d9d6225967a759993f9d5622c6ddd31fb858d4ebe1091d3f963cb8d75`.
Relational keys, not duplicate system names, establish the locations:
SpotIDX 30 -> LocID 22 -> bodyIDX 43 -> Parent_System 16;
31 -> 23 -> 44 -> 17; 33 -> 24 -> 44 -> 17.
The archive publication date is 2026-09-08; individual survey dates are unknown.
Spot 30's location has `locatrion_survyed = no`, retained as a source caveat.
The owner's later field report supplies location confirmation, with six rigs
deployed. The catalog is a small factual extract, not a copy of the database
or field guide. No network fetch is required at runtime.

Choose **Add a spot > Use current position**, then enter a name, commodity and
useful notes. Alternatively enter a reported system, full body name, latitude
and longitude. Save only what was observed: a tested approach, productive
deposit or working rig positions. There is no separate rig counter.

Saved spots and selection belong to the current commander (FID when available,
otherwise commander name), in `rhino-sites.json`. Up to 100 personal spots can
be edited or removed. Previous preview rig-fit fields become ordinary notes.
No route controls the game or uploads sites.
Forms remember which commander opened them. If the commander changes before
submission, reopen the form for the intended commander; the old draft is rejected.

Choose **Navigate** on a spot. Travel to its system and body in game. On that
body, fresh Status coordinates (at most 120 seconds old) and a known radius
produce spherical surface distance and an initial compass bearing. This is
not terrain routing or a ship flight path. Latitude comes first and is
north-positive; longitude is east-positive. Stale or mismatched positions do
not produce directions. Departure clears the position and rejects older or
same-second cached Status data. The target persists across restarts and departures.

The built-in reference is **Shinrarta Dezhra AB 2 j, 35.9491, -31.2339**.
The owner read that position at 2:11 in the linked video and reported three
operating rigs in the area on 2026-11-15. This locates an area, not exact rig
placements, current reserves, guaranteed access or a promised extraction rate.
Later that day the owner reported it Depleted and unchanged after reloading;
the reference notes retain this warning for future visits.

## The mining guide is shared with MCP

[guide.json](../modules/rhino/guide.json) is the single source for the browser
and the `get_rhino_guide` tool. It contains ordered procedures, troubleshooting,
source URLs, evidence labels and a review date. The browser fetches it on demand;
the live state carries only its topic index. The default tool result contains
the overview and topic list, keeping routine calls small.

| Topic | Covers |
| --- | --- |
| `overview` | The complete loop at a glance; topic index |
| `equipment` | Hangar, scanner, fire groups and deployment |
| `finding` | DSS, orbital location lists and ground prospecting |
| `navigation` | Coordinates, heading and the reproduced reference spot |
| `placement` | Deposit footprints, red X and Too close |
| `collection` | Collecting output versus recovering a rig |
| `unloading` | Transfer cargo without boarding or packing up |
| `recovery` | Pack up, synthesis and replacement workarounds |
| `troubleshooting` | Water, missing deposits, failed placements and revisits |
| `evidence` | What an assistant can establish from these tools |
| `all` | The full guide, including every topic's sources |

For example, an MCP call to `get_rhino_guide` with
`{"topic":"unloading"}` returns the same instructions shown in that browser
section. HTTP uses `GET /api/rhino/guide?topic=unloading`. The `rhino_mining`
MCP prompt and server introduction direct assistants to the guide before
advising. Browse coordinates and evidence with `get_rhino_sites`; navigation
and the selected destination come from `get_rhino_status`.

Do not turn early community claims into rules. The guide records the author's
correction about numbered mining locations, the owner's unsuccessful reroll
test, practical placement limits and conflicting restock reports. Recheck
current purchases, compatibility and changed mechanics before advising.

## Tools and limits

- `get_rhino_status`: GET `/api/rhino`; notebook, selected destination,
  current position, navigation, deployment collection totals/chart points,
  separate holds updated by cargo reports and transfers, equipment evidence and
  guide topic index. Missing starting counts remain unknown. Every site includes
  travel distance and estimated jumps from your ship. Follow system -> body ->
  surface directions; the surface bearing works in the ship or SRV.
- `get_rhino_guide`: GET `/api/rhino/guide`; optional `topic`, default `overview`.
- `get_rhino_sites`: GET `/api/rhino/sites`; `verification` defaults to `all`;
  accepts `confirmed` or `unconfirmed`, plus optional exact `commodity` filter.
- `report_rhino_site`: POST `/api/rhino/sites/report`; `id`, `verification`,
  `availability` (`unknown` or `reported_depleted`) and nonempty `evidence`.
  Server records the current time; returns the effective site and original evidence.
- `confirm_rhino_site`: POST `/api/rhino/sites/confirm`; `id` required. Preserves
  existing evidence, report date and depletion flag; adds `confirmed_at`.
- `save_rhino_site`: POST `/api/rhino/sites/save`; name, system, body, commodity,
  latitude and longitude required; notes/radius optional; ID edits an existing spot.
- `select_rhino_site`: POST `/api/rhino/sites/select`; ID selects, empty ID clears.
- `remove_rhino_site`: POST `/api/rhino/sites/remove`; remove a personal spot.

Status and catalog responses include `commander_key`. All notebook POST tools
accept it as an optional precondition; pass the value from the observation or
form that prompted the action. A changed commander rejects the request. The UI
always sends it. HTTP authentication still controls access to the local server.

No deposit footprints, remaining reserves, rig positions, hopper contents,
efficiency or remaining rig inventory were found in the owner's November 2026
journals. The module does not generate deposits or predict resets, overlaps,
rig fit or yield. It has no manual rig counter. SrvSurvey-XP documents experimental
HUD capture for rig detection; this module does not capture the screen or claim
that capture supplies live hopper/reserve data. The shared guide links that
research and the official journal reference with their limitations.

A stopped rig is not enough to diagnose depletion. Check its Contacts status
and the deposit's mineral amount. Collect a full rig; move on from a deposit
explicitly marked Depleted. The owner confirmed reloading did not refill the
tritium patch. Replenishment observations concern days, with no established
universal timer. This distinction is available to MCP under `troubleshooting`.

The module requires `journal` and writes only `rhino.summary`. Explicit
notebook actions persist data atomically. Events and mutations share a lock;
responses are detached copies. The guide is bundled and works offline,
including before commander login. External links are optional further reading.

## Validation

`python -m unittest discover -s tests -p test_rhino.py -v` covers notebook
persistence and identity, collection attribution, transfer continuity, separate
cargo snapshots, stale input, equipment evidence, navigation, guide selection
and MCP discovery/calls. Regressions cover cached positions after departure,
full-length report preservation, confirmation retry and stale commander writes.
`node tests/rhino-browser.mjs` runs an isolated real
CLI/watcher/API/SSE/browser stack with synthetic journals. It checks compact
UI, live collections/holds, unloading continuity, low-space help,
saves/edits/reload, catalog groups/sources, local reports, stable drafts, escaping, live Materials gains, shared
guide content/retry/shortcuts, and desktop/mobile layouts. Screenshots go to
`artifacts/rhino` or `ELITELAB_SCREENSHOT_DIR`. `node tests/materials-feed.mjs`
checks material response ordering and filter preservation.
