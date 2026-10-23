/* EliteLab front-end. Plain JS, no build step.
   Sections: helpers · state polling · map · targets · loop · misc UI */
'use strict';

// ---------------------------------------------------------------- helpers
const $ = id => document.getElementById(id);
const fmt = n => (n == null || isNaN(n)) ? '—' : Number(n).toLocaleString();
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const inaraSys = n => `https://inara.cz/elite/starsystem/?search=${encodeURIComponent(n)}`;
const inaraSt = n => `https://inara.cz/elite/station/?search=${encodeURIComponent(n)}`;
const spanshSys = n => `https://spansh.co.uk/search/${encodeURIComponent(n)}`;
const copy = t => navigator.clipboard && navigator.clipboard.writeText(t);
const dist3 = (a, b) => Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);

document.body.addEventListener('click', e => {
  const b = e.target.closest('[data-copy]');
  if (b) { copy(b.dataset.copy); const t = b.textContent; b.textContent = 'copied'; setTimeout(() => b.textContent = t, 900); }
});

// ---------------------------------------------------------------- static data
const LOOP = [ // {system, station, rares (display), keys (journal internal names), Ly from Leesti}
  { system: 'Leesti', station: 'George Lucas (Coriolis)', rares: 'Leestian Evil Juice, Azure Milk', keys: ['leestianeviljuice', 'bluemilk'], ly: 0 },
  { system: 'Diso', station: 'Shifnalport (Orbis, 291 ls)', rares: 'Diso Ma Corn', keys: ['disomacorn'], ly: 2.6 },
  { system: 'Lave', station: 'Lave Station (Coriolis, 280 ls)', rares: 'Lavian Brandy', keys: ['lavianbrandy'], ly: 3.9 },
  { system: 'Uszaa', station: 'Guest Installation (Orbis, 4350 ls)', rares: 'Uszaian Tree Grub', keys: ['uszaiantreegrub'], ly: 7.6 },
  { system: 'Zaonce', station: 'Ridley Scott (Orbis, 389 ls)', rares: 'Leathery Eggs', keys: ['leatheryeggs'], ly: 8.1 },
  { system: 'Orrere', station: 'Sharon Lee Free Market (Orbis, 962 ls)', rares: 'Orrerian Vicious Brew', keys: ['orrerianviciousbrew'], ly: 9.4 },
];

// ---------------------------------------------------------------- app state
const app = {
  state: null, lastPower: undefined, targets: [], selected: null,
  coords: {},              // name -> {x,y,z} from EDSM
  map: { cx: 0, cz: 0, scale: 2, drag: null, pts: [] },
};

