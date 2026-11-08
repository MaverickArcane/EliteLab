/* Saved material and recipe planning; journal craft evidence remains separate. */
(() => {
  const {esc,fmt,ls}=Lab.util, pref='materials.plan.ui.v1';
  let tradeUI;
  const tradeModule=import('/modules/wishlist/trading.js');
  tradeModule.then(module=>{tradeUI=module;Lab.emit('wishlist');}).catch(error=>console.error('Material trading view',error));
  const metadata=row=>tradeUI?tradeUI.identity(row):`<small>${esc(row.category||'Unknown')} / G${esc(row.grade||'?')}</small>`;
  const opt=(v,t)=>`<option value="${esc(v)}">${esc(t)}</option>`;
  const n=(v,known=true)=>known?fmt(v):'Unknown';
  const table=(rows,known)=>`<div class="plan-scroll"><table><thead><tr><th>Ingredient / category</th><th>Have</th><th>Earlier plans</th><th>Required</th><th>Short</th></tr></thead><tbody>${rows.map(r=>`<tr><td><b>${esc(r.name)}</b>${metadata(r)}</td><td>${n(r.have,known)}</td><td>${fmt(r.reserved_before||0)}</td><td>${fmt(r.need)}</td><td class="${known&&r.short?'bad':''}">${n(r.short,known)}</td></tr>`).join('')}</tbody></table></div>`;
  Lab.card({id:'wishlist',requires:['wishlist','wishlist_ui','materials','synthesis','build'],
    mount(el){
      el.classList.add('material-plan');
      const u=el._plan={dead:false,seq:0,sourceSeq:0,traderSeq:0,previewTimer:null,options:null,tab:'plan',preselected:null,version:null,busy:false};
      const $=s=>el.querySelector(s);
      el.innerHTML=`<div class="plan-overview"><div><span class="k">Saved entries</span><strong data-plan-stat="entries">0</strong></div><div><span class="k">Materials short</span><strong data-plan-stat="materials">Unknown</strong></div><div><span class="k">Units short</span><strong data-plan-stat="units">Unknown</strong></div><span class="tag" data-plan-stock></span></div>
        <div class="plan-tabs view-tabs" role="tablist" aria-label="Materials workflow"><button role="tab" data-plan-tab="plan">Wishlist <span data-plan-tab-count="plan"></span></button><button role="tab" data-plan-tab="add">Add recipes</button><button role="tab" data-plan-tab="requirements">Requirements <span data-plan-tab-count="requirements"></span></button><button role="tab" data-plan-tab="trading">Trading</button><button role="tab" data-plan-tab="gather">Gather</button><button role="tab" data-plan-tab="inventory">Inventory</button><button role="tab" data-plan-tab="evidence">Synthesis / FSD</button></div>
        <div data-plan-page="add" hidden><div class="plan-compose-layout"><section class="plan-composer"><h3>Add to plan</h3>
          <form data-plan-form><label>Type<select id="wl-kind">${opt('synthesis','Synthesis / FSD injection')}${opt('material','Material target')}${opt('blueprint','Engineering blueprint')}${opt('experimental','Experimental effect')}${opt('unlock','Tech broker unlock')}${opt('build','Pinned build')}</select></label>
          <label data-plan-module>Category / module<select id="wl-module"></select></label><label data-plan-recipe>Recipe / material<select id="wl-recipe"></select></label>
          <div id="wl-grades"><label>Current grade<select id="wl-from"></select></label><label>Target grade<select id="wl-to"></select></label></div>
          <label data-plan-quantity>Quantity<input id="wl-qty" type="number" value="1" min="1" max="10000" required></label>
          <label class="plan-follow" data-plan-follow-option hidden><input id="wl-follow-ship" type="checkbox" checked> Follow current ship</label>
          <div class="plan-actions"><button class="primary" type="submit" id="wl-add">Add to saved plan</button><button type="button" data-preview-refresh>Refresh preview</button></div></form>
          <div class="note">Engineering grades plan the rolls above the current grade. Defaults of 1/2/3/4/5 rolls are estimates. Plans never trigger a game action.</div></section><section class="plan-recipe-preview"><h3>Requirements for this addition</h3><div data-plan-preview role="status">Loading catalogue...</div></section></div></div>
          <div data-plan-page="plan"><section class="plan-saved"><div class="plan-heading"><div><h3>Saved wishlist</h3><span class="note" data-plan-count></span></div><button class="primary" data-plan-go="add">Add recipes</button></div><div class="wl-entries"></div><p class="note">Stock is assigned once in this order. Quantities are planning targets; recorded crafts do not automatically reduce them.</p></section></div>
          <div data-plan-page="requirements" hidden><section class="plan-requirements"><div class="plan-heading"><h3>Material requirements</h3><label><input type="checkbox" data-plan-all> Show covered materials</label></div><div class="plan-requirement-filters"><label>Find material<input data-plan-needs-filter placeholder="Name, family or G5"></label><label>Category<select data-plan-needs-category><option value="">All categories</option><option>Raw</option><option>Manufactured</option><option>Encoded</option><option>Guardian</option></select></label></div><div class="wl-needs"></div></section>
          </div><div data-plan-page="trading" hidden><section class="plan-sourcing"><h3>Material trading &amp; sourcing</h3><div class="plan-supply-layout"><section><h4>Suggested exchanges</h4><div class="wl-trades"></div></section><section><h4>Choose a material trader</h4><div class="plan-trader-filters"><label>Trader category<select data-plan-trader-category><option value="">Needed categories</option><option>Raw</option><option>Manufactured</option><option>Encoded</option></select></label><label>Landing pads<select data-plan-trader-pad><option value="">Any size</option><option value="L">Large required</option></select></label><label>Sort nearby stations<select data-plan-trader-sort><option value="distance">System distance</option><option value="arrival">Arrival distance (Ls)</option></select></label></div><div class="plan-actions"><button type="button" id="wl-traders">Find material traders</button></div><div data-plan-traders role="status">Find nearby traders to compare system distance, arrival distance and landing pads.</div></section></div></section></div><div data-plan-page="gather" hidden><section class="plan-farm-sources"><h3>Gather materials</h3><div class="plan-actions"><button type="button" data-plan-farms>Find sites for shortfalls</button></div><div data-plan-sources role="status">Choose a material's Find sources action, or search for the whole plan.</div></section></div>
        <div data-plan-page="inventory" hidden><div class="plan-actions"><label>Filter inventory<input data-plan-inventory-filter placeholder="Material, category, family or G5"></label><button data-plan-inventory-refresh>Refresh inventory</button></div><div data-plan-inventory role="status"></div></div>
        <div data-plan-page="evidence" hidden><div data-plan-evidence></div></div><div class="plan-message" data-plan-message role="status"></div>`;
      const kind=$('#wl-kind'),mod=$('#wl-module'),rec=$('#wl-recipe'),qty=$('#wl-qty');
      for(const panel of el.querySelectorAll('[data-plan-page]')){
        panel.classList.add('plan-workpage');panel.id='materials-page-'+panel.dataset.planPage;panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby','materials-tab-'+panel.dataset.planPage);
      }
      for(const tab of el.querySelectorAll('[data-plan-tab]')){tab.id='materials-tab-'+tab.dataset.planTab;tab.setAttribute('aria-controls','materials-page-'+tab.dataset.planTab);}
      Lab.util.tabKeys($('.plan-tabs'),'[data-plan-tab]');
      u.fit=()=>{if(!el.isConnected||el.closest('.workspace-off'))return;const top=el.getBoundingClientRect().top+scrollY;
        const available=top<innerHeight*.65?innerHeight-top-24:innerHeight-180;
        const height=Math.round(Math.max(380,Math.min(900,innerHeight-80,available)));
        if(el.style.getPropertyValue('--plan-height')!==height+'px')el.style.setProperty('--plan-height',height+'px');
      };
      addEventListener('resize',u.fit);addEventListener('lab:relayout',u.fit);
      u.body=()=>({kind:kind.value,item:kind.value==='build'?'build':rec.value,qty:qty.value,module:mod.value,...(kind.value==='build'?{follow_ship:$('#wl-follow-ship').checked}:{}),...(kind.value==='blueprint'?{from_grade:$('#wl-from').value,grade:$('#wl-to').value}:{})});
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
        rec.innerHTML=rows.map(r=>opt(...r)).join('');$('#wl-grades').hidden=k!=='blueprint';$('[data-plan-follow-option]').hidden=k!=='build';grades();
      };
      const modules=()=>{const o=u.options,k=kind.value;let rows=[];
        if(k==='synthesis')rows=[...new Set(o.synthesis.map(r=>r.name))].sort((a,b)=>a==='FSD Injection'?-1:b==='FSD Injection'?1:a.localeCompare(b));
        if(k==='material')rows=Object.keys(o.materials);
        if(k==='blueprint'||k==='experimental')rows=o.modules.filter(r=>r[k==='blueprint'?'blueprints':'experimentals'].length).map(r=>r.module);
        if(k==='unlock')rows=[...new Set(o.unlocks.map(r=>r.module))];
        mod.innerHTML=rows.map(r=>opt(r,r)).join('');['module','recipe','quantity'].forEach(x=>$(`[data-plan-${x}]`).hidden=k==='build');recipes();
      };
      u.preview=async()=>{clearTimeout(u.previewTimer);const seq=++u.seq,out=$('[data-plan-preview]');save();if(!u.options)return;
        if(kind.value==='build'){out.textContent=$('#wl-follow-ship').checked?'Requirements follow the current ship compared with the pinned build.':'Saves the current build requirements. Switching ships will not change them; material inventory stays live.';return;}
        out.textContent='Checking shared requirements...';
        try{const d=await Lab.post('/api/wishlist/preview',u.body());if(u.dead||seq!==u.seq)return;
          if(d.status==='ambiguous'){out.textContent='Choose a specific recipe.';return;}
          out.innerHTML=`<div class="plan-preview-title">${esc(d.entry.name)}${d.entry.tier?' / '+esc(d.entry.tier):''}</div>${d.entry.kind==='synthesis'?`<div><b>${n(d.entry.craftable,d.inventory_known)}</b> crafts available after earlier plans</div>`:''}${table(d.entry.ingredients,d.inventory_known)}<div class="note">${d.inventory_known?'Includes the saved plan before this addition.':'Waiting for a Materials snapshot. Stock and shortages are unknown.'}</div>`;
        }catch(e){if(!u.dead&&seq===u.seq)out.textContent=e.message+' Use Refresh preview to retry.';}
      };
      const schedule=()=>{++u.seq;clearTimeout(u.previewTimer);save();$('[data-plan-preview]').textContent='Updating preview...';u.previewTimer=setTimeout(u.preview,180);};
      kind.onchange=()=>{modules();schedule();};mod.onchange=()=>{recipes();schedule();};rec.onchange=()=>{grades();schedule();};qty.oninput=schedule;$('#wl-from').onchange=schedule;$('#wl-to').onchange=schedule;
      $('#wl-follow-ship').onchange=schedule;
      $('[data-preview-refresh]').onclick=u.preview;
      $('[data-plan-form]').onsubmit=async e=>{e.preventDefault();if(u.busy||!u.options)return;u.busy=true;$('#wl-add').disabled=true;
        try{const r=await Lab.post('/api/wishlist/add',u.body());if(u.dead)return;if(r.status==='ambiguous')throw Error('Choose a specific recipe.');message('Saved to plan.');await u.refresh();}
        catch(e){if(!u.dead)message(e.message,true);}finally{u.busy=false;if(!u.dead)$('#wl-add').disabled=false;}
      };
      u.refresh=async()=>{const seq=u.refreshSeq=(u.refreshSeq||0)+1,revision=JSON.stringify([Lab.state.materials?.inventory_version,Lab.state.wishlist?.entries]);const d=await Lab.api('/api/wishlist');if(u.dead||seq!==u.refreshSeq||revision!==JSON.stringify([Lab.state.materials?.inventory_version,Lab.state.wishlist?.entries]))return;Lab.set('wishlist',d);};
      u.inventory=async()=>{const seq=u.invSeq=(u.invSeq||0)+1,out=$('[data-plan-inventory]');out.textContent='Loading inventory...';try{const d=await Lab.api('/api/materials');if(u.dead||seq!==u.invSeq)return;u.inventoryRows=d.materials;u.drawInventory();}catch(e){if(!u.dead&&seq===u.invSeq)out.textContent=e.message+' Use Refresh inventory to retry.';}};
      u.drawInventory=()=>{const q=$('[data-plan-inventory-filter]').value.toLowerCase(),known=!!Lab.state.materials?.inventory_known;const rows=(u.inventoryRows||[]).filter(r=>(r.name+' '+r.category+' '+(r.family||'')+' g'+r.grade).toLowerCase().includes(q));$('[data-plan-inventory]').innerHTML=`<p class="note">${known?'Current stock from journal observations.':'A complete inventory snapshot has not been observed.'} Session gained counts receipts, not net changes.</p><div class="plan-scroll"><table><thead><tr><th>Material</th><th>Category</th><th>Have</th><th>Gained this session</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.name)}</td><td>${metadata(r)}</td><td>${n(r.count,known)}</td><td>${fmt(r.gained)}</td></tr>`).join('')}</tbody></table></div>`;};
      $('[data-plan-inventory-filter]').oninput=u.drawInventory;$('[data-plan-inventory-refresh]').onclick=u.inventory;
      u.tabTo=t=>{u.tab=t;el.querySelectorAll('[data-plan-page]').forEach(p=>p.hidden=p.dataset.planPage!==t);el.querySelectorAll('[data-plan-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.planTab===t);b.setAttribute('aria-selected',String(b.dataset.planTab===t));b.tabIndex=b.dataset.planTab===t?0:-1;});save();u.fit();if(t==='inventory')u.inventory();};
      const traderPreferences=ls.get('materials.traders.ui.v1',{});
      for(const [selector,value] of [['category',traderPreferences.category||''],['pad',traderPreferences.pad||''],['sort',traderPreferences.sort||'distance']]){
        const field=$('[data-plan-trader-'+selector+']');if([...field.options].some(option=>option.value===value))field.value=value;
      }
      const saveTraderPreferences=()=>ls.set('materials.traders.ui.v1',{category:$('[data-plan-trader-category]').value,pad:$('[data-plan-trader-pad]').value,sort:$('[data-plan-trader-sort]').value});
      const drawTraders=()=>{if(u.traders&&tradeUI)$('[data-plan-traders]').innerHTML=tradeUI.traders(u.traders,$('[data-plan-trader-sort]').value);};
      $('[data-plan-trader-sort]').onchange=()=>{saveTraderPreferences();drawTraders();};
      for(const selector of ['category','pad'])$('[data-plan-trader-'+selector+']').onchange=()=>{saveTraderPreferences();++u.traderSeq;u.traders=null;$('[data-plan-traders]').textContent='Selection changed. Find material traders to refresh these results.';};
      u.sources=async(type,key)=>{u.tabTo(type==='traders'?'trading':'gather');const counter=type==='traders'?'traderSeq':'sourceSeq',seq=u[counter]=(u[counter]||0)+1,out=$(type==='traders'?'[data-plan-traders]':'[data-plan-sources]');out.textContent='Finding sources...';
        try{const d=await Lab.api(type==='traders'?'/api/wishlist/traders':'/api/farming',type==='traders'?{types:$('[data-plan-trader-category]').value,pad:$('[data-plan-trader-pad]').value,limit:5}:key?{material:key,limit:12}:{for_wishlist:true,limit:12});if(type==='traders')await tradeModule;if(u.dead||seq!==u[counter])return;
          if(type==='traders'){u.traders=d;drawTraders();}
          else out.innerHTML=d.sites.length?d.sites.map(r=>`<article class="plan-site"><b>${esc(r.name)}</b> <span class="muted">${esc(r.system||'Method')}${r.body?' / '+esc(r.body):''}</span>${r.system?` <button class="mini" data-copy="${esc(r.system)}">Copy system</button>`:''}<p>${esc(r.how||r.notes||'')}</p></article>`).join(''):'No listed site covers these materials. Check material exchanges or the game sources.';
        }catch(e){if(!u.dead&&seq===u[counter])out.textContent=e.message+' Retry with the source buttons.';}
      };
      el.onclick=async e=>{const tab=e.target.closest('[data-plan-tab], [data-plan-go]');if(tab){u.tabTo(tab.dataset.planTab||tab.dataset.planGo);return;}
        const trader=e.target.closest('[data-plan-trader-type]');if(trader){$('[data-plan-trader-category]').value=trader.dataset.planTraderType;saveTraderPreferences();u.sources('traders');return;}
        if(e.target.closest('[data-plan-exchange-toggle]')){u.allExchanges=!u.allExchanges;u.draw(Lab.state);return;}
        if(e.target.closest('[data-plan-farms]'))u.sources('farms');if(e.target.closest('#wl-traders'))u.sources('traders');
        const source=e.target.closest('[data-plan-source]');if(source)u.sources('farms',source.dataset.planSource);
        const rm=e.target.closest('[data-rm]'),edit=e.target.closest('[data-plan-edit]');if(!rm&&!edit)return;
        const b=rm||edit;b.disabled=true;
        try{await Lab.post(rm?'/api/wishlist/remove':'/api/wishlist/update',rm?{id:rm.dataset.rm}:{id:edit.dataset.planEdit,qty:edit.closest('[data-plan-entry]').querySelector('input').value});if(!u.dead){message(rm?'Removed from plan.':'Quantity saved.');await u.refresh();}}
        catch(e){if(!u.dead)message(e.message,true);}finally{if(b.isConnected)b.disabled=false;}
      };
      el.onchange=async e=>{const input=e.target.closest('[data-plan-follow]');if(!input)return;input.disabled=true;
        try{await Lab.post('/api/wishlist/update',{id:input.dataset.planFollow,follow_ship:input.checked});if(!u.dead){message(input.checked?'Requirements now follow the current ship.':'Requirements saved. Switching ships will not change this entry.');await u.refresh();}}
        catch(error){if(!u.dead){message(error.message,true);u.draw(Lab.state);}}finally{if(input.isConnected)input.disabled=false;}
      };
      $('[data-plan-all]').onchange=()=>u.draw(Lab.state);
      $('[data-plan-needs-filter]').oninput=()=>u.draw(Lab.state);
      $('[data-plan-needs-category]').onchange=()=>u.draw(Lab.state);
      el._preselect=p=>{if(!u.options||!p)return;kind.value=p.kind;modules();if(p.kind!=='build'){mod.value=p.module;recipes();rec.value=p.key;grades();}u.tabTo('add');schedule();};
      u.loadOptions=async()=>{try{u.options=await Lab.api('/api/wishlist/options');if(u.dead)return;const s=ls.get(pref,{});if([...kind.options].some(o=>o.value===s.kind))kind.value=s.kind;modules();if([...mod.options].some(o=>o.value===s.module)){mod.value=s.module;recipes();}if([...rec.options].some(o=>o.value===s.item))rec.value=s.item;grades();if(s.qty)qty.value=s.qty;if(s.from_grade!=null)$('#wl-from').value=s.from_grade;if(s.grade)$('#wl-to').value=s.grade;$('#wl-follow-ship').checked=s.follow_ship!==false;u.tabTo(['plan','add','requirements','trading','gather','inventory','evidence'].includes(s.tab)?s.tab:'plan');u.preview();const p=Lab.state.wishlist_ui?.preselect;if(p){u.preselected=p.at;el._preselect(p);}}
        catch(e){if(!u.dead){$('[data-plan-preview]').textContent=e.message+' Reload catalogue to retry.';$('[data-preview-refresh]').textContent='Reload catalogue';$('[data-preview-refresh]').onclick=()=>{u.loadOptions();$('[data-preview-refresh]').onclick=u.preview;$('[data-preview-refresh]').textContent='Refresh preview';};}}};
      u.draw=S=>draw(el,S);u.loadOptions();
    },
    render(el,S){const u=el._plan;u.draw(S);const p=S.wishlist_ui?.preselect;if(p&&p.at!==u.preselected&&u.options){u.preselected=p.at;el._preselect(p);}
      const v=JSON.stringify([S.materials?.inventory_version,S.wishlist?.entries?.map(e=>[e.id,e.qty,e.follow_ship,e.units])]);if(v!==u.version){if(u.sourceSeq){++u.sourceSeq;el.querySelector('[data-plan-sources]').textContent='Plan or stock changed. Refresh sources for the current shortfalls.';}u.version=v;if(u.options){++u.seq;clearTimeout(u.previewTimer);u.previewTimer=setTimeout(u.preview,250);}if(u.tab==='inventory')u.inventory();}},
    unmount(el){const u=el._plan;u.dead=true;++u.seq;++u.invSeq;++u.sourceSeq;++u.traderSeq;clearTimeout(u.previewTimer);removeEventListener('resize',u.fit);removeEventListener('lab:relayout',u.fit);}
  });
  function draw(el,S){const $=s=>el.querySelector(s),w=S.wishlist||{},known=!!w.inventory_known,entries=w.entries||[],sum=w.summary||{};
    $('[data-plan-stock]').textContent=known?'Inventory observed':'Inventory unknown';$('[data-plan-count]').textContent=`${entries.length} entries`;
    $('[data-plan-stat="entries"]').textContent=fmt(entries.length);
    $('[data-plan-stat="materials"]').textContent=n(sum.short||0,known);
    $('[data-plan-stat="units"]').textContent=n(sum.units_short||0,known);
    $('[data-plan-tab-count="plan"]').textContent=fmt(entries.length);
    $('[data-plan-tab-count="requirements"]').textContent=known?fmt(sum.short||0):'?';
    // Preserve quantity edits and open details while journal events update stock.
    const edits=new Map([...el.querySelectorAll('[data-plan-entry]')].map(e=>[e.dataset.planEntry,{value:e.querySelector('input')?.value,dirty:e.querySelector('input')?.value!==e.querySelector('input')?.defaultValue,open:e.querySelector('details')?.open}]));
    const focus=document.activeElement,active=focus?.closest('[data-plan-entry]')?.dataset.planEntry;
    $('.wl-entries').innerHTML=entries.length?entries.map((e,i)=>`<article class="plan-entry" data-plan-entry="${esc(e.id)}"><div><span class="plan-order">${i+1}</span><b>${esc(e.name)}</b>${e.tier?' / '+esc(e.tier):''}<span class="tag ${e.complete===true?'ok':e.complete===false?'bad':''}">${e.complete===null?'Stock unknown':e.complete?'Covered':fmt(e.short)+' short'}</span></div><div class="note">${e.legacy?'Existing material target':esc(e.kind)}${e.module?' / '+esc(e.module):''}${e.kind==='blueprint'?' / G'+e.from_grade+' to G'+e.grade:''}${e.label?' / '+esc(e.label):''}</div><div class="plan-actions">${e.kind==='build'?`<label class="plan-follow"><input type="checkbox" data-plan-follow="${esc(e.id)}" ${e.follow_ship!==false?'checked':''}> Follow current ship</label><span class="note">${e.follow_ship===false?'Fixed requirements saved '+esc(e.saved_needs_at||'')+'; inventory stays live.':'Updates requirements when you switch ships or engineer modules.'}</span>`:`<label>Quantity<input type="number" min="1" max="10000" value="${e.qty}" aria-label="Quantity for ${esc(e.name)}"></label><button class="mini" data-plan-edit="${esc(e.id)}">Save quantity</button>`}<button class="mini" data-rm="${esc(e.id)}">Remove</button></div><details><summary>Ingredients${e.kind==='synthesis'?' / '+n(e.craftable,known)+' crafts available after earlier plans':''}</summary>${table(e.ingredients||[],known)}${e.commodities&&Object.keys(e.commodities).length?'<p>Also requires cargo: '+Object.entries(e.commodities).map(([k,v])=>fmt(v)+' '+esc(k)).join(', ')+'</p>':''}</details></article>`).join(''):'<div class="plan-empty">No saved entries. Choose a recipe or material target to see its requirements.</div>';
    el.querySelectorAll('[data-plan-entry]').forEach(e=>{const old=edits.get(e.dataset.planEntry);if(old){if(old.dirty&&e.querySelector('input'))e.querySelector('input').value=old.value;e.querySelector('details').open=old.open;}if(active===e.dataset.planEntry&&focus?.tagName==='INPUT')e.querySelector('input')?.focus();});
    const query=$('[data-plan-needs-filter]').value.toLowerCase(),category=$('[data-plan-needs-category]').value;
    const rows=(w.needs||[]).filter(r=>($('[data-plan-all]').checked||r.short||!known)&&(!category||r.category===category)&&`${r.name} ${r.family||''} g${r.grade}`.toLowerCase().includes(query));
    $('.wl-needs').innerHTML=`<p>${known?`${fmt(sum.units_short||0)} units short across ${fmt(sum.short||0)} materials`:'Waiting for a complete Materials snapshot.'}</p><div class="plan-scroll"><table><thead><tr><th>Material</th><th>Have</th><th>Total planned</th><th>Short</th><th></th></tr></thead><tbody>${rows.map(r=>`<tr><td><b>${esc(r.name)}</b>${metadata(r)}</td><td>${n(r.have,known)}</td><td>${fmt(r.need)}</td><td class="${known&&r.short?'bad':''}">${n(r.short,known)}</td><td><button class="mini" data-plan-source="${esc(r.key)}">Find sources</button></td></tr>`).join('')||'<tr><td colspan="5">No materials match this view.</td></tr>'}</tbody></table></div>`;
    $('.wl-trades').innerHTML=tradeUI?tradeUI.exchanges(w.trades||{},known,el._plan.allExchanges):'<p class="note">Loading exchange details...</p>';
    const d=S.synthesis?.summary;
    if(d){const b=d.boost||{};$('[data-plan-evidence]').innerHTML=`<section class="plan-boost"><h3>Observed FSD boost</h3><strong>${esc((b.status||'unknown').replaceAll('_',' '))}${b.multiplier?' / '+fmt(b.multiplier)+'x':''}</strong><p>${esc(b.observed_at||'No observation in this session')}${b.reason?' / '+esc(b.reason):''}</p><p class="note">Journal evidence, not a live boost gauge. Planning a recipe does not activate a boost. Injection and jet-cone boosts do not stack.</p>${d.last_jump?`<p>Last ship jump: ${esc(d.last_jump.system)} / BoostUsed: ${esc(d.last_jump.boost_used??'Unknown')}</p>`:''}</section><h3>FSD injection alternatives</h3><div class="plan-injections">${(d.injections||[]).map(r=>`<article><b>${esc(r.grade)} / +${Math.round((r.range_multiplier-1)*100)}%</b><p>${fmt(r.craftable)} crafts from total stock</p><small>${r.ingredients.map(i=>fmt(i.per_craft)+' '+esc(i.name)).join(', ')}</small></article>`).join('')}</div><p class="note">These alternatives share stock. Use Plan recipes to reserve a quantity alongside other entries.</p><h3>Recorded synthesis</h3>${d.history.length?d.history.map(r=>`<p>${esc(r.observed_at)} / ${esc(r.name)}${r.recipe_key?' / '+esc(r.recipe_key):' / tier unconfirmed'}</p>`).join(''):'<p>No recorded synthesis in the retained history.</p>'}<details><summary>Evidence limits</summary>${d.notes.map(t=>`<p class="note">${esc(t)}</p>`).join('')}</details>`;}
  }
})();
