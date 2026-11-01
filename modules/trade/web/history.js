/* Persistent correction form; shared history stays collapsed until needed. */
export function mount(el) {
  const {esc, fmt}=Lab.util;
  const u={op:null, state:null, baseline:null, dirty:false, busy:false, request:null, historyKey:'', destroyed:false};
  el.innerHTML=`<div class="row"><button class="mini" data-haul-export>Export test data</button><span class="note" data-export-status role="status"></span></div>
    <details class="trade-details" data-haul-history><summary>Delivery history &amp; corrections</summary>
      <p class="note">Reports record deliveries; they do not change in-game cargo. Corrections keep the original report and a reason. History starts with updates recorded by this version.</p>
      <div data-haul-discrepancy class="note warn"></div><div data-haul-history-list></div>
      <form data-haul-correction class="trade-form"><label>Commander<select name="member"></select></label>
        <label>Leg<select name="phase"><option value="loading">Loading</option><option value="unloading">Unloading</option></select></label>
        <label>Correct total delivered (t)<input name="tonnes" type="number" min="0" step="1" required></label>
        <label>Reason<input name="reason" maxlength="300" required placeholder="For example: duplicate manual report"></label>
        <div class="note trade-wide" data-correction-baseline></div><div class="row trade-wide"><button class="mini" type="submit">Save correction</button><button class="mini" type="button" data-correction-refresh>Refresh totals</button><span class="note" data-correction-status role="status"></span></div>
      </form><p class="note">Export includes quantities and retained history. Commander names are anonymized; connection secrets, addresses, notes and correction reasons are omitted. Nothing is uploaded.</p>
    </details>`;
  const $=s=>el.querySelector(s), form=$('[data-haul-correction]');
  const current=()=>{
    const member=form.elements.member.value,phase=form.elements.phase.value,row=u.op?.reports?.[member] || {};
    const incoming=u.state?.party?.members?.find(m=>m.id===member)?.work;
    const raw=Math.max((row.reported || row)[phase] || 0,incoming?.operation_id===u.op?.id ? incoming?.[phase] || 0 : 0);
    return {id:u.op?.id,member,phase,expected:row[phase] || 0,expected_reported:raw};
  };
  const capture=()=>{u.baseline=current();u.dirty=false;u.request=null;form.elements.tonnes.value=u.baseline.expected;form.elements.reason.value='';$('[data-correction-status]').textContent='';};
  form.elements.member.onchange=form.elements.phase.onchange=()=>{capture();Lab.emit('trade_ui');};
  form.oninput=e=>{if(e.target.matches('input')){u.dirty=true;u.request=null;}};
  $('[data-correction-refresh]').onclick=()=>{capture();Lab.emit('trade_ui');};
  form.onsubmit=async e=>{
    e.preventDefault();if(u.busy || !u.op)return;
    if(JSON.stringify(current())!==JSON.stringify(u.baseline)){$('[data-correction-status]').textContent='New progress arrived. Refresh totals before saving.';return;}
    u.request ||= crypto.randomUUID();
    const command={...u.baseline,tonnes:Number(form.elements.tonnes.value),reason:form.elements.reason.value,request_id:u.request};
    u.busy=true;for(const control of form.elements)control.disabled=true;
    try {
      const op=await Lab.post('/api/trade/correct',command);
      if(u.destroyed)return;
      u.op=op;Lab.set('trade',{operation:op});capture();
      $('[data-correction-status]').textContent='Correction saved and shared with the crew.';
    } catch(error){if(!u.destroyed)$('[data-correction-status]').textContent=error.message;}
    finally{u.busy=false;if(!u.destroyed)Lab.emit('trade_ui');}
  };
  $('[data-haul-export]').onclick=async e=>{
    const button=e.currentTarget;button.disabled=true;
    try {
      const data=await Lab.api('/api/trade/diagnostics');if(u.destroyed)return;
      const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
      const link=document.createElement('a');link.href=url;link.download='EliteLab-hauling-'+new Date().toISOString().replaceAll(':','-')+'.json';
      document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
      $('[data-export-status]').textContent='Test data downloaded. You can review the JSON before sharing it.';
    } catch(error){if(!u.destroyed)$('[data-export-status]').textContent=error.message;}
    finally{button.disabled=false;}
  };
  return {
    render(S){
      u.state=S;
      const member=S.party?.mode==='member', op=member ? S.party.operation : S.trade?.operation;
      u.op=op;$('[data-haul-history]').hidden=!op;form.hidden=member;
      if(!op)return;
      const over=['loading','unloading'].map(phase=>[phase,Object.values(op.reports || {}).reduce((n,r)=>n+(r[phase] || 0),0)-op.quantity]).filter(([,n])=>n>0);
      const pending=[];
      for(const m of S.party?.members || [])if(m.work?.operation_id===op.id){
        const accepted=op.reports?.[m.id] || {};
        for(const phase of ['loading','unloading']){
          const count=(m.work[phase] || 0)-((accepted.reported || accepted)[phase] || 0);
          if(count>0)pending.push(`${m.cmdr || 'Commander'}: ${fmt(count)} t ${phase} awaits acknowledgement. Check the target and any corrections.`);
        }
      }
      $('[data-haul-discrepancy]').textContent=[...over.map(([phase,n])=>`${phase}: ${fmt(n)} t over the target. Check the reports before advancing.`),...pending].join(' ');
      const entries=op.history || [], key=JSON.stringify([entries,op.history_count]);
      if(key!==u.historyKey){
        u.historyKey=key;
        const lines=[...entries].reverse().map(entry=>{
          let text;
          if(entry.kind==='delivery')text=`${entry.cmdr || 'Commander'}: ${entry.phase} ${fmt(entry.before)} -> ${fmt(entry.after)} t. Cumulative report accepted.`;
          else if(entry.kind==='correction')text=`${entry.cmdr || 'Commander'}: ${entry.phase} corrected ${fmt(entry.before)} -> ${fmt(entry.after)} t. ${entry.reason}`;
          else if(entry.kind==='workload')text=entry.action==='join' ? `${entry.cmdr || 'Commander'} joined: remaining work split automatically.` : `Workload updated: ${entry.mode}; owner ${entry.owner_hauls ? 'participating' : 'finishing existing cargo only'}.`;
          else text=`Job: ${entry.action}; ${entry.stage}${entry.paused ? ' (paused)' : ''}.`;
          const evidence=entry.last_entry;
          if(evidence)text+=` Latest local entry: ${evidence.kind==='manual'?'manual report':'journal '+evidence.kind}, ${fmt(evidence.tonnes)} t.`;
          return `<li><span class="note">${esc(new Date(entry.at).toLocaleString())}</span><div>${esc(text)}</div></li>`;
        });
        $('[data-haul-history-list]').innerHTML=lines.length ? `<ol>${lines.join('')}</ol><div class="note">Showing ${entries.length} of ${fmt(op.history_count || entries.length)} recorded updates. Export for retained history.</div>` : '<p class="note">No updates recorded yet. Existing totals are retained.</p>';
      }
      if(member)return;
      const names=new Map();
      for(const m of S.party?.members || [])names.set(m.id,m.cmdr || 'Commander');
      for(const m of S.trade?.workload?.members || [])if(!names.has(m.id))names.set(m.id,m.cmdr || 'Commander');
      for(const [id,r] of Object.entries(op.reports || {}))if(!names.has(id))names.set(id,r.cmdr || 'Commander');
      const select=form.elements.member,options=[...names].map(([id,name])=>`<option value="${esc(id)}">${esc(name)}</option>`).join('');
      if(select.dataset.options!==options){const previous=select.value;select.innerHTML=options;select.dataset.options=options;if(names.has(previous))select.value=previous;}
      if(!u.dirty && !u.busy && JSON.stringify(current())!==JSON.stringify(u.baseline))capture();
      const stale=JSON.stringify(current())!==JSON.stringify(u.baseline);
      for(const control of form.elements)control.disabled=u.busy;
      form.querySelector('[type=submit]').disabled=u.busy || stale || !select.value;
      form.elements.tonnes.max=op.quantity;
      $('[data-correction-baseline]').textContent=`Current credited total: ${fmt(current().expected)} t. Enter the corrected total, not an amount to add. Latest cumulative report: ${fmt(current().expected_reported)} t.`;
      if(stale && u.dirty)$('[data-correction-status]').textContent='New progress arrived. Your draft is preserved; refresh totals before saving.';
    },
    destroy(){u.destroyed=true;},
  };
}
