/* EliteLab shell: state store fed by SSE, card registry, map layer registry, and a drag-and-drop layout.
   Modules load their card scripts from /modules/<name>/... and call Lab.card({...}) / Lab.map.addLayer(...). No build step. */
'use strict';
(() => {
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const fmt = n => (n == null || isNaN(n)) ? '—' : Number(n).toLocaleString();
  const ls = { get: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (e) { return d; } }, set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { } } };

  // ------------------------------------------------------------------ runtime
  const Lab = window.Lab = {
    state: {}, cards: {}, coords: {}, _subs: [], _pending: new Set(),
    util: {
      esc, fmt, ls,
      inaraSys: n => `https://inara.cz/elite/starsystem/?search=${encodeURIComponent(n)}`,
      inaraSt: n => `https://inara.cz/elite/station/?search=${encodeURIComponent(n)}`,
      spanshSys: n => `https://spansh.co.uk/search/${encodeURIComponent(n)}`,
      copy: t => navigator.clipboard && navigator.clipboard.writeText(t),
      dist3: (a, b) => Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z),
    },
    on(ns, fn) { const nss = Array.isArray(ns) ? ns : [ns]; const sub = { nss, fn }; this._subs.push(sub); return () => { this._subs = this._subs.filter(s => s !== sub); }; },
    emit(ns) { this._pending.add(ns); if (!this._raf) this._raf = requestAnimationFrame(() => { const p = new Set(this._pending); this._pending.clear(); this._raf = null; this._subs.slice().forEach(s => { if (s.nss.some(n => p.has(n))) { try { s.fn(this.state); } catch (e) { console.error(e); } } }); }); },
    set(ns, patch) { this.state[ns] = { ...(this.state[ns] || {}), ...patch }; this.emit(ns); },
    get(ns, key) { const d = this.state[ns] || {}; return key == null ? d : d[key]; },
    async api(path, params) { const u = new URL(path, location.origin); Object.entries(params || {}).forEach(([k, v]) => { if (v != null && v !== '') u.searchParams.set(k, v); }); const r = await fetch(u); return r.json(); },
    async post(path, body) { const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }); return r.json(); },
    card(def) { this.cards[def.id] = def; },
    map: { layers: {}, addLayer(id, def) { this.layers[id] = { enabled: true, ...def }; } },
    shipPos(S) { const j = (S || Lab.state).journal || {}; if (j.star_pos) return { x: j.star_pos[0], y: j.star_pos[1], z: j.star_pos[2] }; return j.system && Lab.coords[j.system] ? Lab.coords[j.system] : null; },
    toast(msg, kind) { const t = document.createElement('div'); t.className = 'toast ' + (kind || ''); t.textContent = msg; document.getElementById('toasts').appendChild(t); setTimeout(() => t.classList.add('show'), 10); setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 300); }, 2600); },
    // cards call this to be told when their card is resized/moved (cheaper than a window resize)
    relayout() { if (this._relayoutRaf) return; this._relayoutRaf = requestAnimationFrame(() => { this._relayoutRaf = null; dispatchEvent(new Event('lab:relayout')); }); },
  };

  document.body.addEventListener('click', e => { const b = e.target.closest('[data-copy]'); if (b) { Lab.util.copy(b.dataset.copy); const t = b.textContent; b.textContent = 'copied'; setTimeout(() => b.textContent = t, 900); } });

  // header
  Lab.on('journal', S => { const j = S.journal || {}; document.getElementById('h-cmdr').textContent = j.cmdr || '—'; document.getElementById('h-ship').textContent = [j.ship, j.ship_name, j.ship_ident].filter(Boolean).join(' · ') || '—'; document.getElementById('h-credits').textContent = fmt(j.credits); document.getElementById('h-ver').textContent = j.game_version || '—'; const live = document.getElementById('h-live'); if (j.last_event_time) live.textContent = 'live · ' + j.last_event_time.replace('T', ' ').replace('Z', ' UTC'); });

  // carrier coords for the map
  let coordsAsked = '';
  Lab.on('journal', async S => { const sys = S.journal?.carrier?.system; if (sys && !Lab.coords[sys] && coordsAsked !== sys) { coordsAsked = sys; try { Object.assign(Lab.coords, await Lab.api('/api/coords', { names: sys })); Lab.emit('journal'); } catch (e) { } } });

  function loadScript(src) { return new Promise(res => { const s = document.createElement('script'); s.src = src; s.onload = res; s.onerror = () => { console.error('failed to load', src); res(); }; document.head.appendChild(s); }); }

  // ------------------------------------------------------------------ layout
  const LAYOUT_KEY = 'layout.v1';
  const grid = document.getElementById('grid');
  let allCards = [];                 // manifest cards, default order
  let layout = ls.get(LAYOUT_KEY, { order: [], spans: {}, hidden: [], collapsed: [], locked: false });
  const saveLayout = () => ls.set(LAYOUT_KEY, layout);
  const isMobile = () => matchMedia('(max-width: 760px)').matches;
  const mounted = {};                // id -> { sec, off, def, body }

  function orderedCards() {
    const byId = Object.fromEntries(allCards.map(c => [c.id, c]));
    const seen = new Set(); const out = [];
    layout.order.forEach(id => { if (byId[id] && !seen.has(id)) { out.push(byId[id]); seen.add(id); } });
    allCards.forEach(c => { if (!seen.has(c.id)) out.push(c); });
    return out;
  }
  const spanOf = c => layout.spans[c.id] || c.span || 3;
  function applySpan(sec, n) { sec.className = sec.className.replace(/\bc\d+\b/g, '').replace(/\s+/g, ' ').trim() + ` c${n}`; const h = sec.querySelector('.resize'); if (h) h.dataset.span = n; }

  function buildCard(c) {
    const def = Lab.cards[c.id];
    const sec = document.createElement('section'); sec.className = 'card'; sec.id = 'card-' + c.id; sec.dataset.id = c.id;
    if (layout.collapsed.includes(c.id)) sec.classList.add('collapsed');
    sec.innerHTML = `<h2><span class="grip" title="drag to move">⋮⋮</span><span class="title">${esc(c.title)}</span><span class="mod">${esc(c.module)}</span><span class="right"></span><span class="tools"><button class="icon" data-act="collapse" title="collapse">–</button><button class="icon" data-act="hide" title="hide">×</button></span></h2><div class="body"></div><div class="resize" title="drag to resize"></div>`;
    applySpan(sec, spanOf(c));
    const body = sec.querySelector('.body'), head = sec.querySelector('.right');
    const rec = { sec, def, body, off: () => { } };
    if (!def) body.innerHTML = `<div class="muted">Card "${esc(c.id)}" from module ${esc(c.module)} did not register.</div>`;
    else {
      try { if (def.header) def.header(head); if (def.mount) def.mount(body); } catch (e) { console.error(c.id, e); }
      const render = S => {
        try { def.render && def.render(body, S); body.querySelector(':scope > .render-error')?.remove(); }
        catch (e) { console.error(c.id, e); let b = body.querySelector(':scope > .render-error'); if (!b) { b = document.createElement('div'); b.className = 'render-error bad'; body.prepend(b); } b.textContent = 'render error: ' + e.message; }
      };
      rec.off = Lab.on(def.requires || [], render); render(Lab.state);
    }
    sec.querySelector('[data-act=collapse]').onclick = () => { sec.classList.toggle('collapsed'); layout.collapsed = layout.collapsed.filter(i => i !== c.id); if (sec.classList.contains('collapsed')) layout.collapsed.push(c.id); saveLayout(); Lab.relayout(); };
    sec.querySelector('[data-act=hide]').onclick = () => { hideCard(c.id); Lab.toast(`${c.title} hidden. Bring it back from Layout.`); };
    wireDrag(sec); wireResize(sec, c);
    mounted[c.id] = rec;
    return sec;
  }
  function unmountCard(id) {
    const rec = mounted[id]; if (!rec) return;
    try { rec.off(); if (rec.def && rec.def.unmount) rec.def.unmount(rec.body); } catch (e) { console.error(id, e); }
    rec.sec.remove(); delete mounted[id];
  }
  function hideCard(id) { if (!layout.hidden.includes(id)) layout.hidden.push(id); saveLayout(); unmountCard(id); renderMenu(); }
  function showCard(id) {
    layout.hidden = layout.hidden.filter(i => i !== id); saveLayout();
    const c = allCards.find(x => x.id === id); if (!c || mounted[id]) return;
    // insert at its position in the ordered list
    const order = orderedCards().map(x => x.id); const idx = order.indexOf(id);
    const next = order.slice(idx + 1).map(i => mounted[i]).find(Boolean);
    const sec = buildCard(c); if (next) grid.insertBefore(sec, next.sec); else grid.appendChild(sec);
    renderMenu(); Lab.relayout();
  }
  function mountCards() {
    Object.keys(mounted).forEach(unmountCard); grid.innerHTML = '';
    orderedCards().forEach(c => { if (!layout.hidden.includes(c.id)) grid.appendChild(buildCard(c)); });
    grid.classList.toggle('locked', !!layout.locked);
    renderMenu(); Lab.relayout();
  }

  // drag to reorder: pointer events on the title bar, moves throttled to animation frames, a light ghost follows
  function wireDrag(sec) {
    const h2 = sec.querySelector('h2');
    h2.addEventListener('pointerdown', e => {
      if (layout.locked || isMobile() || e.button !== 0 || e.target.closest('button, a, input, select, .right')) return;
      e.preventDefault();
      const r = sec.getBoundingClientRect(); const ox = e.clientX - r.left, oy = e.clientY - r.top;
      const ghost = document.createElement('div'); ghost.className = 'card ghost'; ghost.style.width = r.width + 'px'; ghost.style.height = Math.min(r.height, 160) + 'px';
      ghost.innerHTML = `<h2><span class="title">${sec.querySelector('.title').textContent}</span></h2>`;
      document.body.appendChild(ghost); sec.classList.add('dragging'); grid.classList.add('is-dragging');
      try { h2.setPointerCapture(e.pointerId); } catch (err) { }
      let last = null, raf = null;
      const place = () => {
        raf = null; if (!last) return;
        ghost.style.transform = `translate(${last.x - ox}px, ${last.y - oy}px)`;
        const under = document.elementFromPoint(last.x, last.y);     // ghost has pointer-events:none, so it is skipped
        const target = under && under.closest('#grid > .card'); if (!target || target === sec) return;
        const tr = target.getBoundingClientRect(); const before = (last.x - tr.left) < tr.width / 2;
        const want = before ? target : target.nextSibling;
        if (want !== sec && sec.nextSibling !== want) grid.insertBefore(sec, want);
      };
      const move = ev => { last = { x: ev.clientX, y: ev.clientY }; if (!raf) raf = requestAnimationFrame(place); };
      const up = () => {
        h2.removeEventListener('pointermove', move); h2.removeEventListener('pointerup', up); h2.removeEventListener('pointercancel', up);
        if (raf) cancelAnimationFrame(raf); ghost.remove(); sec.classList.remove('dragging'); grid.classList.remove('is-dragging');
        layout.order = [...grid.querySelectorAll(':scope > .card')].map(s => s.dataset.id); saveLayout(); Lab.relayout();
      };
      h2.addEventListener('pointermove', move); h2.addEventListener('pointerup', up); h2.addEventListener('pointercancel', up);
      move(e);
    });
  }

  // drag the corner to resize in grid columns
  function wireResize(sec, c) {
    const handle = sec.querySelector('.resize');
    handle.addEventListener('pointerdown', e => {
      if (layout.locked || isMobile() || e.button !== 0) return;
      e.preventDefault(); try { handle.setPointerCapture(e.pointerId); } catch (err) { }
      const startX = e.clientX, start = spanOf(c); const col = grid.clientWidth / 12; let cur = start, raf = null, lastX = startX;
      const apply = () => { raf = null; const n = Math.max(2, Math.min(12, Math.round(start + (lastX - startX) / col))); if (n !== cur) { cur = n; applySpan(sec, n); Lab.relayout(); } };
      const move = ev => { lastX = ev.clientX; if (!raf) raf = requestAnimationFrame(apply); };
      const up = () => { handle.removeEventListener('pointermove', move); handle.removeEventListener('pointerup', up); handle.removeEventListener('pointercancel', up); if (raf) cancelAnimationFrame(raf); apply(); layout.spans[c.id] = cur; saveLayout(); Lab.relayout(); };
      handle.addEventListener('pointermove', move); handle.addEventListener('pointerup', up); handle.addEventListener('pointercancel', up);
    });
    handle.addEventListener('dblclick', () => { const n = spanOf(c) >= 12 ? (c.span || 3) : 12; applySpan(sec, n); layout.spans[c.id] = n; saveLayout(); Lab.relayout(); });
  }

  // layout menu
  const menu = document.getElementById('layout-menu');
  function renderMenu() {
    menu.innerHTML = `
      <div class="menu-row"><label><input type="checkbox" id="lm-lock" ${layout.locked ? 'checked' : ''}> lock layout</label><button class="mini" id="lm-reset">reset</button><button class="mini" id="lm-export">export</button><button class="mini" id="lm-import">import</button></div>
      <div class="menu-list">${orderedCards().map(c => `<label><input type="checkbox" data-id="${esc(c.id)}" ${layout.hidden.includes(c.id) ? '' : 'checked'}> ${esc(c.title)} <span class="muted">${esc(c.module)}</span></label>`).join('')}</div>
      <div class="muted" style="font-size:11px;margin-top:6px">Drag a title bar to move, drag the corner to resize, double-click the corner for full width. Saved in this browser.</div>`;
    menu.querySelector('#lm-lock').onchange = e => { layout.locked = e.target.checked; saveLayout(); grid.classList.toggle('locked', layout.locked); };
    menu.querySelector('#lm-reset').onclick = () => { layout = { order: [], spans: {}, hidden: [], collapsed: [], locked: false }; saveLayout(); mountCards(); Lab.toast('Layout reset'); };
    menu.querySelector('#lm-export').onclick = () => { Lab.util.copy(JSON.stringify(layout)); Lab.toast('Layout JSON copied to clipboard'); };
    menu.querySelector('#lm-import').onclick = () => { const s = prompt('Paste layout JSON'); if (!s) return; try { const l = JSON.parse(s); layout = { order: l.order || [], spans: l.spans || {}, hidden: l.hidden || [], collapsed: l.collapsed || [], locked: !!l.locked }; saveLayout(); mountCards(); Lab.toast('Layout imported'); } catch (e) { Lab.toast('Invalid layout JSON', 'bad'); } };
    menu.querySelectorAll('input[data-id]').forEach(cb => cb.onchange = () => { cb.checked ? showCard(cb.dataset.id) : hideCard(cb.dataset.id); });
  }
  document.getElementById('layout-btn').onclick = e => { e.stopPropagation(); menu.classList.toggle('open'); };

  // UI health: measures frame gaps and warns in the footer when the page is struggling (shown only when visible)
  (() => { let last = performance.now(), worst = 0; const el = document.getElementById('f-perf');
    const tick = now => { const gap = now - last; last = now; if (document.visibilityState === 'visible' && gap > worst) worst = gap; requestAnimationFrame(tick); }; requestAnimationFrame(tick);
    setInterval(() => { if (!el) return; el.textContent = worst > 120 ? ` · UI stalled ${Math.round(worst)} ms` : ''; el.className = worst > 120 ? 'bad' : 'muted'; worst = 0; }, 2000); })();
  document.addEventListener('click', e => { if (!e.target.closest('#layout-menu, #layout-btn')) menu.classList.remove('open'); });
  addEventListener('resize', () => Lab.relayout());

  // ------------------------------------------------------------------ live connection
  function connect() {
    const live = document.getElementById('h-live');
    const es = new EventSource('/events');
    es.addEventListener('snapshot', e => { const snap = JSON.parse(e.data); Object.keys(snap).forEach(ns => { if (ns !== '_version') Lab.state[ns] = { ...(Lab.state[ns] || {}), ...snap[ns] }; }); live.classList.add('live'); Object.keys(Lab.state).forEach(ns => Lab.emit(ns)); });
    es.addEventListener('state', e => { const m = JSON.parse(e.data); (Lab.state[m.ns] = Lab.state[m.ns] || {})[m.key] = m.value; Lab.emit(m.ns); });
    es.onerror = () => { live.classList.remove('live'); live.textContent = 'reconnecting…'; };
  }

  (async () => {
    const manifest = await Lab.api('/api/modules');
    document.getElementById('f-modules').textContent = 'modules: ' + manifest.map(m => m.name).join(', ');
    const scripts = [...new Set(manifest.flatMap(m => m.cards.map(c => c.script)))];
    for (const s of scripts) await loadScript(s);
    const snap = await Lab.api('/api/state'); Object.keys(snap).forEach(ns => { if (ns !== '_version') Lab.state[ns] = snap[ns]; });
    allCards = manifest.flatMap(m => m.cards.map(c => ({ ...c, module: m.name }))).sort((a, b) => (a.order || 100) - (b.order || 100));
    mountCards();
    Object.keys(Lab.state).forEach(ns => Lab.emit(ns));
    connect();
  })();
})();
