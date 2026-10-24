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
      const niceItem = i => (i || '').replace(/^(int_|hpt_)/, '').replace(/_/g, ' ').replace(/size(\d)/, 'S$1').replace(/class(\d)/, 'C$1');
      el.innerHTML = `
        <div class="big">${esc(s.type || '—')} <span class="muted" style="font-size:13px">${[s.name, s.ident].filter(Boolean).map(esc).join(' · ')}</span></div>
        <div class="grid2">
          <div><div class="k">Jump range <span class="muted">now / laden / max</span></div><div class="v">${j.jump_range_now != null ? j.jump_range_now.toFixed(1) : '-'} / ${j.jump_range_laden != null ? j.jump_range_laden.toFixed(1) : '-'} / ${s.max_jump_range != null ? s.max_jump_range.toFixed(1) + ' Ly' : '-'}</div></div>
          <div><div class="k">Cargo</div><div class="v">${fmt((j.cargo || {}).count)} / ${fmt(s.cargo_capacity)} t</div></div>
          <div><div class="k">Fuel</div><div class="v">${st.fuel != null ? st.fuel.toFixed(1) : '—'} / ${fmt(s.fuel_main)} t${fuelPct != null ? ` <span class="muted">(${fuelPct}%)</span>` : ''}</div></div>
          <div><div class="k">Hull</div><div class="v ${s.hull_health != null && s.hull_health < 0.5 ? 'bad' : ''}">${s.hull_health != null ? Math.round(s.hull_health * 100) + '%' : '—'}</div></div>
          <div><div class="k">Rebuy</div><div class="v">${fmt(s.rebuy)} Cr</div></div>
          <div><div class="k">Value</div><div class="v">${fmt((s.hull_value || 0) + (s.modules_value || 0))} Cr</div></div>
        </div>
        ${fuelPct != null ? `<div class="bar"><i style="width:${fuelPct}%;background:${fuelPct < 25 ? 'var(--bad)' : 'var(--accent-2)'}"></i></div>` : ''}
        <div class="note">${(s.core || []).filter(c => c.engineering).length ? 'Engineered core: ' + s.core.filter(c => c.engineering).map(c => `${esc(c.slot)} ${esc(c.engineering)} G${c.level}`).join(', ') : `${s.module_count} modules · ${(s.hardpoints || []).length} hardpoints`}${s.hot ? ' · <span class="bad">HOT</span>' : ''}</div>`;
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
