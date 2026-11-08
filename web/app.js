/* EliteLab shell: state store fed by SSE, card registry, map layer registry, and a drag-and-drop layout.
   Modules load their card scripts from /modules/<name>/... and call Lab.card({...}) / Lab.map.addLayer(...). No build step. */
'use strict';
import {StateFeed} from './state-feed.js';
(() => {
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const fmt = n => (n == null || isNaN(n)) ? '—' : Number(n).toLocaleString();
  const ls = { get: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (e) { return d; } }, set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { } } };

  // ------------------------------------------------------------------ runtime
  const Lab = window.Lab = {
    state: {}, cards: {}, coords: {}, _subs: [], _pending: new Set(),
    util: {
      esc, fmt, ls,
      tabKeys: (list, selector) => list.addEventListener('keydown', event => {
        const tabs=[...list.querySelectorAll(selector)].filter(tab=>!tab.disabled),index=tabs.indexOf(event.target);
        if(index<0)return;
        const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:event.key==='ArrowRight'?(index+1)%tabs.length:event.key==='ArrowLeft'?(index+tabs.length-1)%tabs.length:-1;
        if(next<0)return;event.preventDefault();tabs[next].focus();tabs[next].click();
        list.querySelector('[aria-selected=true]')?.focus({preventScroll:true});
      }),
      inaraSys: n => `https://inara.cz/elite/starsystem/?search=${encodeURIComponent(n)}`,
      inaraSt: n => `https://inara.cz/elite/station/?search=${encodeURIComponent(n)}`,
      inaraMarket: (station, system) => {
        const name = String(station || '').trim(), place = String(system || '').trim();
        if (!name || ['Unknown stop', 'Carrier'].includes(name)) return null;
        return `https://inara.cz/elite/station-market/?search=${encodeURIComponent(place ? `${name} [${place}]` : name)}`;
      },
      spanshSys: n => `https://spansh.co.uk/search/${encodeURIComponent(n)}`,
      copy: t => navigator.clipboard && navigator.clipboard.writeText(t),
      dist3: (a, b) => Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z),
      // a labelled gauge: label + muted text above a segmented bar; colour is optional (background-color keeps the segments)
      bar: (label, pct, text, colour) => { const e = Lab.util.esc; return `<div class="gauge"><div class="k">${e(label)} <span class="muted">${e(text || '')}</span></div><div class="bar"><i style="width:${Math.max(0, Math.min(100, +pct || 0))}%${colour ? `;background-color:${e(colour)}` : ''}"></i></div></div>`; },
    },
    on(ns, fn) { const nss = Array.isArray(ns) ? ns : [ns]; const sub = { nss, fn }; this._subs.push(sub); return () => { this._subs = this._subs.filter(s => s !== sub); }; },
    emit(ns) { this._pending.add(ns); if (!this._raf) this._raf = requestAnimationFrame(() => { const p = new Set(this._pending); this._pending.clear(); this._raf = null; this._subs.slice().forEach(s => { if (s.nss.some(n => p.has(n))) { try { s.fn(this.state); } catch (e) { console.error(e); } } }); }); },
    set(ns, patch) { this.state[ns] = { ...(this.state[ns] || {}), ...patch }; this.emit(ns); },
    get(ns, key) { const d = this.state[ns] || {}; return key == null ? d : d[key]; },
    async response(r) { const data = await r.json(); if (!r.ok) { const error = new Error(data.error || `HTTP ${r.status}`); error.status = r.status; throw error; } return data; },
    async api(path, params) { const u = new URL(path, location.origin); Object.entries(params || {}).forEach(([k, v]) => { if (v != null && v !== '') u.searchParams.set(k, v); }); return this.response(await fetch(u)); },
    async post(path, body) { return this.response(await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })); },
    card(def) { this.cards[def.id] = def; },
    map: { layers: {}, addLayer(id, def) { this.layers[id] = { enabled: true, ...def }; } },
    shipPos(S) { const j = (S || Lab.state).journal || {}; if (j.star_pos) return { x: j.star_pos[0], y: j.star_pos[1], z: j.star_pos[2] }; return j.system && Lab.coords[j.system] ? Lab.coords[j.system] : null; },
    toast(msg, kind) { const t = document.createElement('div'); t.className = 'toast ' + (kind || ''); t.textContent = msg; document.getElementById('toasts').appendChild(t); setTimeout(() => t.classList.add('show'), 10); setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 300); }, 2600); },
    // cards call this to be told when their card is resized/moved (cheaper than a window resize)
    relayout() { if (this._relayoutRaf) return; this._relayoutRaf = requestAnimationFrame(() => { this._relayoutRaf = null; dispatchEvent(new Event('lab:relayout')); }); },
  };

  document.body.addEventListener('click', e => { const b = e.target.closest('[data-copy]'); if (b) { Lab.util.copy(b.dataset.copy); const t = b.textContent; b.textContent = 'copied'; setTimeout(() => b.textContent = t, 900); } });

  // header
  const stopHeader=Lab.on('journal', S => { const j = S.journal || {}; document.getElementById('h-cmdr').textContent = j.cmdr || '—'; document.getElementById('h-ship').textContent = [j.ship, j.ship_name, j.ship_ident].filter(Boolean).join(' · ') || '—'; document.getElementById('h-credits').textContent = fmt(j.credits); document.getElementById('h-ver').textContent = j.game_version || '—'; const live = document.getElementById('h-live'); if (j.last_event_time) live.textContent = 'live · ' + j.last_event_time.replace('T', ' ').replace('Z', ' UTC'); });

  // carrier coords for the map
  let coordsAsked = '';
  Lab.on('journal', async S => { const sys = S.journal?.carrier?.system; if (sys && !Lab.coords[sys] && coordsAsked !== sys) { coordsAsked = sys; try { Object.assign(Lab.coords, await Lab.api('/api/coords', { names: sys })); Lab.emit('journal'); } catch (e) { } } });

  function loadScript(src, type) { return new Promise(res => { const s = document.createElement('script'); if(type === 'module')s.type='module'; s.src = src; s.onload = res; s.onerror = () => { console.error('failed to load', src); res(); }; document.head.appendChild(s); }); }

  // ------------------------------------------------------------------ layout
  const LAYOUT_KEY = 'layout.v1';
  const grid = document.getElementById('grid');
  let allCards = [];                 // manifest cards, default order
  let layout = ls.get(LAYOUT_KEY, { order: [], spans: {}, hidden: [], collapsed: [], locked: false });
  // Preserve old synthesis-only layouts, including named/imported presets.
  function migrateLayout(l){
    if((l.order||[]).includes('synthesis')||Object.hasOwn(l.spans||{},'synthesis')){
      const hidden=l.hidden||[],wasVisible=!hidden.includes('synthesis');
      l={...l,order:[...new Set((l.order||[]).map(id=>id==='synthesis'?'wishlist':id))],
         hidden:wasVisible?hidden.filter(id=>id!=='wishlist'):hidden};
    }
    return l;
  }
  layout=migrateLayout(layout);
  const LAYOUT_TABS_KEY='layout.tabs.v1';
  let activeLayout=ls.get('layout.active.v1',{kind:'custom',name:''});
  if(!activeLayout||!['custom','preset','saved'].includes(activeLayout.kind))activeLayout={kind:'custom',name:''};
  const layoutToken=(kind,name='')=>kind==='custom'?'custom':kind+':'+name;
  const saveLayout = () => {ls.set(LAYOUT_KEY, layout);const tabs=ls.get(LAYOUT_TABS_KEY,{});tabs[layoutToken(activeLayout.kind,activeLayout.name)]=layout;ls.set(LAYOUT_TABS_KEY,tabs);};
  const WORKSPACES = {
    overview:{label:'Overview',description:'Ship, location and recent activity',cards:['location','ship','cargo','feed','map','credits']},
    materials:{label:'Materials / Recipes',description:'Saved recipes, shared materials and recorded synthesis',cards:['wishlist','build']},
    flight:{label:'Flight',description:'Route planning and ship status',cards:['neutron','ship','location','map','feed']},
    ship:{label:'Ship',description:'Loadout, integrity and engineering status',cards:['ship']},
    trade:{label:'Trading',description:'Sell cargo nearby or plan a round trip',cards:['selling','cargo','personal']},
    carrier:{label:'Carrier ops',description:'Plan loading, mining and crew operations',cards:['trade','haul','party','carrier']},
    ptn:{label:'PTN desk',description:'Carrier routes, station checks and affiliate trade adverts',cards:['ptn']},
    mining:{label:'Mining',description:'Mining sessions, locations and buyers',cards:['mining','cargo']},
    powerplay:{label:'Powerplay',description:'Pledge, merits, sell targets and combat',cards:['powerplay','merits','targets','loop','combat']},
    history:{label:'History',description:'Recorded balances, merit cycles and collection locations',cards:['history']},
    all:{label:'Layouts',description:'Choose a layout tab or arrange your own panels',cards:null}
  };
  let workspace=ls.get('workspace.v1',localStorage.getItem(LAYOUT_KEY)?'all':'overview');
  if(!WORKSPACES[workspace])workspace='overview';
  function workspaceView(){
    const chosen=WORKSPACES[workspace];
    const nav=document.getElementById('workspace-nav'),focused=nav.querySelector(':focus')?.dataset.workspace;
    nav.innerHTML=Object.entries(WORKSPACES).map(([k,v])=>`<button id="workspace-tab-${k}" role="tab" aria-controls="grid" tabindex="${k===workspace?0:-1}" data-workspace="${k}" aria-selected="${k===workspace}" aria-pressed="${k===workspace}">${esc(v.label)}</button>`).join('');
    if(focused)[...nav.querySelectorAll('button')].find(button=>button.dataset.workspace===workspace)?.focus({preventScroll:true});
    const heading=workspace==='all'?(activeLayout.kind==='custom'?'Custom layout':activeLayout.name):chosen.label;
    document.getElementById('workspace-heading').innerHTML=`<div><h2>${esc(heading)}</h2><p>${esc(chosen.description)}</p></div><span>${chosen.cards?'Workspace view; your custom layout is preserved.':'Layout tabs remember your panel arrangements.'}</span>`;
    grid.dataset.activeWorkspace=workspace;document.body.dataset.activeWorkspace=workspace;grid.setAttribute('role','tabpanel');grid.setAttribute('aria-labelledby','workspace-tab-'+workspace);
    renderLayoutTabs();
    // Workspace visibility is separate from saved custom layout preferences.
    orderedCards().filter(c=>(chosen.cards?chosen.cards.includes(c.id):!layout.hidden.includes(c.id))&&!mounted[c.id]).forEach(c=>grid.appendChild(buildCard(c)));
    Object.values(mounted).forEach(r=>{r.sec.classList.toggle('workspace-off',chosen.cards?!chosen.cards.includes(r.c.id):layout.hidden.includes(r.c.id));r.sec.style.order=chosen.cards?String(chosen.cards.indexOf(r.c.id)):'';});
    grid.classList.toggle('workspace-focused',workspace!=='all');
    Lab.relayout();
  }
  function setWorkspace(id){if(!WORKSPACES[id])return;workspace=id;ls.set('workspace.v1',id);workspaceView();}
  document.getElementById('workspace-nav').onclick=e=>{const b=e.target.closest('[data-workspace]');if(b)setWorkspace(b.dataset.workspace);};
  Lab.util.tabKeys(document.getElementById('workspace-nav'),'[data-workspace]');
  Lab.focusCard=id=>{setWorkspace(id==='wishlist'?'materials':id==='ptn'?'ptn':'all');if(!mounted[id])showCard(id);const card=mounted[id]?.sec;card?.classList.remove('collapsed');card?.scrollIntoView({block:'start',behavior:'smooth'});};

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
  // The grid always fills the window: 12 columns from laptop width up (cards scale with the window, rows that sum to 12 are
  // always full width), 6 columns on small windows (a span-4 card becomes two thirds, 6 and up full width), 1 on a phone.
  // Spans are nominal (designed for 12) and clamped to the column count; `dense` packing lets later small cards fill holes.
  let cols = 12;
  function computeCols() {
    const w = grid.clientWidth;
    const c = isMobile() ? 1 : (w < 1100 ? 6 : 12);
    if (c === cols) return false;
    cols = c; grid.style.setProperty('--cols', cols);
    Object.values(mounted).forEach(r => applySpan(r.sec, spanOf(r.c)));
    return true;
  }
  function applySpan(sec, n) {
    sec.style.gridColumn = `span ${Math.max(1, Math.min(n, cols))}`;
    const h = sec.querySelector('.resize'); if (h) h.dataset.span = n;
  }
  // Optional height cap per card (drag the corner downwards): the body scrolls inside instead of the card growing.
  function applyHeight(sec, px) {
    const body = sec.querySelector(':scope > .body'); if (!body) return;
    body.style.maxHeight = px ? px + 'px' : ''; body.style.overflowY = px ? 'auto' : '';
  }
  new ResizeObserver(() => { if (computeCols()) Lab.relayout(); }).observe(grid);

  function buildCard(c) {
    const def = Lab.cards[c.id];
    const sec = document.createElement('section'); sec.className = 'card'; sec.id = 'card-' + c.id; sec.dataset.id = c.id;
    if (layout.collapsed.includes(c.id) || (workspace==='trade'&&c.id==='personal')) sec.classList.add('collapsed');
    sec.innerHTML = `<h2><span class="grip" title="drag to move">⋮⋮</span><span class="title">${esc(c.title)}</span><span class="mod">${esc(c.module)}</span><span class="right"></span><span class="tools"><button class="icon" data-act="collapse" title="collapse">–</button><button class="icon" data-act="hide" title="hide">×</button></span></h2><div class="body"></div><div class="resize" title="drag to resize"></div>`;
    if(c.sources?.length){const footer=document.createElement('div');footer.className='card-sources note';footer.innerHTML='Sources: '+c.sources.filter(s=>/^https:\/\//.test(s.url)).map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.label)}</a>`).join(' | ');sec.querySelector('.body').after(footer);}
    applySpan(sec, spanOf(c));
    if ((layout.heights || {})[c.id]) applyHeight(sec, layout.heights[c.id]);
    const body = sec.querySelector('.body'), head = sec.querySelector('.right');
    const rec = { sec, def, body, c, off: () => { } };
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
    wireDrag(sec); wireResize(sec, c); wireKeyboard(sec, c);
    mounted[c.id] = rec;
    return sec;
  }
  function unmountCard(id) {
    const rec = mounted[id]; if (!rec) return;
    try { rec.off(); if (rec.def && rec.def.unmount) rec.def.unmount(rec.body); } catch (e) { console.error(id, e); }
    rec.sec.remove(); delete mounted[id];
  }

  function wireKeyboard(sec, c) {
    const title = sec.querySelector('h2');
    title.tabIndex = 0;
    title.title = 'Arrow keys: move; Shift+arrows: resize; Enter: collapse; Delete: hide';
    title.addEventListener('keydown', e => {
      if (e.target !== title || layout.locked) return;
      if (e.key === 'Enter') { e.preventDefault(); sec.querySelector('[data-act=collapse]').click(); return; }
      if (e.key === 'Delete') {
        e.preventDefault();
        const next = sec.nextElementSibling || sec.previousElementSibling;
        hideCard(c.id);
        (next?.querySelector('h2') || document.getElementById('layout-btn')).focus();
        return;
      }
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) return;
      e.preventDefault();
      const step = ['ArrowLeft', 'ArrowUp'].includes(e.key) ? -1 : 1;
      if (e.shiftKey) {
        const n = Math.max(2, Math.min(cols, spanOf(c) + step));
        layout.spans[c.id] = n; applySpan(sec, n);
      } else {
        const next = step < 0 ? sec.previousElementSibling : sec.nextElementSibling;
        if (next) grid.insertBefore(sec, step < 0 ? next : next.nextSibling);
        layout.order = [...grid.children].map(s => s.dataset.id);
        title.focus();
      }
      saveLayout(); Lab.relayout();
    });
  }
  function hideCard(id) { if (!layout.hidden.includes(id)) layout.hidden.push(id); saveLayout(); unmountCard(id); renderMenu(); }
  function showCard(id) {
    layout.hidden = layout.hidden.filter(i => i !== id); saveLayout();
    const c = allCards.find(x => x.id === id); if (!c || mounted[id]) return;
    // insert at its position in the ordered list
    const order = orderedCards().map(x => x.id); const idx = order.indexOf(id);
    const next = order.slice(idx + 1).map(i => mounted[i]).find(Boolean);
    const sec = buildCard(c); if (next) grid.insertBefore(sec, next.sec); else grid.appendChild(sec);
    setWorkspace('all');renderMenu(); Lab.relayout();
  }
  function mountCards() {
    Object.keys(mounted).forEach(unmountCard); grid.innerHTML = '';
    computeCols();
    orderedCards().forEach(c => { if (workspace==='all'?!layout.hidden.includes(c.id):WORKSPACES[workspace].cards.includes(c.id)) grid.appendChild(buildCard(c)); });
    grid.classList.toggle('locked', !!layout.locked);
    grid.classList.toggle('dense', layout.pack !== false);
    renderMenu(); workspaceView(); Lab.relayout();
  }

  // One interaction at a time. Listeners live on the window, never on the dragged element: moving a card in the DOM
  // would otherwise drop the browser's pointer capture mid-drag and the drag could never end.
  let gesture = null;
  function endGesture() { if (gesture) { const g = gesture; gesture = null; try { g.end(); } catch (e) { console.error(e); } } }
  addEventListener('pointerup', e => { if (gesture) { gesture.move(e); endGesture(); } }, true);
  addEventListener('pointercancel', endGesture, true);
  addEventListener('blur', endGesture);
  addEventListener('keydown', e => { if (e.key === 'Escape') endGesture(); });
  addEventListener('pointermove', e => { if (gesture) { if (!(e.buttons & 1)) return endGesture(); gesture.move(e); } }, true);

  // drag to reorder: moves throttled to animation frames, a light ghost follows the pointer
  function wireDrag(sec) {
    const h2 = sec.querySelector('h2');
    h2.addEventListener('pointerdown', e => {
      if (gesture || layout.locked || isMobile() || e.button !== 0 || e.target.closest('button, a, input, select, .right')) return;
      e.preventDefault();
      const r = sec.getBoundingClientRect(); const ox = e.clientX - r.left, oy = e.clientY - r.top;
      const ghost = document.createElement('div'); ghost.className = 'card ghost'; ghost.style.width = r.width + 'px'; ghost.style.height = Math.min(r.height, 160) + 'px';
      ghost.innerHTML = `<h2><span class="title">${sec.querySelector('.title').textContent}</span></h2>`;
      document.body.appendChild(ghost); sec.classList.add('dragging'); grid.classList.add('is-dragging'); document.body.classList.add('no-select');
      let last = { x: e.clientX, y: e.clientY }, raf = null;
      const place = () => {
        raf = null; if (!sec.isConnected) return;
        ghost.style.transform = `translate(${last.x - ox}px, ${last.y - oy}px)`;
        const under = document.elementFromPoint(last.x, last.y);     // ghost has pointer-events:none, so it is skipped
        const target = under && under.closest('#grid > .card'); if (!target || target === sec) return;
        const tr = target.getBoundingClientRect(); const before = (last.x - tr.left) < tr.width / 2;
        const want = before ? target : target.nextSibling;
        if (want !== sec && sec.nextSibling !== want) grid.insertBefore(sec, want);
      };
      gesture = {
        move: ev => { last = { x: ev.clientX, y: ev.clientY }; if (!raf) raf = requestAnimationFrame(place); },
        end: () => {
          if (raf) { cancelAnimationFrame(raf); raf = null; } place();
          ghost.remove(); sec.classList.remove('dragging'); grid.classList.remove('is-dragging'); document.body.classList.remove('no-select');
          layout.order = [...grid.querySelectorAll(':scope > .card')].map(s => s.dataset.id); saveLayout(); Lab.relayout();
        },
      };
      place();
    });
  }

  // drag the corner to resize in grid columns
  function wireResize(sec, c) {
    const handle = sec.querySelector('.resize');
    handle.addEventListener('pointerdown', e => {
      if (gesture || layout.locked || isMobile() || e.button !== 0) return;
      e.preventDefault(); document.body.classList.add('no-select');
      const startX = e.clientX, startY = e.clientY, start = Math.min(spanOf(c), cols); const col = grid.clientWidth / cols;
      const body = sec.querySelector(':scope > .body'); const startH = body.getBoundingClientRect().height;
      let cur = start, curH = (layout.heights || {})[c.id] || 0, raf = null, lastX = startX, lastY = startY, moved = false;
      const apply = () => {
        raf = null;
        const n = Math.max(2, Math.min(cols, Math.round(start + (lastX - startX) / col)));
        if (n !== cur) { cur = n; applySpan(sec, n); Lab.relayout(); }
        const dy = lastY - startY;
        if (Math.abs(dy) > 12 || moved) {                       // vertical drag caps the body height; drag past the bottom to uncap
          moved = true;
          const h = Math.round(startH + dy);
          curH = (h >= body.scrollHeight + 8) ? 0 : Math.max(120, h);
          applyHeight(sec, curH); Lab.relayout();
        }
      };
      gesture = {
        move: ev => { lastX = ev.clientX; lastY = ev.clientY; if (!raf) raf = requestAnimationFrame(apply); },
        end: () => {
          if (raf) { cancelAnimationFrame(raf); raf = null; } apply(); document.body.classList.remove('no-select');
          layout.spans[c.id] = cur; layout.heights = layout.heights || {};
          if (curH) layout.heights[c.id] = curH; else delete layout.heights[c.id];
          saveLayout(); Lab.relayout();
        },
      };
    });
    handle.addEventListener('dblclick', () => {              // reset: nominal width, no height cap (or full width when already nominal)
      const capped = !!(layout.heights || {})[c.id];
      const n = (capped || spanOf(c) >= cols) ? (c.span || 3) : cols;
      applySpan(sec, n); layout.spans[c.id] = n;
      if (capped) { delete layout.heights[c.id]; applyHeight(sec, 0); }
      saveLayout(); Lab.relayout();
    });
  }

  // presets: order + spans + hidden. Cards not listed in `order` follow in manifest order; cards in `hidden` are off.
  const ALL = () => allCards.map(c => c.id);
  const ENG = ['recipes', 'wishlist', 'farming', 'build'];       // engineering cards, hidden by the non-engineering presets
  const PRESETS = {
    'Expedition': () => ({ order: ['neutron', 'ship', 'wishlist', 'location', 'feed'],
      spans: { neutron: 8, ship: 4, wishlist: 12, location: 4, map: 8, feed: 4 },
      hidden: ALL().filter(id => !['neutron', 'ship', 'wishlist', 'location', 'feed'].includes(id)) }),

    'Rare goods': () => ({ order: ['loop', 'cargo', 'market', 'targets', 'location'],
        spans: { loop: 12, cargo: 6, market: 6, targets: 12, map: 8, location: 4 },
        hidden: ALL().filter(id => !['loop', 'cargo', 'market', 'targets', 'location'].includes(id)) }),
    'Trading': () => ({ order: ['personal', 'cargo', 'ship', 'location', 'market', 'feed'],
      spans: { personal: 12, cargo: 4, ship: 4, location: 4, market: 4, map: 8, feed: 4 },
      hidden: ALL().filter(id => !['personal', 'cargo', 'ship', 'location', 'market', 'feed'].includes(id)) }),
    'Carrier ops': () => ({ order: ['haul', 'party', 'trade', 'carrier', 'cargo', 'location', 'ship', 'feed'],
      spans: { haul: 5, party: 7, trade: 12, carrier: 4, cargo: 4, location: 4, ship: 4, map: 8, feed: 4 },
      hidden: ALL().filter(id => !['haul', 'trade', 'party', 'carrier', 'cargo', 'location', 'ship', 'feed'].includes(id)) }),
    'Default': () => ({ order: ['location', 'ship', 'build', 'wishlist', 'farming', 'recipes', 'materials', 'powerplay', 'merits', 'targets', 'combat', 'feed', 'cargo', 'market', 'carrier', 'loop'],
      spans: { location: 4, ship: 4, build: 4, wishlist: 6, farming: 6, recipes: 4, materials: 4, powerplay: 4, merits: 4, targets: 12, combat: 12, feed: 4, cargo: 4, market: 4, carrier: 4, loop: 4, map: 12 }, hidden: [] }),
    'Powerplay': () => ({ order: ['powerplay', 'merits', 'targets', 'combat', 'location', 'loop', 'cargo', 'ship', 'feed'],
      spans: { map: 8, powerplay: 4, merits: 4, targets: 12, combat: 12, location: 4, loop: 4, cargo: 4, ship: 4, feed: 4 }, hidden: ['materials', 'market', 'carrier', ...ENG] }),
    'Rares run': () => ({ order: ['loop', 'cargo', 'market', 'location', 'targets', 'merits', 'ship', 'feed'],
      spans: { loop: 4, cargo: 4, market: 4, map: 8, location: 4, targets: 12, merits: 4, ship: 4, feed: 4 }, hidden: ['combat', 'materials', 'carrier', 'powerplay', ...ENG] }),
    'Combat': () => ({ order: ['merits', 'ship', 'location', 'combat', 'feed', 'powerplay'],
      spans: { merits: 4, ship: 4, location: 4, combat: 12, map: 8, feed: 4, powerplay: 4 }, hidden: ['loop', 'targets', 'materials', 'market', 'cargo', 'carrier', ...ENG] }),
    'Mining & trade': () => ({ order: ['mining', 'cargo', 'ship', 'trade', 'party', 'carrier', 'market', 'targets', 'location', 'merits', 'feed'],
      spans: { mining: 12, trade: 8, party: 4, cargo: 4, carrier: 4, market: 4, ship: 4, targets: 12, map: 8, location: 4, merits: 4, feed: 4 }, hidden: ['loop', 'combat', 'materials', 'powerplay', ...ENG] }),
    'Engineering': () => ({ order: ['materials', 'wishlist', 'build', 'farming', 'recipes', 'ship', 'location', 'feed'],
      spans: { build: 6, wishlist: 6, farming: 6, recipes: 6, materials: 6, ship: 4, location: 4, map: 12, feed: 4 },
      hidden: ['loop', 'targets', 'combat', 'market', 'powerplay', 'merits', 'carrier', 'cargo'] }),
    'Second screen': () => ({ order: ['ship', 'location', 'cargo', 'merits', 'feed'], spans: { ship: 6, location: 6, cargo: 4, merits: 4, feed: 4 }, heights: {ship:340,feed:240,cargo:240},
      hidden: ALL().filter(id => !['ship', 'location', 'cargo', 'merits', 'feed'].includes(id)) }),
  };
  const PRIMARY_PRESETS = ['Expedition','Rare goods','Second screen'];
  const visiblePresets=()=>Object.keys(PRESETS).filter(name=>PRIMARY_PRESETS.includes(name)||(activeLayout.kind==='preset'&&activeLayout.name===name)||Object.hasOwn(ls.get(LAYOUT_TABS_KEY,{}),layoutToken('preset',name)));
  const SAVED_KEY = 'layouts.v1';
  const savedLayouts = () => ls.get(SAVED_KEY, {});
  function applyLayout(l, name, selection={kind:'custom',name:''}) {saveLayout();activeLayout=selection;ls.set('layout.active.v1',activeLayout);l=migrateLayout(l);workspace='all';ls.set('workspace.v1','all');layout = { order: l.order || [], spans: l.spans || {}, heights: l.heights || {}, hidden: l.hidden || [], collapsed: l.collapsed || [], locked: !!l.locked, pack: l.pack !== false }; saveLayout(); mountCards(); if (name) Lab.toast(`Layout: ${name}`); }
  function selectLayout(kind,name=''){
    const token=layoutToken(kind,name),tabs=ls.get(LAYOUT_TABS_KEY,{});
    const candidate=tabs[token]||(kind==='preset'?PRESETS[name]?.():kind==='saved'?savedLayouts()[name]:layout);
    if(candidate)applyLayout(candidate,kind==='custom'?'Custom':name,{kind,name});
  }
  function renderLayoutTabs(){
    const nav=document.getElementById('layout-tabs');nav.hidden=workspace!=='all';
    const saved=savedLayouts();
    if((activeLayout.kind==='preset'&&!Object.hasOwn(PRESETS,activeLayout.name))||(activeLayout.kind==='saved'&&!Object.hasOwn(saved,activeLayout.name))){activeLayout={kind:'custom',name:''};ls.set('layout.active.v1',activeLayout);}
    const choices=[{kind:'custom',name:'',label:'Custom'},...visiblePresets().map(name=>({kind:'preset',name,label:name})),...Object.keys(saved).map(name=>({kind:'saved',name,label:name}))];
    const focused=nav.querySelector(':focus'),hadFocus=!!focused;
    nav.innerHTML=choices.map((choice,index)=>{const selected=choice.kind===activeLayout.kind&&choice.name===activeLayout.name;return `<button id="layout-tab-${index}" role="tab" aria-controls="grid" aria-selected="${selected}" tabindex="${selected?0:-1}" data-layout-kind="${choice.kind}" data-layout-name="${esc(choice.name)}">${esc(choice.label)}${choice.kind==='saved'?'<span class="layout-saved-mark">saved</span>':''}</button>`;}).join('');
    if(hadFocus)nav.querySelector('[aria-selected=true]')?.focus({preventScroll:true});
    if(workspace==='all')grid.setAttribute('aria-labelledby',nav.querySelector('[aria-selected=true]')?.id||'workspace-tab-all');
  }
  document.getElementById('layout-tabs').onclick=event=>{const button=event.target.closest('[data-layout-kind]');if(button)selectLayout(button.dataset.layoutKind,button.dataset.layoutName);};
  Lab.util.tabKeys(document.getElementById('layout-tabs'),'[data-layout-kind]');

  // layout menu
  const menu = document.getElementById('layout-menu');
  function renderMenu() {
    const saved = savedLayouts();
    menu.innerHTML = `
      <div class="menu-row"><label><input type="checkbox" id="lm-lock" ${layout.locked ? 'checked' : ''}> lock</label><label title="let smaller cards move up to fill gaps left by wide ones"><input type="checkbox" id="lm-pack" ${layout.pack !== false ? 'checked' : ''}> fill gaps</label><label title="beep with alerts (merits, low fuel, interdiction, carrier jump)"><input type="checkbox" id="lm-sound" ${Lab.notifySound && Lab.notifySound() ? 'checked' : ''}> sound</label><button class="mini" id="lm-export">export</button><button class="mini" id="lm-import">import</button></div>
      <div class="menu-sec">Reset to preset</div>
      <div class="menu-chips">${PRIMARY_PRESETS.map(n => `<button class="mini" data-preset="${esc(n)}">${esc(n)}</button>`).join('')}</div>
      <details><summary>Additional presets</summary><div class="menu-chips">${Object.keys(PRESETS).filter(n=>!PRIMARY_PRESETS.includes(n)).map(n=>`<button class="mini" data-preset="${esc(n)}">${esc(n)}</button>`).join('')}</div></details>
        <div class="menu-sec">Saved layouts</div>
      <div class="menu-row"><input id="lm-name" placeholder="name this layout" size="16"><button class="mini primary" id="lm-save">save current</button></div>
      <div class="menu-chips">${Object.keys(saved).length ? Object.keys(saved).map(n => `<span class="chip"><button class="mini" data-load="${esc(n)}">${esc(n)}</button><button class="mini icon" data-del="${esc(n)}" title="delete">×</button></span>`).join('') : '<span class="muted" style="font-size:12px">none yet</span>'}</div>
      <div class="menu-sec">Cards</div>
      <div class="menu-list">${orderedCards().map(c => `<label><input type="checkbox" data-id="${esc(c.id)}" ${layout.hidden.includes(c.id) ? '' : 'checked'}> ${esc(c.title)} <span class="muted">${esc(c.module)}</span></label>`).join('')}</div>
      <div class="muted" style="font-size:11px;margin-top:6px">Drag a title bar to move. Drag the corner sideways for width, downwards to cap a card's height (it scrolls inside); double-click the corner to reset or go full width. The grid fills the window (${cols} columns now). Everything here is saved in this browser.</div>`;
    menu.querySelector('#lm-lock').onchange = e => { layout.locked = e.target.checked; saveLayout(); grid.classList.toggle('locked', layout.locked); };
    menu.querySelector('#lm-pack').onchange = e => { layout.pack = e.target.checked; saveLayout(); grid.classList.toggle('dense', layout.pack); Lab.relayout(); };
    menu.querySelector('#lm-sound').onchange = e => { if (Lab.notifySoundToggle) Lab.notifySoundToggle(e.target.checked); };
    menu.querySelector('#lm-export').onclick = () => { Lab.util.copy(JSON.stringify(layout)); Lab.toast('Layout JSON copied to clipboard'); };
    menu.querySelector('#lm-import').onclick = () => { const s = prompt('Paste layout JSON'); if (!s) return; try { applyLayout(JSON.parse(s), 'imported'); } catch (e) { Lab.toast('Invalid layout JSON', 'bad'); } };
    menu.querySelectorAll('[data-preset]').forEach(b => b.onclick = () => applyLayout(PRESETS[b.dataset.preset](),b.dataset.preset,{kind:'preset',name:b.dataset.preset}));
    menu.querySelector('#lm-save').onclick = () => { const n = menu.querySelector('#lm-name').value.trim(); if (!n) return Lab.toast('Give the layout a name', 'bad'); const snapshot={ ...layout, order: [...grid.querySelectorAll(':scope > .card')].map(s => s.dataset.id) }; ls.set(SAVED_KEY,{...savedLayouts(),[n]:snapshot});const tabs=ls.get(LAYOUT_TABS_KEY,{});tabs[layoutToken('saved',n)]=snapshot;ls.set(LAYOUT_TABS_KEY,tabs);renderMenu();Lab.toast(`Saved layout "${n}"`); };
    menu.querySelectorAll('[data-load]').forEach(b => b.onclick = () => applyLayout(savedLayouts()[b.dataset.load],b.dataset.load,{kind:'saved',name:b.dataset.load}));
    menu.querySelectorAll('[data-del]').forEach(b => b.onclick = () => { const name=b.dataset.del,all=savedLayouts();delete all[name];ls.set(SAVED_KEY,all);if(activeLayout.kind==='saved'&&activeLayout.name===name)selectLayout('custom');const tabs=ls.get(LAYOUT_TABS_KEY,{});delete tabs[layoutToken('saved',name)];ls.set(LAYOUT_TABS_KEY,tabs);renderMenu(); });
    menu.querySelectorAll('input[data-id]').forEach(cb => cb.onchange = () => { cb.checked ? showCard(cb.dataset.id) : hideCard(cb.dataset.id); });
    renderLayoutTabs();
  }
  document.getElementById('layout-btn').onclick = e => { e.stopPropagation(); menu.classList.toggle('open'); };

  // UI health: measures frame gaps and warns in the footer when the page is struggling (shown only when visible)
  (() => { let last = performance.now(), worst = 0; const el = document.getElementById('f-perf');
    const tick = now => { const gap = now - last; last = now; if (document.visibilityState === 'visible' && gap > worst) worst = gap; requestAnimationFrame(tick); }; requestAnimationFrame(tick);
    setInterval(() => { if (!el) return; el.textContent = worst > 120 ? ` · UI stalled ${Math.round(worst)} ms` : ''; el.className = worst > 120 ? 'bad' : 'muted'; worst = 0; }, 2000); })();
  document.addEventListener('click', e => { if (!e.target.closest('#layout-menu, #layout-btn')) menu.classList.remove('open'); });
  addEventListener('resize', () => Lab.relayout());

  // ------------------------------------------------------------------ notifications (issue 5)
  // Toasts for things worth looking up from the HOTAS: merits gained, loop complete, fuel under 25 percent, interdiction,
  // death, carrier jump lock. Optional beep (Web Audio, no asset) toggled in the layout menu; audio needs a user gesture
  // first, so the context is created when the checkbox is ticked.
  (() => {
    const SOUND_KEY = 'notify.sound';
    let audio = null, seen = null, lastMerits = null, lowFuel = null, loopDone = null, armed = false;
    const audioReady = () => {      // browsers only let audio start after a gesture; create/resume on the first click or key
      try { audio = audio || new (window.AudioContext || window.webkitAudioContext)(); if (audio.state === 'suspended') audio.resume(); } catch (e) { }
    };
    addEventListener('pointerdown', audioReady, { once: true }); addEventListener('keydown', audioReady, { once: true });
    const beep = () => {
      if (!ls.get(SOUND_KEY)) return;
      try {
        audioReady();
        const o = audio.createOscillator(), g = audio.createGain();
        o.frequency.value = 880; g.gain.value = 0.08; o.connect(g); g.connect(audio.destination);
        o.start(); o.stop(audio.currentTime + 0.12);
      } catch (e) { }
    };
    const notify = (msg, kind) => { Lab.toast(msg, kind); beep(); };
    const EVENTS = { Interdicted: ['Interdicted!', 'bad'], Died: ['Ship destroyed', 'bad'], CarrierJumpRequest: ['Carrier jump scheduled: lock-down soon', ''],
                     CarrierJump: ['Carrier jumped', ''], CarrierJumpCancelled: ['Carrier jump cancelled', ''] };
    const same = (a, b) => a && b && a.ts === b.ts && a.event === b.event && a.text === b.text;
    Lab.on(['journal', 'powerplay', 'loop'], S => {
      const j = S.journal || {}, feed = j.feed || [];               // newest first
      if (!armed) {                                   // first render: remember where we are, do not replay history as alerts
        seen = feed[0] || null; lastMerits = (S.powerplay || {}).session_merits ?? null;
        loopDone = (S.loop || {}).complete ?? null; armed = true;
      } else {
        // everything above the last entry we saw is new; same-second events are fine because we match the entry itself,
        // and a snapshot that rewinds the feed (server replaying) cannot move the marker backwards
        let idx = seen ? feed.findIndex(f => same(f, seen)) : feed.length;
        if (idx < 0) idx = seen ? feed.filter(f => f.ts > seen.ts).length : feed.length;
        feed.slice(0, idx).reverse().forEach(f => { const spec = EVENTS[f.event]; if (spec) notify(spec[0], spec[1]); });
        if (feed[0] && (!seen || feed[0].ts >= seen.ts)) seen = feed[0];
        const m = (S.powerplay || {}).session_merits;
        if (m != null && lastMerits != null && m > lastMerits) notify(`+${(m - lastMerits).toLocaleString()} merits`);
        if (m != null) lastMerits = m;
        const done = (S.loop || {}).complete;
        if (done === true && loopDone === false) notify('Rares loop complete: everything is aboard');
        if (done != null) loopDone = done;
      }
      const cap = (j.ship_info || {}).fuel_main, fuel = (j.status || {}).fuel;
      if (cap && fuel != null) { const low = fuel / cap < 0.25; if (low && lowFuel === false) notify(`Fuel under 25% (${fuel.toFixed(1)} of ${cap} t)`, 'bad'); lowFuel = low; }
    });
    Lab.notifySoundToggle = on => { ls.set(SOUND_KEY, !!on); if (on) beep(); };
    Lab.notifySound = () => !!ls.get(SOUND_KEY);
  })();

  // ------------------------------------------------------------------ live connection
  function applySnapshot(snap) { Object.keys(snap).forEach(ns => { if (ns !== '_version') Lab.state[ns] = { ...(Lab.state[ns] || {}), ...snap[ns] }; }); Lab._v = snap._version || 0; Object.keys(Lab.state).forEach(ns => Lab.emit(ns)); }
  const feed=new StateFeed({fetchSnapshot:()=>Lab.api('/api/state'),snapshot:applySnapshot,
    change:m=>{Lab._v=m.v;(Lab.state[m.ns]=Lab.state[m.ns] || {})[m.key]=m.value;Lab.emit(m.ns);}});

  function connect() {
    const live = document.getElementById('h-live');
    const es = Lab.events = new EventSource('/events');
    es.addEventListener('snapshot', e => { feed.reset(JSON.parse(e.data)); live.classList.add('live'); });
    es.addEventListener('state', e => {
      feed.receive(JSON.parse(e.data));
    });
    es.onerror = () => { live.classList.remove('live'); live.textContent = 'reconnecting…'; };
  }

  async function boot() {
    const live = document.getElementById('h-live');
    try {
      await checkHealth();
      const manifest = await Lab.api('/api/modules');
      document.getElementById('f-modules').textContent = 'modules: ' + manifest.map(m => m.name).join(', ');
      const scripts = new Map(manifest.flatMap(m => m.cards.map(c => [c.script,c.script_type])));
      await Promise.all([...scripts].map(([src,type])=>loadScript(src,type))); // module scripts may import their own helpers before cards mount
      feed.reset(await Lab.api('/api/state'));
      allCards = manifest.flatMap(m => m.cards.map(c => ({ ...c, module: m.name }))).sort((a, b) => (a.order || 100) - (b.order || 100));
      mountCards();
      Object.keys(Lab.state).forEach(ns => Lab.emit(ns));
      connect();
    } catch (e) {
      if (e.status === 401) {
        live.textContent = 'sign in required';
        grid.innerHTML = '<section class="card" style="grid-column: 1 / -1"><h2>Sign in to EliteLab</h2><form id="login-form"><label>Access token <input type="password" name="token" required autocomplete="current-password"></label> <button type="submit">Sign in</button><p id="login-error" role="alert"></p></form></section>';
        document.getElementById('login-form').onsubmit = async event => {
          event.preventDefault();
          try { await Lab.post('/api/login', { token: event.target.elements.token.value }); event.target.reset(); boot(); }
          catch (error) { document.getElementById('login-error').textContent = error.message; }
        };
        return;
      }
      console.error('boot failed', e);
      live.classList.remove('live'); live.textContent = 'server unreachable, retrying';
      document.getElementById('grid').innerHTML = `<section class="card" style="grid-column: 1 / -1"><h2><span class="title">Cannot reach EliteLab</span></h2><div class="body"><div class="muted">${esc(e.message)}. Is the server running on this address? Retrying in 3 s.</div></div></section>`;
      setTimeout(boot, 3000);
    }
  }
  async function checkHealth() {
    const health = await Lab.api('/api/health');
    let banner = document.getElementById('journal-warning');
    if (health.journal_found) { banner?.remove(); return; }
    if (!banner) {
      banner = document.createElement('div'); banner.id = 'journal-warning';
      banner.className = 'journal-warning'; banner.setAttribute('role', 'status');
      grid.before(banner);
    }
    const link = document.createElement('a'); link.href = '/setup/'; link.textContent = 'Open setup';
    banner.replaceChildren(
      `No journal files found in ${health.journal_dir}. `, link,
      ' to choose your journal folder. In Docker, mount the folder read-only at /journals.');
  }
  Lab.checkHealth = checkHealth;
  const healthTimer=setInterval(() => checkHealth().catch(() => {}), 30000);
  document.getElementById('app-quit').onclick=async e=>{
    const button=e.currentTarget;button.disabled=true;
    try {
      await Lab.post('/api/shutdown');
      stopHeader();Lab.events?.close();feed.stop();clearInterval(healthTimer);Object.keys(mounted).forEach(unmountCard);
      document.getElementById('h-live').textContent='stopped';
      document.getElementById('h-live').classList.remove('live');
      grid.innerHTML='<section class="card" style="grid-column:1/-1"><h2>EliteLab stopped</h2><p>The party is closing. You can close this tab and use Start EliteLab to launch again.</p></section>';
    } catch(error){Lab.toast(error.message,'bad');button.disabled=false;}
  };
  boot();
})();
