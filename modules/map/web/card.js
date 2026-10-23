/* map card: canvas star map. Other modules add layers with Lab.map.addLayer(id, {label, color, z, points(S), lines(S)}). */
(() => {
  const { esc, fmt, dist3 } = Lab.util;
  const M = { cx: 0, cz: 0, scale: 2, drag: null, pts: [], fitted: false, userMoved: false, history: { systems: [], route: [] }, hKey: null, layers: { history: true, labels: false } };

  function starColor(cls) {
    const c = (cls || '').toUpperCase();
    if (c.startsWith('O')) return '#9bb0ff'; if (c.startsWith('B')) return '#aabfff'; if (c.startsWith('A')) return '#cad7ff';
    if (c.startsWith('F')) return '#f8f7ff'; if (c.startsWith('G')) return '#fff4e8'; if (c.startsWith('K')) return '#ffd2a1';
    if (c.startsWith('M')) return '#ffb56b'; if (c.startsWith('L') || c.startsWith('T') || c.startsWith('Y')) return '#b06a4a';
    if (c.startsWith('D')) return '#dfe9ff'; if (c === 'N' || c.startsWith('H')) return '#c9b6ff'; if (c.startsWith('TTS') || c.startsWith('AEBE')) return '#ffe9a8';
    return '#e8dcc4';
  }

  // Built-in layers: ship, carrier, history.
  Lab.map.addLayer('ship', { z: 10, points: S => { const p = Lab.shipPos(S); const j = S.journal || {}; return p ? [{ name: j.system, ...p, r: 5, color: '#ff8c2a', kind: 'ship', label: true, sub: j.docked ? `Docked at ${j.station}` : 'current position' }] : []; } });
  Lab.map.addLayer('carrier', { z: 9, points: S => { const c = S.journal?.carrier; const co = c && c.system && Lab.coords[c.system]; return co ? [{ name: `${c.name} (${c.callsign})`, ...co, r: 5, color: '#2fd4ff', kind: 'carrier', label: true, sub: c.system, copy: c.system }] : []; } });
  Lab.map.addLayer('history', { z: 0, points: S => M.layers.history ? M.history.systems.map(h => ({ name: h.name, x: h.pos[0], y: h.pos[1], z: h.pos[2], r: Math.min(4.5, 2 + Math.log2(1 + h.visits)), color: starColor(h.star_class), kind: 'visited',
      sub: `${h.star_class ? 'class ' + h.star_class + ' · ' : ''}${h.visits} visit${h.visits === 1 ? '' : 's'} · last ${(h.last || '').slice(0, 10)}${h.carrier ? ' · carrier jump' : ''}` })) : [] });

  let canvas, ctx, tip, el;
  const field = document.createElement('canvas'); let fieldSeeded = false;
  function seedField(w, h) {
    field.width = w * 2; field.height = h * 2; const fx = field.getContext('2d');
    fx.fillStyle = '#05070c'; fx.fillRect(0, 0, field.width, field.height);
    let s = 1337; const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647;
    const g = fx.createRadialGradient(field.width * .35, field.height * .3, 0, field.width * .35, field.height * .3, field.width * .6);
    g.addColorStop(0, 'rgba(60,70,120,.18)'); g.addColorStop(.5, 'rgba(40,40,80,.08)'); g.addColorStop(1, 'rgba(0,0,0,0)'); fx.fillStyle = g; fx.fillRect(0, 0, field.width, field.height);
    for (let i = 0; i < 1400; i++) { const x = rnd() * field.width, y = rnd() * field.height, r = rnd() * 1.1 + .2, a = rnd() * .5 + .15; fx.beginPath(); fx.arc(x, y, r, 0, Math.PI * 2); fx.fillStyle = `rgba(${200 + rnd() * 55 | 0},${200 + rnd() * 55 | 0},255,${a})`; fx.fill(); }
    fieldSeeded = true;
  }
  function resize() { const dpr = devicePixelRatio || 1, w = canvas.clientWidth, h = canvas.clientHeight; if (canvas.width !== w * dpr || canvas.height !== h * dpr) { canvas.width = w * dpr; canvas.height = h * dpr; fieldSeeded = false; } ctx.setTransform(dpr, 0, 0, dpr, 0, 0); return { w, h }; }
  const toScreen = (p, w, h) => ({ sx: w / 2 + (p.x - M.cx) * M.scale, sy: h / 2 - (p.z - M.cz) * M.scale });
  function glow(sx, sy, r, color, alpha) { const g = ctx.createRadialGradient(sx, sy, 0, sx, sy, r * 3.2); g.addColorStop(0, color); g.addColorStop(.35, color); g.addColorStop(1, 'rgba(0,0,0,0)'); ctx.globalAlpha = alpha; ctx.fillStyle = g; ctx.beginPath(); ctx.arc(sx, sy, r * 3.2, 0, Math.PI * 2); ctx.fill(); ctx.globalAlpha = 1; }
  function niceScale(px) { const ly = px / M.scale, p = Math.pow(10, Math.floor(Math.log10(ly))), m = ly / p; return (m >= 5 ? 5 : m >= 2 ? 2 : 1) * p; }

  function allPoints(S) {
    const out = [];
    Object.entries(Lab.map.layers).sort((a, b) => (a[1].z || 0) - (b[1].z || 0)).forEach(([id, L]) => {
      if (L.enabled === false) return;
      try { (L.points ? L.points(S) : []).forEach(p => out.push({ ...p, layer: id })); } catch (e) { }
    });
    return out;
  }
  function fit(S, local) {
    const { w, h } = resize(); const ship = Lab.shipPos(S);
    let pts = allPoints(S).filter(p => local ? p.layer !== 'history' && p.layer !== 'targets' : true);
    if (!pts.length) return;
    const ref = ship || pts[0];
    const ext = Math.max(6, ...pts.map(p => Math.max(Math.abs(p.x - ref.x), Math.abs(p.z - ref.z))));
    M.cx = ref.x; M.cz = ref.z; M.scale = Math.min(w, h) / (2.3 * ext); M.fitted = true; M.userMoved = false;
  }

  function draw() {
    if (!canvas) return; const S = Lab.state; const { w, h } = resize(); M.pts = [];
    if (!fieldSeeded) seedField(w, h);
    ctx.drawImage(field, ((-M.cx * 0.15) % w + w) % w, ((M.cz * 0.15) % h + h) % h, w, h, 0, 0, w, h);
    const pts = allPoints(S); const ship = Lab.shipPos(S);
    if (!M.fitted && pts.length) fit(S, false);
    ctx.font = '11px system-ui'; ctx.lineWidth = 1;
    // route trail
    if (M.layers.history && M.history.route.length > 1) {
      const by = {}; M.history.systems.forEach(s => by[s.name] = s); const n = M.history.route.length;
      for (let i = 1; i < n; i++) {
        const a = by[M.history.route[i - 1].name], b = by[M.history.route[i].name]; if (!a || !b) continue;
        const A = toScreen({ x: a.pos[0], z: a.pos[2] }, w, h), B = toScreen({ x: b.pos[0], z: b.pos[2] }, w, h); const age = i / n, carrier = M.history.route[i].event === 'CarrierJump';
        ctx.strokeStyle = carrier ? `rgba(47,212,255,${0.15 + 0.6 * age})` : `rgba(255,140,42,${0.12 + 0.65 * age})`; ctx.lineWidth = carrier ? 1.5 : 1 + age; if (carrier) ctx.setLineDash([6, 4]);
        ctx.beginPath(); ctx.moveTo(A.sx, A.sy); ctx.lineTo(B.sx, B.sy); ctx.stroke(); ctx.setLineDash([]);
      }
      ctx.lineWidth = 1;
    }
    // layer lines
    Object.values(Lab.map.layers).forEach(L => { if (L.enabled === false || !L.lines) return; try { L.lines(S).forEach(l => { const A = toScreen(l.a, w, h), B = toScreen(l.b, w, h); ctx.strokeStyle = l.color || '#fff'; if (l.dash) ctx.setLineDash(l.dash); ctx.beginPath(); ctx.moveTo(A.sx, A.sy); ctx.lineTo(B.sx, B.sy); ctx.stroke(); ctx.setLineDash([]); if (l.label) { ctx.fillStyle = l.color || '#fff'; ctx.fillText(l.label, (A.sx + B.sx) / 2 + 6, (A.sy + B.sy) / 2 - 6); } }); } catch (e) { } });
    // points
    const recent = new Set(M.history.route.slice(-6).map(r => r.name));
    pts.forEach(p => {
      const { sx, sy } = toScreen(p, w, h); if (sx < -30 || sy < -30 || sx > w + 30 || sy > h + 30) return;
      if (p.kind === 'visited') { glow(sx, sy, p.r, p.color, .35); ctx.beginPath(); ctx.arc(sx, sy, p.r * .55, 0, Math.PI * 2); ctx.fillStyle = '#fff'; ctx.fill(); }
      else {
        glow(sx, sy, p.r, p.color, p.kind === 'ship' ? .6 : .4); ctx.beginPath(); ctx.arc(sx, sy, p.r + (p.selected ? 2 : 0), 0, Math.PI * 2); ctx.fillStyle = p.color; ctx.fill();
        if (p.kind === 'ship') { ctx.strokeStyle = 'rgba(255,140,42,.6)'; ctx.beginPath(); ctx.arc(sx, sy, 11, 0, Math.PI * 2); ctx.stroke(); ctx.beginPath(); ctx.arc(sx, sy, 16 + 3 * Math.sin(Date.now() / 300), 0, Math.PI * 2); ctx.strokeStyle = 'rgba(255,140,42,.25)'; ctx.stroke(); }
        if (p.kind === 'carrier') { ctx.strokeStyle = 'rgba(47,212,255,.6)'; ctx.strokeRect(sx - 7, sy - 7, 14, 14); }
      }
      const label = p.label || p.selected || M.layers.labels || M.scale > 6 || (p.kind === 'visited' && recent.has(p.name) && M.scale > 1.5);
      if (label) { ctx.fillStyle = p.kind === 'visited' ? 'rgba(232,237,243,.7)' : (p.layer === 'targets' ? '#a9c8ef' : '#e8edf3'); ctx.fillText(p.name, sx + p.r + 5, sy + 4); }
      M.pts.push({ ...p, sx, sy });
    });
    const ly = niceScale(90); const sc = el.querySelector('.map-scale'); sc.style.width = (ly * M.scale) + 'px'; sc.textContent = ly + ' Ly';
    const hs = M.history; el.querySelector('.map-stats').textContent = hs.systems.length ? `${hs.systems.length} systems · ${hs.jumps} jumps · ${fmt(hs.total_ly)} Ly travelled` : '';
    ctx.fillStyle = 'rgba(255,255,255,.3)'; ctx.fillText('▲ toward galactic core', 10, 16);
  }
  const hit = (x, y) => { let best = null, bd = 10; M.pts.forEach(p => { const d = Math.hypot(p.sx - x, p.sy - y); if (d < bd) { bd = d; best = p; } }); return best; };

  async function loadHistory(force) {
    const days = el.querySelector('#map-range').value; const key = days + '|' + (Lab.state.history?.version);
    if (!force && key === M.hKey) return; M.hKey = key;
    try { M.history = await Lab.api('/api/history', { days }); if (!M.userMoved) fit(Lab.state, false); draw(); } catch (e) { }
  }

  Lab.card({
    id: 'map', requires: ['journal', 'history', 'loop', 'targets'],
    mount(root) {
      el = root;
      el.innerHTML = `<div class="map-wrap"><canvas></canvas>
        <div class="map-ctl">
          <select class="mini" id="map-range" title="history range"><option value="1">24 h</option><option value="7">7 days</option><option value="30" selected>30 days</option><option value="90">90 days</option><option value="0">all time</option></select>
          <span id="map-layers"></span>
          <button class="mini map-layer on" data-layer="labels">all labels</button>
          <button class="mini" id="map-fit">fit all</button><button class="mini" id="map-local">local</button><button class="mini" id="map-center">centre</button>
        </div>
        <div class="map-legend"><span><i style="background:#ff8c2a"></i>you</span><span><i style="background:#2fd4ff"></i>carrier</span><span id="map-legend-layers"></span><span><i style="background:#ffd27a;box-shadow:0 0 6px #ffd27a"></i>visited, by star class</span><span class="muted map-stats"></span></div>
        <div class="map-scale"></div><div class="map-tip"></div></div>`;
      canvas = el.querySelector('canvas'); ctx = canvas.getContext('2d'); tip = el.querySelector('.map-tip');
      el.querySelector('[data-layer=labels]').classList.remove('on');
      // layer toggles for every registered layer except ship/carrier
      const lay = el.querySelector('#map-layers'), leg = el.querySelector('#map-legend-layers');
      Object.entries(Lab.map.layers).forEach(([id, L]) => { if (id === 'ship' || id === 'carrier') return; const b = document.createElement('button'); b.className = 'mini map-layer on'; b.textContent = L.label || id; b.onclick = () => { L.enabled = L.enabled === false; if (id === 'history') M.layers.history = L.enabled !== false; b.classList.toggle('on', L.enabled !== false); draw(); }; lay.appendChild(b); if (L.color) { const s = document.createElement('span'); s.innerHTML = `<i style="background:${L.color}"></i>${esc(L.label || id)}`; leg.appendChild(s); } });
      el.querySelector('[data-layer=labels]').onclick = e => { M.layers.labels = !M.layers.labels; e.target.classList.toggle('on', M.layers.labels); draw(); };
      el.querySelector('#map-fit').onclick = () => { fit(Lab.state, false); draw(); };
      el.querySelector('#map-local').onclick = () => { fit(Lab.state, true); draw(); };
      el.querySelector('#map-center').onclick = () => { const p = Lab.shipPos(Lab.state); if (p) { M.cx = p.x; M.cz = p.z; draw(); } };
      el.querySelector('#map-range').onchange = () => { M.userMoved = false; loadHistory(true); };
      canvas.addEventListener('mousemove', e => {
        const r = canvas.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
        if (M.drag) { M.cx -= (x - M.drag.x) / M.scale; M.cz += (y - M.drag.y) / M.scale; M.drag = { x, y }; M.userMoved = true; draw(); return; }
        const p = hit(x, y); const ship = Lab.shipPos(Lab.state);
        if (p) { tip.style.display = 'block'; tip.style.left = (x + 14) + 'px'; tip.style.top = (y + 14) + 'px'; tip.innerHTML = `<b>${esc(p.name)}</b><br>${esc(p.sub || '')}${ship && p.kind !== 'ship' ? `<br><span class="muted">${dist3(ship, p).toFixed(1)} Ly from you</span>` : ''}`; } else tip.style.display = 'none';
      });
      canvas.addEventListener('mouseleave', () => { tip.style.display = 'none'; M.drag = null; canvas.classList.remove('drag'); });
      canvas.addEventListener('mousedown', e => { const r = canvas.getBoundingClientRect(); M.drag = { x: e.clientX - r.left, y: e.clientY - r.top }; canvas.classList.add('drag'); });
      canvas.addEventListener('mouseup', e => { const r = canvas.getBoundingClientRect(); const p = hit(e.clientX - r.left, e.clientY - r.top); M.drag = null; canvas.classList.remove('drag'); if (p) { if (p.onClick) p.onClick(); else Lab.util.copy(p.copy || p.name); } });
      canvas.addEventListener('wheel', e => { e.preventDefault(); const r = canvas.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top, { w, h } = resize(); const f = e.deltaY < 0 ? 1.18 : 1 / 1.18; const wx = M.cx + (x - w / 2) / M.scale, wz = M.cz - (y - h / 2) / M.scale; M.scale = Math.max(0.05, Math.min(80, M.scale * f)); M.cx = wx - (x - w / 2) / M.scale; M.cz = wz + (y - h / 2) / M.scale; M.userMoved = true; draw(); }, { passive: false });
      addEventListener('resize', draw);
      setInterval(() => { if (document.visibilityState === 'visible') draw(); }, 120);
      loadHistory(true);
    },
    render(root, S) { loadHistory(false); draw(); },
  });
})();
