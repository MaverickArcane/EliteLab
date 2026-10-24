# Using EliteLab from an AI

EliteLab is built so an assistant can look at your live game and act on it. There are three ways in, all backed by the same self-describing API.

## 1. MCP (Claude Code, Claude Desktop, Cursor, any MCP client)

The repo ships `.mcp.json`, so in Claude Code just open the project folder and the `elitelab` server is offered automatically (the lab must be running). For other clients, register:

```json
{ "mcpServers": { "elitelab": { "command": "python", "args": ["-m", "elitelab", "mcp"], "cwd": "C:/path/to/EliteLab" } } }
```

The MCP process is a thin proxy over HTTP; set `ELITELAB_URL` if the lab is not on `http://127.0.0.1:8766`.

## 2. Shell

Any agent with a terminal can do:

```
python -m elitelab tools
python -m elitelab call get_materials only_short=true
python -m elitelab call set_wishlist items='{"Datamined Wake Exceptions": 15}' label="FSD G5"
```

## 3. HTTP

`GET /api/schema` lists every tool with a JSON Schema for its parameters. Tools are plain `GET` routes with query parameters, or `POST` with a JSON body. `GET /api/state` is the whole live state; `GET /events` is a Server-Sent Events stream of changes.

## Tools (as of 0.4)

| Tool | What it answers |
|---|---|
| `get_commander_state` | Who, where, what ship, docked where, cargo (rares tagged), carrier, materials totals, recent feed |
| `get_powerplay_status` | Power, rank, merits, merits this session, cycle end, control of current system |
| `get_rares_loop`, `select_rares_loop` | Which loop stations are done, tons aboard, next stop |
| `get_merits_summary` | Merits per hour and per activity this session (rares, trade, bounties, combat zones, hauling...) with a recent log |
| `find_combat_systems` | Where combat pays merits: contested acquisition systems (combat zones), acquisition (bounties), undermining (power kills), reinforcement |
| `find_sell_targets` | Acquisition starports for a power from a system, with distance, jumps, market age, and which rares in the hold the station will not buy |
| `compare_powers` | Which power has the closest acquisition systems to you |
| `get_system_info` | Spansh summary of any system |
| `get_materials`, `get_wishlist`, `set_wishlist`, `material_sources` | Inventory with caps, a flat per-material wishlist, and where to farm |
| `list_recipes`, `get_recipe` | Engineering blueprints and experimental effects: materials per grade, engineers, total cost to a grade |
| `get_engineering_wishlist`, `wishlist_add`, `wishlist_remove` | Track blueprints ("2x g5 fsd increased range"), effects and materials against live inventory |
| `plan_material_trades`, `find_material_traders` | Which trader exchanges cover the shortfalls from current surplus, and the nearest traders by type |
| `find_farm_sites` | Where to farm a material: known sites with system, body, surface coordinates and method, nearest first; `for_wishlist=true` for the current shortfalls |
| `pin_build`, `get_build_progress`, `build_to_wishlist`, `unpin_build` | Pin an EDSY link; what the current ship still needs to match it (buy, engineer, materials, credits); push the engineering to the wishlist |
| `get_travel_history` | Systems visited, route, star classes |
| `get_system_coords` | Coordinates |
| `get_recent_events` | Raw journal events, newest first |
| `get_state`, `list_modules`, `list_tools`, `health` | Introspection |

## MCP prompts and resources

Besides the tools, the MCP server offers three prompts (`plan_rares_run`, `engineering_plan` with a `goal` argument, `where_am_i`) that tell the model which tools to chain and what to answer, and read-only resources: `elitelab://state` (everything) and `elitelab://state/<namespace>` (one module, e.g. `elitelab://state/wishlist`).

## Example conversations

**"I want to work on getting materials for an FSD G5 Increased Range roll."**
The assistant calls `wishlist_add item="g5 fsd increased range"`; the reply already lists have/need/short per material. `plan_material_trades` says which surplus to hand to which trader, `find_material_traders` says where, and `material_sources` covers what trading cannot. The Engineering wishlist card shows the shortfalls and ticks down as you collect. If the text is ambiguous ("shield reinforced" matches a generator and a booster), the reply has `status: ambiguous` with candidates; repeat with a key.

**"Here is my EDSY build, what do I still need?"**
`pin_build url=...` (EDSY link, Coriolis link or SLEF JSON) then `get_build_progress`: every slot is `ok`, `engineer` (with "Increased Range G3 to G5, apply Mass Manager") or `buy` (with credits), plus every material with have/need/short. `build_to_wishlist` tracks the build as one wishlist entry that follows progress, after which `plan_material_trades` and `find_farm_sites for_wishlist=true` answer "trade or farm what, where".

**"Where do I farm tellurium?"**
`find_farm_sites material=tellurium` returns HIP 36601 C 3 b with the landing coordinates and how to work the shard site, with the distance from the ship.

**"What does G5 dirty drives cost?"**
`get_recipe key="dirty drives"` returns the materials per grade, the engineers who offer each grade, and the total from G1 to G5 using the rolls-per-grade hint.

**"Where should I sell these rares?"**
`get_commander_state` shows the hold and current system; `get_powerplay_status` shows the pledged power; `find_sell_targets min=125 max=165` returns starports with jump counts for your ship. The assistant can rank by jumps and market freshness and tell you the system to plot.

**"Am I done with the loop?"**
`get_rares_loop` returns `complete`, `tons_total` and `next`.

## Design notes for tool authors

- Describe tools for a model: say what the data is *for*, not just what fields it has.
- Default parameters to the live context (current system, pledged power) so the model can call with no arguments.
- Keep responses small and structured; `get_state` exists for when the model needs everything, but specific tools should be the normal path.
- Everything is read from the journal; nothing can act inside the game. The only writes are to EliteLab's own data (wishlist, selected loop).
