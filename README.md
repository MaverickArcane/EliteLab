# EliteLab

A small, self-hosted dashboard for Elite Dangerous that an AI assistant can also talk to. It reads the game's journal files on your PC, shows what is going on right now (location, ship, cargo, Powerplay, carrier, materials, a star map), and exposes the same data as tools that Claude Code, any MCP client, or a shell script can call.

This project is vibe coded. I built it with an AI assistant while playing, to test things out in Elite and to have a dashboard I can interact with and call on with AI help. It is not polished software and does not try to be. Anyone is welcome to fork it, mess around with it, rip modules out, add their own, or take it somewhere else entirely. If you find a bug, open an issue with the journal lines around it. If you build a module, open a PR. Nothing fancy.

No accounts, no uploads, no dependencies: Python standard library, one web page, no build step.

![EliteLab desktop dashboard with the cockpit theme, ship readouts, and engineering panels](docs/screenshot.jpg)

The current desktop layout. Screenshots use the bundled sample journals; live market data and personal builds depend on your session.

### Engineering workspace

Switch to the Engineering preset to bring build planning, the wishlist, recipes, and material farming together.

![Engineering preset showing build planning, the engineering wishlist, recipes, and material farm sites](docs/engineering.jpg)

<details>
<summary>See the mobile layout</summary>

Cards stack vertically on narrow screens, keeping commander, location, and ship information readable.

<img src="docs/mobile.jpg" alt="EliteLab at a 390-pixel mobile width, with location and ship cards stacked vertically" width="300">

</details>

## What it does

| Module | Dashboard card(s) | AI tools |
|---|---|---|
| journal | Location, Ship, Cargo, Rares at this market, Live feed | `get_commander_state` |
| carrier | Fleet carrier: owned details or one pinned visitor carrier | `get_followed_carrier`, `pin_fleet_carrier`, `unpin_fleet_carrier`, `refresh_followed_carrier` |
| powerplay | Power, rank, merits, merits this session, cycle countdown | `get_powerplay_status` |
| merits | Merits per hour and per activity, worked out from the journal | `get_merits_summary` |
| combat | Where combat pays merits: contested systems with combat zones, acquisition, undermining, reinforcement | `find_combat_systems` |
| targets | Powerplay sell-target finder with jump counts, market freshness, and warnings about rares a station will not buy; power comparison | `find_sell_targets`, `compare_powers`, `get_system_info` |
| loop | Rare goods loop that ticks itself from your hold, sorted by distance, with the next stop | `get_rares_loop`, `select_rares_loop` |
| materials | Inventory as the game reports it, filterable; where-to-farm hints; a flat per-material wishlist for scripts | `get_materials`, `set_wishlist`, `get_wishlist`, `material_sources` |
| recipes | Engineering blueprints G1-G5 and experimental effects with materials per grade and which engineers offer them; searchable | `list_recipes`, `get_recipe` |
| wishlist | Engineering wishlist: pick a blueprint (from grade X to grade Y), experimental effect, tech broker unlock or material; have/need/short against live inventory; material trader plan for the shortfalls; nearest traders | `get_engineering_wishlist`, `wishlist_add`, `wishlist_remove`, `wishlist_options`, `plan_material_trades`, `find_material_traders` |
| farming | Where to farm: crystal shards, brain trees, Dav's Hope, Jameson, Guardian structures, HGE by state; nearest first, flagged when they cover a wishlist shortfall; map layer | `find_farm_sites` |
| build | Pin an EDSY or Coriolis build (or SLEF JSON) and measure your ship against it: modules to buy (with credits), blueprints and grades still to roll, effects, every material vs inventory, one click to track it on the wishlist | `get_build_progress`, `pin_build`, `unpin_build`, `build_to_wishlist` |
| history | Feeds the map | `get_travel_history` |
| map | Star map: starfield, visited systems coloured by star class, route trail, layers from other modules | `get_system_coords` |
| core | Header, live connection, layout | `get_state`, `get_recent_events`, `list_modules`, `list_tools`, `health` |

