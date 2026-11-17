/* A read-only, always-on-top surface navigator. No game input or rig telemetry. */
const finite = Number.isFinite;
const degrees = n => ((n % 360) + 360) % 360;
const headingText = n => finite(n) ? String(Math.round(degrees(n)) % 360).padStart(3, '0') + '\u00b0' : '--';
const distanceText = n => n < 1000 ? `${Math.round(n)} m` : `${(n / 1000).toFixed(n < 10000 ? 2 : 1)} km`;
const same = (a, b) => typeof a === 'string' && typeof b === 'string' && a.toLowerCase() === b.toLowerCase();

export function guidance(state = {}, {now = Date.now(), connected = true} = {}) {
  const site = state.selected_site, p = state.position || {}, nav = state.navigation || {};
  const result = {mode: 'waiting', title: 'Choose a mining spot', detail: 'Select Navigate in Rhino > Locations.',
    bearing: null, heading: null, turn: null, distance: null, status: 'WAITING'};
  if (!connected) return {...result, status: 'OFFLINE', title: 'Connection lost', detail: 'Reconnecting to EliteLab. Directions paused.'};
  if (!site) return result;
  const stage = site.travel?.stage;
  if (stage === 'system') return {...result, title: `Travel to ${site.system}`, detail: `Then approach ${site.body}.`, status: 'IN TRANSIT'};
  const age = (now - Date.parse(p.timestamp)) / 1000;
  const fresh = finite(age) && age >= -5 && age <= 120;
  if (!fresh) return {...result, title: 'Waiting for surface GPS', detail: `Approach ${site.body}. Directions resume with a fresh position.`};
  if (!same(p.system, site.system) || !same(p.body, site.body)) {
    return {...result, title: 'Approach the target body', detail: `${site.system} / ${site.body}`, status: 'IN TRANSIT'};
  }
  if (!finite(p.latitude) || !finite(p.longitude) || !finite(nav.distance_m) || nav.distance_m < 0) {
    return {...result, title: 'Surface position unavailable', detail: nav.reason || 'Waiting for surface coordinates and planetary radius.'};
  }
  result.distance = nav.distance_m;
  result.heading = finite(p.heading) && p.heading >= 0 && p.heading <= 360 ? degrees(p.heading) : null;
  if (nav.distance_m < 25) return {...result, mode: 'arrived', title: 'At saved spot', detail: 'Within 25 m. Slow down and scan nearby.', status: 'NEAR TARGET'};
  result.bearing = finite(nav.bearing) && nav.bearing >= 0 && nav.bearing <= 360 ? degrees(nav.bearing) : null;
  if (result.bearing === null) return {...result, title: 'Bearing unavailable', detail: nav.reason || 'Waiting for a surface bearing.'};
  if (result.heading === null) return {...result, mode: 'bearing', title: `Steer to ${headingText(result.bearing)}`, detail: 'Match the in-game compass. Vehicle heading unavailable.', status: 'BEARING ONLY'};
  result.turn = ((result.bearing - result.heading + 540) % 360) - 180;
  const angle = Math.abs(result.turn), aligned = angle <= 5;
  return {...result, mode: aligned ? 'aligned' : 'steering', status: 'SURFACE GPS',
    title: aligned ? 'On course' : `Turn ${result.turn < 0 ? 'left' : 'right'} ${Math.round(angle)}\u00b0`,
    detail: nav.distance_m < 100 ? 'Close to the saved point. Slow down and scan.' : 'Direct surface bearing. Choose a clear path.'};
}

