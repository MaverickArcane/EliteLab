# Front-end reference

`web/index.html` is a shell with a header, an empty `#grid`, a `#toasts` container and a footer. Everything else is built by `web/app.js` and the module card scripts. Plain ES2020, no bundler, no framework. Files are served with `Cache-Control: no-store`, so a browser refresh always gets the current code.

## Boot sequence (app.js, bottom IIFE)

1. `GET /api/modules` -> manifest list. Footer shows module names.
2. Every distinct card `script` URL is loaded sequentially with `<script>` tags (order follows module order, so a module can rely on earlier modules' layers existing).
3. `GET /api/state` -> `Lab.state` initial snapshot.
4. `allCards` = all manifest cards flattened and sorted by card `order`.
5. `mountCards()` builds the grid from the saved layout.
6. Every namespace is emitted once so cards render.
7. `connect()` opens `EventSource('/events')`.

## The `Lab` runtime

| Member | Purpose |
|---|---|
| `Lab.state[ns]` | server namespaces mirrored from SSE; client-only namespaces live here too (`targets` results, `combat` results) |
| `Lab.on(ns or [ns...], fn) -> off` | subscribe; `fn(state)` is called once per animation frame for any pending namespace in the list |
| `Lab.emit(ns)` | mark a namespace changed; batched with `requestAnimationFrame` |
| `Lab.set(ns, patch)` | shallow-merge into a (client) namespace and emit |
| `Lab.get(ns, key?)` | read |
| `Lab.api(path, params)` | GET JSON with query params (null/empty skipped) |
| `Lab.post(path, body)` | POST JSON |
| `Lab.card(def)` | register a card definition by `id` |
| `Lab.map.addLayer(id, def)` | register a map layer (see below) |
| `Lab.shipPos(state)` | `{x,y,z}` from `journal.star_pos`, else from `Lab.coords[journal.system]`, else null |
| `Lab.coords` | `{system: {x,y,z}}` cache |
| `Lab.toast(msg, kind?)` | bottom-right toast for 2.6 s; `kind='bad'` is red |
| `Lab.relayout()` | coalesced dispatch of a `lab:relayout` window event; cards that own canvases listen to it instead of `resize` |
| `Lab.util` | `esc, fmt, ls{get,set}, inaraSys, inaraSt, spanshSys, copy, dist3` |

Global click handler: any element with `data-copy="text"` copies that text and flashes "copied".

SSE: `snapshot` replaces/merges every namespace and emits all; `state` sets one key and emits its namespace; `onerror` flips the header pill to "reconnecting" (EventSource reconnects by itself).

## Card definition

```js
Lab.card({
  id: 'loop',                 // must match module.json cards[].id
  requires: ['loop', 'journal'],
  header(el) {},              // optional, once: right-hand side of the title bar (buttons, links)
  mount(el) {},               // optional, once: build persistent DOM (canvas, inputs); el is the card body
  render(el, state) {},       // on every change of a required namespace; usually sets el.innerHTML
  unmount(el) {},             // optional: clear timers, remove window listeners
});
```

Lifecycle (`buildCard` / `unmountCard` in app.js): header -> mount -> subscribe -> first render. `unmountCard` releases the subscription, calls `unmount`, removes the section. Hiding a card unmounts it; showing re-mounts it fresh. Moving a card in the grid moves the DOM node, so mounted state (canvases, inputs) survives drags.

Render errors are caught and shown as a `.render-error` banner at the top of the body; the body is not replaced, so a mounted canvas survives a bad render.

Cards are `section.card` with classes `cN` for grid span (N = 2..12 of a 12-column grid). Below 1200 px small cards snap to 6 columns and wide ones to 12; below 760 px everything is 12 and the drag/resize handles are hidden.

## Layout engine

State: `layout = {order[], spans{}, hidden[], collapsed[], locked}` in `localStorage.layout.v1`. `orderedCards()` = saved order first (ignoring unknown ids), then any new cards in manifest order. `spanOf(c)` = saved span or manifest span or 3.

Gestures share one `gesture` object (`{move(e), end()}`) and window-level listeners:

- `pointermove` (capture): if the primary button is no longer down, end the gesture; else forward.
- `pointerup` (capture): forward the final position then end.
- `pointercancel`, window `blur`, `Escape`: end.

Why window-level: a card is re-inserted in the DOM while being dragged, and browsers drop pointer capture on the moved element. Element-level listeners went silent mid-drag and the drag never ended (it looked like a hang).

Drag (`wireDrag`): `pointerdown` on the `h2` (not on buttons/links/inputs/the `.right` slot, not when locked or on mobile) creates a light ghost (`div.card.ghost`, title only, `position:fixed`, `pointer-events:none`, moved with `transform`), dims the card (`.dragging`), and sets `body.no-select`. `place()` runs at most once per animation frame: `elementFromPoint` -> nearest `#grid > .card` -> insert before/after depending on which half of the target the pointer is in. On end: the last position is applied synchronously, ghost removed, `layout.order` saved, `Lab.relayout()`.

Resize (`wireResize`): `pointerdown` on `.resize` (bottom-right corner). Column width = `grid.clientWidth / 12`; new span = clamp(2..12, start + round(dx / col)); applied per frame; saved on end. Double-click toggles 12 and the manifest default.

Collapse: toggles `.collapsed` (hides body and resize handle). Hide: `hideCard(id)` unmounts and records in `hidden`. Show: `showCard(id)` builds the card and inserts it at its position among currently mounted cards.

Menu (`renderMenu`): lock checkbox, export (layout JSON to clipboard), import (prompt), presets (buttons), saved layouts (name input + save, chips with load/delete, stored in `localStorage.layouts.v1`), and a checkbox per card. `applyLayout(l, name)` replaces the layout and remounts everything.

Presets are plain objects `{order, spans, hidden}` in `PRESETS` in app.js. Cards not in `order` follow in manifest order; cards in `hidden` are not mounted.

UI health: a `requestAnimationFrame` loop records the worst frame gap every 2 s; above 120 ms the footer shows "UI stalled N ms" in red. Note Chrome throttles rAF to 1 Hz in background tabs, so a stall right after switching back to the tab is expected.

## Map layers

The map card (`modules/map/web/card.js`) draws every registered layer. Register from any card script:

```js
Lab.map.addLayer('mining', {
  label: 'hotspots',            // legend text and toggle button label
  color: '#e6b422',             // legend swatch
  z: 3,                         // draw order, higher on top (ship is 10, carrier 9, history 0)
  points: S => [{ name, x, y, z, r, color, sub, kind?, label?, selected?, copy?, onClick? }],
  lines:  S => [{ a: {x,z}, b: {x,z}, color, dash?, label? }],   // optional
});
```

Point fields: `r` radius in px; `sub` tooltip second line; `label: true` always draws the name; `kind: 'visited'` draws the glow-dot style; `selected` draws a ring; `onClick` runs on click (default copies `copy || name`). Layers can be toggled from the map controls; `enabled: false` hides a layer.

Projection: galactic X to the right, Z up (toward the core), Y ignored except in tooltips. `M = {cx, cz, scale}` is the view; `toScreen(p)` maps. `fit(S, local)` frames all points (or only non-history, non-target points when `local`). The map refits when history loads unless the user has panned or zoomed (`M.userMoved`).

Rendering: a 2400x1400 starfield is generated once into an offscreen canvas and blitted with a slight parallax; the route trail from `/api/history` is drawn newest-brightest; then layer lines; then points sorted by layer `z`. A 120 ms interval redraws (for the ship pulse) while the tab is visible and the canvas is connected. `draw()` returns early when the canvas is under 2 px (collapsed/hidden).

History fetch: `loadHistory()` refetches when the range selector or `history.version` changes.

## Styling

`web/style.css` defines tokens on `:root` (`--bg, --card, --line, --fg, --muted, --accent (HUD orange), --accent-2 (cyan), --ok, --warn, --bad, --link`). Reusable classes: `.big, .muted, .ok/.warn/.bad/.accent, .grid2 (.k/.v), .note, table/.num, .tag(.rare/.ok/.bad/.warn), .bar > i, .row, .mini, .primary, .feed, label.chk, .links`.

Dark theme only. No light theme is planned; it is a cockpit tool.