// ---------------------------------------------------------------- polling
async function refresh() {
  try {
    const r = await fetch('/api/state'); const s = await r.json(); app.state = s;
    $('h-live').textContent = 'live · ' + (s.last_event_time || '').replace('T', ' ').replace('Z', ' UTC'); $('h-live').classList.add('live');
    $('h-cmdr').textContent = s.cmdr || '—';
    $('h-ship').textContent = [s.ship, s.ship_name, s.ship_ident].filter(Boolean).join(' · ') || '—';
    $('h-credits').textContent = fmt(s.credits); $('h-ver').textContent = s.game_version || '—';

    $('loc-system').textContent = s.system || '—';
    $('loc-station').textContent = s.docked ? `Docked at ${s.station} (${s.station_type || ''})` : (s.status.supercruise ? 'In supercruise' : 'In normal space');
    $('loc-power').textContent = s.system_power || 'none'; $('loc-state').textContent = s.system_power_state || 'Unoccupied';
    $('loc-fuel').textContent = s.status.fuel != null ? s.status.fuel.toFixed(1) + ' t' : '—';
    $('loc-legal').textContent = s.status.legal || '—'; $('loc-legal').className = 'v ' + ((s.status.legal && s.status.legal !== 'Clean') ? 'bad' : 'ok');
    $('loc-powers').textContent = s.system_powers.length ? 'Powers present: ' + s.system_powers.join(', ') : '';
    if (s.system) $('loc-links').innerHTML = `<button class="mini" data-copy="${esc(s.system)}">copy</button> <a href="${inaraSys(s.system)}" target="_blank">Inara</a> <a href="${spanshSys(s.system)}" target="_blank">Spansh</a>`;

    if (s.power) {
      $('pp-power').textContent = s.power; $('pp-rank').textContent = s.rank ?? '—'; $('pp-merits').textContent = fmt(s.merits);
      $('pp-time').textContent = s.time_pledged != null ? (s.time_pledged / 86400).toFixed(1) + ' days' : '—'; $('pp-hint').textContent = '';
    } else {
      $('pp-power').textContent = 'Unpledged'; $('pp-rank').textContent = '—'; $('pp-merits').textContent = '—'; $('pp-time').textContent = '—';
      $('pp-hint').textContent = 'Pledge at any station with a Powerplay contact. Use "Compare powers" below to see whose acquisition systems are closest.';
    }
    $('pp-cycle').textContent = nextThursday();

    const cap = s.cargo_capacity; $('cargo-cap').textContent = `${fmt(s.cargo.count)} / ${fmt(cap)} t`;
    $('cargo-bar').style.width = (cap ? Math.min(100, 100 * (s.cargo.count || 0) / cap) : 0) + '%';
    $('cargo-body').innerHTML = s.cargo.items.length ? s.cargo.items.map(i => `<tr><td>${esc(i.name)} ${i.rare ? '<span class="tag rare">rare</span>' : ''} ${i.stolen ? '<span class="tag bad">stolen</span>' : ''}</td><td class="num">${fmt(i.count)}</td></tr>`).join('') : '<tr><td class="muted">Empty hold</td></tr>';

    $('mkt-where').textContent = s.market.station ? `${s.market.station}, ${s.market.system}` : '';
    $('mkt-body').innerHTML = s.market.rares_in_stock.length ? s.market.rares_in_stock.map(r => `<tr><td>${esc(r.name)}</td><td class="num">${fmt(r.buy)}</td><td class="num">${fmt(r.stock)}</td></tr>`).join('') : `<tr><td class="muted" colspan="3">No rares in stock at ${esc(s.market.station || 'the last market')}.</td></tr>`;

    const c = s.carrier;
    if (c) {
      $('fc-name').textContent = `${c.name || ''} ${c.callsign ? '(' + c.callsign + ')' : ''}`; $('fc-system').textContent = c.system || '—';
      $('fc-fuel').textContent = c.fuel != null ? c.fuel + ' / 1000' : '—'; $('fc-balance').textContent = fmt(c.balance);
      $('fc-space').textContent = c.free_space != null ? fmt(c.free_space) + ' t' : '—';
      $('fc-services').textContent = (c.services && c.services.length ? 'Services: ' + c.services.join(', ') : '') + (c.stats_time ? ` · stats from ${c.stats_time.slice(0, 10)}` : '');
    }

    $('mat-raw').textContent = fmt(s.materials.Raw); $('mat-man').textContent = fmt(s.materials.Manufactured); $('mat-enc').textContent = fmt(s.materials.Encoded);
    const md = s.materials_detail || {};
    $('mat-detail').innerHTML = ['Raw', 'Manufactured', 'Encoded'].map(k => `<div><b class="muted">${k}</b><br>${(md[k] || []).slice(0, 8).map(([n, c]) => `${esc(n)} <span class="muted">${c}</span>`).join(' · ')}</div>`).join('');

    $('feed-count').textContent = s.feed.length ? `last ${s.feed.length}` : '';
    $('feed').innerHTML = s.feed.length ? s.feed.map(f => `<div class="ev-${f.event}"><time>${(f.ts || '').slice(11, 16)}</time><span>${esc(f.text)}</span></div>`).join('') : '<div class="muted">No events yet this session.</div>';

    const sel = $('t-power');
    if (!sel.options.length) { s.powers.forEach(p => { const o = document.createElement('option'); o.value = o.textContent = p; sel.appendChild(o); }); sel.value = s.power || 'Edmund Mahon'; }
    else if (s.power && app.lastPower !== s.power) sel.value = s.power;
    app.lastPower = s.power;

    ensureCoords(); renderLoop(); drawMap();
  } catch (e) { $('h-live').textContent = 'server offline'; $('h-live').classList.remove('live'); }
}

function nextThursday() {
  const now = new Date(); const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 7, 0, 0));
  while (d.getUTCDay() !== 4 || d <= now) d.setUTCDate(d.getUTCDate() + 1);
  const h = Math.round((d - now) / 36e5);
  return `${d.toLocaleDateString(undefined, { weekday: 'short' })} ${d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })} (${h} h)`;
}

