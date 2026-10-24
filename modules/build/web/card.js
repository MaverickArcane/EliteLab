/* build card: pin an EDSY link, show progress toward it, push the engineering needs to the wishlist. */
(() => {
  const { esc, fmt } = Lab.util;
  const bad = e => Lab.toast(e.message || String(e), 'bad');
  const bar = (label, pct, text) => `<div style="margin-top:6px"><div class="k">${esc(label)} <span class="muted">${esc(text)}</span></div><div class="bar"><i style="width:${Math.max(0, Math.min(100, pct))}%"></i></div></div>`;
  const ui = { slots: 'todo', mats: 'short' };          // view state, kept across renders
  const short = r => {                                   // one short phrase per slot instead of the full to-do list
    if (r.status === 'ok') return 'done';
    const parts = [];
    if (r.status === 'buy') parts.push(r.credits ? `buy, ${fmt(Math.round(r.credits / 1e6 * 10) / 10)} M Cr` : 'buy');
    if (r.blueprint && r.todo.some(t => t.includes(r.blueprint))) { const cur = (r.current && r.current.blueprint && r.current.level) ? `G${r.current.level}` : 'G0'; parts.push(`${cur} to G${r.grade}`); }
    if (r.experimental && r.todo.some(t => t.startsWith('apply'))) parts.push(r.experimental);
    return parts.join(', ');
  };
  Lab.card({
    id: 'build', requires: ['build', 'journal'],
    header(h) {
      h.innerHTML = `<button class="mini" id="bd-wish" title="track this build's materials on the engineering wishlist as one entry">track in wishlist</button> <button class="mini" id="bd-unpin">unpin</button>`;
      h.querySelector('#bd-wish').onclick = async () => { try { const r = await Lab.post('/api/build/wishlist', {}); Lab.toast(`Wishlist now tracks ${r.entry.name} (${r.needs} materials)`); } catch (e) { bad(e); } };
      h.querySelector('#bd-unpin').onclick = () => Lab.post('/api/build/unpin', {}).catch(bad);
    },
    mount(el) {
      el.innerHTML = `<div class="row"><input id="bd-url" placeholder="paste an EDSY or Coriolis link, or SLEF JSON" size="44"><button class="mini primary" id="bd-pin">pin</button></div>
        <div class="bd-body"></div>
        <div class="note">Hardpoints and internals are matched by module within their group, so slot order does not matter. Rolls count from the grade the module already has.</div>`;
      const pin = async () => { const url = el.querySelector('#bd-url').value.trim(); if (!url) return; try { await Lab.post('/api/build/pin', { url }); el.querySelector('#bd-url').value = ''; Lab.toast('Build pinned'); } catch (e) { bad(e); } };
      el.querySelector('#bd-pin').onclick = pin;
      el.querySelector('#bd-url').onkeydown = e => { if (e.key === 'Enter') pin(); };
      el.onclick = e => { const t = e.target.closest('[data-view]'); if (t) { e.preventDefault(); ui[t.dataset.view] = t.dataset.value; Lab.emit('build'); } };
    },
    render(el, S) {
      const B = S.build || {}, P = B.progress, pin = B.pinned, body = el.querySelector('.bd-body');
      if (!pin || !P) { body.innerHTML = `<div class="muted" style="margin-top:8px">No build pinned. Paste an EDSY link above, or ask your AI to call pin_build.</div>`; return; }
      const T = P.totals, pc = P.percent;
      const tag = s => s === 'ok' ? '<span class="tag ok">ok</span>' : s === 'buy' ? '<span class="tag bad">buy</span>' : '<span class="tag warn">eng</span>';
      const sw = (view, value, label) => ui[view] === value ? `<b>${label}</b>` : `<a href="#" data-view="${view}" data-value="${value}">${label}</a>`;
      const slots = ui.slots === 'all' ? P.slots : P.slots.filter(r => r.status !== 'ok');
      const mats = ui.mats === 'all' ? P.materials : P.materials.filter(r => r.short);
      const link = pin.source === 'slef' ? '' : ` - <a href="${esc(pin.url)}" target="_blank">${pin.source === 'coriolis' ? 'Coriolis' : 'EDSY'}</a>`;
      body.innerHTML = `<div style="margin-top:8px"><span class="big">${esc(pin.name)}</span> <span class="muted">${esc(pin.ship)}${link}</span>
          ${P.same_ship ? '' : `<div class="bad">Flying ${esc(P.current_ship || 'an unknown ship')}; this build is a ${esc(P.target_ship)}. Comparing with the current loadout anyway.</div>`}</div>
        ${bar('Overall', pc.overall, `${T.ok} of ${T.slots} slots done`)}
        ${bar('Fitted', pc.fitted, `${T.fitted} of ${T.slots} modules aboard${T.credits ? `, ${fmt(T.credits)} Cr to buy` : ''}`)}
        ${bar('Engineered', pc.engineered, `${T.engineering_done} of ${T.engineering_total} engineered slots complete`)}
        ${bar('Materials', pc.materials, P.materials.length ? `${P.materials_short} of ${P.materials.length} materials short` : 'nothing needed')}
        <div style="margin-top:8px"><b>Slots</b> <span class="muted">${T.to_buy} to buy, ${T.to_engineer} to engineer - ${sw('slots', 'todo', 'to do')} / ${sw('slots', 'all', 'all')}</span></div>
        <table><tbody>${slots.map(r => `<tr title="${esc(r.todo.join('; '))}"><td class="muted" style="white-space:nowrap">${esc(r.slot)}</td><td style="white-space:nowrap">${esc(r.target)}${r.blueprint ? ` <span class="muted">${esc(r.blueprint)} G${r.grade}${r.experimental ? ' + ' + esc(r.experimental) : ''}</span>` : ''}</td><td>${tag(r.status)}</td><td class="muted" style="white-space:nowrap">${esc(short(r))}</td></tr>`).join('') || `<tr><td class="muted">everything fitted and engineered</td></tr>`}</tbody></table>
        ${P.materials.length ? `<div style="margin-top:8px"><b>Materials</b> <span class="muted">for the engineering above - ${sw('mats', 'short', 'short')} / ${sw('mats', 'all', 'all')}</span></div><table><thead><tr><th>Material</th><th>G</th><th class="num">Have</th><th class="num">Need</th><th class="num">Short</th></tr></thead><tbody>` +
          (mats.map(r => `<tr><td>${esc(r.name)}</td><td>${r.grade ?? ''}</td><td class="num">${fmt(r.have)}</td><td class="num">${fmt(r.need)}</td><td class="num ${r.short ? 'bad' : 'ok'}">${r.short ? fmt(r.short) : 'ok'}</td></tr>`).join('') || `<tr><td class="muted" colspan="5">every material in stock</td></tr>`) + `</tbody></table>` : ''}
        ${P.not_in_build.length ? `<div class="muted" style="margin-top:6px">Aboard but not in the build: ${P.not_in_build.map(m => esc(m.item)).join(', ')}</div>` : ''}`;
    },
  });
})();
