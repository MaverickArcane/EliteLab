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

- The first code review (2026-10-23) found two copies of the rare-goods set that disagreed (`leatheryeggs` vs `alieneggs`), a duplicated `norm()`, and `journal.materials` totals that only ever went up. All shared game facts now live in `elitelab/core/gamedata.py`, and materials are owned by the materials module only.
- No CORS. The API has no auth; `Access-Control-Allow-Origin: *` let any web page the user visits read state and change the wishlist. Removed. If LAN use ever needs cross-origin, it needs a token first (roadmap issue 10).
- Without `ELITELAB_AUTH_TOKEN`, every POST must carry a Host header that is an IP literal (IPv4 or bracketed IPv6), a loopback name, the bind host (unless it is 0.0.0.0), this machine's `socket.gethostname()` (lower-cased, read on first use and cached), or a name in `ELITELAB_ALLOWED_HOSTS`; otherwise 403 naming the variable to set. `getfqdn()` is deliberately not used: it does reverse DNS and can block for seconds on a misconfigured resolver, so nothing in the request path or at import does a DNS lookup, and a fully qualified or Tailscale MagicDNS name goes in `ELITELAB_ALLOWED_HOSTS`. This applies on loopback, LAN and 0.0.0.0 (Docker) binds alike: a DNS-rebinding page always needs a DNS name, so refusing unknown names stops it everywhere while access by IP or by the machine's own name keeps working. The first version only checked loopback binds and left 0.0.0.0 open, and a `--host` flag that was not written back to `config.HOST` made the rule read a stale value. With a token the rule is skipped: a rebinding page cannot present the token or the session cookie. `browser` (an executable) is not saveable over HTTP for the same reason.
- `save_setup` refuses a host or port the lab could not start with (an IPv6 address, since the server is AF_INET only; a port already in use; an address this machine does not have), because a saved value that stops the lab from starting leaves the user with no page to fix it from. When the bind still fails at startup, `start()` prints the host, port, where each came from and the settings file path, and returns 1 (not 75, so the launchers stop instead of looping).
- The server opens the browser itself (`--open-browser`), after a successful bind, at the host and port it really bound. The Windows launcher used to wait two seconds and open `http://localhost:8766/` regardless, which raced the bind and went to the wrong place once the port was changed on the setup page. `serve-loop.cmd` passes the flag on the first run only, so a restart from the setup page does not open a second tab.
- `save_settings` serialises saves with a lock and writes through a unique temp file, and a settings file that exists but does not parse is kept as `settings.json.bad` rather than overwritten, so a hand-edit typo never silently loses the rest of the file.
- POST bodies are always read before replying, even on 404, because the server speaks HTTP/1.1 keep-alive and an unread body becomes the next request.

- Rare goods now come from EDCD FDevIDs `rare_commodity.csv` (142 entries with origin market ids) instead of eight observed keys plus community slugs; five of those slugs were wrong (`zeesszeantgrubglue`, `alyabodysoap`, `lucanonionhead`, `wuthieloku`, `onionheadbetastrain`), which is exactly the failure mode Leathery Eggs had taught us. Issue 15.
- Jump range: `(fuel / fuelmul) ** (1 / fuelpower) * optimal_mass / mass` with fuel = the FSD's max per jump or the tank contents when lower, FSD constants from EDSY, optimal mass from the Loadout's `FSDOptimalMass` modifier, Guardian booster as a flat bonus. It lives in the journal module because it is derived from the Loadout and Status snapshots the journal already owns; notifications live in the shell because they are a cross-card concern of the `Lab` runtime (toasts), not game data. Checked against a real Kestrel: 29.27 Ly from the formula vs 29.27 in the journal when mass is unladen plus one jump of fuel. `jump_range_now` uses `Status.json` fuel and cargo so jump counts in targets, combat, farm sites and traders are honest. Issue 4.

## Engineering data (recipes, wishlist, trading)

