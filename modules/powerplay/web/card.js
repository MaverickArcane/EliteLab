/* powerplay card */
(() => {
  const { esc, fmt } = Lab.util;
  Lab.card({
    id: 'powerplay', requires: ['powerplay'],
    header(h) { h.innerHTML = `<a href="https://inara.cz/elite/powers/" target="_blank">Inara</a>`; },
    render(el, S) {
      const p = S.powerplay || {};
      const end = p.cycle_end ? new Date(p.cycle_end) : null;
      el.innerHTML = `
        <div class="big">${esc(p.power || 'Unpledged')}</div>
        <div class="grid2">
          <div><div class="k">Rank</div><div class="v">${p.rank ?? '—'}</div></div>
          <div><div class="k">Merits</div><div class="v">${fmt(p.merits)}</div></div>
          <div><div class="k">This session</div><div class="v ${p.session_merits ? 'ok' : ''}">${p.session_merits ? '+' + fmt(p.session_merits) : '—'}</div></div>
          <div><div class="k">Pledged</div><div class="v">${p.time_pledged != null ? (p.time_pledged / 86400).toFixed(1) + ' days' : '—'}</div></div>
          <div><div class="k">Cycle ends</div><div class="v">${end ? `${end.toLocaleDateString(undefined, { weekday: 'short' })} ${end.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })} (${Math.round(p.cycle_hours_left)} h)` : '—'}</div></div>
        </div>
        ${(p.merit_log || []).length ? `<div class="note">Recent: ${p.merit_log.slice(-5).reverse().map(m => `+${fmt(m.gained)} <span class="muted">${(m.ts || '').slice(11, 16)}</span>`).join(' · ')}</div>` : ''}
        ${!p.power ? '<div class="note">Pledge at any station with a Powerplay contact. Use "Compare powers" in the sell-targets card to see whose acquisition systems are closest.</div>' : ''}`;
    },
  });
})();
