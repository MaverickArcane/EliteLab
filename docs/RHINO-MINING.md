# Rhino surface mining

Open **Mining > Rhino surface mining**. This module has three jobs: save useful
places, guide you back to them, and explain how to mine. The two tabs are
**Saved spots** and **How to mine**. Site entry and long explanations open only
when needed. The existing Materials panel appears alongside it for visual
progress; when first opened from Mining it selects **gained this session**.
Those gains include pickups, mission rewards and trader receipts since game
login, not only Rhino output.

## Save and revisit a spot

Choose **Add a spot > Use current position**, then enter a name, commodity and
useful notes. Alternatively enter a reported system, full body name, latitude
and longitude. Save only what was observed: a tested approach, productive
deposit or working rig positions. There is no separate rig counter.

Saved spots and selection belong to the current commander (FID when available,
otherwise commander name), in `rhino-sites.json`. Up to 100 personal spots can
be edited or removed. Previous preview rig-fit fields become ordinary notes.
No route controls the game or uploads sites.

Choose **Navigate** on a spot. Travel to its system and body in game. On that
body, fresh Status coordinates (at most 120 seconds old) and a known radius
produce spherical surface distance and an initial compass bearing. This is
not terrain routing or a ship flight path. Latitude comes first and is
north-positive; longitude is east-positive. Stale or mismatched positions do
not produce directions. The target persists across restarts and departures.

The built-in reference is **Shinrarta Dezhra AB 2 j, 35.9491, -31.2339**.
The owner read that position at 2:11 in the linked video and reported three
operating rigs in the area on 2026-11-15. This locates an area, not exact rig
placements, current reserves, guaranteed access or a promised extraction rate.

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
advising. Saved coordinates come from `get_rhino_status`.

Do not turn early community claims into rules. The guide records the author's
correction about numbered mining locations, the owner's unsuccessful reroll
test, practical placement limits and conflicting restock reports. Recheck
current purchases, compatibility and changed mechanics before advising.

## Tools and limits

- `get_rhino_status`: GET `/api/rhino`; notebook, selected destination,
  current position, navigation and guide topic index.
- `get_rhino_guide`: GET `/api/rhino/guide`; optional `topic`, default `overview`.
- `save_rhino_site`: POST `/api/rhino/sites/save`; name, system, body, commodity,
  latitude and longitude required; notes/radius optional; ID edits an existing spot.
- `select_rhino_site`: POST `/api/rhino/sites/select`; ID selects, empty ID clears.
- `remove_rhino_site`: POST `/api/rhino/sites/remove`; remove a personal spot.

The journal does not expose deposit footprints, remaining reserves, rig
positions, hopper contents, efficiency or remaining rig inventory. The module
does not generate deposits or predict resets, overlaps, rig fit or yield.
The earlier preview's manual rig report route and deployment/cargo metrics
have been removed. Use the existing Materials and Cargo panels for inventory.

The module requires `journal` and writes only `rhino.summary`. Explicit
notebook actions persist data atomically. Events and mutations share a lock;
responses are detached copies. The guide is bundled and works offline,
including before commander login. External links are optional further reading.

## Validation

`python -m unittest discover -s tests -p test_rhino.py -v` covers notebook
persistence and identity, validation, navigation, old notes, guide selection
and MCP discovery/calls. `node tests/rhino-browser.mjs` runs an isolated real
CLI/watcher/API/SSE/browser stack with synthetic journals. It checks compact
UI, saves/edits/reload, stable drafts, escaping, live Materials gains, shared
guide content/retry, and desktop/mobile layouts. Screenshots go to
`artifacts/rhino` or `ELITELAB_SCREENSHOT_DIR`. `node tests/materials-feed.mjs`
checks material response ordering and filter preservation.
