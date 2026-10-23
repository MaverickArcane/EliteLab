# EliteLab

A small, self-hosted, **modular live dashboard for Elite Dangerous** with an **AI-facing API**. It reads the game's journal on your PC, shows what matters right now, and exposes the same data as tools that Claude Code (or any MCP client, or a shell) can call: *"what am I short for this blueprint?"*, *"where do I sell these rares for merits?"*, *"am I done with the loop?"*.

No accounts, no uploads, no dependencies. Python standard library, one web page, no build step.

![EliteLab screenshot placeholder](docs/screenshot.jpg)

## What's in the box

| Module | Dashboard card(s) | AI tools |
|---|---|---|
| **journal** | Location, Ship, Cargo, Rares at this market, Fleet carrier, Live feed | `get_commander_state` |
| **powerplay** | Power, rank, merits, merits this session, cycle countdown | `get_powerplay_status` |
| **merits** | Merits per hour and per activity, attributed from the journal | `get_merits_summary` |
| **combat** | Where combat pays merits: contested systems (combat zones), acquisition, undermining, reinforcement | `find_combat_systems` |
| **targets** | Powerplay sell-target finder with jump counts, market freshness and "won't buy" warnings for rares in your hold; power comparison | `find_sell_targets`, `compare_powers`, `get_system_info` |
| **loop** | Rare goods loop that ticks itself from your hold, sorted by distance, next stop | `get_rares_loop`, `select_rares_loop` |
| **materials** | Inventory totals, wishlist with live shortfalls | `get_materials`, `set_wishlist`, `get_wishlist`, `material_sources` |
| **history** | (feeds the map) | `get_travel_history` |
| **map** | Star map: starfield, visited systems coloured by star class, route trail, layers from other modules | `get_system_coords` |
| core | header, live connection | `get_state`, `get_recent_events`, `list_modules`, `list_tools`, `health` |

Everything updates live over Server-Sent Events the moment the game writes a journal line.

## Quick start

### Windows, no Docker

Requires Python 3.10+ ([python.org](https://www.python.org/downloads/), tick "Add to PATH").

```
git clone https://github.com/ELITELAB_REPO.git
cd EliteLab
"Start EliteLab.cmd"
```

Opens http://localhost:8766. The journal folder is auto-detected at `%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous`.

### Docker

```
cp .env.example .env        # set ELITELAB_JOURNAL_DIR
docker compose up -d --build
```

Journals are mounted read-only; wishlists persist in a named volume.

### Linux / macOS

```
./start.sh --journals "/path/to/Saved Games/Frontier Developments/Elite Dangerous"
```

## Talk to it from an AI

With the lab running, open the repo folder in **Claude Code**: `.mcp.json` registers the `elitelab` MCP server automatically. Then just ask:

> I want to work on getting materials for an FSD G5 Increased Range roll.

The assistant sets your wishlist, reads your shortfalls, and tells you where to farm. The Materials card on the dashboard shows the same shortfalls ticking down as you collect.

Any agent with a shell can do the same without MCP:

```
python -m elitelab tools
python -m elitelab call get_materials only_short=true
python -m elitelab call find_sell_targets min=125 max=165
```

See [docs/AI.md](docs/AI.md).

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `ELITELAB_HOST` / `ELITELAB_PORT` | `127.0.0.1` / `8766` | Bind address (`0.0.0.0` in Docker) |
| `ELITELAB_JOURNAL_DIR` | Saved Games path, or `/journals` | Where the game writes `Journal.*.log` |
| `ELITELAB_DATA_DIR` | `./data` | Persistent files (wishlist, selected loop) |
| `ELITELAB_RECENT_JOURNALS` | `3` | Journal files replayed at startup |
| `ELITELAB_DISABLE` | | Comma-separated module names to skip |
| `ELITELAB_URL` | `http://127.0.0.1:8766` | Where the MCP proxy finds the lab |

Bind to `0.0.0.0` to open the dashboard from a tablet on your LAN. There is no auth; don't expose it to the internet.

## How it's built

```
game journal â”€â–¶ watcher â”€â–¶ event bus â”€â–¶ modules â”€â–¶ state store â”€â–¶ SSE â”€â–¶ browser cards
                                          â”‚
                                          â””â”€â–¶ routes = /api/* = MCP tools
```

A **core** (bus, store, services, HTTP, loader, watcher) and **modules** that declare what they `require` and `provide`. Modules talk only through the store and the bus; the loader sorts them by dependency and refuses to start on a missing one. Every route registered with a tool name is automatically an MCP tool.

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how the pieces fit
- [docs/MODULES.md](docs/MODULES.md): write a module in 60 lines
- [docs/API.md](docs/API.md): every endpoint / tool, generated from `/api/schema`
- [docs/AI.md](docs/AI.md): MCP, shell and HTTP usage for assistants

## Similar projects

EliteLab is deliberately tiny and Powerplay-first. For more, see the established open-source tools:

- [EDMarketConnector](https://github.com/EDCD/EDMarketConnector): the standard journal uploader (Inara, EDDN, EDSM) with a plugin API.
- [EDDiscovery](https://github.com/EDDiscovery/EDDiscovery): full logbook, 3D galaxy map, materials, carrier panel.
- [Odyssey Materials Helper](https://github.com/jixxed/ed-odyssey-materials-helper): blueprint-level materials planning.
- [Elite Observatory](https://github.com/Xjph/ObservatoryCore): exploration-focused journal watcher with plugins.
- AI bridges: [EDGPT](https://glama.ai/mcp/servers/bnrkhmvp3c), [Elite Dangerous Local AI Tie-In MCP](https://github.com/GWLlosa/elite-dangerous-local-ai-tie-in-mcp).

## Data sources and thanks

[Spansh](https://spansh.co.uk) for station and system search, [EDSM](https://www.edsm.net) for coordinates, Frontier's [Player Journal manual](https://hosting.zaonce.net/community/journal/) for the format. Elite Dangerous is Â© Frontier Developments plc; this project is not affiliated with Frontier.

## License

MIT. See [LICENSE](LICENSE).