// ---------------------------------------------------------------- coordinates
let coordsRequested = '';
async function ensureCoords() {
  const s = app.state; if (!s) return;
  const names = LOOP.map(l => l.system); if (s.carrier && s.carrier.system) names.push(s.carrier.system); if (s.system) names.push(s.system);
  const want = names.filter(n => !app.coords[n]); const key = want.sort().join('|');
  if (!want.length || key === coordsRequested) return;
  coordsRequested = key;
  try { const r = await fetch('/api/coords?names=' + encodeURIComponent(want.join('|'))); Object.assign(app.coords, await r.json()); renderLoop(); drawMap(); } catch (e) { }
}
function shipPos() {
  const s = app.state; if (!s) return null;
  if (s.star_pos) return { x: s.star_pos[0], y: s.star_pos[1], z: s.star_pos[2] };
  return s.system && app.coords[s.system] ? app.coords[s.system] : null;
}

// ---------------------------------------------------------------- map
const canvas = $('map'), ctx = canvas.getContext('2d'), tip = $('map-tip');
function mapPoints() {
  const pts = []; const s = app.state; if (!s) return pts;
  const ship = shipPos(); if (ship) pts.push({ kind: 'ship', name: s.system, ...ship, r: 6, color: '#ff8c2a', sub: s.docked ? `Docked at ${s.station}` : 'current position' });
  if (s.carrier && s.carrier.system && app.coords[s.carrier.system]) pts.push({ kind: 'carrier', name: `${s.carrier.name} (${s.carrier.callsign})`, ...app.coords[s.carrier.system], r: 5, color: '#2fd4ff', sub: s.carrier.system });
  LOOP.forEach(l => { if (app.coords[l.system]) { const st = loopStatus(l); pts.push({ kind: 'loop', name: l.system, ...app.coords[l.system], r: 4, color: st.done ? '#4e7a3a' : '#9be36b', sub: l.station + ' · ' + l.rares + (st.tons ? ` · ${st.tons} t aboard` : '') }); } });
  app.targets.forEach(t => { if (t.x != null) { const age = t.updated ? Math.round((Date.now() - Date.parse(t.updated)) / 864e5) : null; pts.push({ kind: 'target', name: t.system, x: t.x, y: t.y, z: t.z, r: 4, color: age == null ? '#4b6f9c' : (age > 60 ? '#8a4b5c' : (age > 14 ? '#c9a23a' : '#6fb3ff')), sub: `${t.station} · ${t.type} · ${t.dist} Ly · market ${age == null ? 'unknown' : age + ' d ago'}`, t }); } });
  return pts;
}
function resizeCanvas() {
  const dpr = window.devicePixelRatio || 1; const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== w * dpr || canvas.height !== h * dpr) { canvas.width = w * dpr; canvas.height = h * dpr; }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); return { w, h };
}
function toScreen(p, w, h) { const m = app.map; return { sx: w / 2 + (p.x - m.cx) * m.scale, sy: h / 2 - (p.z - m.cz) * m.scale }; }
function fitMap() {
  const pts = mapPoints(); const { w, h } = resizeCanvas(); const ship = shipPos();
  if (!pts.length) return;
  const ref = ship || pts[0];
  const ext = Math.max(10, ...pts.map(p => Math.max(Math.abs(p.x - ref.x), Math.abs(p.z - ref.z))));
  app.map.cx = ref.x; app.map.cz = ref.z; app.map.scale = Math.min(w, h) / (2.3 * ext);
}
function drawMap() {
  const { w, h } = resizeCanvas(); const m = app.map; const pts = mapPoints(); m.pts = [];
  ctx.clearRect(0, 0, w, h);
  const ship = shipPos() || (pts[0] ? { x: pts[0].x, z: pts[0].z } : { x: m.cx, z: m.cz });
  if (!app.map.fitted && pts.length) { fitMap(); app.map.fitted = true; }
  // range rings around the ship (or ref system)
  const o = toScreen(ship, w, h);
  ctx.strokeStyle = 'rgba(255,255,255,.07)'; ctx.fillStyle = 'rgba(255,255,255,.28)'; ctx.font = '11px system-ui'; ctx.lineWidth = 1;
  const rings = [10, 25, 50, 100, 150, 200, 300, 500];
  rings.forEach(r => { const pr = r * m.scale; if (pr < 12 || pr > Math.max(w, h) * 1.5) return; ctx.beginPath(); ctx.arc(o.sx, o.sy, pr, 0, Math.PI * 2); ctx.stroke(); ctx.fillText(r + ' Ly', o.sx + pr * 0.707 + 4, o.sy - pr * 0.707 - 4); });
  // core direction hint (+Z is "up" = toward galactic core)
  ctx.fillStyle = 'rgba(255,255,255,.25)'; ctx.fillText('▲ toward core (+Z)', 10, 16);
  // selection line
  if (app.selected && ship) {
    const t = app.selected; const a = toScreen(ship, w, h), b = toScreen(t, w, h);
    ctx.strokeStyle = 'rgba(255,140,42,.6)'; ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.moveTo(a.sx, a.sy); ctx.lineTo(b.sx, b.sy); ctx.stroke(); ctx.setLineDash([]);
    const d = dist3(ship, t); ctx.fillStyle = '#ff8c2a'; ctx.fillText(`${d.toFixed(1)} Ly`, (a.sx + b.sx) / 2 + 6, (a.sy + b.sy) / 2 - 6);
  }
  // points: targets first so ship/carrier draw on top
  const order = { target: 0, loop: 1, carrier: 2, ship: 3 };
  pts.sort((a, b) => order[a.kind] - order[b.kind]).forEach(p => {
    const { sx, sy } = toScreen(p, w, h); if (sx < -20 || sy < -20 || sx > w + 20 || sy > h + 20) return;
    const selected = app.selected && p.t === app.selected;
    ctx.beginPath(); ctx.arc(sx, sy, p.r + (selected ? 3 : 0), 0, Math.PI * 2); ctx.fillStyle = p.color; ctx.fill();
    if (p.kind === 'ship') { ctx.strokeStyle = 'rgba(255,140,42,.5)'; ctx.beginPath(); ctx.arc(sx, sy, 12, 0, Math.PI * 2); ctx.stroke(); }
    if (p.kind !== 'target' || selected || m.scale > 4) { ctx.fillStyle = p.kind === 'target' ? '#a9c8ef' : '#e8edf3'; ctx.fillText(p.name, sx + p.r + 4, sy + 4); }
    m.pts.push({ ...p, sx, sy });
  });
}
function hit(x, y) { let best = null, bd = 10; app.map.pts.forEach(p => { const d = Math.hypot(p.sx - x, p.sy - y); if (d < bd) { bd = d; best = p; } }); return best; }
canvas.addEventListener('mousemove', e => {
  const r = canvas.getBoundingClientRect(); const x = e.clientX - r.left, y = e.clientY - r.top;
  if (app.map.drag) { app.map.cx -= (x - app.map.drag.x) / app.map.scale; app.map.cz += (y - app.map.drag.y) / app.map.scale; app.map.drag = { x, y }; drawMap(); return; }
  const p = hit(x, y);
  if (p) { const ship = shipPos(); tip.style.display = 'block'; tip.style.left = (x + 14) + 'px'; tip.style.top = (y + 14) + 'px'; tip.innerHTML = `<b>${esc(p.name)}</b><br>${esc(p.sub || '')}${ship && p.kind !== 'ship' ? `<br><span class="muted">${dist3(ship, p).toFixed(1)} Ly from you · y ${p.y != null ? (p.y - ship.y).toFixed(0) : '?'}</span>` : ''}`; }
  else tip.style.display = 'none';
});
canvas.addEventListener('mouseleave', () => { tip.style.display = 'none'; app.map.drag = null; canvas.classList.remove('drag'); });
canvas.addEventListener('mousedown', e => { const r = canvas.getBoundingClientRect(); app.map.drag = { x: e.clientX - r.left, y: e.clientY - r.top, moved: false }; canvas.classList.add('drag'); });
canvas.addEventListener('mouseup', e => {
  const r = canvas.getBoundingClientRect(); const x = e.clientX - r.left, y = e.clientY - r.top; const p = hit(x, y);
  app.map.drag = null; canvas.classList.remove('drag');
  if (p && p.kind === 'target') selectTarget(p.t); else if (p && p.kind !== 'target') copy(p.name);
});
canvas.addEventListener('wheel', e => {
  e.preventDefault(); const r = canvas.getBoundingClientRect(); const x = e.clientX - r.left, y = e.clientY - r.top; const { w, h } = resizeCanvas();
  const m = app.map; const f = e.deltaY < 0 ? 1.18 : 1 / 1.18;
  const wx = m.cx + (x - w / 2) / m.scale, wz = m.cz - (y - h / 2) / m.scale;
  m.scale = Math.max(0.15, Math.min(60, m.scale * f));
  m.cx = wx - (x - w / 2) / m.scale; m.cz = wz + (y - h / 2) / m.scale; drawMap();
}, { passive: false });
$('map-fit').onclick = () => { fitMap(); drawMap(); };
$('map-center').onclick = () => { const s = shipPos(); if (s) { app.map.cx = s.x; app.map.cz = s.z; drawMap(); } };
window.addEventListener('resize', drawMap);

