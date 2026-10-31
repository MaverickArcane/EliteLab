# Writing a module

A module is one folder under `modules/`:

```
modules/mining/
  module.json      manifest
  module.py        setup(core, module)
  web/card.js      optional UI card(s) and map layers
```

## 1. Manifest

```json
{
  "name": "mining",
  "version": "1.0.0",
  "description": "Tracks prospector results and refinery output.",
  "requires": ["journal"],
  "provides": ["mining"],
  "order": 80,
  "cards": [ { "id": "mining", "title": "Mining", "span": 4, "script": "card.js", "order": 46 } ]
}
```

A module may set `"cards": []` when it has no card, and may serve its own static folder with `core.http.mount(prefix, directory)` (the `setup` module mounts `/setup/` this way).

`requires` are namespaces (not module names). `provides` is the namespace you will write. `order` only affects card placement when dependencies don't force an order. `span` is grid columns out of 12.

## 2. Python

```python
NS = "mining"

def setup(core, module):
    st = {"prospected": 0, "last": None}

    def on_prospect(name, ev):
        st["prospected"] += 1
        st["last"] = {"content": ev.get("Content_Localised"), "materials": ev.get("Materials")}
        core.store.update(NS, st)            # pushed to the browser and to state.mining.* on the bus

    core.bus.on("journal.ProspectedAsteroid", on_prospect)
    core.store.update(NS, st)                # publish initial state

    core.http.route("/api/mining", lambda q: core.store.get(NS),
                    tool="get_mining_status", module=module.name,
                    description="Prospector results this session.")
```

What you get on `core`:

| Member | Use |
|---|---|
| `core.bus.on(pattern, fn)` | `fn(name, payload)`; patterns like `journal.*`, `state.journal.cargo`, `journal.file.Cargo` |
| `core.bus.emit(name, payload)` | emit your own events for other modules |
| `core.store.set/update/get` | your namespace in, anyone's namespace out |
| `core.http.route(path, fn, tool=, description=, params=, method=)` | `fn(query_dict)` returns JSON; `params` is `{name: {type, description, default/required, enum}}` and becomes the tool's input schema |
| `core.services.fetch_json(url, body=None, ttl=600)` | cached HTTP; also `spansh_stations`, `spansh_system`, `edsm_coords` |
| `core.read_data / write_data(value, "file.json")` | persistent JSON under the data dir |
| `core.log` | a logger |

Rules: write only to your own namespace; don't block in bus handlers (spawn a thread for network calls); accept `_replay: true` events like live ones (that is how state is rebuilt at startup).

## 3. Card

```js
(() => {
  const { esc, fmt } = Lab.util;
  Lab.card({
    id: 'mining', requires: ['mining'],
    header(h) { h.innerHTML = `<button class="mini" id="m-reset">reset</button>`; },
    render(el, S) {
      const m = S.mining || {};
      el.innerHTML = `<div class="big">${fmt(m.prospected)} prospected</div>
        <div class="note">${esc(m.last?.content || '')}</div>`;
    },
  });
  // optional: plot something on the star map
  Lab.map.addLayer('mining', { label: 'hotspots', color: '#e6b422', z: 3, points: S => (S.mining?.hotspots || []) });
})();
```

`render` runs whenever any namespace in `requires` changes. Use `mount(el)` for one-time DOM (canvases, event listeners). Always `esc()` journal or API text.

## 4. Make it an AI tool

That already happened: the route with `tool="get_mining_status"` is now in `/api/schema`, listed by `python -m elitelab tools`, callable with `python -m elitelab call get_mining_status`, and offered to any MCP client. Write the `description` for a model, not a human: say what the data is good for and what the parameters mean.

## 5. Test it

```
python -m elitelab modules        # dependency order, cards
python -m elitelab serve -v       # watch the log
python -m elitelab call get_mining_status
```

Disable a module without deleting it: `ELITELAB_DISABLE=mining`.
