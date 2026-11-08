# Architecture

The release adds an independent cargo-selling module and reuses the existing
party transport for group mining. Long PTN/cargo searches return jobs and publish
status through the store/SSE; tools poll through the same bounded HTTP contract.
Card manifests can name their external sources. See [State](STATE.md) and
[API](API.md) for additions; no hosted service, dependency or frontend build step
is introduced.

Source setup uses `Setup EliteLab.cmd` or `setup.sh`, then the existing instance
guard and serve/restart loop. `serve --setup --open-browser` chooses `/setup/`;
`--no-browser` keeps setup automation headless. `Core.start` accepts an optional
`browser_path` (default `/`). Browser launch waits for a health response with
`ready: true` and this process's PID, uses the configured auth token for that
probe, and is cancelled on shutdown. A repeat setup launch reuses the healthy
instance and opens its setup URL. A marked Windows portable bundle uses
`elitelab.window` to launch a known Chromium-family browser in app mode with a
separate profile under the configured data directory; an explicit browser setting
wins, and launch failure falls back to the normal browser. Source launches retain
the normal browser behavior.
The Windows bundle also provides a WScript entry point that starts a `pythonw`
supervisor without a console. It writes child output to the data folder, runs setup
on first launch, and restarts the child on exit 75 without opening a second window.
The notification-area menu opens the dashboard or setup and requests a graceful
shutdown. Before any tray action, the supervisor checks its own live child PID,
the guarded instance record and a ready loopback health response; it does not
send credentials to other hosts or shut down a different instance. The dashboard
Quit control remains available, and closing the window does not stop the server.
Repeated rapid restart requests are bounded. An opt-in tray action stores one
per-user Windows Run value pointing to this bundle's launcher, with a quoted
system WScript path. A conflicting value is not replaced; uninstall removes
only an exact match. No entry is created by default. The source launchers remain
available. The Windows installer stages the portable bundle,
uses a per-user destination, and holds the same instance lock while copying or
uninstalling. It refuses a nonempty unrelated target and leaves untracked data
and user settings in place. A custom instance directory must be the same
absolute path for installer and server. CI builds a test-ID installer and checks
install, upgrade, launch, guard behavior and uninstall in an isolated directory.
HTTP binding uses the bound address as the server name without a reverse-DNS
lookup, so a slow resolver cannot stall local setup. Windows exclusive-port
ownership is preserved.

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
game journal --watcher--> bus: journal.<Event>, journal.file.<Name>
                             |
         modules subscribe --+-- store.set("ns", key, value) --> bus: state.<ns>.<key>
                             |                                 +-> SSE /events --> browser Lab.state
         modules register ---+-- http.route(path, fn, tool=...) --> /api/*  and  MCP tools
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

**Layout** is owned by the shell, not by modules. Cards can be dragged by their title bar to reorder (pointer events, live DOM reordering, a ghost follows the pointer), resized by the corner handle in grid columns (2 to 12), collapsed, or hidden. The Layout menu lists every card, locks the layout, resets it, and exports/imports it as JSON. State lives in `localStorage` under `layout.v1` as `{order, spans, hidden, collapsed, locked}`; manifests supply defaults for anything not overridden. Moving a card moves its DOM node, so a card's `mount` state (the map canvas) survives.

## Threading

The HTTP handler closes abandoned keep-alive connections on peer reset, abort
or broken pipe, including Windows browser reloads before a new request line.
Other exceptions keep their normal error handling and diagnostics.

The watcher runs in one background thread and emits synchronously, so module handlers run there; keep them fast and never block on the network inside a handler (the loop module fetches coordinates in its own thread). HTTP requests run in the server's thread pool. The store is lock-protected; everything else is single-writer.

## Why stdlib only

A friend can `git clone` and double-click a `.cmd`. The MCP server is also dependency-free so Claude Code can launch it with a bare `python`. If the project ever needs websockets, async or a real template engine, the module contract (bus, store, routes) stays the same.
