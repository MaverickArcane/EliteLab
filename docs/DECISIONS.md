# Decisions and lessons

A log of why things are the way they are. Add to it when you change direction or get bitten.

## Architecture

- **Standard library only.** The owner wants a friend to `git clone` and double-click a `.cmd`. The MCP server is dependency-free so Claude Code can launch it with a bare `python`. Reconsider only if a feature genuinely needs it (OAuth with Frontier might).
- **Modules talk through the store and the bus, never by import.** It keeps the dependency graph honest and lets the loader fail early. The map depends on nothing but `journal` and `history`; other modules add layers to it from their card scripts.
- **Routes are tools.** One registration produces an HTTP endpoint, an entry in `/api/schema`, an MCP tool and a CLI target. There is no separate "AI layer" to keep in sync.
- **Stateless journal scan per request for history.** Rescanning 49 files takes ~250 ms and is cached on file mtimes. A SQLite index is on the roadmap for analytics, not needed for the current features.
- **Replay then tail, every start.** State is rebuilt from the last 3 journal files on every launch. Simpler and more robust than persisting derived state.
- **SSE, not WebSockets.** One-way push is all the UI needs, and the stdlib server handles long-lived GET responses fine.
- **Layout belongs to the shell.** Cards never know their position or size. This is what made presets and saved layouts a shell-only change.

## Game-data lessons

- `Leathery Eggs` is `alieneggs`. The loop originally matched on `leatheryeggs` and silently never ticked Zaonce. Match on display name as well as key, and add observed keys to `KNOWN_RARES`.
- `StarClass` comes on `StartJump`, not `FSDJump`. History coloured nothing until that was fixed.
- New hulls have no `Ship_Localised` in `Loadout`. `StoredShips` and `ShipyardSwap` carry both the internal id and the display name; learn from them and never keep a stale display name when the internal id changes.
- `Market.json` item names are `$key_name;`, `Cargo.json` names are `key`. One `norm()` function, used everywhere.
- A station buys a rare only if the rare appears in its market list (demand may be 0 and it still buys). Spansh mirrors that list, so the targets module can warn before you fly. Ross 888's Id10t Error does not list Leestian Evil Juice; Mobius Base in Sharru Sector CV-Y b2 does.
- Powerplay conflict zone kills log no `Bounty` and no `FactionKillBond`. The only evidence is `SupercruiseDestinationDrop` with a `Warzone_Powerplay` type and the `ShipTargeted` stream. Attribution uses those.
- Powerplay zones are auto-assigned to your pledged power; there is no side selection.
- A system only has Powerplay conflict zones when two powers are both past the conflict threshold (~35,000 of 120,000 control points, ~29 %). Spansh `power_conflict_progress` is that fraction and can exceed 1.0. Hydrae Sector LC-V b2-1 at Mahon 64 % / Kaine 22 % had no zone; LP 673-42 at Winters 68 % / Archer 48 % / Mahon 47 % did.
- Spansh has no `Contested` power state. Derive it from `power_conflict_progress`.
- Measured rates (owner's commander, Mahon, October 2026): rares 1 merit per ~667 Cr sold (flat across six rares, 2,573 merits on 1.72 M Cr); one-off 3,600 that looked like a weekly objective; Medium Powerplay zone 14 / 172 / 216 per event, 844 merits in 22 minutes in a Kestrel Mk II.
- Rares must not have been on a fleet carrier and must be sold outside the system they were bought in to count for merits (community-documented; not yet tested here).
- Guides claim mining Platinum into acquisition systems is the top merit method (25-35k/h) and High-intensity zones second (15-25k/h). Unverified; the merits module exists to measure it.

## Front-end lessons

- Pointer capture is lost when the captured element is moved in the DOM. Drag handlers must live on `window`.
- Chrome throttles `requestAnimationFrame` to ~1 Hz in background tabs. A "37 second" drag measured in a hidden tab was 40 frames at 1 Hz. Measure with the tab visible, and treat the footer stall indicator with that in mind.
- Rebuilding all cards without unmounting leaked subscriptions and the map's redraw timer; after a few layout changes the page crawled. Cards now have `unmount`, and show/hide touches one card.
- Dispatching a window `resize` on every pointer move forced a full map redraw per move. Use `Lab.relayout()` (coalesced) and only when a card actually changes slot or size.
- Generating the starfield from the canvas size regenerated it on every resize. Fixed size, generated once.
- A render error used to replace the card body, destroying a mounted canvas and making every later draw fail. Errors are now a banner.
- Scripted `PointerEvent`s do not acquire pointer capture, so they did not reproduce the real-mouse bug. When a user reports a UI hang, test with real input (the Chrome tool's `left_click_drag` does generate real pointer events).

## Process lessons

- `python -I` hides the package (isolated mode drops cwd from `sys.path`). Launchers and Docker use plain `python -m elitelab`.
- Windows PowerShell 5.1 `Set-Content -Encoding utf8` writes a BOM. Docs were cleaned once; write files with the editor tools or `[IO.File]::WriteAllText` with a BOM-less `UTF8Encoding`.
- Inara blocks automated fetches (503 with Retry-After). Link to Inara; do not scrape it.
- The GitHub CLI needs an admin install on Windows; an automated session cannot accept the UAC prompt. The owner installs it by hand.
- Keep docs ASCII. The owner wants no emojis anywhere in the repo.
