/* merits card: session merit rate and attribution */
(() => {
  const { esc, fmt } = Lab.util;
  const COLORS = { rares: '#f0b062', trade: '#e6b422', 'bounty hunting': '#ff5c5c', 'combat zone': '#ff8c2a', hauling: '#6fb3ff', exploration: '#9be36b', missions: '#c9b6ff', 'objective bonus': '#2fd4ff', unattributed: '#8a97a8' };
  Lab.card({
    id: 'merits', requires: ['merits'],
    render(el, S) {
      const m = S.merits || {}; const by = m.by_activity || {}; const acts = Object.entries(by).sort((a, b) => b[1].merits - a[1].merits);
      el.innerHTML = `
        <div class="grid2" style="margin-top:0">
          <div><div class="k">Session merits</div><div class="v">${fmt(m.session_merits)} <span class="muted" style="font-size:12px;font-weight:400">${m.hours != null ? `in ${m.hours} h` : ''}</span></div></div>
          <div><div class="k">Per hour <span style="text-transform:none;letter-spacing:0">(while earning)</span></div><div class="v" title="${m.active_hours != null ? `${m.active_hours} h earning; breaks over 15 min do not count` : ''}">${m.per_hour_active != null ? fmt(m.per_hour_active) : '-'}${m.breaks ? ` <span class="muted" style="font-size:12px;font-weight:400">${m.per_hour != null ? fmt(m.per_hour) + '/h incl. ' : ''}${m.breaks} break${m.breaks === 1 ? '' : 's'}</span>` : ''}</div></div>
          <div><div class="k">Last 60 min</div><div class="v ${m.last_hour ? 'ok' : ''}">${fmt(m.last_hour)}</div></div>
          <div><div class="k">Best activity</div><div class="v">${esc(m.best || '—')}</div></div>
        </div>
        ${acts.length ? `<div class="bar" style="display:flex;overflow:hidden">${acts.map(([a, v]) => `<i style="width:${v.share}%;background:${COLORS[a] || '#888'}" title="${esc(a)} ${v.share}%"></i>`).join('')}</div>
        <table style="margin-top:6px"><thead><tr><th>Activity</th><th class="num">Merits</th><th class="num">Events</th><th class="num">Per event</th></tr></thead><tbody>
        ${acts.map(([a, v]) => `<tr><td><i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${COLORS[a] || '#888'};margin-right:6px"></i>${esc(a)}</td><td class="num">${fmt(v.merits)}</td><td class="num">${v.events}</td><td class="num">${fmt(v.per_event)}</td></tr>`).join('')}</tbody></table>` : '<div class="note">No merits yet this session. Sell something, kill something, or deliver something and the breakdown appears here.</div>'}
        ${(m.recent || []).length ? `<div class="feed" style="margin-top:6px;max-height:140px">${m.recent.slice(0, 8).map(g => `<div><time>${(g.ts || '').slice(11, 16)}</time><span><b class="ok">+${fmt(g.gained)}</b> ${esc(g.activity)} <span class="muted">${esc(g.detail || '')}</span></span></div>`).join('')}</div>` : ''}
        <div class="note">Rares observed at ~1 merit per 667 Cr sold. Resets when you reload the game or change power.</div>`;
    },
  });
})();