Everything updates live over Server-Sent Events the moment the game writes a journal line. Cards can be dragged, resized, hidden, saved as named layouts, or switched between presets (Powerplay, Rares run, Combat, Mining and trade, Engineering, Second screen).

You do not need to own a fleet carrier to use the Fleet carrier card. Choose a carrier from your journal visits and click **Pin** to follow its last reported system and services. The selection survives restarts. Your journal updates it when you dock, log in aboard, or ride a jump; Spansh reports are checked every five minutes while EliteLab runs. **Refresh** uses the same five-minute cache. Reports can lag behind movements, so the card shows the source, observation time and last check separately. Offline mode keeps saved observations. **Unpin** restores the owned-carrier view, if available. Fuel, balance and free capacity are owner-only information. If the card is hidden by your layout preset, enable **Fleet carrier** in the Layout menu.

## Quick start

### Windows, no Docker

Requires Python 3.10 or newer (python.org, tick "Add to PATH").

```
git clone https://github.com/MaverickArcane/EliteLab.git
cd EliteLab
"Start EliteLab.cmd"
```

That opens http://localhost:8766. The journal folder is found automatically: `%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous` on Windows, and on Linux and macOS the Steam Proton prefix in any Steam library (Flatpak Steam included) or the Mac Application Support folder, whichever holds journals. Change it on the setup page if it picked the wrong one.

### Docker

```
cp .env.example .env        # set ELITELAB_JOURNAL_DIR
docker compose up -d --build
```

Journals are mounted read-only. Wishlists and the selected loop persist in a named volume.

### Linux and macOS

```
./start.sh --journals "/path/to/Saved Games/Frontier Developments/Elite Dangerous"
```

`--journals` is optional: without it the lab looks for a Steam Proton prefix and the Mac Application Support folder, and the setup page can save the folder for next time.

### First run

Open http://localhost:8766/setup/. The page lists the Elite Dangerous journal folders it found (Windows Saved Games, Steam Proton including Flatpak Steam and every Steam library, and the Mac Application Support folder), or you can type a path and click **Test** to see how many journals it holds. Pick the folder, save, and click **Restart** if the page says a restart is needed; it waits for the lab to come back and opens the dashboard. When no journal files are found, the dashboard banner links to this page. Saving only writes the settings file, and nothing changes until the restart.

The settings file is `%APPDATA%\EliteLab\settings.json` on Windows and `$XDG_CONFIG_HOME/elitelab/settings.json` elsewhere (`~/.config/elitelab/settings.json` by default). Command line flags and environment variables still win over the file, so a Docker setup behaves as before; the page warns when one of them will override a value you save. Restart works under `start.sh` and `Start EliteLab.cmd`, which start the lab again when it exits with status 75; run the server any other way and Restart simply stops it.

## Talking to it from an AI

With the lab running, open the repo folder in Claude Code. The `.mcp.json` in the repo registers the `elitelab` MCP server automatically. Then ask things like:

> I want to work on getting materials for an FSD G5 Increased Range roll.

The assistant adds the blueprint to your engineering wishlist, reads your shortfalls, suggests material trader exchanges from your surplus, and tells you where to farm the rest. The Engineering wishlist card shows the same shortfalls going down as you collect.

Any agent with a shell can do the same without MCP:

```
python -m elitelab tools
python -m elitelab call get_materials only_short=true
python -m elitelab call find_sell_targets min=125 max=165
```