- Blueprint and experimental-effect costs come from EDCD coriolis-data (`modifications/blueprints.json`, `specials.json`, `modules.json`), material families from EDCD FDevIDs `material.csv`, merged into `elitelab/core/engineering.json` (2026-10-23). Coriolis spells one ingredient "Adaptive Encyptors Capture"; the merge maps it to `adaptiveencryptors`. Three weapon effects (FSD interrupt, penetrator munitions, penetrator payload) have no module in coriolis; they are mapped to missile rack / torpedo pylon by hand.
- Material trader ratios (community-documented, consistent across the Elite wiki, Alioth wiki and the Blackbox guide): within a family 1 unit buys 3 of the grade below and 6 buy 1 of the grade above; crossing families within a type multiplies the cost by 6 once (so G1 to G5 across families is 6^5 = 7776:1). Traders never cross Raw/Manufactured/Encoded. Guardian and Thargoid materials have no family and cannot be traded.
- Rolls per grade (1/2/3/4/5, 15 rolls from fresh to a full G5) is a planning hint, not a game rule. Progress per roll is random and improves with engineer reputation; players report 10-12 rolls at max reputation. The wishlist accepts a `rolls` override per entry. Measure it and change `rolls_per_grade` in `engineering.json` if it is consistently wrong.
- The older flat materials wishlist (`set_wishlist`, per-material quantities) stays for scripts that already use it; the engineering wishlist is the one that knows recipes. Both read the same inventory.
- "FSD boost" is what the owner calls Increased Range, so it is an alias on `FSD_LongRange`; "prismatic" and "bi-weave" are aliases on the shield generator blueprints because the same blueprints apply to those generators.
- Technology broker unlock costs (Guardian modules, weapons and fighters; human broker items) come from scotty.newlevels.org/techbroker (community, October 2026). Two of its rows name the wrong blueprint segment (a shard cannon costing a Vessel segment, a turreted plasma charger costing a Module segment); both are recorded as Weapon segments. Commodities (HN Shock Mount, Reinforced Mounting Plate...) are cargo, listed but not tracked.
- Free text is for the assistant, not for people. The owner found typed wishlist entries easy to get wrong, so the card is a structured picker (kind, module, blueprint, from/to grade, quantity) posting exact keys; `wishlist_add` keeps parsing text because an AI is the one typing there. Same for grade ranges: "2-5" means the module already has G2.
- EDSY links are decoded locally (`elitelab/core/edsy.py`) from the format in EDSY's source (hash version 20, link version 15+). Older links are refused with a message to re-copy the link; EDSY migrates them when opened. The tables (`edsy.json`) were extracted from EDSY's `eddb.js` on 2026-10-24 and need regenerating when new ships or modules ship. Modified-attribute values in the hash are skipped; the comparison only needs blueprint, grade and effect.
- Build comparison matches hardpoints, utilities and internals by item within their group rather than by slot, because people move modules between same-size slots and the journal numbers slots differently from EDSY. Core modules are compared by slot. Credits are EDSY list prices without discounts.
- Coriolis links are decoded from the format in coriolis `Ship.js` (module-id string plus a gzip binary blob of blueprint, grade and special ids per slot; attribute modifier values ignored). Tables from EDCD/coriolis-data on 2026-10-24. SLEF / Loadout JSON is accepted too because both sites export it and it needs no tables at all.
- A tracked build is one wishlist entry, not twenty. The first version pushed every blueprint roll as its own entry and the list became unreadable; now `wishlist_add item=build` makes a single entry whose needs are the build module's live material list, so it shrinks as the ship is engineered.
- Three cards used to let you add materials (the materials card's flat wishlist, the recipes card's add controls, the wishlist picker). That was the "muddle": one place to add (the wishlist picker), one place to look things up (recipes), one place to see stock (materials). The flat `set_wishlist` API stays for scripts.
- Farm sites are a curated table (`modules/farming/sites.json`), not a live feed: the well-known spots have not moved in years, and surface coordinates matter more than freshness. Verified against edmining.com and edblackbox.com in October 2026; Jameson has nine data points since the 2025 overhaul.

## Front-end lessons

- The first theme was a generic dark dashboard (rounded cards, muted titles, pills) and read as machine-made. The redesign commits to one reference, the in-game cockpit: angular panels with corner brackets, HUD orange reserved for titles and things that matter, labels as uppercase micro-text above values, segmented gauges, tabular figures. Rules for new cards: use `.k` for every label, `.grid2`/`.grid3` for stats, `.chips` for lists of fitted things, tags for state, and never a new colour. Everything is in `web/style.css`; cards carry no inline colours beyond bar fills.

- The grid used to be 12 fixed columns capped at 1800 px, so an ultrawide showed a strip with empty margins and a laptop squeezed every card. A first fix made the column count follow the width (one per 150 px) so cards kept their size; that left holes whenever a row's nominal spans did not add up to the new count. Now it is 12 columns with no cap (rows that sum to 12 always fill the width, cards scale), 6 columns below 1100 px, 1 on a phone, and `grid-auto-flow: dense` fills the holes wide cards leave. Dense packing can reorder small cards visually, which is why it is a layout-menu checkbox.

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