// ---------------------------------------------------------------- targets
function selectTarget(t) {
  app.selected = (app.selected === t) ? null : t;
  document.querySelectorAll('#t-body tr').forEach(tr => tr.classList.toggle('sel', app.selected && tr.dataset.sys === app.selected.system && tr.dataset.st === app.selected.station));
  drawMap();
}
async function findTargets() {
  const p = $('t-power').value, ref = $('t-ref').value.trim() || 'Leesti', mn = $('t-min').value, mx = $('t-max').value, pad = $('t-pad').value;
  $('t-status').textContent = 'querying Spansh…'; $('t-compare-out').innerHTML = '';
  try {
    const r = await fetch(`/api/targets?power=${encodeURIComponent(p)}&ref=${encodeURIComponent(ref)}&min=${mn}&max=${mx}&pad=${pad}`); const d = await r.json();
    if (d.error) throw new Error(d.error);
    app.targets = d.results; app.selected = null;
    $('t-status').textContent = `${fmt(d.count)} stations match; showing nearest ${d.results.length} from ${d.ref}`;
    $('t-body').innerHTML = d.results.length ? d.results.map(s => {
      const age = s.updated ? Math.round((Date.now() - Date.parse(s.updated)) / 864e5) : null; const ageCls = age == null ? 'muted' : (age > 60 ? 'bad' : (age > 14 ? 'warn' : 'ok'));
      return `<tr data-sys="${esc(s.system)}" data-st="${esc(s.station)}"><td><b>${esc(s.system)}</b></td><td>${esc(s.station)}</td><td class="num">${s.dist}</td><td class="num">${fmt(s.ls)}</td><td>${esc(s.type)}</td><td>${s.pad}</td><td class="num">${fmt(s.pop)}</td><td class="${ageCls}">${age == null ? 'unknown' : age + ' d ago'}</td><td><button class="mini" data-copy="${esc(s.system)}">copy</button> <a href="${inaraSt(s.station)}" target="_blank">Inara</a> <a href="${spanshSys(s.system)}" target="_blank">Spansh</a></td></tr>`;
    }).join('') : '<tr><td colspan="9" class="muted">Nothing in that band. Widen the distance or include outposts.</td></tr>';
    document.querySelectorAll('#t-body tr[data-sys]').forEach(tr => tr.addEventListener('click', e => { if (e.target.closest('a,button')) return; const t = app.targets.find(x => x.system === tr.dataset.sys && x.station === tr.dataset.st); if (t) selectTarget(t); }));
    app.map.fitted = false; drawMap();
  } catch (e) { $('t-status').textContent = 'error: ' + e.message; }
}
$('t-go').onclick = findTargets;
$('t-here').onclick = () => { if (app.state && app.state.system) { $('t-ref').value = app.state.system; findTargets(); } };
$('t-compare').onclick = async () => {
  const ref = $('t-ref').value.trim() || 'Leesti'; $('t-status').textContent = 'comparing all powers (first run takes ~20 s)…';
  try {
    const r = await fetch(`/api/powers?ref=${encodeURIComponent(ref)}`); const d = await r.json();
    $('t-compare-out').innerHTML = `<table style="margin-top:10px"><thead><tr><th>Power</th><th class="num">Acquisition starports</th><th>Nearest to ${esc(ref)}</th></tr></thead><tbody>` + d.map(p => `<tr><td><b>${esc(p.power)}</b></td><td class="num">${p.error ? '<span class="bad">error</span>' : fmt(p.count)}</td><td>${(p.nearest || []).map(n => `${esc(n.system)} <span class="muted">${n.dist} Ly</span>`).join(' · ')}</td></tr>`).join('') + '</tbody></table>';
    $('t-status').textContent = 'comparison ready';
  } catch (e) { $('t-status').textContent = 'error: ' + e.message; }
};

