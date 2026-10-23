/* loop card: server computes the loop; this renders it, adds manual ticks (localStorage) and a map layer. */
(() => {
  const { esc, inaraSys, ls } = Lab.util;
  // Manual overrides: {system: {done: bool, tons: n}}. An override only applies while the tons of that
  // station's rares in the hold are unchanged, so selling (or buying) naturally clears it.
  const manual = () => ls.get('loopManual', {});
  const effectiveDone = (s, m) => { const o = m[s.system]; return (o && typeof o === 'object' && o.tons === s.tons) ? o.done : (o === true ? true : s.done); };
  Lab.card({
    id: 'loop', requires: ['loop', 'journal'],
    header(h) {
      h.innerHTML = `<select class="mini" id="loop-pick"></select> <button class="mini" id="loop-reset">reset ticks</button>`;
      h.querySelector('#loop-reset').onclick = () => { ls.set('loopManual', {}); Lab.emit('loop'); };
      h.querySelector('#loop-pick').onchange = e => Lab.post('/api/loop/select', { id: e.target.value });
    },
    render(el, S) {
      const L = S.loop || {}; const st = L.stations || []; const m = manual();
      const pick = el.closest('.card').querySelector('#loop-pick');
      if (pick && pick.options.length !== (L.available || []).length) { pick.innerHTML = (L.available || []).map(a => `<option value="${esc(a.id)}">${esc(a.name)}</option>`).join(''); }
      if (pick) pick.value = L.id || '';
      const rows = st.map(s => ({ ...s, done: effectiveDone(s, m) })).sort((a, b) => (a.done - b.done) || ((a.dist ?? 9999) - (b.dist ?? 9999)));
      const done = rows.filter(r => r.done).length; const next = rows.find(r => !r.done);
      el.innerHTML = `
        <div class="muted" style="font-size:12px;margin-bottom:6px">${done}/${rows.length} stations · <b>${L.tons_total || 0} t</b> of loop rares aboard${next ? ` · next: <b class="accent">${esc(next.system)}</b>${next.dist != null ? ` (${next.dist} Ly)` : ''}` : (rows.length && done === rows.length ? ' · <b class="ok">loop complete, go sell</b>' : '')}</div>
        <div class="bar"><i style="width:${rows.length ? 100 * done / rows.length : 0}%"></i></div>
        <div style="margin-top:6px">${rows.map(s => `
          <label class="chk ${s.done ? 'done' : ''}" ${next && next.system === s.system ? 'style="border-left:3px solid var(--accent);padding-left:6px"' : ''}>
            <input type="checkbox" data-sys="${esc(s.system)}" ${s.done ? 'checked' : ''} title="${s.in_hold ? 'auto-ticked from your hold; untick to override (e.g. a station refused this rare)' : 'tick manually'}">
            <span class="n"><b>${esc(s.system)}</b> · ${esc(s.station)} <span class="muted">(${esc(s.type)}, ${s.ls} ls${s.dist != null ? ` · ${s.dist} Ly from you` : ''})</span>${s.docked_here ? ' <span class="tag ok">docked here</span>' : ''}<br>
              ${s.rares.map(r => `<span class="tag rare">${esc(r.name)}</span>`).join(' ')}${s.tons ? ` <span class="tag ${s.done ? 'ok' : 'warn'}">${s.tons} t aboard${!s.done ? ', unsold' : ''}</span>` : ''}</span>
            <span><button class="mini" data-copy="${esc(s.system)}">copy</button> <a href="${inaraSys(s.system)}" target="_blank">Inara</a></span>
          </label>`).join('')}</div>
        <div class="note">${esc(L.note || '')} Stations tick themselves when their rare is in your hold and clear after you sell; distances are live from your current system.</div>`;
      el.querySelectorAll('input[data-sys]').forEach(cb => cb.onchange = () => { const d = manual(); const s = st.find(x => x.system === cb.dataset.sys) || { tons: 0 }; d[cb.dataset.sys] = { done: cb.checked, tons: s.tons }; ls.set('loopManual', d); Lab.emit('loop'); });
    },
  });

  Lab.map.addLayer('loop', {
    label: 'rares loop', color: '#9be36b', z: 2,
    points: S => (S.loop?.stations || []).filter(s => s.coords).map(s => ({ name: s.system, ...s.coords, r: 4, color: effectiveDone(s, manual()) ? '#5c8a46' : '#9be36b', label: true,
      sub: `${s.station} · ${s.rares.map(r => r.name).join(', ')}${s.tons ? ` · ${s.tons} t aboard` : ''}` })),
  });
})();
