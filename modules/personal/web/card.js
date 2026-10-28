/* Personal ship trades. Search snapshots stay visible as the journal updates. */
(() => {
  const {esc, fmt, ls} = Lab.util;
  const KEY = 'personal.search.v1';
  const price = n => `${fmt(n)} Cr`;
  Lab.card({
    id: 'personal', requires: ['journal'],
    mount(el) {
      el._personal = {destroyed: false};
      el.innerHTML = `<div class="row trade-nav"><b>Find a personal trade route</b><a class="mini" href="https://inara.cz/elite/market-traderoutes/" target="_blank" rel="noopener noreferrer">Open Inara</a></div>
        <form data-personal-search class="trade-form">
          <label>Starting system<input name="origin" maxlength="160" placeholder="Current system"></label>
          <label>Destination (optional)<input name="destination" maxlength="160" placeholder="Any system within range"></label>
          <label>Distance limit<select name="distance_mode"><option value="ly">Light-years</option><option value="jumps">Estimated laden jumps</option></select></label>
          <label data-ly>Maximum distance (Ly)<input name="distance" type="number" min="0.1" max="500" step="0.1" value="80" required></label>
          <label data-jumps hidden>Maximum estimated jumps<input name="jumps" type="number" min="1" max="20" value="2" required disabled></label>
          <label>Load (t; blank = ship capacity)<input name="quantity" type="number" min="1" max="1000000" placeholder="Current ship"></label>
          <label>Minimum landing pad<select name="pad"><option>L</option><option>M</option><option>S</option></select></label>
          <label>Maximum report age<select name="hours"><option value="3">3 hours</option><option value="6">6 hours</option><option value="12">12 hours</option><option value="24" selected>24 hours</option><option value="72">72 hours</option></select></label>
          <label>Commodity<select name="commodity"><option value="">Most profitable shortlist</option></select></label>
          <label>Search breadth<select name="breadth"><option value="24">24 commodities</option><option value="48">48 commodities</option></select></label>
          <div class="trade-wide note" data-ship-context></div>
          <div class="trade-wide row"><button type="submit" class="mini primary">Find routes</button><span class="note">Buy in the starting system; sell within the distance limit.</span></div>
        </form><p class="note" data-personal-status role="status">Choose your filters and find routes. No carrier required.</p><div class="trade-pairs" data-personal-results></div>`;
      const form = el.querySelector('form'), status = el.querySelector('[data-personal-status]');
      const saved = ls.get(KEY, {});
      for (const [k, v] of Object.entries(saved)) {
        if (k !== 'commodity' && form.elements[k]) form.elements[k].value = v;
      }
      if (saved.commodity) {
        const option = document.createElement('option'); option.value = saved.commodity; option.textContent = saved.commodity;
        form.elements.commodity.append(option); form.elements.commodity.value = saved.commodity;
      }
      const mode = () => {
        const jumps = form.elements.distance_mode.value === 'jumps';
        el.querySelector('[data-ly]').hidden = jumps; el.querySelector('[data-jumps]').hidden = !jumps;
        form.elements.distance.disabled = jumps; form.elements.jumps.disabled = !jumps;
      };
      form.elements.distance_mode.onchange = mode; mode();
      form.onsubmit = async event => {
        event.preventDefault();
        const params = Object.fromEntries(new FormData(form));
        ls.set(KEY, params);
        const j = Lab.state.journal || {};
        params.origin = params.origin.trim() || j.system || '';
        params.quantity = params.quantity || j.cargo_capacity || '';
        const button = form.querySelector('[type=submit]'); button.disabled = true;
        status.textContent = 'Comparing community buy and sell reports...';
        el.querySelector('[data-personal-results]').innerHTML = '';
        try {
          const result = await Lab.api('/api/personal/routes', params);
          if (el._personal.destroyed) return;
          const selected = form.elements.commodity.value;
          form.elements.commodity.innerHTML = '<option value="">Most profitable shortlist</option>' + result.commodities.map(k => `<option value="${esc(k)}">${esc(k)}</option>`).join('');
          form.elements.commodity.value = selected;
          const s = result.settings;
          status.textContent = `${result.source} | ${s.origin}${s.destination ? ' to '+s.destination : ''} | ${fmt(s.quantity)} t | ${fmt(s.distance)} Ly limit | ${result.screened} of ${result.available} commodities checked | Searched ${new Date(result.queried_at).toLocaleString()}. ${result.note}`;
          const stop = (m, label) => `<div class="trade-pair-stop"><span class="tag">${label}</span> <b>${price(m.price)}/t</b><div><b>${esc(m.station)}</b> / ${esc(m.system)}</div><div class="row"><button class="mini" data-copy="${esc(m.system)}">Copy system</button><button class="mini" data-copy="${esc(m.station)}">Copy station</button><a class="mini" href="${esc(Lab.util.inaraMarket(m.station, m.system))}" target="_blank" rel="noopener noreferrer">Inara market</a></div><div class="note">${fmt(m.volume)} t ${label === 'Buy' ? 'supply' : 'demand'} | ${esc(m.pad)} pad | ${m.arrival_ls == null ? 'Approach unknown' : fmt(m.arrival_ls)+' Ls'}<br>Reported ${esc(new Date(m.observed_at).toLocaleString())}</div></div>`;
          el.querySelector('[data-personal-results]').innerHTML = result.warnings.map(w => `<p class="warn">${esc(w)}</p>`).join('') + (result.rows.length ? result.rows.map(r => `<article class="trade-pair"><div class="row trade-pair-heading"><b>${esc(r.commodity)}</b><span class="ok">${price(r.profit)} estimated profit / load</span><span>${price(r.per_ton)}/t</span></div><div class="trade-pair-stops">${stop(r.buy, 'Buy')}${stop(r.sell, 'Sell')}</div><div class="note">${fmt(r.quantity)} t | ${price(r.cost)} purchase cost | ${fmt(r.distance)} Ly | ${r.estimated_jumps == null ? 'Laden jump estimate unavailable' : fmt(r.estimated_jumps)+' estimated laden jumps'}${result.credits != null && r.cost > result.credits ? ' | Purchase cost exceeds reported credits' : ''}${result.ship_capacity != null && r.quantity > result.ship_capacity ? ' | Load exceeds reported ship capacity' : ''}</div></article>`).join('') : '<p class="note">No routes found in the reports checked. Try a smaller load, older reports, more commodities or a wider distance. A specific commodity search can check beyond the shortlist; community quote limits may omit local markets.</p>');
        } catch (error) {
          if (!el._personal.destroyed) status.textContent = error.message;
        } finally { if (!el._personal.destroyed) button.disabled = false; }
      };
    },
    render(el, S) {
      const j = S.journal || {}, form = el.querySelector('form');
      form.elements.origin.placeholder = j.system || 'Enter starting system';
      form.elements.quantity.placeholder = j.cargo_capacity ? `${fmt(j.cargo_capacity)} t` : 'Enter load size';
      el.querySelector('[data-ship-context]').textContent = `${j.ship_name || j.ship || 'Current ship'} | ${j.system || 'Location unknown'} | ${j.cargo_capacity == null ? 'Capacity unknown' : fmt(j.cargo_capacity)+' t capacity'} | ${j.jump_range_laden == null ? 'Laden range unknown; use light-years' : fmt(j.jump_range_laden)+' Ly fully laden'}. Jump limits use straight-line distance, not plotted navigation. Results retain the settings used when searched.`;
    },
    unmount(el) { el._personal.destroyed = true; },
  });
})();