// ---------------------------------------------------------------- loop checklist
// Two sources of truth: manual ticks (localStorage) and, when auto is on, what is actually in the hold.
const lsGet = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (e) { return d; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { } };
function loopAuto() { return lsGet('loopAuto', true); }
function loopStatus(l) {
  const items = (app.state && app.state.cargo && app.state.cargo.items) || [];
  const tons = items.filter(i => l.keys.includes(i.key)).reduce((a, i) => a + (i.count || 0), 0);
  const manual = !!lsGet('loopDone', {})[l.system];
  const here = !!(app.state && app.state.docked && app.state.system === l.system);
  return { tons, inHold: tons > 0, manual, here, done: manual || (loopAuto() && tons > 0) };
}
function renderLoop() {
  const auto = loopAuto(); $('loop-auto').textContent = 'auto: ' + (auto ? 'on' : 'off'); $('loop-auto').style.borderColor = auto ? 'var(--ok)' : '';
  const ship = shipPos();
  const rows = LOOP.map(l => ({ l, st: loopStatus(l), d: ship && app.coords[l.system] ? dist3(ship, app.coords[l.system]) : null }));
  // Always nearest-first from the ship's current position; with auto on, finished stations sink to the bottom.
  rows.sort((a, b) => (auto ? (a.st.done - b.st.done) : 0) || ((a.d ?? a.l.ly) - (b.d ?? b.l.ly)));
  const doneCount = rows.filter(r => r.st.done).length; const tons = rows.reduce((a, r) => a + r.st.tons, 0);
  const next = auto ? rows.find(r => !r.st.done) : null;
  $('loop-summary').innerHTML = `${doneCount}/${rows.length} stations · <b>${tons} t</b> of loop rares aboard` + (next ? ` · next: <b class="accent">${esc(next.l.system)}</b>${next.d != null ? ` (${next.d.toFixed(1)} Ly)` : ''}` : (doneCount === rows.length ? ' · <b class="ok">loop complete, go sell</b>' : ''));
  $('loop-bar').style.width = (100 * doneCount / rows.length) + '%';
  $('loop').innerHTML = rows.map(({ l, st, d }) => `<label class="chk ${st.done ? 'done' : ''}" ${next && next.l === l ? 'style="border-left:3px solid var(--accent);padding-left:6px"' : ''}><input type="checkbox" data-sys="${esc(l.system)}" ${st.done ? 'checked' : ''} ${auto && st.inHold ? 'disabled title="in hold (auto)"' : ''}><span class="n"><b>${esc(l.system)}</b> · ${esc(l.station)} <span class="muted">(${d != null ? d.toFixed(1) + ' Ly from you' : l.ly + ' Ly from Leesti'})</span>${st.here ? ' <span class="tag ok">docked here</span>' : ''}<br><span class="tag rare">${esc(l.rares)}</span>${st.tons ? ` <span class="tag ok">${st.tons} t aboard</span>` : ''}</span><span><button class="mini" data-copy="${esc(l.system)}">copy</button> <a href="${inaraSys(l.system)}" target="_blank">Inara</a></span></label>`).join('');
}
$('loop').addEventListener('change', e => { if (e.target.matches('input')) { const d = lsGet('loopDone', {}); d[e.target.dataset.sys] = e.target.checked; lsSet('loopDone', d); renderLoop(); } });
$('loop-reset').onclick = () => { localStorage.removeItem('loopDone'); renderLoop(); };
$('loop-auto').onclick = () => { lsSet('loopAuto', !loopAuto()); renderLoop(); drawMap(); };
renderLoop();

// ---------------------------------------------------------------- misc
$('mat-toggle').onclick = () => { const d = $('mat-detail'); const show = d.style.display === 'none'; d.style.display = show ? 'block' : 'none'; $('mat-toggle').textContent = show ? 'hide' : 'show top'; };
$('q-inara').onclick = () => window.open(inaraSys($('q-sys').value.trim()), '_blank');
$('q-inara-st').onclick = () => window.open(inaraSt($('q-sys').value.trim()), '_blank');
$('q-spansh').onclick = () => window.open(spanshSys($('q-sys').value.trim()), '_blank');

refresh(); setInterval(refresh, 3000);
