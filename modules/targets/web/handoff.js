/* Own-module extension: the existing finder and PR #69 share this explicit handoff. */
import './card.js';

const card=Lab.cards.targets, original={mount:card.mount,render:card.render,unmount:card.unmount};
const {esc,fmt}=Lab.util;
const field=(el,name)=>el.querySelector(`[name="${name}"],#t-${name}`);
const matching=(result,context)=>result&&result.ref===context.stop.system&&result.power===context.power;
const evidence=S=>JSON.stringify([S.journal?.cmdr,S.journal?.system,S.journal?.cargo,S.journal?.jump_range_now,S.journal?.jump_range_laden,S.powerplay?.power]);
card.requires=[...new Set([...card.requires,'personal'])];

function clear(el) {
  const u=el._tradeHandoff;u.response=null;u.awaitSearch=true;++u.generation;
  el._targets?.invalidate(); // PR #69 owns forecast cancellation and display state.
  Lab.set('targets',{last:null,selected:null,visible:[],handoff_last:null});
  const rows=el.querySelector('#t-body');
  if(rows)rows.innerHTML='<tr><td colspan="10">Review the planning origin and filters, then find targets.</td></tr>';
  const compare=el.querySelector('#t-compare-out');if(compare)compare.textContent='';
}

function apply(el,request) {
  const u=el._tradeHandoff;u.applied=request;u.stale=false;u.applying=true;u.evidence=evidence(Lab.state);
  Lab.set('targets',{handoff_active:true});
  clear(el);
  for(const name of ['ref','power']) {
    const value=request.next_tool.arguments[name];
    const input=field(el,name);if(!input)continue;
    input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
  }
  u.applying=false;
  const status=el.querySelector('[data-target-status],#t-status');
  if(status)status.textContent='Trade stop applied. Distance and pad filters are unchanged; review them before searching.';
}

card.mount=function(el) {
  original.mount.call(this,el);
  el._tradeHandoff={seen:null,applied:null,stale:false,applying:false,generation:0,response:null,awaitSearch:true,dead:false};
  const banner=document.createElement('section');banner.className='trade-powerplay-context';banner.dataset.tradePowerplayContext='';banner.hidden=true;el.prepend(banner);
  el.addEventListener('input',event=>{
    const u=el._tradeHandoff;if(u.applying||!u.applied)return;
    if(event.target===field(el,'ref')||event.target===field(el,'power')){u.applied=null;u.stale=false;Lab.set('targets',{handoff_active:false});}
    clear(el);Lab.emit('personal');
  });
  el.addEventListener('click',event=>{
    if(event.target.closest('[data-handoff-return]'))Lab.focusCard('personal');
    if(event.target.closest('[data-handoff-manual]')){const u=el._tradeHandoff;clear(el);u.applied=null;u.stale=false;Lab.set('targets',{handoff_active:false});Lab.emit('personal');}
  });
  const guard=event=>{
    const u=el._tradeHandoff;
    if(!u.applied)return;
    if(event.target.closest('#t-here')){clear(el);u.applied=null;u.stale=false;Lab.set('targets',{handoff_active:false});Lab.emit('personal');return;}
    const row=event.target.closest('#t-body tr[data-handoff-id]');
    if(event.type==='click'&&row&&!event.target.closest('button,a')) {
      event.preventDefault();event.stopImmediatePropagation();
      const target=u.response?.results.find(r=>JSON.stringify([r.system,r.station])===row.dataset.handoffId);
      if(target)Lab.set('targets',{selected:Lab.state.targets?.selected===target?null:target});
      return;
    }
    const searching=event.type==='submit'||event.target.closest('#t-go,[data-target-compare],#t-compare');
    if(!searching)return;
    if(u.stale||u.applied.token!==Lab.state.personal?.powerplay_handoff?.token){event.preventDefault();event.stopImmediatePropagation();u.stale=true;clear(el);Lab.emit('personal');return;}
    if(event.target.closest('#t-compare')){event.preventDefault();event.stopImmediatePropagation();el.querySelector('#t-status').textContent='Use finder manually to compare other powers.';return;}
    if(event.target.closest?.('#t-go')) {
      // The legacy finder has no request generation guard. Keep bound searches
      // local until their response still matches this route/pledge and filters.
      event.preventDefault();event.stopImmediatePropagation();legacyFind(el);return;
    }
    u.awaitSearch=false;
  };
  el.addEventListener('click',guard,true);el.addEventListener('submit',guard,true);
};

