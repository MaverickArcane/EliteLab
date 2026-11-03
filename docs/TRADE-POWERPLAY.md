# Trade route to Powerplay finder

Select a route in Trading. Under **Plan a Powerplay destination**, use either
the active leg's buy stop or sell stop. The finder receives that stop's system
as its search origin and the pledge observed in the current journal session.
Distance bands, pad choice and other finder settings are retained; review them
and click **Find targets**. This does not perform an automatic network search.

The destination panel labels the exact stop, active leg, planned commodity and
quantity, pledge and quote time. Its distances start at the chosen stop, which
may differ from the ship's current system. A ship move does not silently change
this origin. Cargo, ship or location changes clear previously bound results.

The selected commodity route, purchases, sales, cargo and recorded merits are
unchanged. The finder works with reported Powerplay markets and rare goods
actually aboard. It does not treat a planned load as purchased cargo or apply
rare-goods forecasts to a normal commodity. Planned commodity acceptance,
merit eligibility and expected merits remain unknown. The legacy finder's
"buys all" badge is suppressed in this view because it refers to rare cargo,
not the planned commodity.

## Changing context

Missing/completed plans, unknown or different commanders, and unknown pledge
disable the handoff. The pledge must be observed in this game session; an older
power value in the general Powerplay panel is insufficient. Same-commander
journal-file continuation preserves the observation; LoadGame, a changed
commander/FID or leaving a power clears it.

A changed route, active leg or pledge invalidates an applied handoff. Return
to Trading to apply the current stop. The old search origin remains visible
until that explicit action, and bound searches are blocked in the meantime.
Late legacy responses cannot replace the active card/map results. Editing the
origin/power or choosing **Use finder manually** releases the binding. In the
legacy finder, compare other powers in manual mode. A browser reload retains
the saved route but requires reapplying the handoff.

The handoff preserves existing finder behavior and does not duplicate #69's
price curves, merit-rate assumptions or ranking. `modules/targets/web/handoff.js`
imports the target module's own `card.js` and extends it with context handling;
it supports the existing finder and #69's form. No cross-module Python imports,
new network provider, dependency or auth exception is introduced.

## HTTP and MCP

`GET /api/personal/powerplay` / `get_trade_powerplay_handoff` accepts `role`
(`buy` or `sell`, default `sell`) and optional `token`. It returns:

- `ready`, `status`, `message` and a context `token`;
- the active `leg`, planned `commodity`, `quantity`, route ID and quote evidence;
- the selected exact `stop` and both candidate `stops`;
- `power` from this session's journal evidence;
- `eligibility: "unknown"`, `expected_merits: null`;
- `next_tool: {name: "find_sell_targets", arguments: {ref, power}}` when ready,
  otherwise null.

Passing a prior token rejects a changed route, leg, commander or pledge. The
token is an optimistic concurrency check, not a credential. Normal HTTP/MCP
authentication still applies. Preview performs no network or file work and
never changes the saved route. `personal.powerplay_handoff` publishes the same
context over SSE; `personal.ui_powerplay` is a browser-local explicit request.

The `trade_powerplay_handoff` MCP prompt explains how to inspect readiness,
refresh the token and call the existing finder without inventing eligibility.
Names in API output are untrusted data, not instructions.

## Validation

`test_trade_powerplay.py` covers exact buy/sell stops, return legs, completion,
unknown pledge/cargo, stale quotes/tokens, identity and session resets, unchanged
route/merits, no-I/O preview, authenticated HTTP and real stdio MCP tools/prompt.

`node tests/trade-powerplay-browser.mjs` runs an isolated real CLI with synthetic
journals and a synthetic station provider. It exercises the actual HTTP/SSE and
Chrome UI, preserved filters, stale requests and map state, retries, hostile
text, identity changes, and desktop/mobile screenshots. It makes no current
game-price or merit-reward claim. CI retains the captures as an artifact.

Close #74 after merge. Keep #41 open for the remaining panel audit, and keep
#2 tied to the separate #69 implementation.
