/* Journal earnings and explicit handoffs to Inara's public commodity search. */
export function profitSummary(state, esc, fmt) {
  const p = state.profits, s = p?.session;
  if (!s) return '<p class="note">Trading profit is unavailable. Enable the profits module to track sales.</p>';
  const last = s.recent?.[0], run = p.estimate;
  const money = v => Number.isFinite(v) ? `${fmt(v)} Cr` : 'Unknown';
  const tone = v => Number.isFinite(v) ? v < 0 ? 'bad' : 'ok' : 'muted';
  return `<div class="row trade-profit-head"><b>Trading profit</b><a class="mini" href="elitelab-hud:open?mode=profits">Open profit HUD</a></div>
    <div class="trade-profit-grid">
      <div><span class="k">Earned this session${s.ended ? ' (ended)' : ''}</span><strong class="${tone(s.profit)}" data-earned-profit>${money(s.profit)}</strong><span class="note">${fmt(s.sales)} sales | ${fmt(s.sold_tons)} t sold</span></div>
      <div><span class="k">Latest sale profit</span><strong class="${tone(last?.profit)}" data-last-profit>${last ? money(last.profit) : 'No sales yet'}</strong><span class="note">${last ? `${fmt(last.quantity)} t ${esc(last.commodity)}` : 'Updates when you sell in game'}</span></div>
      <div><span class="k">${esc(run?.label || 'Current run estimate')}</span><strong data-run-estimate>${money(run?.profit)}</strong><span class="note">${run ? `${run.quantity == null ? 'Unknown load' : fmt(run.quantity) + ' t'} ${esc(run.commodity || '')}` : 'Select a trade route or join a hauling job'}</span></div>
    </div>
    ${s.unknown_sales ? `<p class="warn">${fmt(s.unknown_sales)} sales lack complete price evidence. Known profit subtotal: ${money(s.known_profit)}.</p>` : ''}
    ${s.partial ? '<p class="warn">Partial session: the journal session start was not available.</p>' : ''}
    <p class="note">Sale proceeds less the journal average purchase cost, before fuel, repairs, fees and NPC crew deductions. All commodity sales count, including mined goods. Resets when the game loads or commander changes.</p>
    ${run ? `<p class="note">${esc(run.note)}</p>` : ''}
    ${last ? `<details><summary>Recent sale receipts</summary><div class="table-scroll"><table><thead><tr><th>Commodity</th><th>Tonnes</th><th>Proceeds</th><th>Purchase cost</th><th>Profit</th></tr></thead><tbody>${s.recent.map(r => `<tr><td>${esc(r.commodity)}</td><td>${fmt(r.quantity)}</td><td>${money(r.proceeds)}</td><td>${money(r.cost)}</td><td class="${tone(r.profit)}">${money(r.profit)}</td></tr>`).join('')}</tbody></table></div></details>` : ''}`;
}

export function inaraLink(values, direction, system) {
  // Names and option values verified against Inara's public form on 2026-11-17.
  const params = new URLSearchParams({pi1: direction === 'sell' ? '2' : '1', ps1: values.system.trim() || system || '',
    pi3: values.pad, pi5: values.age, pi8: values.carriers, pi4: values.surface, pi10: '1'});
  if (values.commodity) params.set('pa1[]', values.commodity);
  return 'https://inara.cz/elite/commodities/?' + params;
}

export function mountInara(el, Lab) {
  const {esc} = Lab.util;
  el.innerHTML = `<div class="row trade-profit-head"><b>Inara commodity search</b><span class="note">Buy or sell near your current system</span></div>
    <div class="trade-form trading-form">
      <label>Commodity<select name="commodity" data-inara-commodity><option value="">Choose on Inara</option></select></label>
      <label>Near system<input name="system" maxlength="160" placeholder="Current system"></label>
      <label>Minimum landing pad<select name="pad"><option value="3">Large</option><option value="2">Medium</option><option value="1">Small</option></select></label>
      <label>Maximum price age<select name="age"><option value="1">1 hour</option><option value="8">8 hours</option><option value="24" selected>1 day</option><option value="72">3 days</option></select></label>
      <label>Fleet carriers<select name="carriers"><option value="2">Recently reported access</option><option value="0">Include all</option><option value="1">Exclude</option></select></label>
      <label>Surface stations<select name="surface"><option value="1">Exclude</option><option value="2">Include without Odyssey</option><option value="0">Include all</option></select></label>
    </div><div class="row trading-actions"><a class="mini primary" data-inara-buy target="_blank" rel="noopener noreferrer">Buy on Inara</a><a class="mini" data-inara-sell target="_blank" rel="noopener noreferrer">Sell on Inara</a></div>
    <p class="note" data-inara-note>Opens Inara in a new tab, sorted by best price. Check supply, demand, access and report age before travelling. Search results do not change your selected route.</p>`;
  let destroyed = false;
  const update = () => {
    const values = Object.fromEntries([...el.querySelectorAll('[name]')].map(n => [n.name, n.value]));
    const system = Lab.state.journal?.system || '';
    el.querySelector('[name=system]').placeholder = system || 'Enter a system';
    el.querySelector('[data-inara-buy]').href = inaraLink(values, 'buy', system);
    el.querySelector('[data-inara-sell]').href = inaraLink(values, 'sell', system);
  };
  el.addEventListener('input', update);
  el.addEventListener('change', update);
  update();
  fetch('/modules/personal/inara-commodities.json').then(r => {
    if (!r.ok) throw Error('Commodity list unavailable');
    return r.json();
  }).then(data => {
    if (destroyed) return;
    el.querySelector('[data-inara-commodity]').innerHTML += data.commodities.map(c => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('');
    update();
  }).catch(() => {
    if (!destroyed) el.querySelector('[data-inara-note]').textContent = 'Commodity list unavailable. Open either search and choose the commodity on Inara; system and filters are still included.';
  });
  return {update, destroy: () => {destroyed = true;}};
}