See docs/AI.md.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `ELITELAB_SETTINGS` / `--settings PATH` | platform path (see First run) | Settings file to read and write. Order of precedence: flag, environment, settings file, default |
| `ELITELAB_HOST` / `ELITELAB_PORT` | `127.0.0.1` / `8766` | Bind address (`0.0.0.0` in Docker) and port; an IPv4 address or a host name. Empty means the default |
| `ELITELAB_AUTH_TOKEN` | | When set, `/api/*` and `/events` need `Authorization: Bearer TOKEN` or the session cookie from `POST /api/login`, and the Host rule below is skipped |
| `ELITELAB_ALLOWED_HOSTS` | | Comma-separated extra host names a POST may use in its Host header, for example `nas.local` (see below) |
| `ELITELAB_JOURNAL_DIR` | `/journals` in Docker, else the first detected folder with journals (Windows Saved Games, Steam Proton, Mac Application Support), else the Windows Saved Games path | Where the game writes `Journal.*.log` |
| `ELITELAB_BROWSER` | | Browser executable setting, reserved for the launcher (nothing reads it yet); the setup page shows it but cannot change it, so set it here or as `browser` in the settings file |
| `ELITELAB_DATA_DIR` | `./data` | Persistent files (wishlist, selected loop) |
| `ELITELAB_RECENT_JOURNALS` | `3` | Journal files replayed at startup |
| `ELITELAB_DISABLE` | | Comma-separated module names to skip |
| `ELITELAB_OFFLINE` | | Set to `1` to never call Spansh or EDSM (tests use this) |
| `ELITELAB_URL` | `http://127.0.0.1:8766` | Where the MCP proxy finds the lab |

Without `ELITELAB_AUTH_TOKEN`, the server answers a POST only when its Host header is an IP address, `localhost`, the bind host, this machine's own name, or a name in `ELITELAB_ALLOWED_HOSTS`; any other gets 403 with the variable to set. This holds on every bind, so a DNS-rebinding web page (which always needs a DNS name) cannot change anything, while opening the dashboard by IP or by the machine's name keeps working. Bind to `0.0.0.0` to open the dashboard from a tablet on your LAN; this machine's own name is its short host name, so if you reach it by any other name, such as `nas.local`, a fully qualified name or a Tailscale MagicDNS name, add that name to `ELITELAB_ALLOWED_HOSTS`. Inside Docker the container's own name is not the host's name, so reaching the container by the host's name needs `ELITELAB_ALLOWED_HOSTS`. Without a token there is no auth, so do not expose it to the internet.

## How it is built

```
game journal --> watcher --> event bus --> modules --> state store --> SSE --> browser cards
                                              |
                                              +--> routes = /api/* = MCP tools
```

A core (bus, store, services, HTTP, loader, journal watcher) and modules that declare what they require and provide. Modules talk only through the store and the bus. The loader sorts them by dependency and refuses to start on a missing one. Every route registered with a tool name is automatically an MCP tool.

- docs/ARCHITECTURE.md: how the pieces fit
- docs/MODULES.md: how to write a module
- docs/API.md: every endpoint and tool, generated from `/api/schema`
- docs/AI.md: MCP, shell and HTTP usage for assistants
- ROADMAP.md: what I want to do next
- CONTRIBUTING.md: how to help

## Tests

```
python -m unittest discover -s tests -v
```

Runs offline against a synthetic journal in `tests/fixtures/journals`. CI runs the same on Linux and Windows, syntax-checks the front end, and builds the Docker image.

## Similar projects

EliteLab is small and Powerplay-first. For more complete tools, see:

- EDMarketConnector (https://github.com/EDCD/EDMarketConnector): the standard journal uploader (Inara, EDDN, EDSM) with a plugin API.
- EDDiscovery (https://github.com/EDDiscovery/EDDiscovery): full logbook, 3D galaxy map, materials, carrier panel.
- Odyssey Materials Helper (https://github.com/jixxed/ed-odyssey-materials-helper): blueprint-level materials planning.
- Elite Observatory (https://github.com/Xjph/ObservatoryCore): exploration-focused journal watcher with plugins.
- AI bridges: EDGPT (https://glama.ai/mcp/servers/bnrkhmvp3c) and Elite Dangerous Local AI Tie-In MCP (https://github.com/GWLlosa/elite-dangerous-local-ai-tie-in-mcp).

## Data sources and thanks

Spansh (https://spansh.co.uk) for station and system search, EDSM (https://www.edsm.net) for coordinates, and Frontier's Player Journal manual for the format. Elite Dangerous is a trademark of Frontier Developments plc. This project is not affiliated with Frontier.

## License

MIT. See LICENSE.
