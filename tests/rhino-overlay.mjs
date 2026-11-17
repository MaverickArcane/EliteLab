/* Direction semantics: north wrap, unknown telemetry, body identity and arrival. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
const source = fs.readFileSync(new URL('../modules/rhino/web/overlay.js', import.meta.url), 'utf8');
const {guidance} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

const now = Date.now();
const state = {
  selected_site: {system: 'Test', body: 'Test A 1', travel: {stage: 'surface'}},
  position: {system: 'Test', body: 'Test A 1', latitude: 0, longitude: 0, timestamp: new Date(now).toISOString(), heading: 350},
  navigation: {distance_m: 1500, bearing: 10},
};
const view = (patch = {}, options = {}) => guidance({...state, ...patch}, {now, ...options});
assert.equal(view().turn, 20);
assert.equal(view().title, 'Turn right 20\u00b0');
assert.equal(view({position: {...state.position, heading: 10}, navigation: {distance_m: 1500, bearing: 350}}).turn, -20);
assert.equal(view({navigation: {distance_m: 100, bearing: 354}}).mode, 'aligned');
assert.equal(view({position: {...state.position, heading: 360}, navigation: {distance_m: 100, bearing: 0}}).mode, 'aligned');
assert.equal(view({position: {...state.position, heading: null}}).mode, 'bearing');
assert.equal(view({position: {...state.position, heading: null}}).turn, null);
assert.equal(view({position: {...state.position, heading: NaN}}).turn, null);
assert.equal(view({position: {...state.position, heading: -1}}).turn, null);
assert.equal(view({navigation: {distance_m: 24.9, bearing: 200}}).mode, 'arrived');
assert.equal(view({navigation: {distance_m: 0, bearing: null}}).turn, null);
assert.equal(view({navigation: {distance_m: 25, bearing: 200}}).mode, 'steering');
assert.equal(view({navigation: {distance_m: null, bearing: 200}}).distance, null);
assert.equal(view({navigation: {distance_m: 200, bearing: null}}).turn, null);
assert.equal(view({position: {...state.position, latitude: null}}).turn, null);
assert.equal(view({position: {...state.position, body: 'Test A 2'}}).turn, null);
assert.equal(view({position: {...state.position, system: 'Other'}}).turn, null);
assert.equal(view({position: {...state.position, body: 'test a 1'}}).turn, 20);
assert.equal(view({selected_site: {...state.selected_site, travel: {stage: 'system'}}}).status, 'IN TRANSIT');
assert.equal(view({selected_site: null}).turn, null);
assert.equal(view({}, {connected: false}).distance, null);
assert.equal(view({}, {connected: false}).status, 'OFFLINE');
for (const timestamp of [null, 'bad', new Date(now - 121000).toISOString(), new Date(now + 6000).toISOString()]) {
  assert.equal(view({position: {...state.position, timestamp}}).turn, null);
}
console.log('Rhino overlay guidance passed: wrap, alignment, arrival, absent/invalid heading, stale/future GPS, body/system and disconnect.');
