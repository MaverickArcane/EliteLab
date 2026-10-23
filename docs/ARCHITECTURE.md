# Architecture

EliteLab is three small layers. Each can be replaced without touching the others.

```
elitelab/
  config.py    paths, ports, env overrides          (no imports from the package)
  journal.py   journal files  →  state dict         (depends on config)
  spansh.py    cached Spansh + EDSM clients         (depends on config)
  server.py    HTTP routes, static files            (depends on all of the above)
  __main__.py  CLI entry: python -m elitelab
web/
  index.html   layout only, no inline JS
  app.js       polling, map, targets, checklist
  style.css    theme tokens and layout
```

## Data flow

1. The browser polls `GET /api/state` every 3 s.
2. `journal.build_state()` scans the newest `ELITELAB_RECENT_JOURNALS` journal files line by line, folding each event into a dict with `apply_event()`. It then overlays the snapshot files (`Status.json`, `Cargo.json`, `Market.json`). If the carrier has never been seen in those files, `_backfill_carrier()` searches older journals for the last `CarrierStats`.
3. On demand the browser hits `/api/targets`, `/api/powers`, `/api/system` or `/api/coords`. These go through `spansh.py`, which caches every response (10 min for Spansh, 24 h for coordinates) so the community APIs are never hammered.

The journal scan is stateless and runs on every request. With the default three files (a few hundred KB) it takes a few milliseconds, which is simpler and more robust than tailing files and tracking offsets. If you need a very long history, raise `ELITELAB_RECENT_JOURNALS` or add a tailing reader; `apply_event()` is already incremental.

## Adding a journal event

1. In `journal.py`, add a branch to `apply_event()` that updates the state dict.
2. If it should show in the live feed, add a one-line formatter to `FEED_EVENTS`.
3. Render it in `app.js` inside `refresh()`.

The event names and fields are documented in Frontier's Player Journal manual.

## Adding an API endpoint

Add a branch in `server.Handler.do_GET()`. Keep it a thin call into a module function so it stays testable without HTTP. Everything returns JSON; errors are `{"error": "..."}` with a 500.

## Adding a card to the UI

`index.html` is grid-based: a `.card` spans 3 of 12 columns, `.c4` / `.c6` / `.c8` / `.c12` span more. Cards reflow to full width on narrow screens. Fill them from `refresh()` in `app.js`; use `esc()` on anything that came from the journal or an API.

## Map

The map is a plain `<canvas>`: galactic X on the horizontal axis, Z vertical (up is toward the core), Y shown only in tooltips. `mapPoints()` gathers everything plottable (ship from `StarPos`, carrier and loop systems via EDSM coords, sell targets from Spansh), `drawMap()` projects with `app.map.{cx,cz,scale}`. Zoom and pan only change those three numbers.

## Why no framework

Zero build step means a friend can `git clone` and double-click a `.cmd`. Everything is readable in one sitting. If the UI grows past a couple of thousand lines, Preact or Svelte would be a reasonable next step; the API contract would not change.

## Docker

The image copies `elitelab/` and `web/`, sets `ELITELAB_HOST=0.0.0.0`, and expects journals at `/journals` (mounted read-only by compose). It runs as `nobody`. There is a healthcheck on `/api/health`.
