/* powerplay card */
(() => {
  const { esc, fmt } = Lab.util;
  const at = value => typeof value === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d/.test(value) ? value.slice(11,16) + ' UTC' : 'time unknown';
  const dateAt = value => typeof value === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d/.test(value) ? value.slice(0,10) + ' ' + value.slice(11,16) + ' UTC' : 'time unknown';
  Lab.card({
    id: 'powerplay', requires: ['powerplay'],
    header(h) { h.innerHTML = `<a href="https://inara.cz/elite/powers/" target="_blank">Inara</a>`; },
    render(el, S) {
      const p = S.powerplay || {};
      const end = p.cycle_end ? new Date(p.cycle_end) : null;
      const gains = (p.merit_log || []).slice(-8).reverse();
      el.innerHTML = `
        <div class="big">${esc(p.power || 'Unpledged')}</div>
        ${p.power && !p.power_observed_this_session ? '<div class="note warn">Pledge is from an earlier observation. Confirm it in this game session; current rank and total merits may be unavailable.</div>' : ''}
        <div class="grid2">
          <div><div class="k">Rank</div><div class="v">${p.rank ?? '—'}</div></div>
          <div><div class="k">Merits</div><div class="v">${fmt(p.merits)}</div></div>
          <div><div class="k">Recorded this session</div><div class="v ${p.session_merits ? 'ok' : ''}">${p.session_merits ? '+' + fmt(p.session_merits) : '0'}</div></div>
          <div><div class="k">Pledged</div><div class="v">${p.time_pledged != null ? (p.time_pledged / 86400).toFixed(1) + ' days' : '—'}</div></div>
          <div><div class="k">Cycle ends</div><div class="v">${end ? `${end.toLocaleDateString(undefined, { weekday: 'short' })} ${end.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })} (${Math.round(p.cycle_hours_left)} h)` : '—'}</div></div>
        </div>
        <div class="note">Session: ${esc(p.commander || 'commander unknown')} since ${esc(dateAt(p.session_started_at))}${p.pledge_changed_at ? ` | Pledge changed ${esc(dateAt(p.pledge_changed_at))}` : ''}. Merit amounts below are recorded; nearby activities are possible context only.</div>
        <div class="k ship-sec">Recent recorded gains</div>
        <div class="powerplay-gains">${gains.length ? gains.map(m => `<div class="powerplay-gain"><div><b class="ok">+${fmt(m.gained)}</b><time>${esc(at(m.ts))}</time></div><small>${m.context ? `${esc(m.context.detail || m.context.kind)} ${m.context.detail ? esc(m.context.kind) : ''} nearby; association unconfirmed` : 'Source not established'}${m.power ? ` | ${esc(m.power)}` : ''}</small></div>`).join('') : '<div class="note">No recorded gains in this session.</div>'}</div>
        ${!p.power ? '<div class="note">Pledge at any station with a Powerplay contact. Use "Compare powers" in the sell-targets card to see whose acquisition systems are closest.</div>' : ''}`;
    },
  });
})();
