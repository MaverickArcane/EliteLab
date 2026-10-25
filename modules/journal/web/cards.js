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
    id: 'cargo', requires: ['journal'],
    render(el, S) {
      const j = S.journal || {}, c = j.cargo || { items: [] }, cap = j.cargo_capacity;
      el.innerHTML = `
        <div class="muted" style="font-size:12px">${fmt(c.count)} / ${fmt(cap)} t</div>
        <div class="bar"><i style="width:${cap ? Math.min(100, 100 * (c.count || 0) / cap) : 0}%"></i></div>
        <table style="margin-top:8px"><tbody>${c.items.length ? c.items.map(i => `<tr><td>${esc(i.name)} ${i.rare ? '<span class="tag rare">rare</span>' : ''} ${i.stolen ? '<span class="tag bad">stolen</span>' : ''}</td><td class="num">${fmt(i.count)}</td></tr>`).join('') : '<tr><td class="muted">Empty hold</td></tr>'}</tbody></table>
        <div class="note">Anything that rode on a fleet carrier loses its Powerplay merit eligibility.</div>`;
    },
  });

  Lab.card({
    id: 'market', requires: ['journal'],
    render(el, S) {
      const m = (S.journal || {}).market || {};
      el.innerHTML = `<div class="muted" style="font-size:12px">${m.station ? `${esc(m.station)}, ${esc(m.system)}` : 'Open a commodities market in game to populate.'}</div>
        <table><thead><tr><th>Rare</th><th class="num">Buy</th><th class="num">Stock</th></tr></thead><tbody>${(m.rares_in_stock || []).length ? m.rares_in_stock.map(r => `<tr><td>${esc(r.name)}</td><td class="num">${fmt(r.buy)}</td><td class="num">${fmt(r.stock)}</td></tr>`).join('') : `<tr><td class="muted" colspan="3">No rares in stock here.</td></tr>`}</tbody></table>`;
    },
  });

})();
