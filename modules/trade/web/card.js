/* Paired buy/sell routes with carrier sizing and in-place planning. */
(() => {
  const { esc, fmt, ls } = Lab.util;
  const KEY = 'trade.routes.v1';
  const when = s => s ? new Date(s).toLocaleString() : 'Unknown';
  const tons = n => n == null ? 'Unknown' : fmt(n) + ' t';
  const money = n => n == null ? 'Unknown' : fmt(n) + ' Cr';
  const splitProfit = (buy, sell, quantity, loading, unloading) => {
    const spread = sell - buy, load = Math.floor(spread * loading / 100), unload = Math.floor(spread * unloading / 100);
    const total = n => quantity == null ? null : n * quantity;
    return {carrier_buy_price: buy + load, carrier_sell_price: sell - unload, loading_per_ton: load, unloading_per_ton: unload,
      gross_profit: total(spread), owner_profit: total(spread - load - unload), loading_profit: total(load), unloading_profit: total(unload)};
  };
  const profitView = (split, gross) => `<div class="trade-profit-totals"><div><div class="k">Total route profit</div><strong data-total-profit>${money(gross)}</strong><div class="note">Before crew, fuel and fees</div></div><div><div class="k">Your carrier profit</div><strong data-owner-profit>${money(split?.owner_profit)}</strong><div class="note">After both crew payments; before fuel and fees</div></div></div>${split ? `<div class="trade-crew-prices"><div><div class="k">Loading: carrier buys</div><b data-carrier-buy>${money(split.carrier_buy_price)}/t</b> <button class="mini" data-copy="${split.carrier_buy_price}">copy price</button><div class="note">Crew earns ${money(split.loading_per_ton)}/t | ${money(split.loading_profit)} total</div></div><div><div class="k">Unloading: carrier sells</div><b data-carrier-sell>${money(split.carrier_sell_price)}/t</b> <button class="mini" data-copy="${split.carrier_sell_price}">copy price</button><div class="note">Crew earns ${money(split.unloading_per_ton)}/t | ${money(split.unloading_profit)} total</div></div></div>` : ''}`;
  const control = (name, label, value = 0, type = 'number') => `<label>${label}<input name="${name}" type="${type}" value="${esc(value)}" ${type === 'number' ? 'min="0" step="1"' : 'maxlength="160"'}></label>`;
  Lab.card({
    id: 'trade', requires: ['trade', 'journal', 'powerplay', 'party', 'trade_ui'],
    mount(el) {
      const saved = ls.get(KEY, {});
      const u = el._trade = { generation: 0, signature: '', selected: null, dirty: false, destroyed: false, lastFetch: 0, restoredCommodity: saved.commodity || '' };
      el.innerHTML = `<div class="row trade-nav"><button class="mini" data-trade-tab="search">Find a route</button><button class="mini" data-trade-tab="operation">Manage trade</button></div>
        <section data-search-view><div class="row trade-toolbar">
          <select data-commodity aria-label="Commodity"><option value="">Bulk shortlist</option></select>
          <label>Both stops from carrier <select data-radius aria-label="Maximum distance of either stop from carrier">${[25, 50, 100, 250, 500, 1000, 0].map(n => `<option value="${n}">${n ? 'within '+n+' Ly' : 'Any distance'}</option>`).join('')}</select></label>
          <label>Buy to sell <select data-route-distance aria-label="Maximum distance between buy and sell">${[25, 50, 100, 250, 500].map(n => `<option value="${n}">${n} Ly max</option>`).join('')}</select></label>
          <button class="mini primary" data-refresh>Find routes</button>
        </div>
        <div data-context class="note"></div>
        <details class="trade-filters"><summary>Search settings</summary><div class="row">
          <label>Report age <select data-hours>${[3, 6, 12, 24, 72].map(h => `<option value="${h}">${h} hours</option>`).join('')}</select></label>
          <label>Minimum pad <select data-pad><option>L</option><option>M</option><option>S</option></select></label>
          <label class="chk"><input data-auto-volume type="checkbox" checked>Fill carrier free space</label>
          <label>Supply &amp; demand (t)<input data-volume type="number" min="1" max="1000000" disabled placeholder="Capacity unknown" aria-label="Minimum supply and demand"></label>
          <label>Sell price <select data-sell-percent><option value="80">At least 80% of reported high</option><option value="90">At least 90% of reported high</option><option value="95">At least 95% of reported high</option><option value="0">Any profitable price</option></select></label>
          <label>Station approach <select data-arrival><option value="2000">Within 2,000 Ls</option><option value="10000">Within 10,000 Ls</option><option value="50000">Within 50,000 Ls</option><option value="0">Any distance</option></select></label>
          <label>Shortlist size <select data-breadth><option>24</option><option>48</option><option>96</option></select></label>
        </div><div class="note">Cheapest qualifying buy stop for each high-paying sell stop, ranked by spread per ton. Reports refresh every five minutes. Estimates exclude fuel, fees and hauler payments.</div></details>
        <div class="trade-crew-controls"><div class="row"><b>Crew profit split</b>
          <label>Loading <input data-crew-load type="number" min="0" max="100" step="1" required value="25"> %</label>
          <label>Unloading <input data-crew-unload type="number" min="0" max="100" step="1" required value="25"> %</label>
          <span data-crew-owner></span></div><div class="note">Shares of route profit, paid through carrier prices per tonne hauled. Whole-credit rounding stays with the carrier.</div><div data-crew-error class="warn" role="status"></div></div>
        <div data-results-status class="note" role="status"></div><div data-opportunities class="trade-pairs"></div>
        </section><section data-operation-view><div data-operation></div>
        <form data-operation-notes hidden><label>Crew instructions<textarea name="notes" maxlength="500" rows="2" placeholder="Docking location, departure timing, or other instructions"></textarea></label><button class="mini" type="submit">Update instructions</button><span data-notes-status class="note"></span></form>
        <details data-edit-operation class="trade-details"><summary>Adjust operation</summary><form data-trade-plan class="trade-form">
          ${["source_market_id", "destination_market_id", "carrier_market_id"].map(k=>`<input type="hidden" name="${k}" value="0">`).join('')}
          <label>Direction<select name="mode"><option value="load">Load</option><option value="unload">Unload</option></select></label>
          ${control('commodity', 'Commodity', '', 'text')}${control('target', 'Target left aboard (t)')}${control('ship_capacity', 'Ship capacity (0 = live)')}
          ${control('source', 'Buy stop', '', 'text')}${control('destination', 'Sell stop', '', 'text')}
          ${control('source_price', 'Buy price (Cr/t)')}${control('carrier_price', 'Manual carrier price (Cr/t)')}${control('destination_price', 'Sell price (Cr/t)')}
          <label class="chk"><input name="crew_enabled" type="checkbox">Auto carrier prices from crew split</label>
          <label>Loading crew (%)<input name="crew_load_percent" type="number" min="0" max="100" step="1" value="25" required></label>
          <label>Unloading crew (%)<input name="crew_unload_percent" type="number" min="0" max="100" step="1" value="25" required></label>
          ${control('planned_quantity', 'Operation size (t; 0 = remaining)')}
          <label>Known prices<select name="price_basis"><option value="known">Both station prices</option><option value="unknown acquisition">Acquisition cost unknown</option><option value="unknown resale">Resale price unknown</option></select></label>
          <label class="chk"><input name="carrier_price_known" type="checkbox" checked>Carrier price is known</label>
          <label class="chk"><input name="use_ship_cargo" type="checkbox">Use my ship cargo toward loading</label>
          <details class="trade-wide"><summary>Personal Powerplay bonus</summary><div data-power class="note"></div>
            ${control('bonus_per_ton', 'Verified personal bonus (Cr/t)')}
            <label class="chk"><input name="bonus_confirmed" type="checkbox">Verified for my rank, commodity and destination</label>
            <label class="chk"><input name="price_includes_bonus" type="checkbox">Sell price already includes bonus</label>
          </details>
          <div class="row trade-wide"><button class="mini primary" type="submit">Save operation</button><span data-saved class="note" role="status"></span></div>
        </form></details>
        </section><details data-inventory class="trade-details"><summary>Carrier inventory &amp; orders <span data-stock-count class="muted"></span></summary>
          <div class="note">Historical journal evidence. Trades by other commanders can be missing. Reconcile physical stock after checking your carrier in game.</div>
          <div class="row"><label class="chk"><input data-keep-tritium type="checkbox" checked>Keep tritium, quantity unknown</label><button class="mini" data-reset-ledger>Clear inventory &amp; orders</button></div><div class="note">Clearing starts tracking from now; older journals will not bring these rows back.</div>
          <div data-ledger class="trade-table"></div><form data-trade-count class="row">
          <label>Commodity<input name="commodity" maxlength="160" required></label><label>Stock now (t)<input name="stock" type="number" min="0" max="1000000" required></label><button class="mini" type="submit">Update count</button></form>
        </details>`;
      const $ = s => el.querySelector(s);
      u.tab = Lab.state.trade?.plan ? 'operation' : 'search';
      const showTab = el._showTab = tab => { u.tab = tab; if (tab === 'search') u.signature = ''; Lab.emit('trade_ui'); };
      for (const button of el.querySelectorAll('[data-trade-tab]')) button.onclick = () => showTab(button.dataset.tradeTab);
      const notes = $('[data-operation-notes]');
      notes.oninput = () => { u.notesDirty = true; $('[data-notes-status]').textContent = 'Unsaved'; };
      notes.onsubmit = async e => { e.preventDefault(); try {
        await Lab.post('/api/trade/operation', {action: 'notes', id: Lab.state.trade.operation.id, notes: notes.elements.notes.value});
        u.notesDirty = false; $('[data-notes-status]').textContent = 'Shared with crew';
      } catch (error) { Lab.toast(error.message, 'bad'); } };
      el.addEventListener('input', e => { if (e.target.matches('[data-prepare-stock]')) u.pendingStock = e.target.value; });
      el.addEventListener('submit', async e => {
        if (!e.target.matches('[data-prepare-route]')) return;
        e.preventDefault(); const button = e.target.querySelector('button[type=submit]'); button.disabled = true;
        try { await Lab.post('/api/trade/select', {id: u.pendingRoute.id, stock: Number(u.pendingStock), ...el._crewSettings()}); u.pendingRoute = null; u.dirty = false; Lab.emit('trade_ui'); }
        catch (error) { Lab.toast(error.message, 'bad'); } finally { button.disabled = false; }
      });
      const crewSaved = ls.get('trade.crew.v1', {});
      $('[data-crew-load]').value = crewSaved.loading ?? 25; $('[data-crew-unload]').value = crewSaved.unloading ?? 25;
      const crewSettings = el._crewSettings = () => {
        const load = $('[data-crew-load]'), unload = $('[data-crew-unload]');
        if (!load.checkValidity() || !unload.checkValidity() || Number(load.value) + Number(unload.value) > 100) return null;
        return {crew_enabled: true, crew_load_percent: Number(load.value), crew_unload_percent: Number(unload.value)};
      };
      for (const field of ['[data-crew-load]', '[data-crew-unload]']) $(field).oninput = () => {
        const split = crewSettings(); if (split) ls.set('trade.crew.v1', {loading: split.crew_load_percent, unloading: split.crew_unload_percent});
        Lab.emit('trade_ui');
      };
      $('[data-hours]').value = saved.hours || 6; $('[data-radius]').value = saved.distance_version === 2 ? (saved.radius ?? 100) : Math.min(saved.radius || 1000, saved.route_distance || 100); $('[data-pad]').value = saved.pad || 'L';
      $('[data-route-distance]').value = saved.route_distance || 100;
      $('[data-auto-volume]').checked = saved.volume_mode !== 'manual';
      $('[data-volume]').value = saved.volume_mode === 'manual' ? saved.min_volume : ''; $('[data-sell-percent]').value = saved.sell_percent ?? 80;
      $('[data-arrival]').value = saved.arrival ?? 10000; $('[data-breadth]').value = saved.breadth || 24;
      const settings = () => ({distance_version:2, commodity: $('[data-commodity]').value, hours: Number($('[data-hours]').value), radius: Number($('[data-radius]').value), pad: $('[data-pad]').value,
        route_distance: Number($('[data-route-distance]').value), min_volume: $('[data-auto-volume]').checked ? 0 : Number($('[data-volume]').value), volume_mode: $('[data-auto-volume]').checked ? 'carrier' : 'manual', sell_percent: Number($('[data-sell-percent]').value), arrival: Number($('[data-arrival]').value), breadth: Number($('[data-breadth]').value)});
      const query = el._query = async () => {
        if (u.destroyed || !el.isConnected || Lab.state.party?.mode === 'member') return;
        if (!$('[data-auto-volume]').checked && (!$('[data-volume]').value || !$('[data-volume]').checkValidity())) {
          u.error = 'Enter a positive supply and demand minimum, or enable Fill carrier free space.'; u.result = null; Lab.emit('trade_ui'); return;
        }
        const generation = ++u.generation;
        u.lastFetch = Date.now(); u.loading = true;
        $('[data-refresh]').disabled = true;
        $('[data-results-status]').textContent = 'Comparing buy and sell stops...';
        $('[data-opportunities]').classList.add('trade-loading');
        try {
          const result = await Lab.api('/api/trade/opportunities', settings());
          if (u.destroyed || generation !== u.generation) return;
          u.result = result; u.catalog = result.commodities || []; u.error = null;
        } catch (error) {
          if (u.destroyed || generation !== u.generation) return;
          u.error = error.message.includes('no GET route') ? 'The server needs restarting to load the route search.' : error.message; u.result = null;
        } finally {
          if (!u.destroyed && generation === u.generation) {
            u.loading = false; $('[data-refresh]').disabled = false;
            $('[data-opportunities]').classList.remove('trade-loading'); Lab.emit('trade_ui');
          }
        }
      };
      const schedule = el._schedule = () => { clearTimeout(u.debounce); u.debounce = setTimeout(query, 600); };
      for (const selector of ['[data-commodity]', '[data-route-distance]', '[data-hours]', '[data-radius]', '[data-pad]', '[data-auto-volume]', '[data-volume]', '[data-sell-percent]', '[data-arrival]', '[data-breadth]']) {
        $(selector).onchange = () => {
          u.restoredCommodity = '';
          ls.set(KEY, settings()); u.result = null; u.signature = ''; Lab.emit('trade_ui');
        };
      }
      $('[data-refresh]').onclick = query;
      $('[data-reset-ledger]').onclick = async e => { e.target.disabled = true; try { await Lab.post('/api/trade/reset-inventory', {keep_tritium: $('[data-keep-tritium]').checked}); Lab.toast('Ledger cleared. Older records will stay cleared.'); } catch(error) { Lab.toast(error.message, 'bad'); } finally {e.target.disabled=false;} };
      u.timer = setInterval(() => { if (u.tab === 'search' && !document.hidden && el.offsetParent !== null && Date.now() - u.lastFetch >= 300000 && !u.loading) query(); }, 30000);
      const plan = $('[data-trade-plan]');
      plan.addEventListener('input', e => { u.dirty = true; if (e.target.name === 'source') plan.elements.source_market_id.value = 0; if (e.target.name === 'destination') plan.elements.destination_market_id.value = 0; if (['commodity', 'source', 'destination'].includes(e.target.name)) plan.elements.bonus_confirmed.checked = false; $('[data-saved]').textContent = 'Unsaved changes'; });
      plan.onsubmit = async e => {
        e.preventDefault(); const body = Object.fromEntries(new FormData(plan));
        for (const k of ['target', 'ship_capacity', 'source_price', 'carrier_price', 'destination_price', 'bonus_per_ton', 'crew_load_percent', 'crew_unload_percent', 'planned_quantity', 'source_market_id', 'destination_market_id', 'carrier_market_id']) body[k] = Number(body[k]);
        for (const k of ['use_ship_cargo', 'carrier_price_known', 'bonus_confirmed', 'price_includes_bonus', 'crew_enabled']) body[k] = plan.elements[k].checked;
        const b = plan.querySelector('[type=submit]'); b.disabled = true;
        try { await Lab.post('/api/trade/plan', body); u.dirty = false; $('[data-saved]').textContent = 'Saved'; Lab.emit('trade_ui'); }
        catch (error) { Lab.toast(error.message, 'bad'); } finally { b.disabled = false; }
      };
      const count = $('[data-trade-count]');
      count.onsubmit = async e => {
        e.preventDefault(); const b = count.querySelector('button'); b.disabled = true;
        try { await Lab.post('/api/trade/reconcile', {commodity: count.elements.commodity.value, stock: Number(count.elements.stock.value)}); Lab.toast('Carrier count updated'); }
        catch (error) { Lab.toast(error.message, 'bad'); } finally { b.disabled = false; }
      };
      el.addEventListener('click', async e => {
        const button = e.target.closest('[data-select-op]');
        if (button) {
          const row = u.result?.rows.find(r => r.id === button.dataset.selectOp); if (!row) return;
          if (row.stock == null || row.stock_needs_check) { u.pendingRoute = row; u.pendingStock = ''; showTab('operation'); return; }
          const crew = crewSettings(); if (!crew) return;
          button.disabled = true;
          try { await Lab.post('/api/trade/select', {id: row.id, ...crew}); u.dirty = false; showTab('operation'); Lab.toast('Route ready. Start loading when the carrier order is set.'); }
          catch (error) { Lab.toast(error.message, 'bad'); } finally { button.disabled = false; }
        }
        const action = e.target.closest('[data-op-action]');
        if (action) { action.disabled = true; try { await Lab.post('/api/trade/operation', {action: action.dataset.opAction, id: Lab.state.trade.operation?.id}); Lab.emit('trade_ui'); }
          catch (error) { Lab.toast(error.message, 'bad'); } finally { action.disabled = false; } }
        if (e.target.closest('[data-back-search]')) {u.pendingRoute = null; showTab('search');}
        const edit = e.target.closest('[data-edit]');
        if (edit) { $('[data-edit-operation]').open = true; $('[data-edit-operation]').scrollIntoView({block:'nearest'}); }
        const rec = e.target.closest('[data-count-key]');
        if (rec) { count.elements.commodity.value = rec.dataset.countKey; count.elements.stock.value = ''; count.elements.stock.focus(); }
      });
    },
    unmount(el) { const u = el._trade; u.destroyed = true; ++u.generation; clearTimeout(u.debounce); clearInterval(u.timer); },
    render(el, S) {
      const u = el._trade, t = S.trade || {}, j = S.journal || {}, carrier = j.carrier || {}, p = t.plan, c = t.calculation, $ = s => el.querySelector(s);
      const member = S.party?.mode === 'member', op = member ? S.party.operation : t.operation, plan = member ? S.party.plan : p;
      const active = op && ['loading', 'transit', 'unloading'].includes(op.stage);
      if (member) u.tab = 'operation';
      $('[data-search-view]').hidden = u.tab !== 'search'; $('[data-operation-view]').hidden = u.tab !== 'operation';
      $('[data-trade-tab="search"]').hidden = member;
      for (const button of el.querySelectorAll('[data-trade-tab]')) {button.classList.toggle('primary', button.dataset.tradeTab === u.tab); button.setAttribute('aria-pressed', String(button.dataset.tradeTab === u.tab));}
      $('[data-edit-operation]').hidden = member || active || !!u.pendingRoute;
      $('[data-inventory]').hidden = member;
      const crew = el._crewSettings();
      $('[data-crew-owner]').textContent = crew ? 'Carrier: ' + (100 - crew.crew_load_percent - crew.crew_unload_percent) + '%' : '';
      $('[data-crew-error]').textContent = crew ? '' : 'Use whole percentages adding up to 100% or less.';
      const inv = t.inventory || {}, orders = t.orders || {};
      const names = Object.fromEntries((u.catalog || []).map(r => [r.key, r.name]));
      Object.keys({...inv, ...orders}).forEach(k => {names[k] = inv[k]?.name || orders[k]?.name || k;});
      if (u.restoredCommodity) names[u.restoredCommodity] ||= u.restoredCommodity;
      const commodities = Object.keys(names).sort();
      const options = '<option value="">Bulk shortlist</option>' + commodities.map(k => `<option value="${esc(k)}">${esc(names[k])}${inv[k]?.stock > 0 ? ' (' + fmt(inv[k].stock) + ' t aboard)' : ''}</option>`).join('');
      const select = $('[data-commodity]');
      if (select.dataset.options !== options) { const previous = select.value || u.restoredCommodity; select.innerHTML = options; select.dataset.options = options; if (commodities.includes(previous)) { select.value = previous; u.restoredCommodity = ''; } }
      const autoVolume = $('[data-auto-volume]').checked;
      $('[data-volume]').disabled = autoVolume;
      const loadSpace = carrier.free_space == null ? null : carrier.free_space + (carrier.reserved_space || 0);
      if (autoVolume) $('[data-volume]').value = loadSpace ?? '';
      $('[data-context]').innerHTML = `<b>${esc(carrier.name || 'Your carrier')}</b>${carrier.callsign ? ' / ' + esc(carrier.callsign) : ''} <span class="muted">${esc(carrier.system || j.system || 'Location unknown')} | ${tons(carrier.free_space)} unreserved | ${tons(j.cargo_capacity)} ship</span>${autoVolume && loadSpace > 0 ? ' | Supply and demand: ' + tons(loadSpace) + ' minimum (auto)' : ''}${t.inventory_scan === 'reading' ? ' | Reading carrier history...' : ''}`;
      $('[data-context]').innerHTML += ` | Search origin: ${esc(carrier.system || j.system || 'Unknown')} | Both stops: ${$('[data-radius]').value === '0' ? 'any distance' : 'within '+esc($('[data-radius]').value)+' Ly'}${carrier.reserved_space ? ' | '+tons(carrier.reserved_space)+' reserved by buy orders; replace those orders in game' : ''}`;
      const signature = JSON.stringify([select.value, autoVolume, ...['hours', 'radius', 'pad', 'route-distance', 'volume', 'sell-percent', 'arrival', 'breadth'].map(k => $('[data-' + k + ']').value), inv, orders, carrier.system, carrier.free_space, carrier.reserved_space, j.cargo_capacity, t.inventory_scan]);
      if (signature !== u.signature) { u.signature = signature; ++u.generation; u.loading = false; $('[data-refresh]').disabled = false; u.result = null; if (u.tab === 'search' && t.inventory_scan !== 'reading') el._schedule(); }
      if (!u.loading) {
        const result = u.result;
        $('[data-results-status]').innerHTML = u.error ? `<span class="warn">${esc(u.error)}</span>` : result ? `<span>${esc(result.source)} | Checked ${esc(when(result.queried_at))} | ${result.screened} of ${result.available} commodities checked</span><div class="muted">Up to 100 reported quotes per side; best matches in this search.</div>${result.outdated ? '<div class="warn">Carrier context changed. Refresh before using a route.</div>' : ''}${result.warnings.map(w => `<div class="muted">${esc(w)}</div>`).join('')}` : '';
        $('[data-opportunities]').innerHTML = result?.rows.length ? result.rows.map(r => {
          const split = crew ? splitProfit(r.buy.price, r.sell.price, r.quantity, crew.crew_load_percent, crew.crew_unload_percent) : null;
          const market = (m, side) => `<div class="trade-pair-stop"><div class="row"><span class="tag">${side}</span><b>${money(m.price)}/t</b></div><b>${esc(m.station)}</b><div>${esc(m.system)} <button class="mini" data-copy="${esc(m.system)}">copy</button></div><div class="note">${tons(m.volume)} ${side === 'Buy' ? 'supply' : 'demand'} | ${esc(m.pad)} pad | ${m.arrival_ls == null ? 'Approach unknown' : fmt(m.arrival_ls)+' Ls'} | ${m.distance == null ? 'Origin distance unknown' : fmt(m.distance)+' Ly from carrier'}<br>Observed ${esc(when(m.observed_at))}</div></div>`;
          return `<article class="trade-pair"><div class="row trade-pair-heading"><b>${esc(r.name)}</b><span class="ok">${money(r.per_ton)}/t spread</span><span>${fmt(r.route_distance)} Ly between stops</span></div><div class="trade-pair-stops">${market(r.buy, 'Buy')}${market(r.sell, 'Sell')}</div><div class="note">${r.buy.distance == null ? 'Carrier to buy distance unknown' : fmt(r.buy.distance)+' Ly carrier to buy'} | Sell: ${fmt(r.sell_percent)}% of reported high (${money(r.reported_high)}/t)</div>${profitView(split, r.value)}<div class="row trade-pair-footer"><span>${tons(r.quantity)} load</span><button class="mini primary" data-select-op="${esc(r.id)}" ${result.outdated || !r.quantity || !crew || active ? 'disabled' : ''}>Prepare trade</button></div><div class="note">${r.runs == null ? 'Runs unknown' : fmt(r.runs)+' loading + '+fmt(r.runs)+' unloading runs'} | ${money(r.purchase_cost)} purchase cost | ${tons(r.stock)} aboard${r.stock_needs_check ? ' (needs reconciliation)' : ''}${r.order?.quantity ? ' | '+esc(r.order.side)+' order: '+tons(r.order.quantity) : ''}${!r.quantity ? ' | Check carrier free capacity before planning.' : ''}</div></article>`;
        }).join('') : result ? '<div class="muted trade-empty">No paired routes match. Increase the distance between stops, widen the search, or lower the minimum volume.</div>' : '';
      }
      const opCarrier = member ? S.party.carrier || {} : carrier;
      const carrierName = [opCarrier.name || 'Carrier', opCarrier.callsign].filter(Boolean).join(' / ');
      const phase = op?.stage || 'ready', loading = phase === 'loading', unloading = phase === 'unloading';
      const stageName = {ready:'Ready to start',loading:'Loading',transit:'In transit',unloading:'Unloading',complete:'Completed',cancelled:'Cancelled'}[phase];
      const price = plan?.crew_split?.[(loading || phase === 'ready') ? 'carrier_buy_price' : 'carrier_sell_price'] ?? (plan?.carrier_price_known ? plan.carrier_price : null);
      const instruction = !plan ? 'Choose a route to prepare a trade.' : op?.paused ? 'Paused. Do not begin another run. You can still report completed deliveries.' : loading ? (member ? `Buy ${plan.commodity} at ${plan.source}, then sell it to ${carrierName} at ${money(price)}/t.` : `Buy ${plan.commodity} at ${plan.source}, then transfer it directly into ${carrierName}. No sale to your own carrier is needed.`) : unloading ? (member ? `Buy ${plan.commodity} from ${carrierName} at ${money(price)}/t, then sell it at ${plan.destination}.` : `Transfer ${plan.commodity} from ${carrierName} to your ship, then sell at ${plan.destination}. The station sale records delivery.`) : phase === 'transit' ? `Wait for the carrier owner to open unloading near ${plan.destination}.` : phase === 'ready' ? 'Set the carrier buy order in game, then start loading to give the crew their instructions.' : 'This trade has ended. No further runs are requested.';
      const actionButton = (action, label, primary=false) => `<button class="mini ${primary ? 'primary' : ''}" data-op-action="${action}">${label}</button>`;
      const controls = member ? '' : !active ? plan?.mode === 'load' ? actionButton('start', ['complete','cancelled'].includes(phase) ? 'Start new loading' : 'Start loading', true) + ' <button class="mini" data-edit>Edit plan</button>' : '<button class="mini primary" data-back-search>Find a route</button>' : `<div class="row">${actionButton(op.paused ? 'resume' : 'pause', op.paused ? 'Resume trade' : 'Pause new runs')}${!op.paused ? loading ? actionButton('depart','Loading finished - depart',true) : phase === 'transit' ? actionButton('unload','Open unloading',true) : actionButton('complete','Finish trade',true) : ''}${actionButton('cancel','End trade')}</div>`;
      const ownerOrder = !member && plan && !['complete','cancelled'].includes(phase) ? `<div class="trade-owner-order"><b>${loading || phase === 'ready' ? 'Carrier BUY order' : 'Carrier SELL order'}</b><span>${money(price)}/t</span>${price != null ? `<button class="mini" data-copy="${price}">Copy price</button>` : ''}<span class="note">${tons(c?.to_haul)} remaining by observed inventory | ${tons(c?.stock)} aboard</span></div>` : '';
      const profitSummary = !member && c?.profit_split ? `<div class="trade-operation-progress"><div><span class="note">Total planned profit before crew</span><b class="trade-summary-money">${money(c.profit_split.gross_profit)}</b></div><div><span class="note">Your planned profit after crew</span><b class="trade-summary-money">${money(c.profit_split.owner_profit)}</b></div></div><div class="note">Estimates before fuel and fees; not realised earnings.</div>` : '';
      const reported = op ? `<div class="trade-operation-progress"><div><b>${tons(op.loaded)} / ${tons(op.quantity)}</b><div>Loading reported</div><progress max="${op.quantity}" value="${Math.min(op.quantity, op.loaded)}"></progress></div><div><b>${tons(op.unloaded)} / ${tons(op.quantity)}</b><div>Unloading reported</div><progress max="${op.quantity}" value="${Math.min(op.quantity, op.unloaded)}"></progress></div></div><div class="note">Crew reports, not confirmed carrier inventory. Stage buttons are the owner's confirmation to proceed.</div>` : '';
      const reports = Object.values(op?.reports || {});
      const roster = reports.length ? `<details class="trade-details"><summary>Delivered by crew</summary><table><thead><tr><th>Commander</th><th>Loaded</th><th>Unloaded</th></tr></thead><tbody>${reports.map(r=>`<tr><td>${esc(r.cmdr)}</td><td>${tons(r.loading)}</td><td>${tons(r.unloading)}</td></tr>`).join('')}</tbody></table></details>` : '';
      const draft = u.pendingRoute;
      const operationHtml = draft && !active ? `<div class="trade-active"><h3>Prepare ${esc(draft.name)} trade</h3><div>${esc(draft.buy.station)} / ${esc(draft.buy.system)} &gt; ${esc(draft.sell.station)} / ${esc(draft.sell.system)}</div><p>${tons(draft.quantity)} to move. Check current carrier stock so this load gets the right target.</p><form data-prepare-route class="row"><label>Currently aboard (t)<input data-prepare-stock type="number" min="0" max="1000000" required value="${esc(u.pendingStock)}"></label><button class="mini primary" type="submit">Save route</button><button class="mini" type="button" data-back-search>Back to routes</button></form></div>` : `<div class="trade-active"><div class="row"><span class="tag">${esc(op?.paused ? 'Paused' : stageName)}</span><h3>${esc(plan?.commodity || 'No trade selected')}</h3></div>${plan ? `<div class="note">${esc(plan.source)} &gt; ${esc(carrierName)} &gt; ${esc(plan.destination)}</div>` : ''}<div class="k">Crew task</div><p class="trade-instruction">${esc(instruction)}</p>${ownerOrder}${!member && S.party?.mode !== 'leader' ? '<div class="note">Not shared yet. Create a hauling party to give your crew this job.</div>' : ''}${member && S.party.stale ? '<div class="warn">Leader connection is stale. Confirm instructions before continuing.</div>' : ''}${opCarrier.system ? `<div class="note">Carrier last reported in ${esc(opCarrier.system)}</div>` : ''}${op?.notes ? `<p><b>Owner instructions:</b> ${esc(op.notes)}</p>` : ''}${reported}${profitSummary}<div class="trade-operation-controls">${controls}</div>${!member && plan ? `<div class="note">Carrier orders and jumps are set in game. This controls the team's instructions.</div>` : ''}${roster}${!member && c?.profit_split ? `<details class="trade-details"><summary>Prices and estimated profit</summary>${profitView(c.profit_split, c.profit_split.gross_profit)}</details>` : ''}</div>`;
      if (!draft || active || u.renderedDraft !== draft.id) { $('[data-operation]').innerHTML = operationHtml; u.renderedDraft = draft?.id; }
      const notes = $('[data-operation-notes]'); notes.hidden = member || !active;
      if (op && !u.notesDirty) notes.elements.notes.value = op.notes || '';
      const form = $('[data-trade-plan]'), planKey = JSON.stringify(p);
      if (p && !u.dirty && u.planKey !== planKey) { Object.entries(p).forEach(([k,v]) => {const i=form.elements[k];if(i){if(i.type==='checkbox')i.checked=v;else i.value=v;}});u.planKey=planKey; }
      const power = S.powerplay || {};
      $('[data-power]').textContent = `${power.power || 'Unpledged'} | Rank ${power.rank ?? 'unknown'}. Bonuses stay personal and require verified destination eligibility.`;
      const keys = [...new Set([...Object.keys(inv), ...Object.keys(orders)])].sort();
      $('[data-stock-count]').textContent = `(${keys.length} commodities)`;
      $('[data-ledger]').innerHTML = keys.length ? `<table><thead><tr><th>Commodity</th><th class="num">Aboard</th><th class="num">Order</th><th>Observed</th><th></th></tr></thead><tbody>${keys.map(k => `<tr><td>${esc(inv[k]?.name || orders[k]?.name || k)}</td><td class="num">${tons(inv[k]?.stock)}</td><td class="num">${orders[k]?.quantity ? esc(orders[k].side)+' '+tons(orders[k].quantity) : '-'}</td><td class="note">${esc(when(inv[k]?.updated_at))}</td><td><button class="mini" data-count-key="${esc(k)}">reconcile</button></td></tr>`).join('')}</tbody></table>` : '<div class="note">No commodity stock baseline found. Carrier history loads automatically; unknown counts stay unknown.</div>';
    },
  });
})();
