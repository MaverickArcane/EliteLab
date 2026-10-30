# Changelog

## Unreleased

- Materials: show current inventory and gross gains since the latest game login,
  including pickups, mission rewards and trader receipts. Journal replay restores
  session totals after dashboard restarts. The Engineering preset puts inventory
  beside the wishlist; delayed inventory responses cannot overwrite newer counts.
- Fix #50 (Tbehrends4587): Heat Sink Launcher now offers Lightweight, Reinforced,
  and Shielded alongside Ammo Capacity in recipe filters and the engineering
  wishlist. Shared blueprint keys and costs stay compatible with saved entries;
  new wishlist entries retain the selected module.

## 0.5.0 (2026-10-25)

- Merit rate: three rates instead of one. The headline is the pace while earning (time between merit gains, gaps capped at 20 min), beside the rate while playing (any journal activity; a 10 min silence is a break) and the elapsed-session rate, plus the break count and an idle flag. A three-hour engineering stop used to halve the only figure shown.
- Jump range now and laden (issue 4): computed from the FSD, its engineered optimal mass, fuel and cargo; the ship card shows now / laden / max and every jump estimate (targets, combat, farm sites, traders) uses the current range.
- Rare goods table is the full FDevIDs list of 142 with origin market ids (issue 15); five wrong community slugs dropped.
- Notifications (issue 5): toasts for merits gained, loop complete, fuel under 25 percent, interdiction, death and carrier jumps, with an optional beep.
- Visual overhaul: one cockpit-panel theme across the page (readout-strip header, angular cards with corner brackets, orange card titles with a rule, uppercase micro-labels, segmented gauge bars, tabular numbers, scanline background); every card class kept, so module cards needed no changes.
- Ship card redesigned: jump range up front, fuel and hull bars, a stats grid, and the whole loadout as chips (core, hardpoints, utility, internals) with class/rating, mount, blueprint grade and effect; engineered modules outlined, powered-off ones dimmed. `ship_info.modules` now carries display names.
- Farm sites: "find systems" on each High Grade Emissions entry asks Spansh for the nearest populated systems in that state or allegiance (`find_hge_systems`).
- MCP prompts and resources (issue 8): `plan_rares_run`, `engineering_plan`, `where_am_i`; live state readable as `elitelab://state` and per namespace.
- New `recipes` module: 81 engineering blueprints (materials per grade G1-G5, engineers per grade) and 87 experimental effects, searchable by free text; `list_recipes`, `get_recipe`.
- New `wishlist` module: an engineering wishlist that takes "2x g5 fsd increased range", "mass manager" or "50 tellurium", tracks have/need/short against the live inventory, plans material trader exchanges for the shortfalls (same-family 1:3 down, 6:1 up, cross-family x6), and finds the nearest traders by type on Spansh; `get_engineering_wishlist`, `wishlist_add`, `wishlist_remove`, `plan_material_trades`, `find_material_traders`.
- New `farming` module: curated material farm sites (crystal shards, brain trees, Dav's Hope, Jameson Crash Site, Guardian structures, crashed ships) and methods (High Grade Emissions by state, wake and ship scans), nearest first with EDSM distances, flagged when they cover a wishlist shortfall; map layer; `find_farm_sites`.
- New `build` module: pin an EDSY link, a Coriolis link or SLEF/Loadout JSON (decoded locally by `elitelab/core/edsy.py`, `coriolis.py`, `builds.py`), compare it with the current loadout slot by slot (buy / engineer / ok, credits, blueprint rolls from the current grade, effects), sum the materials against inventory, and track it on the wishlist as one live entry; `pin_build`, `get_build_progress`, `build_to_wishlist`, `unpin_build`.
- Shell: the grid fills the window (12 columns with no width cap, 6 on small windows, dense packing fills gaps, "fill gaps" toggle in the layout menu); the default layout starts with location and ship, then the engineering cards, Powerplay, and the map last; the Engineering preset shows build, wishlist, farm sites, recipes and materials; the materials card is now a filterable inventory and no longer has its own wishlist.
- MCP: a failed tool call now returns the lab's own error message instead of "HTTP Error 400".
- Core: `CoordCache` (core/coords.py) replaces the duplicated EDSM coordinate fetching in loop and farming; the materials inventory no longer rides SSE on every pickup (modules read it through `get_material_inventory` and watch `inventory_version`).
- Cards can be made shorter: drag the corner downwards to cap a card's height (it scrolls inside), double-click to reset; the build and wishlist cards show the first 12 short materials and 8 trades with "more" links, and the build's slot table can be hidden.
- Recipes: 37 technology broker unlocks (Guardian modules, weapons, fighters; human broker items) with materials and commodities; module, kind and engineer filters on the card.
- Wishlist: structured picker instead of free text (kind, module, blueprint, from/to grade, quantity); grade ranges ("2-5") for modules that already have some grades; tech broker unlock entries; `wishlist_options`.
- Journal: `ship_info.modules` now carries every functional module with full engineering (blueprint, level, quality, experimental effect) and `ship_internal` the hull id.
- Core: the material catalog (with trader families and caps, now including Thargoid and Guardian materials), blueprints, effects and unlocks live in `elitelab/core/engineering.json` and are exposed by `gamedata`; the materials module reads the catalog from there and now publishes `materials.inventory`.
- New `carrier` module (Tbehrends4587, #31): pin a visited fleet carrier and follow its last reported location and services on its own card and map layer; `get_followed_carrier`, `pin_fleet_carrier`, `unpin_fleet_carrier`, `refresh_followed_carrier`.
- Fix (Tbehrends4587, #26): an undocked `Location` snapshot clears stale docking state.
- docs/API.md regenerated (40 tools).

## 0.4.0 (2026-10-23)

First public version.

- Core: event bus, namespaced state store, journal tailer with replay, cached Spansh/EDSM services, HTTP router whose routes double as AI tools, Server-Sent Events, dependency-ordered module loader.
- Modules: journal, history, powerplay, merits, targets, combat, loop, materials, map.
- Shell: drag-and-drop layout (reorder, resize, collapse, hide), layout export/import, star map with starfield, star-class colouring and route trail, live feed, UI stall indicator.
- AI: MCP stdio server proxying every tool, `.mcp.json` for Claude Code, `python -m elitelab call` for shells, `docs/AI.md`.
- Powerplay: sell-target finder with jump counts, market age and "won't buy" warnings; combat finder that applies the conflict threshold so contested systems are real; merit attribution per activity including Powerplay conflict zone kills.
- Docker image and compose file; GitHub Actions CI; offline test suite with a fixture journal.
