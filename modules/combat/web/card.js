/* combat card: where combat pays merits, plus a map layer */
(() => {
  const { esc, fmt, inaraSys, spanshSys } = Lab.util;
  let refTouched = false;
  const KIND_COLOR = { contested: '#ff5c5c', acquisition: '#ff8c2a', undermining: '#c9b6ff', reinforcement: '#9be36b' };
  Lab.card({
    id: 'combat', requires: ['journal', 'powerplay', 'combat'],
    mount(el) {
      el.innerHTML = `
        <div class="row">
          <label>Kind <select id="c-kind"><option value="contested">Contested (combat zones)</option><option value="acquisition">Acquisition (bounties +5%)</option><option value="undermining">Undermining (power kills)</option><option value="reinforcement">Reinforcement (bounties -35%)</option><option value="all">All</option></select></label>
          <label>From <input id="c-ref" size="16" placeholder="current system"></label>
          <label>Radius Ly <input id="c-max" size="4" value="60"></label>
          <button class="primary" id="c-go">Find</button>
          <span class="muted" id="c-status"></span>
        </div>
        <div class="note" id="c-hint"></div>
        <table><thead><tr><th>System</th><th>Kind</th><th class="num">Ly</th><th class="num">Jumps</th><th>State / power</th><th>Security</th><th class="num">Pop</th><th>Conflict progress</th><th></th></tr></thead>
        <tbody id="c-body"><tr><td colspan="9" class="muted">Merits for combat are paid on the kill, in the right kind of system. Pick a kind and hit Find; results plot on the map in red.</td></tr></tbody></table>
        <div class="note"><b>Rules of thumb</b> (community-documented, verify in game): bounties and bonds pay merits roughly proportional to credit value; rares paid ~1 merit per 667 Cr sold in your last run. A combat ship in a High RES inside an acquisition system, or a Powerplay combat zone in a contested one, is the usual way to beat rares. Undermining needs you to target ships flagged with the rival power, not pirates. The Merit rate card measures whatever you try.</div>`;
      const $ = s => el.querySelector(s);
      $('#c-ref').addEventListener('input', () => refTouched = $('#c-ref').value.trim() !== '');
      $('#c-go').onclick = async () => {
        $('#c-status').textContent = 'querying Spansh…';
        try {
          const d = await Lab.api('/api/combat', { kind: $('#c-kind').value, ref: $('#c-ref').value.trim() || undefined, max: $('#c-max').value });
          if (d.error) throw new Error(d.error);
          Lab.set('combat', { last: d });
          $('#c-status').textContent = `${d.results.length} systems within ${d.radius} Ly of ${d.ref}`;
        } catch (e) { $('#c-status').textContent = 'error: ' + e.message; }
      };
    },
    render(el, S) {
      const $ = s => el.querySelector(s); const j = S.journal || {}; const d = (S.combat || {}).last;
      if (j.system && !refTouched && $('#c-ref').value !== j.system) $('#c-ref').value = j.system;
      if (!d) return;
      $('#c-hint').innerHTML = Object.entries(d.hints || {}).map(([k, h]) => `<b style="color:${KIND_COLOR[k]}">${esc(k)}</b>: ${esc(h)}`).join('<br>');
      $('#c-body').innerHTML = d.results.length ? d.results.map(r => `<tr><td><b>${esc(r.system)}</b>${r.zone_likely ? ' <span class="tag bad" title="both sides past the conflict threshold">zone</span>' : ''}</td><td><span class="tag" style="border-color:${KIND_COLOR[r.kind]};color:${KIND_COLOR[r.kind]}">${esc(r.kind)}</span></td><td class="num">${r.dist}</td><td class="num">${r.jumps != null ? '~' + r.jumps : '—'}</td><td>${esc(r.state || '')}${r.controlling_power ? ' · ' + esc(r.controlling_power) : ''}</td><td>${esc(r.security || '')}</td><td class="num">${fmt(r.population)}</td><td>${(r.conflict || []).map(c => `${esc(c.power.split(' ').pop())} <b>${Math.round(c.progress * 100)}%</b>`).join(' · ') || '—'}</td><td><button class="mini" data-copy="${esc(r.system)}">copy</button> <a href="${inaraSys(r.system)}" target="_blank">Inara</a> <a href="${spanshSys(r.system)}" target="_blank">Spansh</a></td></tr>`).join('') : '<tr><td colspan="9" class="muted">Nothing of that kind in range. Widen the radius.</td></tr>';
    },
  });
  Lab.map.addLayer('combat', {
    label: 'combat', color: '#ff5c5c', z: 1,
    points: S => ((S.combat || {}).last?.results || []).filter(r => r.x != null).map(r => ({ name: r.system, x: r.x, y: r.y, z: r.z, r: 4, color: KIND_COLOR[r.kind] || '#ff5c5c',
      sub: `${r.kind} · ${r.dist} Ly${r.jumps != null ? ` (~${r.jumps} jumps)` : ''} · ${r.security || ''} security${r.conflict?.length ? ' · ' + r.conflict.map(c => `${c.power.split(' ').pop()} ${Math.round(c.progress * 100)}%`).join(', ') : ''}` })),
  });
})();
