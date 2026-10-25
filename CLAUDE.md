# Agent guide to this repository

Read this first. It is written for an AI assistant (or a human) landing in this repo cold. Everything here is current as of 0.5.0.

## What this is

A self-hosted dashboard for Elite Dangerous that reads the game's journal files, shows live state in a browser, and exposes the same data as tools an AI can call (HTTP, MCP, or `python -m elitelab call`). Standard-library Python 3.10+, vanilla JS, no build step, no dependencies.

The owner plays Elite and builds this while testing things in game. The code is intentionally small. Do not add frameworks, package managers or build steps without being asked.

## Map of the repo

| Path | What | Read when |
|---|---|---|
| `elitelab/core/` | bus, store, services, http, loader, watcher, Core; `gamedata` (shared game tables), `coords` (EDSM cache), `edsy` / `coriolis` / `builds` (build link decoders) | changing plumbing or shared game data |
| `elitelab/mcp.py` | MCP stdio server (proxies the HTTP tools) | AI integration |
| `elitelab/__main__.py` | CLI: serve, mcp, modules, tools, call | |
| `modules/<name>/` | one feature each: `module.json` + `module.py` + `web/*.js` | adding or changing a feature |
| `web/` | shell: `index.html`, `app.js` (the `Lab` runtime and layout engine), `style.css` | changing the UI chrome |
| `tests/` | offline unittest suite + fixture journal | always, before and after a change |
| `docs/` | reference docs, see below | |
| `data/` | runtime files (wishlist, selected loop); gitignored | |

Reference docs, most specific first:

- `docs/CODE.md`: every file, class and function, what it does and its gotchas.
- `docs/STATE.md`: every store namespace and key, who writes it, who reads it.
- `docs/EVENTS.md`: every journal event consumed, the fields used, and what they mean.
- `docs/FRONTEND.md`: the `Lab` runtime, card lifecycle, layout engine, map layers.
- `docs/DECISIONS.md`: why things are the way they are, and the traps we already fell into.
- `docs/TESTING.md`: how to test, how to extend the fixture journal.
- `docs/ARCHITECTURE.md`, `docs/MODULES.md`, `docs/API.md`, `docs/AI.md`: the human-facing versions.

## How to run and verify

```
python -m unittest discover -s tests -v     # 65 tests, offline, a few seconds (the transport tests start a server)
python -m elitelab modules                   # dependency order and cards
python -m elitelab serve -v                  # http://localhost:8766, logs to stderr
python -m elitelab call get_commander_state  # any tool against a running lab
```

Never run the package with `python -I`: isolated mode drops the current directory from `sys.path` and the package is not found.

To restart the server on Windows from a script, kill the existing `python -m elitelab` process first (the port is 8766). The front end is static and is re-read on every request, so JS/CSS/HTML changes need only a browser refresh. Python changes need a server restart.

## The contract, in one paragraph

The watcher emits `journal.<Event>` on the bus for every journal line (replayed lines carry `_replay: true`) and `journal.file.<Name>` for snapshot files. Modules subscribe, fold events into their own store namespace with `core.store.update(ns, {...})`, and register routes with `core.http.route(path, fn, tool=..., description=..., params=...)`. Store changes fan out to the bus as `state.<ns>.<key>` and to browsers over SSE. Routes with a `tool` name are listed in `/api/schema` and become MCP tools automatically. Modules never import each other.

## Rules for changes

1. Run the tests before and after. Add a test for parsing changes using `tests/fixtures/journals/`.
2. A new feature is a new module. Do not grow `journal` into a god module.
3. Write only to your own namespace. Read others via `core.store.get(ns, key)`.
4. Bus handlers run on the watcher thread. Do not block or do network I/O in them; spawn a thread (see `modules/loop/module.py`) or do it in a route.
5. Every route gets a `tool=` name and a description written for a model: what the data is for, what the parameters mean, what the defaults are.
6. `esc()` any text from the journal or an API before it goes into HTML.
7. ASCII in docs and messages. No emojis anywhere.
8. Keep responses small. Add parameters rather than returning everything.
9. Commit messages: plain, present tense, say what changed. Commits in this repo end with a `Co-Authored-By` line for the AI assistant.

## Things that bit us (short list; long list in docs/DECISIONS.md)

- Rare goods: Leathery Eggs is `alieneggs` in the journal. Never assume the key is the slugified name. The one table is `elitelab/core/gamedata.py` (`RARES`, `is_rare`, `norm`); modules import from there, never keep their own copy. We shipped two disagreeing copies once.
- `StarClass` is on `StartJump`, not `FSDJump`.
- New hulls (Kestrel, Panther...) appear in `Loadout` as internal ids with no `Ship_Localised`. Learn names from `StoredShips`/`ShipyardSwap`.
- `Market.json` names look like `$alieneggs_name;`; `Cargo.json` names look like `alieneggs`. Normalise with `norm()`.
- Powerplay conflict zone kills log no `Bounty`/`FactionKillBond`. Attribute by "we are in a zone" (`SupercruiseDestinationDrop` with `Warzone_Powerplay`).
- Spansh `power_conflict_progress` is a fraction of the acquisition threshold and can exceed 1.0. A system is contested only when two powers are both >= ~0.29.
- Pointer capture is lost when the captured element is moved in the DOM. The layout engine listens on `window` for that reason.
- Chrome throttles `requestAnimationFrame` to 1 Hz in background tabs. Do not measure UI performance in a hidden tab.

## Current game facts the code relies on

Rates were measured on the owner's commander in October 2026 and are encoded as hints, not rules: rares paid 1 merit per ~667 Cr of sale value with Mahon's bonus; a Medium Powerplay conflict zone paid 14 (assist) / 172 (kill) / 216 (Expert kill) per event. Update `docs/DECISIONS.md` if you measure something different.

Engineering: blueprint costs, experimental effects, technology broker unlocks and the material catalog (with trader families) are the one table `elitelab/core/engineering.json`, read through `gamedata`. Build links are decoded locally: `elitelab/core/edsy.py` (EDSY, tables in `edsy.json`), `coriolis.py` (Coriolis, `coriolis.json`), `builds.py` (dispatch plus SLEF/Loadout JSON); regenerate the tables when new ships appear. Farm sites are `modules/farming/sites.json`. Material trader ratios are 1:3 down and 6:1 up per grade within a family, times 6 across families, never across Raw/Manufactured/Encoded. Rolls per grade default to 1/2/3/4/5 as a planning hint (`rolls_per_grade`); override per wishlist entry with `rolls`.
