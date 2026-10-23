/* combat card: where combat pays merits, zones seen in your own journal, and a map layer */
(() => {
  const { esc, fmt, inaraSys, spanshSys } = Lab.util;
  let refTouched = false;
  const KIND_COLOR = { contested: '#ff5c5c', acquisition: '#ff8c2a', undermining: '#c9b6ff', reinforcement: '#9be36b' };
  const INT_COLOR = { 'Low': '#9be36b', 'Medium': '#e6b422', 'High': '#ff5c5c', 'Very High': '#ff2bd6' };
  const zoneTags = z => Object.entries(z || {}).sort((a, b) => (['Low', 'Medium', 'High', 'Very High'].indexOf(b[0])) - (['Low', 'Medium', 'High', 'Very High'].indexOf(a[0]))).map(([lvl, n]) => `<span class="tag" style="border-color:${INT_COLOR[lvl] || '#888'};color:${INT_COLOR[lvl] || '#888'}">${n} x ${esc(lvl)}</span>`).join(' ');

  Lab.card({
    id: 'combat', requires: ['journal', 'powerplay', 'combat'],
    mount(el) {
      el.innerHTML = `
        <div id="c-here"></div>
        <div class="row">
          <label>Kind <select id="c-kind"><option value="contested">Contested (combat zones)</option><option value="acquisition">Acquisition (bounties +5%)</option><option value="undermining">Undermining (power kills)</option><option value="reinforcement">Reinforcement (bounties -35%)</option><option value="all">All</option></select></label>
          <label>From <input id="c-ref" size="16" placeholder="current system"></label>
          <label>Radius Ly <input id="c-max" size="4" value="150"></label>
          <button class="primary" id="c-go">Find</button>
          <span class="muted" id="c-status"></span>
        </div>
        <div class="note" id="c-hint"></div>
        <table><thead><tr><th>System</th><th>Kind</th><th class="num">Ly</th><th class="num">Jumps</th><th>State / power</th><th>Sec</th><th>Conflict progress</th><th>Data</th><th>Seen</th><th></th></tr></thead>
        <tbody id="c-body"><tr><td colspan="10" class="muted">Contested = both sides past 29% and nobody past 100%. Results are sorted by closest race. Scout one; the zone log above fills in the moment you arrive.</td></tr></tbody></table>
        <details style="margin-top:10px"><summary class="muted" style="cursor:pointer">Zones seen in my journal</summary><table style="margin-top:6px"><thead><tr><th>System</th><th>Zones</th><th>Last seen</th><th></th></tr></thead><tbody id="c-seen"></tbody></table></details>
        <div class="note"><b>Rules of thumb</b>: bounties and bonds pay merits roughly proportional to credit value; rares paid ~1 merit per 667 Cr sold. A Medium zone in a Kestrel measured 14 per assist, 172-216 per kill. Powerplay zone kills log no bond or bounty; merits are the whole reward. The Merit rate card measures whatever you try.</div>`;
      const $ = s => el.querySelector(s);
      $('#c-ref').addEventListener('input', () => refTouched = $('#c-ref').value.trim() !== '');
      $('#c-go').onclick = async () => {
        $('#c-status').textContent = 'querying Spansh (contested scans up to 4,000 systems)…';
        try {
          const d = await Lab.api('/api/combat', { kind: $('#c-kind').value, ref: $('#c-ref').value.trim() || undefined, max: $('#c-max').value });
          if (d.error) throw new Error(d.error);
          Lab.set('combat', { last: d });
          $('#c-status').textContent = `${d.results.length} systems within ${d.radius} Ly of ${d.ref}`;
        } catch (e) { $('#c-status').textContent = 'error: ' + e.message; }
      };
    },
    render(el, S) {
      const $ = s => el.querySelector(s); const j = S.journal || {}; const C = S.combat || {}; const d = C.last;
      if (j.system && !refTouched && $('#c-ref').value !== j.system) $('#c-ref').value = j.system;
      const here = C.zones_here || {}; const n = Object.values(here).reduce((a, b) => a + b, 0);
      $('#c-here').innerHTML = n ? `<div class="big" style="font-size:16px;margin-bottom:8px"><span class="bad">Conflict zones here</span> in ${esc(j.system)}: ${zoneTags(here)} <span class="muted" style="font-size:12px">(from the nav signals; drop in via the nav panel)</span></div>`
        : `<div class="muted" style="font-size:12px;margin-bottom:8px">No Powerplay conflict zones detected in ${esc(j.system || 'this system')} yet. They appear in the log within seconds of arrival or when near the nav beacon.</div>`;
      $('#c-seen').innerHTML = (C.zones_seen || []).length ? C.zones_seen.map(z => `<tr><td><b>${esc(z.system)}</b>${z.last_dropped ? ` <span class="muted">fought ${esc(z.last_dropped)}</span>` : ''}</td><td>${zoneTags(z.zones)}</td><td>${z.age_h != null ? (z.age_h < 48 ? z.age_h + ' h ago' : Math.round(z.age_h / 24) + ' d ago') : ''}</td><td><button class="mini" data-copy="${esc(z.system)}">copy</button></td></tr>`).join('') : '<tr><td colspan="4" class="muted">None yet. Jump into a contested system and honk.</td></tr>';
      if (!d) return;
      $('#c-hint').innerHTML = Object.entries(d.hints || {}).map(([k, h]) => `<b style="color:${KIND_COLOR[k]}">${esc(k)}</b>: ${esc(h)}`).join('<br>');
      $('#c-body').innerHTML = d.results.length ? d.results.map(r => {
        const age = r.data_age_h; const ageCls = age == null ? 'muted' : (age > 72 ? 'bad' : (age > 24 ? 'warn' : 'ok'));
        return `<tr><td><b>${esc(r.system)}</b>${r.zone_likely ? ' <span class="tag bad" title="both sides past the threshold, nobody past 100%">zone</span>' : ''}${r.decided ? ' <span class="tag muted" title="a power is past 100%: acquisition decided, zones likely gone">decided</span>' : ''}</td><td><span class="tag" style="border-color:${KIND_COLOR[r.kind]};color:${KIND_COLOR[r.kind]}">${esc(r.kind)}</span></td><td class="num">${r.dist}</td><td class="num">${r.jumps != null ? '~' + r.jumps : '—'}</td><td>${esc(r.state || '')}${r.controlling_power ? ' · ' + esc(r.controlling_power) : ''}</td><td>${esc(r.security || '')}</td><td>${(r.conflict || []).map(c => `${esc(c.power.split(' ').pop())} <b>${Math.round(c.progress * 100)}%</b>`).join(' · ') || '—'}</td><td class="${ageCls}">${age == null ? '?' : (age < 48 ? age + ' h' : Math.round(age / 24) + ' d')}</td><td>${r.seen_zones ? zoneTags(r.seen_zones) : '<span class="muted">not scouted</span>'}</td><td><button class="mini" data-copy="${esc(r.system)}">copy</button> <a href="${inaraSys(r.system)}" target="_blank">Inara</a> <a href="${spanshSys(r.system)}" target="_blank">Spansh</a></td></tr>`;
      }).join('') : '<tr><td colspan="10" class="muted">Nothing of that kind in range. Widen the radius.</td></tr>';
    },
  });

  Lab.map.addLayer('combat', {
    label: 'combat', color: '#ff5c5c', z: 1,
    points: S => {
      const pts = ((S.combat || {}).last?.results || []).filter(r => r.x != null).map(r => ({ name: r.system, x: r.x, y: r.y, z: r.z, r: 4, color: KIND_COLOR[r.kind] || '#ff5c5c',
        sub: `${r.kind}${r.zone_likely ? ' (zone likely)' : ''}${r.decided ? ' (decided)' : ''} · ${r.dist} Ly${r.jumps != null ? ` (~${r.jumps} jumps)` : ''} · data ${r.data_age_h != null ? Math.round(r.data_age_h) + ' h old' : '?'}${r.conflict?.length ? ' · ' + r.conflict.map(c => `${c.power.split(' ').pop()} ${Math.round(c.progress * 100)}%`).join(', ') : ''}` }));
      ((S.combat || {}).zones_seen || []).filter(z => z.pos).forEach(z => { const hot = z.hottest || 'Low'; pts.push({ name: z.system, x: z.pos[0], y: z.pos[1], z: z.pos[2], r: 5, color: INT_COLOR[hot] || '#ff5c5c', label: true, sub: `zones seen: ${Object.entries(z.zones || {}).map(([l, n]) => `${n} x ${l}`).join(', ')} · ${z.age_h != null ? Math.round(z.age_h) + ' h ago' : ''}` }); });
      return pts;
    },
  });
})();
