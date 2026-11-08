/* Display-only estimates from acknowledged deliveries and saved price settings. */
const amount = (tonnes, rate) => tonnes === 0 ? 0 : tonnes == null || rate == null ? null : tonnes * rate;
const sum = values => values.some(v=>v==null) ? null : values.reduce((a,b)=>a+b,0);
const money = n => Number.isFinite(n) ? `${n.toLocaleString()} Cr` : 'Unknown';

export function profit(plan, report={}, assignment=null, stage='ready') {
  plan=plan || {};
  const split = plan.crew_enabled ? plan.crew_split : null;
  const rates = {loading:split?.loading_per_ton ?? null, unloading:split?.unloading_per_ton ?? null};
  if (!split && plan.carrier_price_known) {
    if (plan.mode==='load' && plan.price_basis!=='unknown acquisition') rates.loading=plan.carrier_price-plan.source_price;
    if (plan.mode==='unload' && plan.price_basis!=='unknown resale') rates.unloading=plan.destination_price-(plan.price_includes_bonus ? plan.bonus_per_ton || 0 : 0)-plan.carrier_price;
  }
  const legs={};
  for(const phase of ['loading','unloading']) {
    const delivered=report[phase] || 0, rate=Number.isFinite(rates[phase]) ? rates[phase] : null;
    const finished=['complete','cancelled'].includes(stage) || (phase==='loading' && ['transit','unloading'].includes(stage));
    const remaining=finished ? 0 : Number.isFinite(assignment?.[phase+'_target']) ? Math.max(0,assignment[phase+'_target']-delivered) : null;
    legs[phase]={delivered,per_ton:rate,recorded:amount(delivered,rate),remaining:amount(remaining,rate)};
  }
  const recorded=sum(Object.values(legs).map(l=>l.recorded)), remaining=sum(Object.values(legs).map(l=>l.remaining));
  return {...legs,recorded,remaining,estimated:sum([recorded,remaining])};
}

export function profitSummary(plan, report, assignment, stage, owner=false, ownerEstimate=null) {
  if(owner) return `<b>Carrier owner</b><div class="note">Est. job profit: ${money(ownerEstimate)}</div><div class="note">Direct transfers are not crew pay</div>`;
  const p=profit(plan,report,assignment,stage);
  return `<b data-profit-recorded>${money(p.recorded)}</b><div class="note">Load ${money(p.loading.recorded)} | Unload ${money(p.unloading.recorded)}</div><div class="note" data-profit-remaining>Remaining est. ${money(p.remaining)}</div><div class="note" data-profit-estimated>Total est. ${money(p.estimated)}</div>`;
}

export function profitTable(plan, operation, workload, members, esc) {
  plan=plan || {};
  const reports=operation?.reports || {}, assignments=new Map((workload?.members || []).map(m=>[m.id,m]));
  const live=new Map((members || []).map(m=>[m.id,m]));
  const ids=new Set([...live.keys(),...assignments.keys(),...Object.keys(reports)]);
  if(!ids.size)return '';
  const ownerEstimate=workload?.economics?.owner_profit ?? (plan.crew_enabled ? plan.crew_split?.owner_profit : null);
  const rows=[...ids].map(id=>{
    const r=reports[id] || {}, m=live.get(id) || {}, a=assignments.get(id);
    const owner=m.leader || r.owner || a?.owner;
    return `<tr><td>${esc(m.cmdr || r.cmdr || a?.cmdr || 'Unknown commander')}${owner ? ' (owner)' : ''}</td><td>${esc((r.loading || 0).toLocaleString())} t</td><td>${esc((r.unloading || 0).toLocaleString())} t</td><td>${profitSummary(plan,r,a,operation?.stage,owner,ownerEstimate)}</td></tr>`;
  });
  return `<div class="table-scroll"><table><thead><tr><th>Commander</th><th>Loaded</th><th>Unloaded</th><th>Individual profit*</th></tr></thead><tbody>${rows.join('')}</tbody></table></div><p class="note">*At agreed prices on acknowledged deliveries; excludes fuel, fees and personal bonuses. Remaining and total estimates follow assigned work. Without an assignment, future profit is unknown.</p>`;
}
