/* A persistent personal panel: live reports update values, never rebuild inputs. */
(() => {
  const { fmt, ls } = Lab.util;
  let profits;
  import('/modules/trade/earnings.js').then(module=>{profits=module;Lab.emit('party');}).catch(error=>console.error('Individual profits',error));
  let compact = ls.get('haul.compact.v1', true);
  const tons = n => n == null ? 'Unknown' : `${fmt(n)} t`;
  const money = n => n == null ? 'Unknown' : `${fmt(n)} Cr`;
  const phases = {ready:'Ready to start', loading:'Loading', transit:'In transit', unloading:'Unloading', complete:'Complete', cancelled:'Cancelled'};
  const actions = {wait:'Stand by', buy:'Buy your next load', deliver:'Deliver your cargo', transfer_in:'Transfer into carrier', transfer_out:'Collect from carrier'};
  Lab.card({
    id: 'haul', requires: ['party'],
    header(h) {
      h.innerHTML = '<button class="mini" data-haul-compact>Compact</button>';
      const button = h.querySelector('button');
      button.setAttribute('aria-pressed', String(compact));
      button.onclick = () => {compact = !compact; ls.set('haul.compact.v1', compact); button.setAttribute('aria-pressed', String(compact)); Lab.emit('party');};
    },
    mount(el) {
      el.innerHTML = `<div data-haul-empty class="haul-empty"><div class="k">Your next run</div><h3>Join your crew</h3><p>Create or join a party in Crew progress. Your next pickup and delivery will appear here when the owner chooses a route.</p></div>
        <div data-haul-job hidden>
          <div class="row haul-heading"><span class="tag" data-value="phase"></span><b data-value="commodity"></b><span class="muted" data-value="role"></span></div>
          <div class="haul-action"><div class="k">Your next action</div><h3 data-value="action"></h3><p data-value="reason"></p></div>
          <div class="haul-quantity"><div><span class="k" data-value="quantity-label">This run</span><strong data-value="quantity"></strong></div><button class="mini" data-haul-copy="quantity">Copy tonnes</button><span class="note" data-value="hold"></span></div>
          <div class="haul-assignment" data-assignment hidden><div><span class="k">My share this leg</span><b data-value="assigned"></b></div><div><span class="k">Still to deliver</span><b data-value="remaining"></b></div><div><span class="k">Est. loads left</span><b data-value="runs-left"></b></div><div class="note" data-value="load-breakdown"></div></div>
          <div class="haul-stops">
            <section data-stop="pickup"><div class="row"><span class="tag">1</span><b data-value="pickup-label">Pick up</b><span class="muted" data-value="buy-price"></span></div><strong data-value="pickup-system"></strong><div data-value="pickup-station"></div><div class="row"><button class="mini" data-haul-copy="pickup-system">Copy system</button><button class="mini" data-haul-copy="pickup-station">Copy station</button><a class="mini" data-haul-inara="pickup" target="_blank" rel="noopener noreferrer" hidden>Inara market</a></div></section>
            <section data-stop="delivery"><div class="row"><span class="tag">2</span><b data-value="delivery-label">Deliver</b><span class="muted" data-value="sell-price"></span></div><strong data-value="delivery-system"></strong><div data-value="delivery-station"></div><div class="row"><button class="mini" data-haul-copy="delivery-system">Copy system</button><button class="mini" data-haul-copy="delivery-station">Copy station</button><a class="mini" data-haul-inara="delivery" target="_blank" rel="noopener noreferrer" hidden>Inara market</a></div></section>
          </div>
          <div class="haul-pay"><div><span class="k">Margin per tonne</span><b data-value="rate"></b></div><div><span class="k">This run, estimated</span><b data-value="run-pay"></b></div></div>
          <div class="ship-sec">My progress</div>
          <div class="haul-personal"><div><span class="k">Loaded</span><strong data-value="loaded"></strong><progress data-progress="loading" aria-label="Your contribution to the loading target"></progress></div><div><span class="k">Unloaded</span><strong data-value="unloaded"></strong><progress data-progress="unloading" aria-label="Your contribution to the unloading target"></progress></div><div><span class="k">Recorded profit*</span><strong data-value="earned"></strong></div></div>
          <div data-personal-profit><div class="haul-pay"><div><span class="k">Remaining profit, estimated</span><b data-value="profit-remaining"></b></div><div><span class="k">My total profit, estimated</span><b data-value="profit-estimated"></b></div></div><div class="note" data-value="profit-breakdown"></div></div>
          <div class="note" data-value="earnings-note"></div><div class="note" data-value="adjustments"></div><div class="note warn" data-value="pending" role="status"></div>
          <div class="haul-notes" data-haul-notes hidden><span class="k">Owner instructions</span><div data-value="notes"></div></div>
          <div class="row haul-activity"><label>My status <select data-activity><option value="ready">Ready</option><option value="hauling">Hauling</option><option value="away">Away</option></select></label><span class="note" data-auto-tracking></span></div>
          <details class="trade-details" data-manual-details><summary>Record a missed delivery</summary><p class="note">Journal deliveries are automatic. Only add a delivery that was missed; adding an already tracked delivery would count it twice.</p><form data-delivery class="row"><label>Delivered tonnes<input name="tonnes" type="number" min="1" max="1000000" required></label><button class="mini" type="submit">Record delivery</button></form><div data-delivery-status class="note" role="status"></div></details>
          <div class="note haul-advisory">Suggested loads are shared estimates, not reserved stock. Check the in-game price and available quantity before buying.</div>
        </div>`;
      el._haul = {busy:false, request:null, draft:null};
      el.querySelector('[data-activity]').onchange = async e => {
        try { await Lab.post('/api/party/work', {activity:e.target.value}); }
        catch (error) { Lab.toast(error.message, 'bad'); Lab.emit('party'); }
      };
      const form = el.querySelector('[data-delivery]');
      form.oninput = () => {
        const p = Lab.state.party || {};
        el._haul.draft = {id:p.operation?.id, phase:p.operation?.stage};
        el._haul.request = null;
      };
      form.onsubmit = async e => {
        e.preventDefault();
        const u = el._haul, p = Lab.state.party || {}, status = el.querySelector('[data-delivery-status]');
        if (u.busy) return;
        const draft = u.draft || {id:p.operation?.id, phase:p.operation?.stage};
        if (draft.id !== p.operation?.id || draft.phase !== p.operation?.stage) {
          status.textContent = 'The trade stage changed while you were entering this delivery. Check the new stage and re-enter the amount.';
          return;
        }
        const signature = JSON.stringify([draft.id, draft.phase, Number(form.elements.tonnes.value)]);
        if (u.request?.signature !== signature) u.request = {signature, id:crypto.randomUUID()};
        u.busy = true; Lab.emit('party');
        try {
          const state = await Lab.post('/api/party/work', {...draft, tonnes:Number(form.elements.tonnes.value), request_id:u.request.id});
          form.reset(); u.draft = null; u.request = null;
          status.textContent = state.error || 'Delivery saved. Progress updates when the leader acknowledges it.';
        } catch (error) { status.textContent = error.message + ' You can retry this report safely.'; }
        finally {u.busy = false; Lab.emit('party');}
      };
    },
    render(el, S) {
      const p = S.party || {}, d = p.desk, active = !!d;
      el.classList.toggle('haul-compact', compact);
      el.querySelector('[data-haul-empty]').hidden = active && !!d;
      el.querySelector('[data-haul-job]').hidden = !active || !d;
      if (!active || !d) return;
      const set = (key, value) => { const node = el.querySelector(`[data-value="${key}"]`); const text = String(value ?? ''); if (node.textContent !== text) node.textContent = text; };
      const copy = (key, value) => { const button = el.querySelector(`[data-haul-copy="${key}"]`); button.disabled = value == null || value === ''; if (button.disabled) delete button.dataset.copy; else button.dataset.copy = String(value); };
      set('phase', d.stale ? 'Connection stale' : d.paused ? 'Paused' : phases[d.phase]);
      set('commodity', d.commodity); set('role', d.owner ? p.mode === 'idle' ? 'Owner / solo' : 'Carrier owner' : 'Crew');
      set('action', actions[d.action]); set('reason', d.reason); set('quantity', d.quantity == null ? '--' : tons(d.quantity));
      set('quantity-label', ['buy','transfer_out'].includes(d.action) ? 'Pick up now' : ['deliver','transfer_in'].includes(d.action) ? 'Deliver now' : 'This run');
      const assignment=d.assignment, leg=['transit','unloading','complete'].includes(d.phase) ? 'unloading' : 'loading';
      el.querySelector('[data-assignment]').hidden=!assignment;
      if(assignment) {
        set('assigned',tons(assignment[leg+'_target']));set('remaining',tons(assignment[leg+'_remaining']));
        set('runs-left',assignment[leg+'_runs_left'] ?? 'Unknown');
        const full=assignment[leg+'_full_loads'], tail=assignment[leg+'_partial_load'];
        set('load-breakdown',full==null ? 'Waiting for ship capacity to estimate loads.' : (full ? `${fmt(full)} full load${full===1?'':'s'} of ${tons(assignment.usable)}` : '')+(tail ? `${full ? ' + ' : ''}1 final load of ${tons(tail)}` : '')+(!full && !tail ? 'Your share is complete.' : '. Includes cargo already aboard; pickup amounts exclude it.'));
      }
      copy('quantity', d.action === 'wait' ? null : d.quantity);
      set('hold', `${tons(d.aboard)} ${d.commodity} aboard | ${tons(d.cargo_count)} / ${tons(d.capacity)} hold`);
      for (const key of ['pickup', 'delivery']) {
        set(key+'-system', d[key].system || 'System unknown'); set(key+'-station', d[key].station);
        copy(key+'-system', d[key].system); copy(key+'-station', d[key].copy_name || d[key].station);
        const link = el.querySelector(`[data-haul-inara="${key}"]`);
        // Carrier callsigns remain searchable after a jump; their reported system can lag.
        const url = Lab.util.inaraMarket(d[key].copy_name || d[key].station, d[key].copy_name ? null : d[key].system);
        link.hidden = !url;
        if (url) { link.href = url; link.title = `Open ${d[key].copy_name || d[key].station} market on Inara (new tab)`; }
        else { link.removeAttribute('href'); link.removeAttribute('title'); }
        el.querySelector(`[data-stop="${key}"]`).classList.toggle('is-next', d.action !== 'wait' && (key === 'pickup' ? ['buy','transfer_out'].includes(d.action) : ['deliver','transfer_in'].includes(d.action)));
      }
      set('pickup-label', d.owner && d.phase === 'unloading' ? 'Transfer from carrier' : 'Buy here');
      set('delivery-label', d.owner && d.phase === 'loading' ? 'Transfer to carrier' : 'Sell here');
      set('buy-price', d.owner && d.phase === 'unloading' ? 'Direct transfer' : `${money(d.buy_price)}/t`);
      set('sell-price', d.owner && d.phase === 'loading' ? 'Direct transfer' : `${money(d.sell_price)}/t`);
      set('rate', d.owner ? 'Owner' : money(d.per_ton)); set('run-pay', d.owner ? 'See job totals' : money(d.load_earnings));
      set('loaded', assignment ? `${fmt(d.progress.loading)} / ${tons(assignment.loading_target)}` : tons(d.progress.loading)); set('unloaded', assignment ? `${fmt(d.progress.unloading)} / ${tons(assignment.unloading_target)}` : tons(d.progress.unloading)); set('earned', d.owner ? 'See job totals' : money(d.earnings));
      el.querySelector('[data-personal-profit]').hidden=d.owner;
      if(!d.owner && profits) {
        const income=profits.profit(p.plan,d.progress,assignment,d.phase);
        set('profit-remaining',money(income.remaining));set('profit-estimated',money(income.estimated));
        set('profit-breakdown',`Recorded: loading ${money(income.loading.recorded)} | unloading ${money(income.unloading.recorded)}. Estimates follow your assigned work.`);
      }
      set('earnings-note', d.owner ? 'Your direct transfers count toward progress. Owner profit estimates are in Carrier job.' : 'Margin at agreed prices on acknowledged deliveries; excludes fuel, fees and personal bonuses. '+(assignment ? 'Bars show progress against your assigned tonnes.' : 'Bars show your contribution to the job target.'));
      el.querySelector('.haul-personal').title = el.querySelector('[data-value=earnings-note]').textContent;
      el.querySelector('.haul-pay').title = 'Estimated margin at agreed prices, before fuel, fees and personal bonuses.';
      el.querySelector('.haul-quantity').title = 'Suggested load, not reserved stock. Confirm quantity and price in game.';
      for (const phase of ['loading','unloading']) { const bar = el.querySelector(`[data-progress="${phase}"]`); const target=assignment ? assignment[phase+'_target'] : d.target; bar.max = target || 1; bar.value = Math.min(target || 1, d.progress[phase]);bar.setAttribute('aria-label',assignment ? `Your assigned ${phase} progress` : `Your contribution to the ${phase} target`); }
      const pending = Object.entries(d.pending).filter(([,n])=>n).map(([phase,n])=>`${tons(n)} ${phase}`).join(', ');
      set('pending', pending ? `${pending} saved locally, awaiting leader acknowledgement. Do not report again.` : '');
      const adjustments=Object.entries(d.adjustments || {}).filter(([,n])=>n).map(([phase,n])=>`${phase}: ${n>0?'+':''}${fmt(n)} t`).join(', ');
      set('adjustments',adjustments ? `Owner corrections included in your progress (${adjustments}). See Delivery history in Carrier job.` : '');
      set('notes', d.notes); el.querySelector('[data-haul-notes]').hidden = !d.notes;
      const activity = el.querySelector('[data-activity]'); if (document.activeElement !== activity) activity.value = p.activity || 'ready';
      const working = ['loading','unloading'].includes(d.phase), tracking = p.auto_tracking?.[d.phase];
      el.querySelector('[data-auto-tracking]').textContent = working ? tracking ? 'Journal tracking on' : 'Market ID missing: use manual reporting' : 'Journal tracking waits for an active leg';
      const form = el.querySelector('[data-delivery]'), canReport = working && !d.stale && !el._haul.busy;
      form.elements.tonnes.disabled = !canReport; form.querySelector('button').disabled = !canReport;
    },
  });
})();
