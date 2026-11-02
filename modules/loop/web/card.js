/* Rare buying workflow; visit marks and destination selection stay local. */
(() => {
  const {esc,fmt,ls,inaraSt}=Lab.util, storage='elitelab.rares.visits.v2';
  const id=s=>JSON.stringify([s.system,s.station]);
  const scope=S=>JSON.stringify([S.journal?.cmdr||'',S.loop?.id||'']);
  const signature=S=>JSON.stringify(S.journal?.cargo||null);
  const marks=()=>{const m=ls.get(storage,{});return m&&typeof m==='object'&&!Array.isArray(m)?m:{};};
  const save=m=>ls.set(storage,Object.fromEntries(Object.entries(m).slice(-128)));
  function rows(S) {
    const m=marks(), prefix=scope(S), sig=signature(S), known=S.loop?.workflow?.cargo_known;
    return (S.loop?.stations||[]).map(s=>{const v=m[JSON.stringify([prefix,id(s)])], manual=known&&v?.signature===sig&&typeof v.done==='boolean';
      return {...s,done:manual?v.done:!!s.in_hold,manual:!!manual};
    }).sort((a,b)=>Number(a.done)-Number(b.done)||(a.dist??Infinity)-(b.dist??Infinity));
  }
  function prune(S) {
    if(!S.loop?.workflow)return;
    const m=marks(), prefix=scope(S), sig=signature(S);let changed=false;
    for(const k of Object.keys(m)) {
      try {if(JSON.parse(k)[0]===prefix&&(!S.loop?.workflow?.cargo_known||m[k]?.signature!==sig)){delete m[k];changed=true;}}
      catch {delete m[k];changed=true;}
    }
    if(changed)save(m);
  }
  const select=s=>Lab.set('loop',{ui_selected:{system:s.system,station:s.station}});
  Lab.card({id:'loop',requires:['loop','journal'],
    mount(el) {
      el.classList.add('rares-desk');el._rares={pending:false,dead:false};
      el.innerHTML=`<div class="row"><label>Rare loop <select data-rares-loop></select></label><button class="mini" data-rares-reset>Reset my visit marks</button></div><p role="status" class="note" data-rares-status></p><div data-rares-next class="rares-next"></div>
        <div class="row"><button class="mini" data-rares-focus="cargo">View cargo</button><button class="mini" data-rares-focus="market">View local rare stock</button><button class="mini" data-rares-focus="targets">Compare rare sell targets</button></div>
        <p class="note" data-rares-summary></p><div data-rares-list class="rares-list"></div><p class="note" data-rares-note></p>`;
      const pick=el.querySelector('[data-rares-loop]');
      pick.onchange=async()=>{const u=el._rares;u.pending=true;pick.disabled=true;el.querySelector('[data-rares-status]').textContent='Changing rare loop...';
        try{await Lab.post('/api/loop/select',{id:pick.value});if(!u.dead)el.querySelector('[data-rares-status]').textContent='Rare loop selected.';}
        catch(e){if(!u.dead)el.querySelector('[data-rares-status]').textContent=e.message;}
        finally{u.pending=false;if(!u.dead){pick.disabled=false;pick.value=Lab.state.loop?.id||'';}}
      };
      el.addEventListener('click',e=>{
        const focus=e.target.closest('[data-rares-focus]');if(focus)Lab.focusCard(focus.dataset.raresFocus);
        if(e.target.closest('[data-rares-reset]')){const m=marks(),prefix=scope(Lab.state);for(const k of Object.keys(m)){try{if(JSON.parse(k)[0]===prefix)delete m[k];}catch{delete m[k];}}save(m);Lab.emit('loop');}
        const pin=e.target.closest('[data-rares-select]');if(pin){const s=rows(Lab.state).find(s=>id(s)===pin.dataset.raresSelect);if(s)select(s);}
      });
      el.addEventListener('change',e=>{if(!e.target.matches('[data-rares-visit]')||!Lab.state.loop?.workflow?.cargo_known)return;
        const s=rows(Lab.state).find(s=>id(s)===e.target.dataset.raresVisit);if(!s)return;
        const m=marks();m[JSON.stringify([scope(Lab.state),id(s)])]={done:e.target.checked,signature:signature(Lab.state)};save(m);Lab.emit('loop');
      });
    },
    render(el,S) {
      prune(S);
      const L=S.loop||{}, list=rows(S), known=L.workflow?.cargo_known, next=list.find(s=>!s.done), selected=list.find(s=>L.ui_selected&&id(s)===id(L.ui_selected));
      const pick=el.querySelector('[data-rares-loop]'), available=JSON.stringify(L.available||[]);
      if(pick.dataset.options!==available){pick.innerHTML=(L.available||[]).map(a=>`<option value="${esc(a.id)}">${esc(a.name)}</option>`).join('');pick.dataset.options=available;}
      if(!el._rares.pending)pick.value=L.id||'';
      el.querySelector('[data-rares-next]').innerHTML=next?`<small>Next buy stop${!known?' - cargo unknown':''}</small><h3>${esc(next.station)}</h3><b>${esc(next.system)}</b><p>${next.dist==null?'Distance unknown':fmt(next.dist)+' Ly from current system'} | ${esc(next.type)} | ${fmt(next.ls)} ls arrival</p><p>${next.docked_here?'Docked at this buy station. Open its market and confirm stock before buying.':'Travel to this station and check local stock.'}</p><button class="primary" data-rares-select="${esc(id(next))}">Select buy stop</button> <button class="mini" data-copy="${esc(next.system)}">Copy system</button>`
        :`<h3>${list.length?'All stops have cargo aboard or a manual visit mark':'No rare loop loaded'}</h3><p>${list.length?'Review cargo, then compare sell targets. Marks do not prove a purchase, profit or merit eligibility.':'Choose an available loop to plan buy stops.'}</p>`;
      el.querySelector('[data-rares-summary]').textContent=`${list.filter(s=>s.done).length}/${list.length} stops marked. ${known?fmt(L.tons_total)+' t of loop rares aboard; '+(L.workflow.free_capacity==null?'free capacity unknown':fmt(L.workflow.free_capacity)+' t free')+'.':'Cargo has not been reliably observed. Visit marks are disabled.'} ${selected?'Selected: '+selected.station+', '+selected.system+'. No in-game route is plotted.':''}`;
      el.querySelector('[data-rares-list]').innerHTML=list.map(s=>`<article class="rares-stop ${selected&&id(s)===id(selected)?'selected':''}"><div><b>${esc(s.station)}</b><p>${esc(s.system)} | ${s.dist==null?'Distance unknown':fmt(s.dist)+' Ly'} | ${fmt(s.ls)} ls</p><p>${s.rares.map(r=>esc(r.name)).join(' | ')}</p><p>${s.tons==null?'Cargo unknown':fmt(s.tons)+' t aboard'}${s.docked_here?' | Docked at this station':''}${s.manual?' | Manual visit mark':''}</p></div>
        <label><input type="checkbox" data-rares-visit="${esc(id(s))}" ${s.done?'checked':''} ${known?'':'disabled'}> ${s.manual?'Manually marked':'Cargo aboard / mark visited'}</label><div class="row"><button class="mini" data-rares-select="${esc(id(s))}">Select stop</button><button class="mini" data-copy="${esc(s.system)}">Copy system</button><a href="${inaraSt(s.station)}" target="_blank" rel="noopener noreferrer">Check station</a></div></article>`).join('');
      el.querySelector('[data-rares-note]').textContent=`${L.note||''} Cargo presence marks a stop automatically. Manual marks apply to this commander, loop and unchanged cargo snapshot. Selecting or copying a destination does not plot a route.`;
    },
    unmount(el){el._rares.dead=true;}
  });
  Lab.map.addLayer('loop',{label:'rares buy stops',color:'#9be36b',z:2,
    points:S=>rows(S).filter(s=>s.coords&&['x','y','z'].every(k=>Number.isFinite(s.coords[k]))).map(s=>({name:s.system,...s.coords,r:4,label:true,selected:S.loop?.ui_selected&&id(s)===id(S.loop.ui_selected),color:s.done?'#5c8a46':'#9be36b',sub:`${s.station} | ${s.rares.map(r=>r.name).join(', ')}`,onClick:()=>select(s)}))
  });
})();
