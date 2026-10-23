# EliteLab

A small, self-hosted **live dashboard for Elite Dangerous**. It reads the game's journal files on your PC and shows what matters right now: where you are, what's in your hold, your Powerplay standing, your fleet carrier, and a sector map with the stations worth flying to next.

No accounts, no uploads, no dependencies. One Python process (standard library only) and one web page.

![EliteLab screenshot placeholder](docs/screenshot.png)

## What it does

- **Live state** polled from the journal every 3 seconds: commander, ship, credits, location, docked station, fuel, legal state.
- **Sector map**: top-down galactic X/Z canvas centred on your ship, with range rings, your carrier, the Lave cluster rares loop and any Powerplay sell targets you've searched for. Scroll to zoom, drag to pan, click a target to draw the leg and its distance.
- **Powerplay**: pledged power, rank, merits, pledge age, cycle countdown, and a **sell-target finder** that asks Spansh for unoccupied systems your power can acquire that have a market, in whatever distance band you want. Market freshness is colour-coded so you don't fly 150 Ly to a station nobody has visited since last year.
- **Compare powers**: for any reference system, how many acquisition starports every power has and the three nearest.
- **Cargo** with rare goods tagged, **rares in stock** at the market you last opened, **fleet carrier** fuel / balance / free space, **materials** totals, and a **live event feed** (jumps, docking, trades, merits gained, bounties, interdictions).
- **Rares loop checklist** for the Lave cluster with per-station notes, persisted in your browser.
- One-click **Inara** and **Spansh** lookups for anything on screen.

## Quick start

### Windows, no Docker

Requires Python 3.10+ ([python.org](https://www.python.org/downloads/), tick "Add to PATH").

```
git clone https://github.com/ELITELAB_REPO.git
cd EliteLab
"Start EliteLab.cmd"
```

That opens http://localhost:8766 and starts the server in a console window. The journal folder is auto-detected at `%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous`.

### Docker

```
cp .env.example .env        # edit ELITELAB_JOURNAL_DIR to your journal folder
docker compose up -d --build
```

Then open http://localhost:8766. The journal folder is mounted read-only; the container never writes to it. On Windows use forward slashes in `.env`, e.g. `C:/Users/you/Saved Games/Frontier Developments/Elite Dangerous`.

### Linux / macOS (Steam Proton journals)

```
./start.sh --journals "/path/to/Saved Games/Frontier Developments/Elite Dangerous"
```

## Configuration

Everything is an environment variable (or a CLI flag for the native run):

| Variable | Default | Meaning |
|---|---|---|
| `ELITELAB_HOST` | `127.0.0.1` (`0.0.0.0` in Docker) | Bind address |
| `ELITELAB_PORT` | `8766` | Port |
| `ELITELAB_JOURNAL_DIR` | Saved Games path, or `/journals` if it exists | Where the game writes `Journal.*.log` |
| `ELITELAB_RECENT_JOURNALS` | `3` | How many recent journal files to scan for live state |
| `ELITELAB_CACHE_TTL` | `600` | Seconds to cache Spansh/EDSM responses |

Bind to `0.0.0.0` if you want to open the dashboard from another device on your LAN (a tablet next to the HOTAS, say). There is no auth, so don't expose it to the internet.

## How it works

```
Elite Dangerous ──writes──▶ Journal.*.log, Status.json, Cargo.json, Market.json
                                      │
                                      ▼  (read-only, every request)
                           elitelab/journal.py  →  one state dict
                                      │
            Spansh / EDSM ◀── elitelab/spansh.py (cached) ──┐
                                      │                      │
                           elitelab/server.py  (stdlib HTTP, JSON API + static)
                                      │
                                      ▼
                           web/  index.html · app.js · style.css  (polls /api/state)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the module layout and how to extend it, and [docs/API.md](docs/API.md) for the JSON endpoints.

## Roadmap / ideas

- WebSocket push instead of polling
- Per-commodity profit calculator for the sell targets (Spansh market data is already in the response)
- Engineering blueprint wishlist (or just deep-link into Odyssey Materials Helper)
- EDMC plugin mode so one process does both uploading and the dashboard
- Route export to the in-game clipboard route plotter

## Similar projects

EliteLab is deliberately tiny. If you want more, these are the established open-source tools:

- [EDMarketConnector](https://github.com/EDCD/EDMarketConnector): the standard journal uploader (Inara, EDDN, EDSM) with a plugin API.
- [EDDiscovery](https://github.com/EDDiscovery/EDDiscovery): full logbook, 3D galaxy map, materials, carrier panel.
- [Odyssey Materials Helper](https://github.com/jixxed/ed-odyssey-materials-helper): materials and engineering wishlists.
- [Elite Observatory](https://github.com/Xjph/ObservatoryCore): exploration-focused journal watcher with plugins.
- [EDDI](https://github.com/EDCD/EDDI): voice responder driven by journal events.

## Data sources and thanks

- Station and system search: [Spansh](https://spansh.co.uk)
- Coordinates: [EDSM](https://www.edsm.net)
- Journal format: Frontier's [Player Journal manual](https://hosting.zaonce.net/community/journal/)

Elite Dangerous is © Frontier Developments plc. This project is not affiliated with Frontier.

## License

MIT. See [LICENSE](LICENSE).