export function mountOverlay(doc) {
  doc.title = 'Rhino navigation | EliteLab';
  const style = doc.createElement('link');
  style.rel = 'stylesheet'; style.href = new URL('./overlay.css', import.meta.url).href;
  doc.head.append(style);
  doc.body.innerHTML = `<main class="hud" data-mode="waiting">
    <header><span class="brand"><i></i> RHINO <span>/ NAV</span></span><button data-compact aria-pressed="false" title="Toggle compact view">Compact</button></header>
    <section class="destination"><div class="eyebrow" data-mineral>MINING DESTINATION</div><h1 data-site>No target selected</h1><p data-body></p></section>
    <section class="guidance">
      <div class="dial" aria-hidden="true"><svg viewBox="0 0 120 120">
        <circle class="dial-ring" cx="60" cy="60" r="47"/><path class="ticks" d="M60 9v8 M111 60h-8 M60 111v-8 M9 60h8 M24 24l5 5 M96 24l-5 5 M96 96l-5-5 M24 96l5-5"/>
        <text class="ahead" x="60" y="28">FWD</text>
        <g data-arrow hidden><path class="arrow" d="M60 33L77 78 60 68 43 78Z"/></g>
        <circle class="arrival" cx="60" cy="60" r="15"/><path class="arrival-check" d="m52 60 6 6 11-13"/>
        <text class="no-heading" x="60" y="70">--</text>
      </svg></div>
      <div class="instruction"><div class="signal" data-status>WAITING</div><h2 data-instruction>Choose a mining spot</h2><div class="distance"><strong data-distance>--</strong><span>to saved point</span></div></div>
    </section>
    <div class="readouts"><div><span>TARGET</span><strong data-bearing>--</strong></div><div><span>HEADING</span><strong data-heading>--</strong></div><div><span>RHINO HOLD</span><strong data-hold>--</strong></div></div>
    <p class="detail" data-detail role="status"></p><p class="warning" data-warning hidden></p>
    <footer><span>ELITELAB</span><span>Drag title bar to move</span></footer>
  </main>`;
  const root = doc.querySelector('.hud'), nodes = {};
  for (const name of ['site', 'body', 'mineral', 'status', 'instruction', 'distance', 'bearing', 'heading', 'hold', 'detail', 'warning', 'arrow']) {
    nodes[name] = root.querySelector(`[data-${name}]`);
  }
  const compact = root.querySelector('[data-compact]');
  compact.addEventListener('click', () => {
    const active = root.classList.toggle('compact');
    compact.setAttribute('aria-pressed', String(active)); compact.textContent = active ? 'Expand' : 'Compact';
    try { doc.defaultView.resizeTo(doc.defaultView.outerWidth, active ? 242 : 390); } catch { /* Browser controls sizing. */ }
  });
  return (state, options) => {
    const model = guidance(state, options), site = state?.selected_site;
    root.dataset.mode = model.mode;
    const write = (key, value) => { if (nodes[key].textContent !== value) nodes[key].textContent = value; };
    write('site', site?.name || 'No target selected'); nodes.site.title = site?.name || '';
    write('body', site?.body || 'Choose a spot in the Rhino dashboard');
    write('mineral', site ? [site.commodity, site.pml ? `PML ${site.pml}` : 'SURFACE'].filter(Boolean).join(' / ') : 'MINING DESTINATION');
    write('status', model.status); write('instruction', model.title); write('detail', model.detail);
    write('distance', model.distance === null ? '--' : distanceText(model.distance));
    write('bearing', headingText(model.bearing)); write('heading', headingText(model.heading));
    const hold = state?.cargo?.rhino;
    write('hold', options?.connected === false || !finite(hold?.count) ? '--' : `${hold.count}${finite(hold.capacity) ? '/' + hold.capacity : ''} t`);
    nodes.hold.title = 'Last reported cargo aboard the Rhino';
    nodes.arrow.toggleAttribute('hidden', model.turn === null);
    if (model.turn !== null) nodes.arrow.setAttribute('transform', `rotate(${model.turn} 60 60)`);
    const warning = site?.availability === 'reported_depleted' ? 'Reported depleted - check the deposit.' : site?.verification === 'unconfirmed' ? 'Unconfirmed location - verify on arrival.' : '';
    write('warning', warning); nodes.warning.hidden = !warning;
    return model;
  };
}

let overlayWindow = null;
let opening = false;

export async function openOverlay() {
  if (overlayWindow && !overlayWindow.closed) { overlayWindow.focus(); return overlayWindow; }
  if (opening) return;
  if (!window.documentPictureInPicture?.requestWindow) {
    throw new Error('The overlay needs a browser with Document Picture-in-Picture, such as current Chrome or Edge. Open EliteLab on localhost in that browser.');
  }
  opening = true;
  try {
    const win = await window.documentPictureInPicture.requestWindow({width: 370, height: 390, disallowReturnToOpener: true});
    overlayWindow = win;
    const render = mountOverlay(win.document);
    let state = {}, connected = false, stopped = false, pending = false, lastSuccess = 0, request = null;
    const draw = () => render(state, {connected: connected && Date.now() - lastSuccess < 5000});
    const poll = async () => {
      if (stopped || pending) return;
      pending = true;
      const controller = new AbortController(); request = controller;
      const timeout = win.setTimeout(() => controller.abort(), 4000);
      try {
        const response = await win.fetch('/api/rhino', {cache: 'no-store', signal: controller.signal});
        if (!response.ok) throw new Error('Rhino data unavailable');
        const next = await response.json();
        if (!stopped) { state = next; connected = true; lastSuccess = Date.now(); }
      } catch { connected = false; }
      finally { win.clearTimeout(timeout); pending = false; if (!stopped) draw(); }
    };
    // Timers belong to the visible overlay, independent of dashboard RAF or card mounting.
    draw(); poll();
    const refresh = win.setInterval(poll, 1000), freshness = win.setInterval(draw, 500);
    win.addEventListener('pagehide', () => {
      stopped = true; request?.abort(); win.clearInterval(refresh); win.clearInterval(freshness);
      if (overlayWindow === win) overlayWindow = null;
    }, {once: true});
    return win;
  } catch (error) {
    if (overlayWindow && !overlayWindow.closed) overlayWindow.close();
    overlayWindow = null;
    throw new Error(`Could not open the navigation overlay. ${error.message || 'Try the launch button again.'}`);
  } finally { opening = false; }
}
