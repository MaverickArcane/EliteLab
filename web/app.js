/* EliteLab shell: state store fed by SSE, card registry, map layer registry. Modules load their card scripts
   from /modules/<name>/... and call Lab.card({...}) / Lab.map.addLayer(...). No build step. */
'use strict';
(() => {
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const fmt = n => (n == null || isNaN(n)) ? '—' : Number(n).toLocaleString();
  const ls = { get: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (e) { return d; } }, set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { } } };

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
    emit(ns) { this._pending.add(ns); if (!this._raf) this._raf = requestAnimationFrame(() => { const p = new Set(this._pending); this._pending.clear(); this._raf = null; this._subs.forEach(s => { if (s.nss.some(n => p.has(n))) { try { s.fn(this.state); } catch (e) { console.error(e); } } }); }); },
    set(ns, patch) { this.state[ns] = { ...(this.state[ns] || {}), ...patch }; this.emit(ns); },
    get(ns, key) { const d = this.state[ns] || {}; return key == null ? d : d[key]; },
    async api(path, params) { const u = new URL(path, location.origin); Object.entries(params || {}).forEach(([k, v]) => { if (v != null && v !== '') u.searchParams.set(k, v); }); const r = await fetch(u); return r.json(); },
    async post(path, body) { const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }); return r.json(); },
    card(def) { this.cards[def.id] = def; },
    map: { layers: {}, addLayer(id, def) { this.layers[id] = { enabled: true, ...def }; } },
    shipPos(S) { const j = (S || Lab.state).journal || {}; if (j.star_pos) return { x: j.star_pos[0], y: j.star_pos[1], z: j.star_pos[2] }; return j.system && Lab.coords[j.system] ? Lab.coords[j.system] : null; },
  };

  // copy buttons anywhere
  document.body.addEventListener('click', e => { const b = e.target.closest('[data-copy]'); if (b) { Lab.util.copy(b.dataset.copy); const t = b.textContent; b.textContent = 'copied'; setTimeout(() => b.textContent = t, 900); } });

  // header
  Lab.on('journal', S => { const j = S.journal || {}; document.getElementById('h-cmdr').textContent = j.cmdr || '—'; document.getElementById('h-ship').textContent = [j.ship, j.ship_name, j.ship_ident].filter(Boolean).join(' · ') || '—'; document.getElementById('h-credits').textContent = fmt(j.credits); document.getElementById('h-ver').textContent = j.game_version || '—'; const live = document.getElementById('h-live'); if (j.last_event_time) live.textContent = 'live · ' + j.last_event_time.replace('T', ' ').replace('Z', ' UTC'); });

  // carrier coords for the map
  let coordsAsked = '';
  Lab.on('journal', async S => { const sys = S.journal?.carrier?.system; if (sys && !Lab.coords[sys] && coordsAsked !== sys) { coordsAsked = sys; try { Object.assign(Lab.coords, await Lab.api('/api/coords', { names: sys })); Lab.emit('journal'); } catch (e) { } } });

  function loadScript(src) { return new Promise((res, rej) => { const s = document.createElement('script'); s.src = src; s.onload = res; s.onerror = () => { console.error('failed to load', src); res(); }; document.head.appendChild(s); }); }

  function mountCards(manifest) {
    const grid = document.getElementById('grid');
    const cards = manifest.flatMap(m => m.cards.map(c => ({ ...c, module: m.name }))).sort((a, b) => (a.order || 100) - (b.order || 100));
    cards.forEach(c => {
      const def = Lab.cards[c.id];
      const sec = document.createElement('section'); sec.className = `card c${c.span || 3}`; sec.id = 'card-' + c.id;
      sec.innerHTML = `<h2>${esc(c.title)} <span class="right"></span></h2><div class="body"></div>`;
      grid.appendChild(sec);
      const body = sec.querySelector('.body'), head = sec.querySelector('.right');
      if (!def) { body.innerHTML = `<div class="muted">Card "${esc(c.id)}" from module ${esc(c.module)} did not register.</div>`; return; }
      try { if (def.header) def.header(head); if (def.mount) def.mount(body); } catch (e) { console.error(c.id, e); }
      const render = S => { try { def.render && def.render(body, S); } catch (e) { console.error(c.id, e); body.innerHTML = `<div class="bad">render error: ${esc(e.message)}</div>`; } };
      Lab.on(def.requires || [], render); render(Lab.state);
    });
  }

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
    mountCards(manifest);
    Object.keys(Lab.state).forEach(ns => Lab.emit(ns));
    connect();
  })();
})();
