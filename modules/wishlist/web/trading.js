/* Material identity, ordered exchanges and comparable trader destinations. */
const {esc,fmt}=Lab.util;
const number=value=>Number.isFinite(value)?fmt(value):'Unknown';
export const identity=row=>`<span class="plan-material-meta"><span class="plan-grade">${row.grade?`G${esc(row.grade)}`:'Grade unknown'}</span><span>${esc(row.category||'Category unknown')}</span></span>${row.family?`<small>Family: ${esc(row.family)}</small>`:''}`;

export function exchanges(plan,known,all=false){
  if(!known)return '<p class="note">Observe a Materials snapshot to calculate exchanges from your inventory.</p>';
  const trades=plan.trades||[],shown=all?trades:trades.slice(0,8),unresolved=plan.unresolved||[];
  const types=Object.entries(plan.by_trader||{});
  return `<div class="plan-exchange-summary">${types.map(([category,value])=>`<button class="mini" data-plan-trader-type="${esc(category)}">${esc(category)} trader / ${fmt(value.trades)} ${value.trades===1?'exchange':'exchanges'}</button>`).join('')}</div>
    ${shown.length?`<p class="note">Follow the numbered steps in order. Ratios show units given : units received. Stock below is projected after each step.</p><ol class="plan-exchange-list">${shown.map((trade,index)=>`<li class="plan-exchange" data-plan-exchange><div class="plan-exchange-heading"><b>Step ${index+1}</b><span>${esc(trade.category)} trader</span><span class="${trade.same_family?'muted':'warn'}">${trade.same_family?'Same family':'Cross family'}</span></div><div class="plan-exchange-pair"><div><span class="k">Give</span><strong>${fmt(trade.give.qty)} ${esc(trade.give.name)}</strong>${identity(trade.give)}<small>Stock ${number(trade.give.before)} to ${number(trade.give.after)}</small></div><div class="plan-exchange-rate"><b>${esc(trade.ratio)}</b><small>give : receive</small></div><div><span class="k">Receive</span><strong>${fmt(trade.get.qty)} ${esc(trade.get.name)}</strong>${identity(trade.get)}<small>Stock ${number(trade.get.before)} to ${number(trade.get.after)}</small></div></div></li>`).join('')}</ol>`:'<p class="note">No exchanges found from your available surplus.</p>'}
    ${trades.length>8?`<button class="mini" data-plan-exchange-toggle>${all?'Show first 8 exchanges':`Show all ${fmt(trades.length)} exchanges`}</button>`:''}
    ${unresolved.length?`<details class="plan-unresolved"><summary>${fmt(unresolved.reduce((sum,row)=>sum+row.short,0))} units still short after these exchanges</summary>${unresolved.map(row=>`<p><b>${fmt(row.short)} ${esc(row.name)}</b> ${identity(row)}${row.note?`<small>${esc(row.note)}</small>`:''}</p>`).join('')}</details>`:''}
    <p class="note">Uses surplus after saved requirements and reserves. Recheck stock after trading.</p><details><summary>Planner notes</summary><p class="note">${esc(plan.note||'The in-game trader screen is authoritative.')}</p></details>`;
}

export function traders(result,sort='distance'){
  const metric=(value,unit)=>Number.isFinite(value)?`${fmt(value)} ${unit}`:'Unknown';
  return `<p class="note">Distances from <b>${esc(result.ref||'Unknown system')}</b>. Arrival is the reported distance from the main star.${result.pad==='L'?' Large pads required.':''}</p>${Object.entries(result.traders||{}).map(([category,list])=>{
    if(!Array.isArray(list))return `<section class="plan-trader-group"><h4>${esc(category)} traders</h4><p class="bad">${esc(list?.error||'Trader search failed.')}</p></section>`;
    const rows=[...list].sort((a,b)=>{const key=sort==='arrival'?'ls':'dist';return (a[key]??Infinity)-(b[key]??Infinity)||(a.dist??Infinity)-(b.dist??Infinity);});
    return `<section class="plan-trader-group"><h4>${esc(category)} traders</h4>${rows.length?rows.map(row=>{
      const link=Lab.util.inaraMarket(row.station,row.system);
      return `<article class="plan-trader" data-plan-trader><div class="plan-trader-title"><b>${esc(row.station||'Unknown station')}</b><span class="plan-grade">${esc(row.pad||'?')} pads</span></div><div>${esc(row.system||'Unknown system')}</div><div class="plan-trader-metrics"><div><span class="k">System distance</span><strong>${metric(row.dist,'Ly')}</strong></div><div><span class="k">Arrival from star</span><strong data-plan-arrival>${metric(row.ls,'Ls')}</strong></div><div><span class="k">Est. ship jumps</span><strong>${number(row.jumps)}</strong></div></div><p class="note">${esc(row.type||'Station type unknown')} / ${esc(row.economy||'Economy unknown')} / ${esc(category)} materials</p><div class="plan-actions">${row.system?`<button class="mini" data-copy="${esc(row.system)}">Copy system</button>`:''}${row.station?`<button class="mini" data-copy="${esc(row.station)}">Copy station</button>`:''}${link?`<a class="mini" href="${esc(link)}" target="_blank" rel="noopener noreferrer">Inara station</a>`:''}</div></article>`;
    }).join(''):'<p class="note">No matching stations returned.</p>'}</section>`;
  }).join('')}<p class="note">Sorted within the returned nearby candidates. Provider reports may be old; confirm services in game.</p>`;
}
