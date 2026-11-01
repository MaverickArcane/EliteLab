/* wishlist card: what you are collecting. Structured picker (kind, module, blueprint/effect/unlock/material, grade range, qty),
   entries vs live inventory, trade plan, nearest traders. A pinned build is tracked as one entry. */
(() => {
  const { esc, fmt, inaraSys } = Lab.util;
  const bad = e => Lab.toast(e.message || String(e), 'bad');
  const opt = (v, label, sel) => `<option value="${esc(v)}"${sel ? ' selected' : ''}>${esc(label)}</option>`;
  const ui = { needs: 'short', trades: 'few', preselected: 0 };
  const LIMIT = 12;
  Lab.card({
    id: 'wishlist', requires: ['wishlist', 'wishlist_ui', 'build'],
    header(h) {
      h.innerHTML = `<button class="mini" id="wl-clear">clear</button>`;
      h.querySelector('#wl-clear').onclick = () => Lab.post('/api/wishlist/remove', { all: true }).catch(bad);
    },
    mount(el) {
      el.innerHTML = `<div class="row">
          <select id="wl-kind">${opt('blueprint', 'Blueprint')}${opt('experimental', 'Experimental effect')}${opt('unlock', 'Tech broker unlock')}${opt('material', 'Material')}${opt('build', 'Pinned build')}</select>
          <select id="wl-module"></select><select id="wl-recipe"></select>
          <span id="wl-grades">from <select id="wl-from"></select> to <select id="wl-to"></select></span>
          <select id="wl-qty" title="how many">${[1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30, 50, 100].map(n => opt(n, n + ' x')).join('')}</select>
          <button class="mini primary" id="wl-add">add</button> <button class="mini" id="wl-traders">nearest traders</button></div>
        <div class="wl-entries"></div><div class="wl-needs"></div><div class="wl-trades"></div><div class="wl-traders"></div>
        <div class="note">"from" is the grade the module already has, "to" the target: from G2 to G5 buys the rolls for G3, G4 and G5 (1/2/3/4/5 rolls per grade is a planning hint). "Pinned build" tracks the build card's materials as one entry.</div>`;
      const $ = s => el.querySelector(s);
      const kind = $('#wl-kind'), mod = $('#wl-module'), rec = $('#wl-recipe'), from = $('#wl-from'), to = $('#wl-to'), grades = $('#wl-grades'), qty = $('#wl-qty');
      let O = null;
      const fillModules = () => {
        const k = kind.value;
        if (!O) return;
        let list = [];
        if (k === 'blueprint') list = O.modules.filter(m => m.blueprints.length).map(m => [m.module, m.module]);
        else if (k === 'experimental') list = O.modules.filter(m => m.experimentals.length).map(m => [m.module, m.module]);
        else if (k === 'unlock') list = [...new Set(O.unlocks.map(u => u.module))].map(m => [m, m]);
        else if (k === 'material') list = Object.keys(O.materials).map(c => [c, c]);
        mod.innerHTML = list.map(([v, l]) => opt(v, l)).join('');
        mod.style.display = rec.style.display = k === 'build' ? 'none' : '';
        qty.style.display = k === 'build' ? 'none' : '';
        fillRecipes();
      };
      const fillRecipes = () => {
        const k = kind.value, m = mod.value;
        let list = [];
        if (k === 'blueprint') list = (O.modules.find(x => x.module === m) || { blueprints: [] }).blueprints.map(b => [b.key, `${b.name} (G1-${b.max_grade})`]);
        else if (k === 'experimental') list = (O.modules.find(x => x.module === m) || { experimentals: [] }).experimentals.map(e => [e.key, e.name]);
        else if (k === 'unlock') list = O.unlocks.filter(u => u.module === m).map(u => [u.key, u.name]);
        else if (k === 'material') list = (O.materials[m] || []).map(x => [x.key, `${x.name} (G${x.grade})`]);
        rec.innerHTML = list.map(([v, l]) => opt(v, l)).join('');
        grades.style.display = k === 'blueprint' ? '' : 'none';
        fillGrades();
      };
      const fillGrades = () => {
        if (kind.value !== 'blueprint') return;
        const b = (O.modules.find(x => x.module === mod.value) || { blueprints: [] }).blueprints.find(x => x.key === rec.value);
        const max = b ? b.max_grade : 5;
        from.innerHTML = [...Array(max).keys()].map(g => opt(g, g === 0 ? 'unengineered' : 'G' + g)).join('');
        to.innerHTML = [...Array(max).keys()].map(g => opt(g + 1, 'G' + (g + 1), g + 1 === max)).join('');
      };
      kind.onchange = fillModules; mod.onchange = fillRecipes; rec.onchange = fillGrades;
      from.onchange = () => { if (+from.value >= +to.value) to.value = Math.min(+from.value + 1, to.options.length); };
      el._preselect = p => {              // from the recipes card
        if (!O || !p) return;
        kind.value = p.kind; fillModules();
        if (p.kind !== 'build') { mod.value = p.module; fillRecipes(); rec.value = p.key; fillGrades(); }
        $('#wl-add').focus();
        const row = $('#wl-add').closest('.row'); row.style.outline = '2px solid var(--accent)'; row.style.outlineOffset = '4px';
        setTimeout(() => { row.style.outline = ''; row.style.outlineOffset = ''; }, 2500);
      };
      Lab.api('/api/wishlist/options').then(o => { O = o; fillModules(); const p = Lab.get('wishlist_ui', 'preselect'); if (p && p.at !== ui.preselected) { ui.preselected = p.at; el._preselect(p); } }).catch(bad);
      $('#wl-add').onclick = async () => {
        const body = { item: kind.value === 'build' ? 'build' : rec.value, kind: kind.value, qty: +qty.value || 1 };
        if (!body.item) return;
        if (kind.value === 'experimental' || kind.value === 'blueprint') body.module = mod.value;
        if (kind.value === 'blueprint') { body.from_grade = +from.value; body.grade = +to.value; }
        try {
          const r = await Lab.post('/api/wishlist/add', body);
          Lab.toast(`Added ${r.entry.kind === 'build' ? 'build ' : r.entry.qty + ' x '}${r.entry.module && r.entry.kind !== 'build' ? r.entry.module + ' ' : ''}${r.entry.name}${r.entry.grade ? ` G${r.entry.from_grade || 0} to G${r.entry.grade}` : ''}`);
        } catch (e) { bad(e); }
      };
      $('#wl-traders').onclick = async () => {
        Lab.set('wishlist_ui', { traders: 'loading' });
        try { Lab.set('wishlist_ui', { traders: await Lab.api('/api/wishlist/traders') }); } catch (e) { Lab.set('wishlist_ui', { traders: null }); bad(e); }
      };
      el.onclick = e => {
        const b = e.target.closest('[data-rm]'); if (b) { Lab.post('/api/wishlist/remove', { id: b.dataset.rm }).catch(bad); return; }
        const v = e.target.closest('[data-view]'); if (v) { e.preventDefault(); ui[v.dataset.view] = v.dataset.value; Lab.emit('wishlist'); }
      };
    },
    render(el, S) {
      const W = S.wishlist || {}, U = S.wishlist_ui || {};
      if (U.preselect && U.preselect.at !== ui.preselected && el._preselect) { ui.preselected = U.preselect.at; el._preselect(U.preselect); }
      const entries = W.entries || [], needs = W.needs || [], T = W.trades || {}, sum = W.summary || {};
      const sw = (view, value, label) => ui[view] === value ? `<b>${label}</b>` : `<a href="#" data-view="${view}" data-value="${value}">${label}</a>`;
      const what = e => e.kind === 'build' ? `<b>Build: ${esc(e.name)}</b> <span class="muted">${esc(e.module || '')}, follows the build card</span>`
        : `${e.qty} x ${e.module && e.kind !== 'unlock' ? esc(e.module) + ' ' : ''}<b>${esc(e.name)}</b>` + (e.kind === 'blueprint' ? ` <span class="muted">G${e.from_grade || 0} to G${e.grade}</span>` : e.kind === 'experimental' ? ` <span class="muted">experimental${!e.module && e.fits ? ', fits ' + esc(e.fits.join(', ')) : ''}</span>`
          : e.kind === 'unlock' ? ` <span class="muted">${esc(e.broker || '')} tech broker${Object.keys(e.commodities || {}).length ? '; also buy ' + Object.entries(e.commodities).map(([n, q]) => `${q} ${esc(n)}`).join(', ') : ''}</span>` : '');
      el.querySelector('.wl-entries').innerHTML = entries.length ? `<table style="margin-top:8px"><tbody>` + entries.map(e => `<tr>
          <td>${what(e)}${e.label ? ` <span class="muted">- ${esc(e.label)}</span>` : ''}</td>
          <td class="num">${e.complete ? '<span class="tag ok">ready</span>' : `<span class="tag bad">${fmt(e.short)} short</span>`}</td>
          <td class="num"><button class="mini" data-rm="${esc(e.id)}" title="remove">x</button></td></tr>`).join('') + `</tbody></table>`
        : `<div class="muted" style="margin-top:8px">Nothing tracked. Pick something above, or track the pinned build.</div>`;
      const shortRows = needs.filter(r => r.short);
      const rows = ui.needs === 'all' ? needs : ui.needs === 'short' ? shortRows.slice(0, LIMIT) : shortRows;
      const more = ui.needs === 'short' && shortRows.length > LIMIT ? `<tr><td colspan="5" class="muted"><a href="#" data-view="needs" data-value="shortall">${shortRows.length - LIMIT} more short</a></td></tr>` : '';
      el.querySelector('.wl-needs').innerHTML = needs.length ? `<div style="margin-top:8px"><b>Materials</b> <span class="muted">${sum.short ? `${sum.short} of ${sum.materials} short (${fmt(sum.units_short)} units)` : `all ${sum.materials} in stock`} - ${sw('needs', 'short', 'short')} / ${sw('needs', 'all', 'all')}</span></div>
        <table><thead><tr><th>Material</th><th>G</th><th class="num">Have</th><th class="num">Need</th><th class="num">Short</th></tr></thead><tbody>` +
        (rows.map(r => `<tr><td>${esc(r.name)} <span class="muted">${esc((r.category || '').slice(0, 3))}</span></td><td>${r.grade ?? ''}</td><td class="num">${fmt(r.have)}${r.cap ? `<span class="muted">/${r.cap}</span>` : ''}</td><td class="num">${fmt(r.need)}</td><td class="num ${r.short ? 'bad' : 'ok'}">${r.short ? fmt(r.short) : 'ok'}</td></tr>`).join('') || `<tr><td colspan="5" class="muted">nothing short</td></tr>`) + more + `</tbody></table>` : '';
      const trades = T.trades || [];
      const shown = ui.trades === 'all' ? trades : trades.slice(0, 8);
      el.querySelector('.wl-trades').innerHTML = (trades.length || (T.unresolved || []).length) ? `<div style="margin-top:8px"><b>Trader plan</b> <span class="muted">${Object.entries(T.by_trader || {}).map(([k, v]) => `${k}: ${v.trades} trade${v.trades === 1 ? '' : 's'}`).join(', ') || 'nothing tradeable'}${trades.length > 8 ? ` - ${sw('trades', 'few', 'first 8')} / ${sw('trades', 'all', 'all')}` : ''}</span></div>` +
        (shown.length ? `<table><tbody>` + shown.map(t => `<tr><td class="muted">${esc(t.category)}</td><td>give <b>${fmt(t.give.qty)}</b> ${esc(t.give.name)} <span class="muted">G${t.give.grade}</span></td><td>for <b>${fmt(t.get.qty)}</b> ${esc(t.get.name)} <span class="muted">G${t.get.grade}</span></td><td class="muted">${t.ratio}${t.same_family ? '' : ', cross family'}</td></tr>`).join('') + `</tbody></table>` : '') +
        ((T.unresolved || []).length ? `<div class="muted" style="margin-top:4px">Still short after trading: ${T.unresolved.slice(0, 8).map(u => `${fmt(u.short)} ${esc(u.name)}${u.note ? ' (' + esc(u.note) + ')' : ''}`).join(', ')}${T.unresolved.length > 8 ? ` and ${T.unresolved.length - 8} more` : ''}. See the farm sites card.</div>` : '') : '';
      const tr = U.traders;
      el.querySelector('.wl-traders').innerHTML = tr === 'loading' ? `<div class="muted" style="margin-top:8px">looking up traders</div>` : tr && tr.traders ? `<div style="margin-top:8px"><b>Nearest traders</b> <span class="muted">from ${esc(tr.ref)}</span></div>` +
        `<table><tbody>` + Object.entries(tr.traders).map(([type, list]) => Array.isArray(list)
          ? list.map((s, i) => `<tr>${i === 0 ? `<td rowspan="${list.length}"><span class="tag">${esc(type)}</span></td>` : ''}<td><b>${esc(s.system)}</b> <button class="mini" data-copy="${esc(s.system)}" title="copy the system name for the galaxy map">copy</button> <a href="${inaraSys(s.system)}" target="_blank">Inara</a></td><td>${esc(s.station)} <span class="muted">${esc(s.pad)} pad, ${fmt(s.ls)} ls</span></td><td class="num">${fmt(s.dist)} Ly${s.jumps ? ` <span class="muted">~${s.jumps} j</span>` : ''}</td></tr>`).join('')
          : `<tr><td><span class="tag">${esc(type)}</span></td><td colspan="3" class="bad">${esc(list.error)}</td></tr>`).join('') + `</tbody></table>` : '';
    },
  });
})();
