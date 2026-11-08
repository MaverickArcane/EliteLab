/* Local archive evidence; stable filters and bounded results. */
(() => {
  const {esc, fmt, ls} = Lab.util;
  const pref='elitelab.history.filters.v1', money=n=>n==null?'--':fmt(Math.round(n))+' Cr';
  function plot(rows) {
    if(!rows.length)return '<div class="note">No recorded credit snapshots in this range.</div>';
    const values=rows.map(r=>r.credits), low=Math.min(...values), high=Math.max(...values), times=rows.map(r=>Date.parse(r.timestamp)), first=Math.min(...times), last=Math.max(...times);
    const pts=rows.map((r,i)=>[25+(times[i]-first)/Math.max(1,last-first)*950,150-(r.credits-low)/Math.max(1,high-low)*115]);
    return `<svg class="history-chart" viewBox="0 0 1000 180" role="img" aria-label="Recorded credit balance snapshots; line connects observations only"><path d="M25 150 H975" stroke="currentColor" opacity=".2"/><polyline points="${pts.map(p=>p.join(',')).join(' ')}" fill="none" stroke="var(--accent-2)" stroke-width="2"/>${pts.map((p,i)=>`<circle cx="${p[0]}" cy="${p[1]}" r="3" fill="var(--accent)"><title>${esc(rows[i].timestamp)}: ${money(rows[i].credits)}</title></circle>`).join('')}<text x="25" y="18" fill="currentColor">${money(high)}</text><text x="25" y="174" fill="currentColor">${esc(rows[0].timestamp.slice(0,10))}</text><text x="975" y="174" text-anchor="end" fill="currentColor">${esc(rows.at(-1).timestamp.slice(0,10))}</text></svg>`;
  }
  Lab.card({id:'credits',requires:['history','journal'],
    mount(el){el._credits={token:null,generation:0,dead:false,timer:null};el.innerHTML='<p class="note">Loading recorded credit balances...</p>';},
    render(el,S){
      const u=el._credits,token=JSON.stringify([S.history?.version,S.journal?.cmdr]);
      if(u.token===token)return;u.token=token;const generation=++u.generation;
      clearTimeout(u.timer);el.innerHTML='<p class="note">Reading credit history...</p>';
      const load=async()=>{try{const d=await Lab.api('/api/history/analytics',{days:30,commander:'auto'});if(u.dead||u.generation!==generation)return;
        el.innerHTML=d.selection_required?'<p>Select a commander in History to inspect their credit records.</p>':`<div class="row"><b>${money(d.credits.at(-1)?.credits)}</b><span class="muted">Latest recorded balance</span><button class="mini" data-credit-history>Open History</button></div>${plot(d.credits)}<p class="note">Last 30 days of recorded balances. Gaps are unknown; this is not a profit ledger.</p>`;
        el.querySelector('[data-credit-history]')?.addEventListener('click',()=>Lab.focusCard('history'));
        if(d.index.pending_files)u.timer=setTimeout(load,1000);
      }catch(error){if(!u.dead&&u.generation===generation)el.textContent=error.message;}};
      u.timer=setTimeout(load,150);
    },
    unmount(el){el._credits.dead=true;++el._credits.generation;clearTimeout(el._credits.timer);}
  });
  function draw(el,d) {
    const st=d.index||{}, total=d.totals||{}, select=el.querySelector('[name=commander]'), selected=select.value;
    select.innerHTML='<option value="auto">Current / only commander</option>'+d.commanders.map(c=>`<option value="${esc(c.key)}">${esc(c.name)} (${esc(c.key)})</option>`).join('');
    if([...select.options].some(o=>o.value===selected))select.value=selected;
    el.querySelector('[data-history-status]').textContent=`${fmt(st.files)} files; ${fmt(st.records)} indexed records. ${st.pending_files?fmt(st.pending_files)+' files still indexing. ':'Index caught up. '}${st.waiting_files?fmt(st.waiting_files)+' incomplete final lines. ':''}${st.skipped_lines?fmt(st.skipped_lines)+' malformed or oversized lines skipped. ':''}${st.unreadable_files?fmt(st.unreadable_files)+' unreadable files. ':''}${st.excluded_files?fmt(st.excluded_files)+' files exceed archive limit. ':''}${st.unidentified_records?fmt(st.unidentified_records)+' records without commander identity. ':''}`;
    const out=el.querySelector('[data-history-results]');
    Lab.set('history',{selected_commander:d.commander||'auto'});
    if(d.selection_required){out.innerHTML='<div class="note">Multiple commanders are present. Select one to view their history.</div>';return;}
    const latest=d.credits.at(-1);
    out.innerHTML=`<div class="history-metrics"><div><div class="k">Latest recorded balance</div><strong>${money(latest?.credits)}</strong><small>${esc(latest?.timestamp||'No snapshot in range')}</small></div><div><div class="k">Observed merit gains</div><strong data-history-merits>${fmt(total.merits?.amount||0)}</strong><small>${fmt(total.merits?.events||0)} journal events in range</small></div><div><div class="k">Materials collected</div><strong>${fmt(total.material?.amount||0)}</strong><small>Recorded units; not current inventory</small></div></div>
      <section class="history-section"><b>Credit balance snapshots</b>${plot(d.credits)}<div class="note">Latest login snapshot per UTC day, up to 400 days. Gaps are not a reconstructed balance or profit ledger.</div><details><summary>Snapshot values</summary><div class="history-scroll"><table><thead><tr><th>Recorded UTC</th><th class="num">Credits</th></tr></thead><tbody>${[...d.credits].reverse().map(r=>`<tr><td>${esc(r.timestamp)}</td><td class="num">${money(r.credits)}</td></tr>`).join('')}</tbody></table></div></details></section>
      <div class="history-columns"><section class="history-section"><b>Merits by cycle</b><div class="note">Thursday 07:00 UTC boundaries. Date filters may cover only part of a cycle. Up to 200 cycle/power groups.</div><div class="history-scroll">${d.merit_cycles.length?`<table><thead><tr><th>Cycle start UTC</th><th>Power</th><th class="num">Gained</th></tr></thead><tbody>${d.merit_cycles.map(r=>`<tr><td>${esc(r.cycle_start.slice(0,16).replace('T',' '))}</td><td>${esc(r.power||'Unknown')}</td><td class="num">${fmt(r.merits)}</td></tr>`).join('')}</tbody></table>`:'<div class="note">No merit gains recorded in this range.</div>'}</div></section>
      <section class="history-section"><b>Material collection locations</b><div class="note">Top 100 matching locations. Collection events only; missing locations stay unknown.</div><div class="history-scroll">${d.materials.length?`<table><thead><tr><th>Material / location</th><th class="num">Collected</th></tr></thead><tbody>${d.materials.map(r=>`<tr><td><b>${esc(r.label)}</b><div>${esc(r.system||'Unknown system')}${r.body?' / '+esc(r.body):''}</div><small>${esc(r.category)} | ${esc(r.last_seen.slice(0,10))}</small>${r.system?`<button class="mini" data-copy="${esc(r.system)}">Copy system</button>`:''}</td><td class="num">${fmt(r.collected)}</td></tr>`).join('')}</tbody></table>`:'<div class="note">No matching material collections in this range.</div>'}</div></section></div><details><summary>Coverage and accounting limits</summary><div class="note">${esc(d.note)} ${esc(st.note)}</div></details>`;
  }
  Lab.card({id:'history',requires:['history','journal'],
    mount(el){
      el.classList.add('history-card');const u=el._history={generation:0,dead:false,version:null,timer:null,dirty:false};
      el.innerHTML=`<form class="history-filters"><label>Commander<select name="commander"><option value="auto">Current / only commander</option></select></label><label>Time range<select name="days"><option value="30">Last 30 days</option><option value="7">Last 7 days</option><option value="90">Last 90 days</option><option value="365">Last year</option><option value="0">All available history</option></select></label><label>Material filter<input name="material" maxlength="160" placeholder="Any material"></label><button class="primary" type="submit">Refresh history</button><button type="button" data-history-rebuild>Rebuild cache</button></form><div class="note" role="status" data-history-status>Loading journal history...</div><div data-history-results></div>`;
      const form=el.querySelector('form'),saved=ls.get(pref,{});
      if(typeof saved.commander==='string'&&saved.commander.length<=165&&saved.commander!=='auto'){const o=document.createElement('option');o.value=saved.commander;o.textContent='Saved commander';form.elements.commander.appendChild(o);form.elements.commander.value=saved.commander;}
      if(['0','7','30','90','365'].includes(saved.days))form.elements.days.value=saved.days;
      if(typeof saved.material==='string')form.elements.material.value=saved.material.slice(0,160);
      u.load=async rebuild=>{
        clearTimeout(u.timer);const generation=++u.generation;
        el.querySelector('[data-history-status]').textContent=rebuild?'Rebuilding derived cache...':'Reading journal history...';el.querySelector('[data-history-results]').innerHTML='';
        const q=Object.fromEntries(new FormData(form));ls.set(pref,q);
        try{if(rebuild)await Lab.post('/api/history/rebuild',{});if(u.dead||generation!==u.generation)return;const d=await Lab.api('/api/history/analytics',q);if(u.dead||generation!==u.generation)return;draw(el,d);if(d.index.pending_files)u.timer=setTimeout(()=>u.load(false),500);}
        catch(error){if(!u.dead&&generation===u.generation)el.querySelector('[data-history-status]').textContent=error.message+' Adjust filters or retry Refresh history.';}
      };
      form.onsubmit=e=>{e.preventDefault();u.dirty=false;u.load(false);};
      form.oninput=()=>{u.dirty=true;++u.generation;clearTimeout(u.timer);el.querySelector('[data-history-results]').innerHTML='';el.querySelector('[data-history-status]').textContent='Filters changed. Refresh history to apply.';};
      el.querySelector('[data-history-rebuild]').onclick=()=>{u.dirty=false;u.load(true);};
    },
    render(el,S){const u=el._history;if(u.version!==S.history?.version){u.version=S.history?.version;if(u.dirty)return;clearTimeout(u.timer);u.timer=setTimeout(()=>u.load(false),300);}},
    unmount(el){el._history.dead=true;++el._history.generation;clearTimeout(el._history.timer);},
  });
})();
