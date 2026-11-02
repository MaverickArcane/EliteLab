/* journal cards: location, ship, feed, cargo, market rares. */
(() => {
  const { esc, fmt, inaraSys, spanshSys } = Lab.util;

  Lab.card({
    id: 'location', requires: ['journal'],
    render(el, S) {
      const j = S.journal || {}, st = j.status || {};
      el.innerHTML = `
        <div class="big">${esc(j.system || '—')} <span class="right" style="font-size:12px;font-weight:400">${j.system ? `<button class="mini" data-copy="${esc(j.system)}">copy</button> <a href="${inaraSys(j.system)}" target="_blank">Inara</a> <a href="${spanshSys(j.system)}" target="_blank">Spansh</a>` : ''}</span></div>
        <div class="muted">${j.docked ? `Docked at ${esc(j.station)} (${esc(j.station_type || '')})` : (st.supercruise ? 'In supercruise' : 'In normal space')}</div>
        <div class="grid2">
          <div><div class="k">Controlling power</div><div class="v">${esc(j.system_power || 'none')}</div></div>
          <div><div class="k">System state</div><div class="v">${esc(j.system_power_state || 'Unoccupied')}</div></div>
          <div><div class="k">Fuel</div><div class="v">${st.fuel != null ? st.fuel.toFixed(1) + ' t' : '—'}</div></div>
          <div><div class="k">Legal</div><div class="v ${st.legal && st.legal !== 'Clean' ? 'bad' : 'ok'}">${esc(st.legal || '—')}</div></div>
        </div>
        <div class="note">${(j.system_powers || []).length ? 'Powers present: ' + esc(j.system_powers.join(', ')) : ''}</div>`;
    },
  });

  Lab.card({
    id: 'ship', requires: ['journal'],
    render(el, S) {
      const j = S.journal || {}, s = j.ship_info, st = j.status || {};
      if (!s) { el.innerHTML = '<div class="muted">No loadout seen yet. Appears after you load into the game or change ship.</div>'; return; }
      const fuelPct = s.fuel_main && st.fuel != null ? Math.round(100 * st.fuel / s.fuel_main) : null;
      const hullPct = s.hull_health != null ? Math.round(s.hull_health * 100) : null;
      const mods = s.modules || [];
      const CORE_SHORT = { PowerPlant: 'PP', MainEngines: 'THR', FrameShiftDrive: 'FSD', LifeSupport: 'LS', PowerDistributor: 'PD', Radar: 'SNS', FuelTank: 'FT', Armour: 'HULL' };
      const CORE_ORDER = Object.keys(CORE_SHORT);
      const engText = e => e ? `${esc(e.blueprint_name || e.blueprint)} G${e.level}${e.experimental ? ' + ' + esc(e.experimental_name || e.experimental) : ''}` : '';
      const chip = (m, label) => `<span class="chip${m.engineering ? ' eng' : ''}${m.on === false ? ' off' : ''}" title="${esc(m.slot)}${m.engineering && m.engineering.engineer ? ' - ' + esc(m.engineering.engineer) : ''}${m.on === false ? ' - powered off' : ''}">
          ${label ? `<span class="lbl">${esc(label)}</span>` : ''}<b>${m.class != null ? m.class : ''}${esc(m.rating || '')}</b> ${esc(m.name)}${m.mount ? ` <span class="muted">${{ F: 'fixed', G: 'gimballed', T: 'turreted' }[m.mount] || m.mount}</span>` : ''}
          ${m.engineering ? `<span class="sub">${engText(m.engineering)}</span>` : ''}</span>`;
      // every component slot the server classified, in cockpit order; unknown core slots still show, after the known ones
      const core = mods.filter(m => m.group === 'component').sort((a, b) => (CORE_ORDER.indexOf(a.slot) + 99) % 99 - (CORE_ORDER.indexOf(b.slot) + 99) % 99);
      const hard = mods.filter(m => m.group === 'hardpoint'), util = mods.filter(m => m.group === 'utility'), inner = mods.filter(m => m.group === 'internal' || m.group === 'military');
      const engineered = mods.filter(m => m.engineering).length;
      const bar = Lab.util.bar;
      el.innerHTML = `
        <div class="ship-head"><div><div class="big">${esc(s.type || '-')}</div><div class="muted">${[s.name, s.ident].filter(Boolean).map(esc).join(' - ') || 'unnamed'}${s.hot ? ' <span class="tag bad">HOT</span>' : ''}${j.docked ? ` <span class="tag">docked</span>` : st.supercruise ? ' <span class="tag">supercruise</span>' : ''}</div></div>
          <div class="ship-range"><div class="k">Jump range</div><div class="v">${j.jump_range_now != null ? j.jump_range_now.toFixed(1) : '-'} <span class="muted">Ly now</span></div><div class="muted">${j.jump_range_laden != null ? j.jump_range_laden.toFixed(1) + ' laden' : ''}${s.max_jump_range != null ? ` / ${s.max_jump_range.toFixed(1)} max` : ''}</div></div></div>
        ${fuelPct != null ? bar('Fuel', fuelPct, `${st.fuel.toFixed(1)} of ${fmt(s.fuel_main)} t (${fuelPct}%)`, fuelPct < 25 ? 'var(--bad)' : 'var(--accent-2)') : ''}
        ${hullPct != null ? bar('Hull', hullPct, `${hullPct}%`, hullPct < 50 ? 'var(--bad)' : hullPct < 80 ? 'var(--warn)' : 'var(--ok)') : ''}
        <div class="grid3">
          <div><div class="k">Cargo</div><div class="v">${fmt((j.cargo || {}).count)} / ${fmt(s.cargo_capacity)} t</div></div>
          <div><div class="k">Unladen mass</div><div class="v">${s.unladen_mass != null ? fmt(Math.round(s.unladen_mass)) + ' t' : '-'}</div></div>
          <div><div class="k">Rebuy</div><div class="v">${fmt(s.rebuy)} Cr</div></div>
          <div><div class="k">Value</div><div class="v">${fmt((s.hull_value || 0) + (s.modules_value || 0))} Cr</div></div>
          <div><div class="k">Modules</div><div class="v">${mods.length} <span class="muted">${engineered} engineered</span></div></div>
          <div><div class="k">Hardpoints</div><div class="v">${hard.length} <span class="muted">+ ${util.length} utility</span></div></div>
        </div>
        ${core.length ? `<div class="k ship-sec">Core</div><div class="chips">${core.map(m => chip(m, CORE_SHORT[m.slot] || m.slot)).join('')}</div>` : ''}
        ${hard.length ? `<div class="k ship-sec">Hardpoints</div><div class="chips">${hard.map(m => chip(m)).join('')}</div>` : ''}
        ${util.length ? `<div class="k ship-sec">Utility</div><div class="chips">${util.map(m => chip(m)).join('')}</div>` : ''}
        ${inner.length ? `<div class="k ship-sec">Internals</div><div class="chips">${inner.map(m => chip(m)).join('')}</div>` : ''}
        ${!mods.length ? `<div class="note">${s.module_count} modules; details appear after the next Loadout event (relog or change ship).</div>` : ''}`;
    },
  });

  Lab.card({
    id: 'feed', requires: ['journal'],
    render(el, S) {
      const f = (S.journal || {}).feed || [];
      el.innerHTML = `<div class="feed">${f.length ? f.map(x => `<div class="ev-${esc(x.event)}"><time>${(x.ts || '').slice(11, 16)}</time><span>${esc(x.text)}</span></div>`).join('') : '<div class="muted">No events yet this session.</div>'}</div>`;
    },
  });

  Lab.card({
    id: 'cargo', requires: ['journal','loop'],
    render(el,S) {
      const j=S.journal||{}, c=j.cargo||{}, items=Array.isArray(c.items)?c.items.slice(0,256):[], w=S.loop?.workflow||{
        cargo_known:Number.isInteger(c.count)&&c.count>=0&&Array.isArray(c.items)&&c.items.every(i=>i&&Number.isInteger(i.count)&&i.count>=0)&&c.items.reduce((n,i)=>n+i.count,0)===c.count,
        free_capacity:null
      };
      el.innerHTML=`<div class="big">${w.cargo_known?fmt(c.count)+' t aboard':'Cargo unknown'}</div><p class="note">Capacity: ${j.cargo_capacity==null?'unknown':fmt(j.cargo_capacity)+' t'} | Free: ${w.free_capacity==null?'unknown':fmt(w.free_capacity)+' t'}</p>
        <table><thead><tr><th>Commodity</th><th class="num">Tons</th></tr></thead><tbody>${(w.cargo_known?items:[]).filter(i=>i&&typeof i==='object').map(i=>`<tr><td>${esc(i.name||i.key||'Unknown commodity')} ${i.rare?'<span class="tag rare">rare</span>':''} ${i.stolen?'<span class="tag bad">stolen</span>':''}</td><td class="num">${Number.isFinite(i.count)?fmt(i.count):'Unknown'}</td></tr>`).join('')||`<tr><td colspan="2">${w.cargo_known?'Empty hold':'Waiting for a cargo snapshot from the game.'}</td></tr>`}</tbody></table>
        <p class="note">Cargo aboard is separate from purchase history. Powerplay rewards require eligible origin and local activity; carrier transfers can remove mining provenance.</p>`;
    }
  });
  Lab.card({
    id:'market', requires:['journal','loop'],
    render(el,S) {
      const local=S.journal?.market||{}, m=S.loop?.workflow?.market||{
        ...local,status:local.station?'undated':'not_recorded',message:'Arrival evidence unavailable. Open the market in game and verify stock before buying.',
        rares:(Array.isArray(local.rares_in_stock)?local.rares_in_stock:[]).slice(0,256).filter(r=>r&&typeof r==='object').map(r=>({
          name:r.name,buy:Number.isFinite(r.buy)&&r.buy>=0?r.buy:null,stock:Number.isFinite(r.stock)&&r.stock>=0?r.stock:null
        }))
      }, current=m.status==='current_snapshot', rows=m.rares||[];
      el.innerHTML=`<b>${current?'Rare stock snapshot at this station':m.status==='not_recorded'?'No market recorded':'Previous or unverified market snapshot'}</b>
        <p class="note" data-market-evidence>${esc(m.message||'Waiting for local market evidence.')}</p>
        <p>${esc(m.station||'Unknown station')}${m.system?', '+esc(m.system):''}</p><p class="note">Recorded: ${esc(m.timestamp||'unknown')}. These are buy prices and reported stock, not sell quotes.</p>
        <table><thead><tr><th>Rare</th><th class="num">Buy / t</th><th class="num">Stock</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.name)}</td><td class="num">${r.buy==null?'Unknown':fmt(r.buy)+' Cr'}</td><td class="num">${r.stock==null?'Unknown':fmt(r.stock)+' t'}</td></tr>`).join('')||`<tr><td colspan="3">${current?'No rares with positive stock in this snapshot.':'No usable rare-stock entries. Open the market in game to refresh.'}</td></tr>`}</tbody></table>`;
    }
  });
})();
