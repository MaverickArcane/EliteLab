/* Journal-only mining: recorded production, not current cargo or sale income. */
(() => {
  const { esc, fmt } = Lab.util;
  const percent = v => v == null ? 'unknown' : `${fmt(v)}%`;
  Lab.card({
    id: 'mining', requires: ['mining'],
    render(el, S) {
      const m = S.mining?.summary || {};
      const last = m.last_prospect;
      el.style.overflowWrap = 'anywhere';
      el.innerHTML = `
        <div class="grid2" style="margin-top:0">
          <div><div class="k">Refined</div><div class="v" data-mining-total>${fmt(m.refined_tons || 0)} t</div></div>
          <div><div class="k">Recorded rate</div><div class="v">${m.tons_per_hour == null ? '--' : fmt(m.tons_per_hour)} t/h</div></div>
          <div><div class="k">Prospector reports</div><div class="v">${fmt(m.prospector_reports || 0)}</div></div>
        </div>
        <div class="note">${m.ended ? 'Last game session ended.' : 'Current game session.'} ${m.partial ? 'Partial history: session start is outside the loaded journals.' : ''}</div>
        ${m.refined_tons ? `<table><thead><tr><th>Refinery output</th><th class="num">Tons</th></tr></thead><tbody>
          ${(m.commodities || []).map(r => `<tr><td>${esc(r.name)}</td><td class="num">${fmt(r.tons)}</td></tr>`).join('')}
          ${m.other_tons ? `<tr><td>Other / unknown</td><td class="num">${fmt(m.other_tons)}</td></tr>` : ''}
          </tbody></table>` : '<div class="note">No refinery output recorded. Refine mining fragments to start counting tons.</div>'}
        ${last ? `<div style="margin-top:10px"><b>Latest prospector report</b></div>
          <div class="note">${esc(last.content || 'Material content unknown')} | Remaining: ${percent(last.remaining)}</div>
          ${last.motherlode ? `<div>Core: <b>${esc(last.motherlode)}</b></div>` : ''}
          ${last.materials?.length ? `<table><thead><tr><th>Composition</th><th class="num">Proportion</th></tr></thead><tbody>
            ${last.materials.map(r => `<tr><td>${esc(r.name)}</td><td class="num">${percent(r.proportion)}</td></tr>`).join('')}
            </tbody></table>` : '<div class="note">No composition reported.</div>'}
          <div class="note">Recorded ${esc(last.timestamp || 'at an unknown time')}. Reports may revisit the same asteroid.</div>` :
          '<div class="note">Prospect an asteroid to see its composition and remaining percentage.</div>'}
        <div class="note">${esc(m.rate_note || 'Rate appears after one minute of recorded mining-session time.')} ${m.timing_incomplete ? 'Rate unavailable: a mining timestamp is missing or invalid.' : ''}</div>
        <div class="note">${m.as_of ? `As of ${esc(m.as_of)}. ` : ''}Output is production, independent of cargo held, sold or ejected.</div>`;
    },
  });
})();
