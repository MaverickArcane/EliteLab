# Architecture

EliteLab is a small core plus self-contained modules. The core owns the plumbing; every feature, including reading the journal, is a module.

```
elitelab/core/
  config.py     paths, ports, env overrides
  bus.py        EventBus: on("journal.*", fn) / emit(name, payload)
  store.py      Store: namespaced state, versioned, change notifications
  services.py   cached JSON fetcher + Spansh/EDSM helpers shared by all modules
  http.py       Router (routes double as AI tools), SSE /events, static files
  loader.py     discovers modules/, resolves dependency order, calls setup()
  watcher.py    replays recent journals, then tails for new lines + snapshot files
  __init__.py   Core: wires everything, built-in routes (/api/state, /api/schema ...)
elitelab/mcp.py Model Context Protocol server: proxies the HTTP API as MCP tools
modules/<name>/ module.json + module.py + web/*.js
web/            shell: index.html, app.js (Lab runtime), style.css
```

## Data flow

```
game journal ──watcher──▶ bus: journal.<Event>, journal.file.<Name>
                              │
          modules subscribe ──┤── store.set("ns", key, value) ──▶ bus: state.<ns>.<key>
                              │                                 └─▶ SSE /events ──▶ browser Lab.state
          modules register ───┴── http.route(path, fn, tool=...) ──▶ /api/*  and  MCP tools
```

1. **Watcher** replays the last `ELITELAB_RECENT_JOURNALS` files (events carry `_replay: true`), emits `journal.replay.done`, then polls the newest file every second. Snapshot files (`Status.json`, `Cargo.json`, `Market.json`...) are emitted as `journal.file.<Name>` whenever their mtime changes.
2. **Modules** fold events into their own namespace with `core.store.update(ns, {...})`. Writes that don't change a value are no-ops, so modules can publish freely.
3. **Store** changes fan out two ways: `state.<ns>.<key>` on the bus (other modules react; the loop module recomputes when `state.journal.cargo` changes) and the SSE stream (browser cards re-render).
4. **Routes** registered with a `tool` name appear in `/api/schema`; the MCP server turns that list into tools. There is one source of truth for "what can an AI do here".

## Dependency rules

- A module declares `requires` (namespaces it reads) and `provides` (namespaces it writes) in `module.json`. The loader topologically sorts and refuses to start on a missing or circular dependency.
- Data modules never import UI modules. The map depends on `journal` and `history`, and *other* modules add layers to it from their own card scripts (`Lab.map.addLayer`). The map never knows about loops or targets.
- Modules talk through the store and the bus, never by importing each other's Python. If you need another module's data, read its namespace.

## Browser runtime (`web/app.js`)

`window.Lab` is tiny:

- `Lab.state[ns]` mirrors the server store, fed by `/events`. Client-only namespaces (like `targets` search results) live alongside.
- `Lab.on(ns | [ns...], fn)` subscribes; emits are batched per animation frame.
- `Lab.card({ id, requires, header?, mount?, render })` registers a card; the shell mounts cards in the order the manifests say and re-renders when a required namespace changes.
- `Lab.map.addLayer(id, { label, color, z, points(S), lines(S) })` plots on the star map.
- `Lab.api(path, params)`, `Lab.post(path, body)`, `Lab.util.{esc, fmt, inaraSys, ...}`.

No framework, no build. Cards render by replacing their body's innerHTML; the map keeps a canvas across renders via `mount`.

## Threading

The watcher runs in one background thread and emits synchronously, so module handlers run there; keep them fast and never block on the network inside a handler (the loop module fetches coordinates in its own thread). HTTP requests run in the server's thread pool. The store is lock-protected; everything else is single-writer.

## Why stdlib only

A friend can `git clone` and double-click a `.cmd`. The MCP server is also dependency-free so Claude Code can launch it with a bare `python`. If the project ever needs websockets, async or a real template engine, the module contract (bus, store, routes) stays the same.