async function legacyFind(el) {
  const u=el._tradeHandoff, context=u.applied;
  clear(el);const generation=u.generation;
  const args=Object.fromEntries(['ref','power','min','max','pad'].map(name=>[name,field(el,name).value]));
  const status=el.querySelector('#t-status');status.textContent='Searching reported Powerplay markets...';
  try {
    let result=await Lab.api('/api/targets',args);
    if(u.dead||u.generation!==generation||context.token!==Lab.state.personal?.powerplay_handoff?.token)return;
    if(!matching(result,context))throw Error('Search context changed. Review the route and retry.');
    // The legacy "buys all" badge describes rare cargo, not this planned load.
    result={...result,results:result.results.map(r=>({...r,refuses:null,accepts_all:null}))};
    u.response=result;u.awaitSearch=false;Lab.set('targets',{handoff_last:result});
    if(!result.results.length)el.querySelector('#t-body').innerHTML='<tr><td colspan="10">No reported markets matched. Adjust the filters and retry.</td></tr>';
    status.textContent=`${fmt(result.results.length)} reported markets from ${result.ref}. Planned commodity eligibility remains unknown.`;
  } catch(error) {if(!u.dead&&u.generation===generation)status.textContent=error.message;}
}

card.render=function(el,S) {
  const u=el._tradeHandoff, current=S.personal?.powerplay_handoff, request=S.personal?.ui_powerplay;
  if(request&&request.request_id!==u.seen) {
    u.seen=request.request_id;
    if(current?.ready&&request.token===current.token&&request.next_tool?.name==='find_sell_targets')apply(el,request);
  }
  if(u.applied&&(!current?.ready||current.token!==u.applied.token)&&!u.stale){u.stale=true;clear(el);}
  if(u.applied&&u.evidence!==evidence(S)){u.evidence=evidence(S);clear(el);const status=el.querySelector('[data-target-status],#t-status');if(status)status.textContent='Cargo, ship, location or pledge changed. Search again from this planning origin.';}
  const preserved=u.applied?{ref:field(el,'ref').value,power:field(el,'power').value}:null;
  let state=S;
  if(u.applied) {
    const last=el._targets?(u.awaitSearch||u.stale||!matching(S.targets?.last,u.applied)?null:S.targets.last):u.response;
    state={...S,targets:{...S.targets,last}};
  }
  original.render.call(this,el,state);
  if(u.applied&&!el._targets)el.querySelectorAll('#t-body tr[data-i]').forEach(row=>{const r=u.response?.results[Number(row.dataset.i)];if(r)row.dataset.handoffId=JSON.stringify([r.system,r.station]);});
  if(preserved)for(const [name,value] of Object.entries(preserved))field(el,name).value=value;
  const banner=el.querySelector('[data-trade-powerplay-context]');banner.hidden=!u.applied;
  if(u.applied) {
    const c=u.applied;
    banner.innerHTML=`<b>${u.stale?'Trade handoff changed - refresh required':'Planning from the selected trade route'}</b>
      <p>${esc(c.stop.station)}, ${esc(c.stop.system)} | ${esc(c.role)} stop, leg ${c.leg+1}</p>
      <p>${fmt(c.quantity)} t ${esc(c.commodity)} planned | Pledge: ${esc(c.power)}</p>
      <p class="note">Quote reported: ${esc(c.stop.reported_at||'unknown')}. ${esc(current?.quotes?.message||'Quote freshness unknown.')}</p>
      <p class="note">${esc(u.stale?'The route, active leg, commander or pledge changed. Return to Trading and apply the current stop before searching.':c.note)}</p>
      <p class="note">Planned commodity eligibility: unknown. Expected merits: unknown.</p>
      <div class="row"><button type="button" class="mini" data-handoff-return>Return to Trading</button><button type="button" class="mini" data-handoff-manual>Use finder manually</button></div>`;
  }
};

card.unmount=function(el){el._tradeHandoff.dead=true;++el._tradeHandoff.generation;Lab.set('targets',{handoff_active:false});original.unmount?.call(this,el);};

// The legacy map reads targets.last; keep it on the same accepted response as
// the bound card. PR #69 uses targets.visible and already clears that on edits.
const layer=Lab.map.layers.targets;
for(const key of ['points','lines'])if(layer[key]) {
  const originalLayer=layer[key];
  layer[key]=S=>originalLayer(S.targets?.handoff_active?{...S,targets:{...S.targets,last:S.targets.handoff_last}}:S);
}
