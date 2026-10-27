/* Persistent owner controls; previews never overwrite a typed custom share. */
export function mount(el) {
  const {esc, fmt} = Lab.util;
  const tons = n => n == null ? 'Unknown' : `${fmt(n)} t`;
  const money = n => n == null ? 'Unknown' : `${fmt(n)} Cr`;
  const u = {generation:0, dirty:false, state:null, preview:null, key:'', destroyed:false};
  el.innerHTML = `<section class="workload-panel"><div class="row workload-heading"><h3>Crew workload</h3><span class="tag" data-wl-status>Preview</span></div>
    <div class="row"><label>Split <select data-wl-mode><option value="equal">Equal tonnes per commander</option><option value="custom">Custom shares</option></select></label><label class="chk"><input type="checkbox" data-wl-owner checked>I haul too (direct transfers)</label></div>
    <div data-wl-custom hidden><div class="note">Share weights: 1 each is equal tonnes; 2 gets twice as much as 1. Use 0 to sit out. Only connected, ready/hauling commanders receive new work.</div><div data-wl-inputs class="workload-shares"></div></div>
    <div data-wl-preview></div><div class="row"><button type="button" class="mini primary" data-wl-apply>Apply split</button><button type="button" class="mini" data-wl-refresh>Recalculate</button><span data-wl-message class="note" role="status"></span></div>
    <div class="note">Saved shares stay fixed through ship changes and disconnects. Rebalancing keeps completed deliveries and assigned cargo already aboard, then splits the remaining work. Orders are placed in game.</div></section>`;
  const $ = selector => el.querySelector(selector);
  const settings = () => ({mode:$('[data-wl-mode]').value, owner_hauls:$('[data-wl-owner]').checked,
    shares:Object.fromEntries([...el.querySelectorAll('[data-wl-share]')].map(input=>[input.dataset.wlShare,Number(input.value)]))});
  const busy = value => {
    u.busy=value;
    if(value) {++u.generation;clearTimeout(u.timer);}
    for(const control of el.querySelectorAll('[data-wl-mode], [data-wl-owner], [data-wl-refresh]')) control.disabled=value;
    if(value) for(const input of el.querySelectorAll('[data-wl-share]')) input.disabled=true;
    Lab.emit('trade_ui');
  };
  const invalidate = () => {
    u.preview=null; $('[data-wl-apply]').disabled=true;
    for(const button of el.querySelectorAll('[data-wl-preview] [data-copy]')) button.disabled=true;
  };
  const draw = w => {
    const op = u.state?.party?.operation || u.state?.trade?.operation;
    const phase = ['transit','unloading'].includes(op?.stage) ? 'unloading' : 'loading', loading = phase === 'loading';
    const total = w[phase], price = loading ? w.buy_price : w.sell_price;
    const value = total.order_remaining * price;
    $('[data-wl-preview]').innerHTML = `<div class="workload-orders"><div><span class="k">Carrier ${loading ? 'buy' : 'sell'} order</span><strong data-wl-order>${tons(total.order_remaining)}</strong><button class="mini" data-copy="${total.order_remaining}">Copy order tonnes</button></div><div><span class="k">Price per tonne</span><strong>${money(price)}</strong>${price == null ? '' : `<button class="mini" data-copy="${price}">Copy price</button>`}</div><div><span class="k">${loading ? 'Buy-order budget' : 'Order proceeds'}</span><strong>${price == null ? 'Unknown' : money(value)}</strong></div></div>
      <div class="note" data-wl-equation>${tons(total.remaining)} left ${loading ? 'to load' : 'to unload'} - ${tons(total.owner_remaining)} your direct transfers = ${tons(total.order_remaining)} for crew ${loading ? 'sales to' : 'purchases from'} the carrier.</div>
      <div class="table-scroll"><table class="workload-table"><thead><tr><th>Commander</th><th class="num">Assigned ${loading ? 'loading' : 'unloading'}</th><th class="num">Delivered</th><th class="num">Left</th><th class="num">Est. loads left</th></tr></thead><tbody>${w.members.map(r=>`<tr><td>${esc(r.cmdr)}${r.owner ? ' (you)' : ''}${r.connected ? '' : '<div class="note warn">Disconnected / stale</div>'}</td><td class="num">${tons(r[phase+'_target'])}</td><td class="num">${tons(r[phase+'_done'])}</td><td class="num">${tons(r[phase+'_remaining'])}</td><td class="num">${r[phase+'_runs_left'] == null ? 'Ship capacity unknown' : fmt(r[phase+'_runs_left'])}${r[phase+'_partial_load'] ? `<div class="note">Last load ${tons(r[phase+'_partial_load'])}</div>` : ''}</td></tr>`).join('')}</tbody></table></div>`;
  };
  const preview = async () => {
    if (u.destroyed || el.hidden || !u.state || u.busy) return;
    const generation = ++u.generation;
    invalidate();
    $('[data-wl-message]').textContent = 'Calculating shares...';
    try {
      const w = await Lab.post('/api/trade/workload', {action:'preview', ...settings()});
      if (u.destroyed || generation !== u.generation) return;
      u.preview = w; draw(w); $('[data-wl-message]').textContent = '';
      $('[data-wl-apply]').disabled = false;
    } catch(error) {if (!u.destroyed && generation === u.generation) {u.preview=null; $('[data-wl-preview]').replaceChildren(); $('[data-wl-message]').textContent=error.message;}}
  };
  const schedule = () => {clearTimeout(u.timer); u.timer=setTimeout(preview,250);};
  el.addEventListener('input', e => {
    if (!e.target.matches('[data-wl-mode], [data-wl-owner], [data-wl-share]')) return;
    u.dirty = true; ++u.generation; invalidate();
    $('[data-wl-custom]').hidden = $('[data-wl-mode]').value !== 'custom';
    $('[data-wl-status]').textContent = 'Unsaved preview'; schedule();
  });
  $('[data-wl-refresh]').onclick = () => {u.dirty=true; $('[data-wl-status]').textContent='Rebalance preview'; preview();};
  $('[data-wl-apply]').onclick = async () => {
    if (!u.preview || u.busy) return;
    busy(true); $('[data-wl-apply]').disabled=true;
    try {
      await Lab.post('/api/trade/workload',{action:'apply',...settings(),basis:u.preview.basis});
      u.dirty=false; u.key=''; $('[data-wl-message]').textContent='Workload shared with crew'; Lab.emit('trade_ui');
    } catch(error) { $('[data-wl-message]').textContent=error.message; u.preview=null; }
    finally {busy(false); if(u.preview) $('[data-wl-apply]').disabled=false;}
  };
  return {
    async beforeStart() {
      const trade=u.state?.trade;
      if(u.busy) throw new Error('Wait for the workload update to finish before starting.');
      if(!trade?.plan || ['complete','cancelled'].includes(trade.operation?.stage)) return;
      if(!u.dirty && trade.workload) return;
      // Starting uses the controls the owner can see, even if they have not
      // pressed Apply separately. Never silently start with different shares.
      const q=settings();
      busy(true);
      try {
        const draft=await Lab.post('/api/trade/workload',{action:'preview',...q});
        await Lab.post('/api/trade/workload',{action:'apply',...q,basis:draft.basis});
        u.dirty=false;u.key='';
      } finally {busy(false);}
    },
    render(S) {
      u.state=S;
      const p=S.party || {}, plan=S.trade?.plan, op=S.trade?.operation, saved=S.trade?.workload;
      el.hidden = p.mode === 'member' || !plan || ['complete','cancelled'].includes(op?.stage);
      if (el.hidden) return;
      for(const control of el.querySelectorAll('[data-wl-mode], [data-wl-owner], [data-wl-refresh]')) control.disabled=!!u.busy;
      const members=p.members || [];
      if (!u.dirty && u.savedBasis !== saved?.basis) {
        $('[data-wl-mode]').value=saved?.mode || 'equal'; $('[data-wl-owner]').checked=saved?.owner_hauls ?? true;
        for(const input of el.querySelectorAll('[data-wl-share]')) input.value=saved?.shares?.[input.dataset.wlShare] ?? 1;
        u.savedBasis=saved?.basis;
      }
      const container=$('[data-wl-inputs]'), known=new Set(members.map(m=>m.id));
      for (const row of [...container.children]) if (!known.has(row.dataset.member)) row.remove();
      for (const m of members) {
        let row=[...container.children].find(r=>r.dataset.member===m.id);
        if(!row) {row=document.createElement('label');row.dataset.member=m.id;row.innerHTML='<span></span><input type="number" min="0" max="10000" step="1">';const input=row.querySelector('input');input.dataset.wlShare=m.id;input.value=saved?.shares?.[m.id] ?? 1;container.append(row);}
        row.querySelector('span').textContent=(m.cmdr || 'Unknown')+(m.leader ? ' (you)' : '');
        row.querySelector('input').disabled=!!u.busy || !!m.stale || m.activity==='away' || (m.leader && !$('[data-wl-owner]').checked);
      }
      $('[data-wl-custom]').hidden=$('[data-wl-mode]').value!=='custom';
      if (!u.dirty) $('[data-wl-status]').textContent=saved ? 'Saved split' : 'Preview';
      $('[data-wl-apply]').textContent=op ? 'Rebalance remaining work' : 'Apply split';
      const key=JSON.stringify([plan,op?.id,op?.stage,op?.reports,saved?.basis,members.map(m=>[m.id,m.cmdr,m.leader,m.stale,m.activity,m.capacity,m.cargo_count,m.cargo])]);
      if(key!==u.key){u.key=key;++u.generation;u.preview=null;$('[data-wl-apply]').disabled=true;if(!u.busy)schedule();}
      // Once applied, show stable quotas as deliveries arrive. Rebalance previews
      // require an edit or Recalculate; they must not masquerade as saved quotas.
      if(saved && !u.dirty && p.workload) {
        draw(p.workload); $('[data-wl-apply]').disabled=true; clearTimeout(u.timer);
        const assigned=new Set(saved.members.map(m=>m.id));
        const newcomers=members.filter(m=>!assigned.has(m.id) && !m.stale && m.activity!=='away');
        if(!u.busy) $('[data-wl-message]').textContent=newcomers.length ? `${newcomers.map(m=>m.cmdr || 'A commander').join(', ')} joined after the split. Recalculate to include them.` : '';
      }
    },
    destroy(){u.destroyed=true;++u.generation;clearTimeout(u.timer);},
  };
}
