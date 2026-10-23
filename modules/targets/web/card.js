/* targets card: Powerplay sell-target finder + power comparison. Publishes results to Lab.state.targets (client side)
   and registers a map layer. */
(() => {
  const { esc, fmt, inaraSt, spanshSys } = Lab.util;
  let refTouched = false;

  Lab.card({
    id: 'targets', requires: ['journal', 'powerplay', 'targets'],
    mount(el) {
      el.innerHTML = `
        <div class="row">
          <label>Power <select id="t-power"></select></label>
          <label>From <input id="t-ref" size="18" placeholder="current system" title="Follows your current system until you type your own"></label>
          <label>Min Ly <input id="t-min" size="4" value="125"></label>
          <label>Max Ly <input id="t-max" size="4" value="165"></label>
          <label>Pad <select id="t-pad"><option value="L">Large starports</option><option value="M">Include outposts</option></select></label>
          <button class="primary" id="t-go">Find targets</button>
          <button id="t-here">Use current system</button>
          <button id="t-compare">Compare powers</button>
          <span class="muted" id="t-status"></span>
        </div>
        <table><thead><tr><th>System</th><th>Station</th><th class="num">Ly</th><th class="num" title="at max unladen jump range; laden needs more">Jumps</th><th class="num">ls</th><th>Type</th><th>Pad</th><th class="num">Pop</th><th>Market data</th><th></th></tr></thead>
        <tbody id="t-body"><tr><td class="muted" colspan="10">Rare goods pay best around 130 to 160 Ly from where you bought them. Set the band and hit Find; results also plot on the map.</td></tr></tbody></table>
        <div id="t-compare-out"></div>
        <div class="note">Data from Spansh (community-updated). An old market date means nobody has docked there recently. Rares must be bought outside the system you sell them in and must not have been on a fleet carrier.</div>`;
      const $ = s => el.querySelector(s);
      const sel = $('#t-power');
      (Lab.state.powerplay?.powers || []).forEach(p => { const o = document.createElement('option'); o.value = o.textContent = p; sel.appendChild(o); });
      $('#t-ref').addEventListener('input', () => { refTouched = $('#t-ref').value.trim() !== ''; });
      $('#t-here').onclick = () => { refTouched = false; $('#t-ref').value = Lab.state.journal?.system || ''; find(); };
      $('#t-go').onclick = find;
      $('#t-compare').onclick = compare;
      $('#t-body').addEventListener('click', e => {
        const tr = e.target.closest('tr[data-i]'); if (!tr || e.target.closest('a,button')) return;
        const t = (Lab.state.targets?.last?.results || [])[+tr.dataset.i]; select(t);
      });

      async function find() {
        const params = { power: sel.value, ref: $('#t-ref').value.trim() || undefined, min: $('#t-min').value, max: $('#t-max').value, pad: $('#t-pad').value };
        $('#t-status').textContent = 'querying Spansh…'; $('#t-compare-out').innerHTML = '';
        try {
          const d = await Lab.api('/api/targets', params); if (d.error) throw new Error(d.error);
          // The server stores the result as targets.last and pushes it over SSE; the card renders from there, so a
          // search made by an AI tool call shows up here too. Only the selection is client-side.
          Lab.set('targets', { selected: null });
          $('#t-status').textContent = `${fmt(d.count)} stations match; showing nearest ${d.results.length} from ${d.ref}${d.jump_range ? ` · jumps at ${d.jump_range.toFixed(1)} Ly max range` : ''}`;
        } catch (e) { $('#t-status').textContent = 'error: ' + e.message; }
      }
      async function compare() {
        $('#t-status').textContent = 'comparing all powers (first run takes ~20 s)…';
        try {
          const d = await Lab.api('/api/powers', { ref: $('#t-ref').value.trim() || undefined });
          $('#t-compare-out').innerHTML = `<table style="margin-top:10px"><thead><tr><th>Power</th><th class="num">Acquisition starports</th><th>Nearest to ${esc(d.ref)}</th></tr></thead><tbody>` +
            d.powers.map(p => `<tr><td><b>${esc(p.power)}</b></td><td class="num">${p.error ? '<span class="bad">error</span>' : fmt(p.count)}</td><td>${(p.nearest || []).map(n => `${esc(n.system)} <span class="muted">${n.dist} Ly</span>`).join(' · ')}</td></tr>`).join('') + '</tbody></table>';
          $('#t-status').textContent = 'comparison ready';
        } catch (e) { $('#t-status').textContent = 'error: ' + e.message; }
      }
      function select(t) { const cur = Lab.state.targets?.selected; Lab.set('targets', { selected: cur === t ? null : t }); }
      el._select = select;
    },
    render(el, S) {
      const $ = s => el.querySelector(s);
      const j = S.journal || {}, pp = S.powerplay || {}, T = S.targets || {};
      if (j.system && !refTouched && $('#t-ref').value !== j.system) $('#t-ref').value = j.system;
      const sel = $('#t-power'); if (pp.power && sel.value !== pp.power && !sel.dataset.touched) sel.value = pp.power;
      sel.onchange = () => sel.dataset.touched = '1';
      const rows = T.last?.results || [];
      if (rows.length) $('#t-body').innerHTML = rows.map((s, i) => {
        const age = s.updated ? Math.round((Date.now() - Date.parse(s.updated)) / 864e5) : null; const cls = age == null ? 'muted' : (age > 60 ? 'bad' : (age > 14 ? 'warn' : 'ok'));
        const ref = s.refuses === null || s.refuses === undefined ? '' : (s.refuses.length ? ` <span class="tag bad" title="not in this station's market list">won't buy: ${esc(s.refuses.join(', '))}</span>` : ' <span class="tag ok" title="all rares in your hold are listed here">buys all</span>');
        return `<tr data-i="${i}" class="${T.selected === s ? 'sel' : ''}"><td><b>${esc(s.system)}</b></td><td>${esc(s.station)}${ref}</td><td class="num">${s.dist}</td><td class="num">${s.jumps != null ? '~' + s.jumps : '—'}</td><td class="num">${fmt(s.ls)}</td><td>${esc(s.type)}</td><td>${s.pad}</td><td class="num">${fmt(s.pop)}</td><td class="${cls}">${age == null ? 'unknown' : age + ' d ago'}</td><td><button class="mini" data-copy="${esc(s.system)}">copy</button> <a href="${inaraSt(s.station)}" target="_blank">Inara</a> <a href="${spanshSys(s.system)}" target="_blank">Spansh</a></td></tr>`;
      }).join('');
    },
  });

  Lab.map.addLayer('targets', {
    label: 'sell targets', color: '#6fb3ff', z: 1,
    points: S => (S.targets?.last?.results || []).filter(t => t.x != null).map(t => {
      const age = t.updated ? Math.round((Date.now() - Date.parse(t.updated)) / 864e5) : null;
      return { name: t.system, x: t.x, y: t.y, z: t.z, r: 4, color: age == null ? '#4b6f9c' : (age > 60 ? '#8a4b5c' : (age > 14 ? '#c9a23a' : '#6fb3ff')),
               sub: `${t.station} · ${t.type} · ${t.dist} Ly${t.jumps != null ? ` (~${t.jumps} jumps)` : ''} · market ${age == null ? 'unknown' : age + ' d ago'}${t.refuses && t.refuses.length ? ` · WON'T BUY ${t.refuses.join(', ')}` : ''}`, selected: S.targets?.selected === t, onClick: () => Lab.set('targets', { selected: S.targets?.selected === t ? null : t }) };
    }),
    lines: S => { const t = S.targets?.selected, p = Lab.shipPos(S); return t && p ? [{ a: p, b: t, color: 'rgba(111,179,255,.8)', dash: [4, 4], label: Lab.util.dist3(p, t).toFixed(1) + ' Ly' }] : []; },
  });
})();
