/* Saved material and recipe planning; journal craft evidence remains separate. */
(() => {
  const {esc,fmt,ls}=Lab.util, pref='materials.plan.ui.v1';
  const opt=(v,t)=>`<option value="${esc(v)}">${esc(t)}</option>`;
  const n=(v,known=true)=>known?fmt(v):'Unknown';
  const table=(rows,known)=>`<div class="plan-scroll"><table><thead><tr><th>Ingredient</th><th>Have</th><th>Earlier plans</th><th>Required</th><th>Short</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.name)}</td><td>${n(r.have,known)}</td><td>${fmt(r.reserved_before||0)}</td><td>${fmt(r.need)}</td><td class="${known&&r.short?'bad':''}">${n(r.short,known)}</td></tr>`).join('')}</tbody></table></div>`;
  Lab.card({id:'wishlist',requires:['wishlist','wishlist_ui','materials','synthesis','build'],
    mount(el){
      el.classList.add('material-plan');
      const u=el._plan={dead:false,seq:0,previewTimer:null,options:null,tab:'plan',preselected:null,version:null,busy:false};
      const $=s=>el.querySelector(s);
      el.innerHTML=`<div class="plan-intro"><div><p class="note">Plan quantities, compare shared stock, and find the remaining materials.</p></div><span class="tag" data-plan-stock></span></div>
        <div class="plan-tabs" role="tablist" aria-label="Materials workflow"><button role="tab" data-plan-tab="plan">Plan recipes</button><button role="tab" data-plan-tab="inventory">Inventory</button><button role="tab" data-plan-tab="evidence">Recorded synthesis / FSD</button></div>
        <div data-plan-page="plan"><div class="plan-columns"><section class="plan-composer"><h3>Add to plan</h3>
          <form data-plan-form><label>Type<select id="wl-kind">${opt('synthesis','Synthesis / FSD injection')}${opt('material','Material target')}${opt('blueprint','Engineering blueprint')}${opt('experimental','Experimental effect')}${opt('unlock','Tech broker unlock')}${opt('build','Pinned build')}</select></label>
          <label data-plan-module>Category / module<select id="wl-module"></select></label><label data-plan-recipe>Recipe / material<select id="wl-recipe"></select></label>
          <div id="wl-grades"><label>Current grade<select id="wl-from"></select></label><label>Target grade<select id="wl-to"></select></label></div>
          <label data-plan-quantity>Quantity<input id="wl-qty" type="number" value="1" min="1" max="10000" required></label>
          <div data-plan-preview role="status">Loading catalogue...</div><div class="plan-actions"><button class="primary" type="submit" id="wl-add">Add to saved plan</button><button type="button" data-preview-refresh>Refresh preview</button></div></form>
          <div class="note">Engineering grades plan the rolls above the current grade. Defaults of 1/2/3/4/5 rolls are estimates. Plans never trigger a game action.</div></section>
          <section><div class="plan-heading"><h3>Saved plan</h3><span data-plan-count></span></div><div class="wl-entries"></div><p class="note">Stock is assigned once in this order. Quantities are planning targets; recorded crafts do not automatically reduce them.</p></section></div>
          <section class="plan-requirements"><div class="plan-heading"><h3>Shared material requirements</h3><label><input type="checkbox" data-plan-all> Show covered materials</label></div><div class="wl-needs"></div></section>
          <section class="plan-sourcing"><h3>Source materials</h3><div class="plan-actions"><button type="button" data-plan-farms>Find sites for shortfalls</button><button type="button" id="wl-traders">Find material traders</button></div><div data-plan-sources role="status">Choose a material's Find sources action, or search for the whole plan.</div><details><summary>Suggested material exchanges</summary><div class="wl-trades"></div></details></section></div>
        <div data-plan-page="inventory" hidden><div class="plan-actions"><label>Filter inventory<input data-plan-inventory-filter placeholder="Material or category"></label><button data-plan-inventory-refresh>Refresh inventory</button></div><div data-plan-inventory role="status"></div></div>
        <div data-plan-page="evidence" hidden><div data-plan-evidence></div></div><div class="plan-message" data-plan-message role="status"></div>`;
      const kind=$('#wl-kind'),mod=$('#wl-module'),rec=$('#wl-recipe'),qty=$('#wl-qty');
      u.body=()=>({kind:kind.value,item:kind.value==='build'?'build':rec.value,qty:qty.value,module:mod.value,...(kind.value==='blueprint'?{from_grade:$('#wl-from').value,grade:$('#wl-to').value}:{})});
      const save=()=>ls.set(pref,{...u.body(),tab:u.tab});
      const message=(s,error=false)=>{const e=$('[data-plan-message]');e.textContent=s;e.classList.toggle('bad',error);};
      const grades=()=>{const b=(u.options.modules.find(m=>m.module===mod.value)?.blueprints||[]).find(b=>b.key===rec.value),max=b?.max_grade||5;$('#wl-from').innerHTML=Array.from({length:max},(_,i)=>opt(i,i?'G'+i:'Unengineered')).join('');$('#wl-to').innerHTML=Array.from({length:max},(_,i)=>opt(i+1,'G'+(i+1))).join('');$('#wl-to').value=String(max);};
      const recipes=()=>{
        const o=u.options,k=kind.value,m=mod.value;let rows=[];
        if(k==='synthesis')rows=o.synthesis.filter(r=>r.name===m).map(r=>[r.key,`${r.grade}${r.range_multiplier?' / +'+Math.round((r.range_multiplier-1)*100)+'% range':''}`]);
        if(k==='material')rows=(o.materials[m]||[]).map(r=>[r.key,`${r.name} / G${r.grade}`]);
        if(k==='blueprint')rows=(o.modules.find(r=>r.module===m)?.blueprints||[]).map(r=>[r.key,r.name]);
        if(k==='experimental')rows=(o.modules.find(r=>r.module===m)?.experimentals||[]).map(r=>[r.key,r.name]);
        if(k==='unlock')rows=o.unlocks.filter(r=>r.module===m).map(r=>[r.key,r.name]);
        rec.innerHTML=rows.map(r=>opt(...r)).join('');$('#wl-grades').hidden=k!=='blueprint';grades();
      };
      const modules=()=>{const o=u.options,k=kind.value;let rows=[];
        if(k==='synthesis')rows=[...new Set(o.synthesis.map(r=>r.name))].sort((a,b)=>a==='FSD Injection'?-1:b==='FSD Injection'?1:a.localeCompare(b));
        if(k==='material')rows=Object.keys(o.materials);
        if(k==='blueprint'||k==='experimental')rows=o.modules.filter(r=>r[k==='blueprint'?'blueprints':'experimentals'].length).map(r=>r.module);
        if(k==='unlock')rows=[...new Set(o.unlocks.map(r=>r.module))];
        mod.innerHTML=rows.map(r=>opt(r,r)).join('');['module','recipe','quantity'].forEach(x=>$(`[data-plan-${x}]`).hidden=k==='build');recipes();
      };
      u.preview=async()=>{clearTimeout(u.previewTimer);const seq=++u.seq,out=$('[data-plan-preview]');save();if(!u.options)return;
        if(kind.value==='build'){out.textContent='Tracks the pinned build and its live engineering requirements.';return;}
        out.textContent='Checking shared requirements...';
        try{const d=await Lab.post('/api/wishlist/preview',u.body());if(u.dead||seq!==u.seq)return;
          if(d.status==='ambiguous'){out.textContent='Choose a specific recipe.';return;}
          out.innerHTML=`<div class="plan-preview-title">${esc(d.entry.name)}${d.entry.tier?' / '+esc(d.entry.tier):''}</div>${d.entry.kind==='synthesis'?`<div><b>${n(d.entry.craftable,d.inventory_known)}</b> crafts available after earlier plans</div>`:''}${table(d.entry.ingredients,d.inventory_known)}<div class="note">${d.inventory_known?'Includes the saved plan before this addition.':'Waiting for a Materials snapshot. Stock and shortages are unknown.'}</div>`;
        }catch(e){if(!u.dead&&seq===u.seq)out.textContent=e.message+' Use Refresh preview to retry.';}
      };
      const schedule=()=>{++u.seq;clearTimeout(u.previewTimer);save();$('[data-plan-preview]').textContent='Updating preview...';u.previewTimer=setTimeout(u.preview,180);};
      kind.onchange=()=>{modules();schedule();};mod.onchange=()=>{recipes();schedule();};rec.onchange=()=>{grades();schedule();};qty.oninput=schedule;$('#wl-from').onchange=schedule;$('#wl-to').onchange=schedule;
      $('[data-preview-refresh]').onclick=u.preview;
      $('[data-plan-form]').onsubmit=async e=>{e.preventDefault();if(u.busy||!u.options)return;u.busy=true;$('#wl-add').disabled=true;
        try{const r=await Lab.post('/api/wishlist/add',u.body());if(u.dead)return;if(r.status==='ambiguous')throw Error('Choose a specific recipe.');message('Saved to plan.');await u.refresh();}
        catch(e){if(!u.dead)message(e.message,true);}finally{u.busy=false;if(!u.dead)$('#wl-add').disabled=false;}
      };
      u.refresh=async()=>{const seq=u.refreshSeq=(u.refreshSeq||0)+1,revision=JSON.stringify([Lab.state.materials?.inventory_version,Lab.state.wishlist?.entries]);const d=await Lab.api('/api/wishlist');if(u.dead||seq!==u.refreshSeq||revision!==JSON.stringify([Lab.state.materials?.inventory_version,Lab.state.wishlist?.entries]))return;Lab.set('wishlist',d);};
      u.inventory=async()=>{const seq=u.invSeq=(u.invSeq||0)+1,out=$('[data-plan-inventory]');out.textContent='Loading inventory...';try{const d=await Lab.api('/api/materials');if(u.dead||seq!==u.invSeq)return;u.inventoryRows=d.materials;u.drawInventory();}catch(e){if(!u.dead&&seq===u.invSeq)out.textContent=e.message+' Use Refresh inventory to retry.';}};
      u.drawInventory=()=>{const q=$('[data-plan-inventory-filter]').value.toLowerCase(),known=!!Lab.state.materials?.inventory_known;const rows=(u.inventoryRows||[]).filter(r=>(r.name+' '+r.category).toLowerCase().includes(q));$('[data-plan-inventory]').innerHTML=`<p class="note">${known?'Current stock from journal observations.':'A complete inventory snapshot has not been observed.'} Session gained counts receipts, not net changes.</p><div class="plan-scroll"><table><thead><tr><th>Material</th><th>Category</th><th>Have</th><th>Gained this session</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.name)}</td><td>${esc(r.category)} / G${r.grade||'?'}</td><td>${n(r.count,known)}</td><td>${fmt(r.gained)}</td></tr>`).join('')}</tbody></table></div>`;};
      $('[data-plan-inventory-filter]').oninput=u.drawInventory;$('[data-plan-inventory-refresh]').onclick=u.inventory;
      u.tabTo=t=>{u.tab=t;el.querySelectorAll('[data-plan-page]').forEach(p=>p.hidden=p.dataset.planPage!==t);el.querySelectorAll('[data-plan-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.planTab===t);b.setAttribute('aria-selected',String(b.dataset.planTab===t));});save();if(t==='inventory')u.inventory();};
      u.sources=async(type,key)=>{const seq=u.sourceSeq=(u.sourceSeq||0)+1,out=$('[data-plan-sources]');out.textContent='Finding sources...';
        try{const d=await Lab.api(type==='traders'?'/api/wishlist/traders':'/api/farming',type==='traders'?{}:key?{material:key,limit:12}:{for_wishlist:true,limit:12});if(u.dead||seq!==u.sourceSeq)return;
          if(type==='traders')out.innerHTML=Object.entries(d.traders).map(([k,v])=>`<h4>${esc(k)}</h4>`+(Array.isArray(v)?v.map(r=>`<p><b>${esc(r.system)}</b> / ${esc(r.station)} / ${fmt(r.dist)} Ly <button class="mini" data-copy="${esc(r.system)}">Copy system</button></p>`).join('')||'<p>No matching traders returned.</p>':`<p class="bad">${esc(v.error)}</p>`)).join('');
          else out.innerHTML=d.sites.length?d.sites.map(r=>`<article class="plan-site"><b>${esc(r.name)}</b> <span class="muted">${esc(r.system||'Method')}${r.body?' / '+esc(r.body):''}</span>${r.system?` <button class="mini" data-copy="${esc(r.system)}">Copy system</button>`:''}<p>${esc(r.how||r.notes||'')}</p></article>`).join(''):'No listed site covers these materials. Check material exchanges or the game sources.';
        }catch(e){if(!u.dead&&seq===u.sourceSeq)out.textContent=e.message+' Retry with the source buttons.';}
      };
      el.onclick=async e=>{const tab=e.target.closest('[data-plan-tab]');if(tab){u.tabTo(tab.dataset.planTab);return;}
        if(e.target.closest('[data-plan-farms]'))u.sources('farms');if(e.target.closest('#wl-traders'))u.sources('traders');
        const source=e.target.closest('[data-plan-source]');if(source)u.sources('farms',source.dataset.planSource);
        const rm=e.target.closest('[data-rm]'),edit=e.target.closest('[data-plan-edit]');if(!rm&&!edit)return;
        const b=rm||edit;b.disabled=true;
        try{await Lab.post(rm?'/api/wishlist/remove':'/api/wishlist/update',rm?{id:rm.dataset.rm}:{id:edit.dataset.planEdit,qty:edit.closest('[data-plan-entry]').querySelector('input').value});if(!u.dead){message(rm?'Removed from plan.':'Quantity saved.');await u.refresh();}}
        catch(e){if(!u.dead)message(e.message,true);}finally{if(b.isConnected)b.disabled=false;}
      };
      $('[data-plan-all]').onchange=()=>u.draw(Lab.state);
      el._preselect=p=>{if(!u.options||!p)return;kind.value=p.kind;modules();if(p.kind!=='build'){mod.value=p.module;recipes();rec.value=p.key;grades();}u.tabTo('plan');schedule();};
      u.loadOptions=async()=>{try{u.options=await Lab.api('/api/wishlist/options');if(u.dead)return;const s=ls.get(pref,{});if([...kind.options].some(o=>o.value===s.kind))kind.value=s.kind;modules();if([...mod.options].some(o=>o.value===s.module)){mod.value=s.module;recipes();}if([...rec.options].some(o=>o.value===s.item))rec.value=s.item;grades();if(s.qty)qty.value=s.qty;if(s.from_grade!=null)$('#wl-from').value=s.from_grade;if(s.grade)$('#wl-to').value=s.grade;u.tabTo(['plan','inventory','evidence'].includes(s.tab)?s.tab:'plan');u.preview();const p=Lab.state.wishlist_ui?.preselect;if(p){u.preselected=p.at;el._preselect(p);}}
        catch(e){if(!u.dead){$('[data-plan-preview]').textContent=e.message+' Reload catalogue to retry.';$('[data-preview-refresh]').textContent='Reload catalogue';$('[data-preview-refresh]').onclick=()=>{u.loadOptions();$('[data-preview-refresh]').onclick=u.preview;$('[data-preview-refresh]').textContent='Refresh preview';};}}};
      u.draw=S=>draw(el,S);u.loadOptions();
    },
    render(el,S){const u=el._plan;u.draw(S);const p=S.wishlist_ui?.preselect;if(p&&p.at!==u.preselected&&u.options){u.preselected=p.at;el._preselect(p);}
      const v=JSON.stringify([S.materials?.inventory_version,S.wishlist?.entries?.map(e=>[e.id,e.qty])]);if(v!==u.version){if(u.sourceSeq){++u.sourceSeq;el.querySelector('[data-plan-sources]').textContent='Plan or stock changed. Refresh sources for the current shortfalls.';}u.version=v;if(u.options){++u.seq;clearTimeout(u.previewTimer);u.previewTimer=setTimeout(u.preview,250);}if(u.tab==='inventory')u.inventory();}},
    unmount(el){const u=el._plan;u.dead=true;++u.seq;++u.invSeq;++u.sourceSeq;clearTimeout(u.previewTimer);}
  });
  function draw(el,S){const $=s=>el.querySelector(s),w=S.wishlist||{},known=!!w.inventory_known,entries=w.entries||[],sum=w.summary||{};
    $('[data-plan-stock]').textContent=known?'Inventory observed':'Inventory unknown';$('[data-plan-count]').textContent=`${entries.length} entries`;
    // Preserve quantity edits and open details while journal events update stock.
    const edits=new Map([...el.querySelectorAll('[data-plan-entry]')].map(e=>[e.dataset.planEntry,{value:e.querySelector('input')?.value,dirty:e.querySelector('input')?.value!==e.querySelector('input')?.defaultValue,open:e.querySelector('details')?.open}]));
    const focus=document.activeElement,active=focus?.closest('[data-plan-entry]')?.dataset.planEntry;
    $('.wl-entries').innerHTML=entries.length?entries.map((e,i)=>`<article class="plan-entry" data-plan-entry="${esc(e.id)}"><div><span class="plan-order">${i+1}</span><b>${esc(e.name)}</b>${e.tier?' / '+esc(e.tier):''}<span class="tag ${e.complete===true?'ok':e.complete===false?'bad':''}">${e.complete===null?'Stock unknown':e.complete?'Covered':fmt(e.short)+' short'}</span></div><div class="note">${e.legacy?'Existing material target':esc(e.kind)}${e.module?' / '+esc(e.module):''}${e.kind==='blueprint'?' / G'+e.from_grade+' to G'+e.grade:''}${e.label?' / '+esc(e.label):''}</div><div class="plan-actions">${e.kind==='build'?'<span>Follows pinned build</span>':`<label>Quantity<input type="number" min="1" max="10000" value="${e.qty}" aria-label="Quantity for ${esc(e.name)}"></label><button class="mini" data-plan-edit="${esc(e.id)}">Save quantity</button>`}<button class="mini" data-rm="${esc(e.id)}">Remove</button></div><details><summary>Ingredients${e.kind==='synthesis'?' / '+n(e.craftable,known)+' crafts available after earlier plans':''}</summary>${table(e.ingredients||[],known)}${e.commodities&&Object.keys(e.commodities).length?'<p>Also requires cargo: '+Object.entries(e.commodities).map(([k,v])=>fmt(v)+' '+esc(k)).join(', ')+'</p>':''}</details></article>`).join(''):'<div class="plan-empty">No saved entries. Choose a recipe or material target to see its requirements.</div>';
    el.querySelectorAll('[data-plan-entry]').forEach(e=>{const old=edits.get(e.dataset.planEntry);if(old){if(old.dirty&&e.querySelector('input'))e.querySelector('input').value=old.value;e.querySelector('details').open=old.open;}if(active===e.dataset.planEntry&&focus?.tagName==='INPUT')e.querySelector('input')?.focus();});
    const rows=(w.needs||[]).filter(r=>$('[data-plan-all]').checked||r.short||!known);
    $('.wl-needs').innerHTML=`<p>${known?`${fmt(sum.units_short||0)} units short across ${fmt(sum.short||0)} materials`:'Waiting for a complete Materials snapshot.'}</p><div class="plan-scroll"><table><thead><tr><th>Material</th><th>Have</th><th>Total planned</th><th>Short</th><th></th></tr></thead><tbody>${rows.map(r=>`<tr><td><b>${esc(r.name)}</b><small>${esc(r.category)} / G${r.grade||'?'}</small></td><td>${n(r.have,known)}</td><td>${fmt(r.need)}</td><td class="${known&&r.short?'bad':''}">${n(r.short,known)}</td><td><button class="mini" data-plan-source="${esc(r.key)}">Find sources</button></td></tr>`).join('')||'<tr><td colspan="5">No remaining shortfalls.</td></tr>'}</tbody></table></div>`;
    const t=w.trades||{};$('.wl-trades').innerHTML=known?`<div class="plan-scroll"><table><tbody>${(t.trades||[]).map((r,i)=>`<tr><td>${i+1}. ${esc(r.category)}</td><td>give ${fmt(r.give.qty)} ${esc(r.give.name)}</td><td>for ${fmt(r.get.qty)} ${esc(r.get.name)}</td></tr>`).join('')}</tbody></table></div>${(t.unresolved||[]).length?'<p>Still short after this plan: '+t.unresolved.map(r=>fmt(r.short)+' '+esc(r.name)).join(', ')+'</p>':''}<p class="note">${esc(t.note||'No exchanges found.')} Follow exchanges in the listed order; check outstanding shortfalls after trading.</p>`:'A complete inventory snapshot is needed before using exchange suggestions.';
    const d=S.synthesis?.summary;
    if(d){const b=d.boost||{};$('[data-plan-evidence]').innerHTML=`<section class="plan-boost"><h3>Observed FSD boost</h3><strong>${esc((b.status||'unknown').replaceAll('_',' '))}${b.multiplier?' / '+fmt(b.multiplier)+'x':''}</strong><p>${esc(b.observed_at||'No observation in this session')}${b.reason?' / '+esc(b.reason):''}</p><p class="note">Journal evidence, not a live boost gauge. Planning a recipe does not activate a boost. Injection and jet-cone boosts do not stack.</p>${d.last_jump?`<p>Last ship jump: ${esc(d.last_jump.system)} / BoostUsed: ${esc(d.last_jump.boost_used??'Unknown')}</p>`:''}</section><h3>FSD injection alternatives</h3><div class="plan-injections">${(d.injections||[]).map(r=>`<article><b>${esc(r.grade)} / +${Math.round((r.range_multiplier-1)*100)}%</b><p>${fmt(r.craftable)} crafts from total stock</p><small>${r.ingredients.map(i=>fmt(i.per_craft)+' '+esc(i.name)).join(', ')}</small></article>`).join('')}</div><p class="note">These alternatives share stock. Use Plan recipes to reserve a quantity alongside other entries.</p><h3>Recorded synthesis</h3>${d.history.length?d.history.map(r=>`<p>${esc(r.observed_at)} / ${esc(r.name)}${r.recipe_key?' / '+esc(r.recipe_key):' / tier unconfirmed'}</p>`).join(''):'<p>No recorded synthesis in the retained history.</p>'}<details><summary>Evidence limits</summary>${d.notes.map(t=>`<p class="note">${esc(t)}</p>`).join('')}</details>`;}
  }
})();
