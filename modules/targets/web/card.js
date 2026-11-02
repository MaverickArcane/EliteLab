/* Rare-goods target planning. Quotes, modeled prices and merit assumptions stay separate. */
(() => {
  const {esc,fmt,ls,inaraSt,spanshSys}=Lab.util;
  const key='elitelab.targets.filters.v2';
  const money=n=>n==null?'Unknown':`${fmt(Math.round(n))} Cr`;
  const metric=n=>n==null?'Unknown':fmt(Math.round(n));
  const identity=r=>r ? `${r.system}\n${r.station}` : '';
  const field=(title,name,value='',type='text')=>`<label>${title}<input name="${name}" value="${value}" type="${type}" ${type==='number'?'min="0" step="any"':'maxlength="160"'}></label>`;
  const fields=f=>Object.fromEntries(new FormData(f));
  const context=S=>JSON.stringify([S.journal?.system,S.journal?.cmdr,S.journal?.cargo,S.journal?.jump_range_laden,S.journal?.jump_range_now,S.targets?.pledge,S.targets?.origins,S.targets?.evidence_revision]);
  const statusName=s=>({reported:'Reported quote',interpolated:'Interpolated price',not_reported:'Not reported',quantity_unknown:'Quantity unknown',stale_or_undated:'Stale or undated',prohibited:'Prohibited',demand_unknown:'Demand unknown',insufficient_demand:'Demand below load',price_unknown:'Price unknown'}[s]||'Unknown');

  function curve(el,d) {
    const select=el.querySelector('[data-target-curve]');
    const c=(d?.curves||[]).find(c=>c.key===select.value), out=el.querySelector('[data-target-chart]');
    if(!c||c.points.length<2){out.innerHTML='<p class="note">At least two fresh source-distance observations are needed. No curve is invented for missing data.</p>';return;}
    const points=c.points, minX=points[0].distance,maxX=points.at(-1).distance,maxY=Math.max(...points.map(p=>p.price));
    const xy=p=>[50+(p.distance-minX)/(maxX-minX||1)*520,150-p.price/(maxY||1)*125];
    out.innerHTML=`<svg viewBox="0 0 600 185" role="img" aria-label="${esc(c.name)} reported prices by source distance"><path d="M50 15V150H575" fill="none" stroke="currentColor" opacity=".4"/><polyline points="${points.map(p=>xy(p).join(',')).join(' ')}" fill="none" stroke="#ff9d32" stroke-dasharray="5 3"/>${points.map(p=>{const [x,y]=xy(p);return `<circle cx="${x}" cy="${y}" r="3" fill="#6fb3ff"><title>${esc(c.name)}: ${fmt(p.distance)} Ly from ${esc(c.origin)}, ${money(p.price)} / t (${p.observations} reports)</title></circle>`;}).join('')}<text x="50" y="175" fill="currentColor" font-size="11">${fmt(minX)} Ly</text><text x="570" y="175" text-anchor="end" fill="currentColor" font-size="11">${fmt(maxX)} Ly from ${esc(c.origin)}</text><text x="55" y="12" fill="currentColor" font-size="11">${money(maxY)} / t</text></svg><p class="note">${esc(c.note)} No extrapolation beyond observed distances.</p>`;
  }

  function show(el,d) {
    const u=el._targets;u.display=d;Lab.set('targets',{visible:d.results,selected:null});
    el.querySelector('[data-target-results]').innerHTML=d.results.length?d.results.map((r,i)=>`<article class="target-result" data-target-index="${i}">
      <div class="target-title"><div><small>${i+1}. ${esc(r.system)}</small><b>${esc(r.station)}</b></div><div><strong>${metric(r.merits_per_jump)}</strong><small>est. merits / jump</small></div></div>
      <div class="target-stats"><span>${metric(r.estimated_merits)} estimated merits</span><span>${money(r.estimated_sale)} load value</span><span>${fmt(r.dist)} Ly travel</span><span>${r.jumps==null?'Jumps unknown':`~${fmt(r.jumps)} jumps`}</span><span>Pad ${esc(r.pad)}</span><span>${r.ls==null?'Arrival unknown':`${fmt(r.ls)} ls`}</span></div>
      <p class="note">${r.age_hours==null?'Market date unknown/future':`Market ${fmt(Math.round(r.age_hours))}h old`}. ${r.priced_goods}/${r.goods_count} goods priced. ${r.estimated_sale==null?`Known subtotal: ${money(r.priced_subtotal)}; full load unknown.`:'Conditional forecast; confirm local Powerplay activity and cargo provenance.'} ${r.merit_eligibility==='blocked'?'Known cargo restriction blocks merit estimates.':''}</p>
      <details><summary>Per-good prices and origin distances</summary><div class="target-table"><table><thead><tr><th>Rare / tons</th><th>Origin / distance</th><th>Price / basis</th></tr></thead><tbody>${Object.values(r.goods).map(g=>`<tr><td>${esc(g.name)}<br>${fmt(g.tons)} t</td><td>${esc(g.origin||'Unknown origin')}<br>${g.source_distance==null?'Unknown':`${fmt(g.source_distance)} Ly`}</td><td>${money(g.price)} / t<br>${esc(statusName(g.status))}${g.eligibility==='blocked'?'<br>Merits blocked':''}</td></tr>`).join('')}</tbody></table></div></details>
      <div class="row"><button class="mini primary" data-target-select="${i}">Select sell target</button><button class="mini" data-copy="${esc(r.system)}">Copy system</button><a href="${inaraSt(r.station)}" target="_blank" rel="noopener noreferrer">Check station</a></div>
    </article>`).join(''):'<p class="note">No reported markets matched this power, distance band and pad. Adjust the filters and retry.</p>';
    const select=el.querySelector('[data-target-curve]'), previous=select.value;
    select.innerHTML=(d.curves||[]).map(c=>`<option value="${esc(c.key)}">${esc(c.name)}</option>`).join('');
    if((d.curves||[]).some(c=>c.key===previous))select.value=previous;
    el.querySelector('[data-target-limits]').textContent=`${d.rate_note} ${d.note}`;
    el.querySelector('[data-target-status]').textContent=`${d.results.length} shown from ${d.stations_checked} markets checked near ${d.ref}. ${d.manual_origin?'Manual planning origin; travel is not from your current location.':''} ${d.partial?'Partial provider results.':''}`;
    curve(el,d);
  }

  Lab.card({id:'targets',requires:['journal','powerplay','targets'],
    mount(el) {
      el.classList.add('target-desk');
      const u=el._targets={generation:0,compareGeneration:0,dead:false,dirty:false,pending:false,display:null};
      el.innerHTML=`<p data-target-context class="note"></p><form class="target-form" data-target-form>
        <label>Power<select name="power"><option value="">Use observed pledge</option>${(Lab.state.powerplay?.powers||[]).map(p=>`<option>${esc(p)}</option>`).join('')}</select></label>${field('Travel from','ref')}${field('Min distance (Ly)','min',125,'number')}${field('Max distance (Ly)','max',200,'number')}
        <label>Minimum pad<select name="pad"><option value="L">Large</option><option value="M">Medium</option></select></label>${field('Max quote age (hours)','hours',24,'number')}
        <label>Order by<select name="sort"><option value="merits_per_jump">Estimated merits / jump</option><option value="merits">Estimated merits</option><option value="distance">Travel distance</option></select></label>
        <label>Merit conversion<select name="rate_mode"><option value="unknown">Unknown rate</option><option value="mahon_observed">Mahon observation: 667 Cr / merit</option><option value="custom">My measured rate</option></select></label>${field('Custom Cr per merit','credits_per_merit','','number')}
        <label>Missing prices<select name="interpolate"><option value="false">Reported prices only</option><option value="true">Interpolate between observations</option></select></label>
        <button class="primary" type="submit">Find sell targets</button><button type="button" data-target-here>Use current system</button>
      </form><p class="note">Choose a merit conversion to calculate conditional rewards. The Mahon setting assumes the bonus conditions of the recorded observation still apply. Missing data stays unknown.</p>
      <p role="status" class="note" data-target-status>Load rare goods, choose a power and search for sell destinations.</p>
      <div data-target-results class="target-results"></div><div data-target-selection class="target-selection"></div>
      <details class="target-curves"><summary>Distance-price observations</summary><label>Rare <select data-target-curve></select></label><div data-target-chart></div></details>
      <details><summary>Forecast assumptions and coverage</summary><p class="note" data-target-limits>Prices and merit rates are estimates. Your recorded merit counter is separate.</p></details>
      <button class="mini" data-target-compare>Compare powers</button><div data-target-compare-out></div>`;
      const f=el.querySelector('form'), status=el.querySelector('[data-target-status]');
      for(const [name,value] of Object.entries(ls.get(key,{})||{})){const input=f.elements.namedItem(name);if(input&&typeof value==='string'&&value.length<=160)input.value=value;}
      const clear=()=>{u.display=null;el.querySelector('[data-target-results]').innerHTML='';el.querySelector('[data-target-chart]').innerHTML='';el.querySelector('[data-target-curve]').innerHTML='';Lab.set('targets',{selected:null,visible:[]});};
      u.invalidate=()=>{++u.generation;++u.compareGeneration;u.pending=false;clear();};
      f.addEventListener('input',()=>{u.dirty=true;u.invalidate();status.textContent='Filters changed. Search to refresh results.';ls.set(key,fields(f));});
      f.onsubmit=async event=>{
        event.preventDefault();u.context=context(Lab.state);++u.compareGeneration;const generation=++u.generation;clear();u.pending=true;u.dirty=false;status.textContent='Searching community markets...';
        try{const d=await Lab.api('/api/targets',fields(f));if(u.dead||generation!==u.generation)return;show(el,d);u.lastSeen=d.request_id;}
        catch(e){if(!u.dead&&generation===u.generation){clear();status.textContent=e.message;}}
        finally{if(generation===u.generation)u.pending=false;}
      };
      el.querySelector('[data-target-here]').onclick=()=>{f.elements.ref.value=Lab.state.journal?.system||'';f.dispatchEvent(new Event('input'));};
      el.querySelector('[data-target-curve]').onchange=()=>curve(el,u.display);
      el.addEventListener('click',e=>{const b=e.target.closest('[data-target-select]');if(b&&u.display?.results[+b.dataset.targetSelect])Lab.set('targets',{selected:u.display.results[+b.dataset.targetSelect]});});
      el.querySelector('[data-target-compare]').onclick=async()=>{const generation=++u.compareGeneration;status.textContent='Comparing reported acquisition markets...';try{const d=await Lab.api('/api/powers',{ref:f.elements.ref.value});if(u.dead||generation!==u.compareGeneration)return;el.querySelector('[data-target-compare-out]').innerHTML=d.powers.map(p=>`<p>${esc(p.power)}: ${p.error?'unavailable':fmt(p.count)} reported markets</p>`).join('');status.textContent='Power comparison ready; this does not change your pledge.';}catch(e){if(!u.dead&&generation===u.compareGeneration)status.textContent=e.message;}};
    },
    render(el,S) {
      const u=el._targets,f=el.querySelector('form'), next=context(S), changed=u.context!==undefined&&u.context!==next;
      if(changed){u.invalidate();u.lastSeen=Math.max(u.lastSeen||0,S.targets?.last?.request_id||0);el.querySelector('[data-target-status]').textContent='Cargo, ship, location or pledge changed. Search to refresh estimates.';}
      u.context=next;
      if(!f.elements.ref.value||f.elements.ref.value===u.lastSystem)f.elements.ref.value=S.journal?.system||'';
      u.lastSystem=S.journal?.system;
      const rares=(S.journal?.cargo?.items||[]).filter(r=>r.rare);
      el.querySelector('[data-target-context]').textContent=`${rares.length?rares.map(r=>`${r.count} t ${r.name}`).join(' | '):'No rare goods reported aboard.'} Pledge: ${S.targets?.pledge||'unknown'}. Search uses unboosted laden range; unknown range leaves merits/jump unknown.`;
      const d=S.targets?.last;
      if(d&&d.request_id>(u.lastSeen||0)&&!u.pending&&!u.dirty&&!changed){show(el,d);u.lastSeen=d.request_id;}
      const selected=S.targets?.selected;
      el.querySelector('[data-target-selection]').innerHTML=selected?`<b>Selected sell target: ${esc(selected.station)}</b><p class="note">${esc(selected.system)}. Highlighted in EliteLab; no in-game route is plotted.</p><button class="mini" data-copy="${esc(selected.system)}">Copy system</button><a href="${spanshSys(selected.system)}" target="_blank" rel="noopener noreferrer">Spansh</a>`:'';
      el.querySelectorAll('[data-target-index]').forEach(row=>row.classList.toggle('selected',identity(u.display?.results[+row.dataset.targetIndex])===identity(selected)));
    },
    unmount(el){el._targets.dead=true;}
  });
  Lab.map.addLayer('targets',{label:'sell targets',color:'#6fb3ff',z:1,
    points:S=>(S.targets?.visible||[]).filter(r=>[r.x,r.y,r.z].every(Number.isFinite)).map(r=>({name:r.system,x:r.x,y:r.y,z:r.z,r:4,sub:`${r.station} | ${r.dist} Ly | estimated merits/jump: ${metric(r.merits_per_jump)}`,selected:identity(S.targets?.selected)===identity(r),onClick:()=>Lab.set('targets',{selected:r})}))
  });
})();
