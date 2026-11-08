(() => {
  const {esc} = Lab.util;
  const val = x => x == null ? '?' : esc(x);
  const ingredients = rows => rows.map(i => `${esc(i.name)} ${val(i.have)}/${val(i.required)}${i.short ? ` (short ${val(i.short)})` : ''}`).join(' / ');
  Lab.card({id:'synthesis', requires:['synthesis'],
    mount(el) {
      el.innerHTML = `<div data-synthesis-status></div>
        <form data-synthesis-search style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
          <label>Recipe <input name="query" placeholder="FSD, AFM, Heat Sinks..." style="width:180px"></label>
          <label>Grade <select name="grade"><option value="">All</option><option>basic</option><option>standard</option><option>premium</option></select></label>
          <label>Quantity <input name="quantity" type="number" min="1" max="10000" value="1" style="width:65px"></label>
          <button type="submit">Find recipes</button></form><div data-synthesis-results aria-live="polite"></div>
        <div data-synthesis-basket></div><button data-synthesis-budget>Check combined material budget</button>
        <button data-synthesis-empty>Clear selection</button><div data-synthesis-budget-result></div>`;
      el._basket = [];
      el._searchSeq = 0;
      el.querySelector('form').onsubmit = async e => {
        e.preventDefault(); const output = el.querySelector('[data-synthesis-results]'), revision = el._revision;
        const sequence = ++el._searchSeq;
        try {
          const f = e.currentTarget;
          const d = await Lab.api('/api/synthesis/recipes', {query:f.elements.query.value,grade:f.elements.grade.value,quantity:f.elements.quantity.value,limit:100});
          if (!el.isConnected || sequence !== el._searchSeq) return;
          if (revision !== el._revision) { output.textContent = 'Inventory changed; search again for current quantities.'; return; }
          el._recipes = d.recipes;
          output.innerHTML = `<div class="note">${esc(d.note)}</div>` + d.recipes.map((r,i) => `<div style="margin-top:8px"><strong>${esc(r.name)} / ${esc(r.grade)}</strong> / ${val(r.craftable)} craftable
            <button data-synthesis-add="${i}">Add ${val(r.quantity)} to budget</button><div class="muted">${ingredients(r.ingredients)}</div></div>`).join('') + (!d.recipes.length ? '<div>No matching recipes in this catalogue.</div>' : '');
        } catch(err) { if (el.isConnected && sequence === el._searchSeq) output.textContent = err.message; }
      };
      el.onclick = async e => {
        const add = e.target.closest('[data-synthesis-add]');
        if (add) { const r = el._recipes[Number(add.dataset.synthesisAdd)]; el._basket.push({key:r.key,quantity:r.quantity}); }
        if (e.target.closest('[data-synthesis-empty]')) el._basket = [];
        if (add || e.target.closest('[data-synthesis-empty]')) {
          el.querySelector('[data-synthesis-basket]').textContent = el._basket.map(r => `${r.quantity} ${r.key.replaceAll('_',' ')}`).join(' + ');
          el.querySelector('[data-synthesis-budget-result]').textContent = '';
        }
        if (e.target.closest('[data-synthesis-budget]')) {
          const output = el.querySelector('[data-synthesis-budget-result]'), revision = el._revision, selection = JSON.stringify(el._basket);
          if (!el._basket.length) { output.textContent = 'Add recipes to the budget first.'; return; }
          try {
            const d = await Lab.post('/api/synthesis/plan', {items:el._basket}); if (!el.isConnected) return;
            if (revision !== el._revision || selection !== JSON.stringify(el._basket)) { output.textContent = 'Selection or inventory changed; check the budget again.'; return; }
            output.innerHTML = `<div>${d.affordable === null ? 'Inventory unknown' : d.affordable ? 'Materials available' : 'Materials missing'}</div><div>${ingredients(d.materials)}</div><div class="note">${esc(d.note)}</div>`;
          } catch(err) { output.textContent = err.message; }
        }
      };
    },
    render(el, state) {
      const d = state.synthesis?.summary; if (!d) return;
      const revision = JSON.stringify([d.commander,d.inventory_observed_at,d.inventory_revision]);
      if (el._revision !== revision) {
        if (el._revision) {
          el.querySelector('[data-synthesis-results]').textContent = 'Inventory updated; search again to refresh recipe quantities.';
          el.querySelector('[data-synthesis-budget-result]').textContent = 'Check the combined budget again for current materials.';
        }
        el._revision = revision;
      }
      el.querySelector('[data-synthesis-status]').innerHTML =
        `<div>Boost evidence: <strong>${esc(d.boost.status.replaceAll('_',' '))}</strong>${d.boost.multiplier ? ` / ${val(d.boost.multiplier)}x` : ''}</div>
         <div class="note">Injections and neutron boosts do not stack. Availability below shares the same material stock.</div>
         ${d.injections.map(r => `<div>${esc(r.grade)} (+${val(Math.round((r.range_multiplier-1)*100))}%): <strong>${val(r.craftable)} craftable</strong></div>`).join('')}
         <details><summary>Recent synthesis and evidence limits</summary>${d.history.map(r => `<div>${esc(r.observed_at)} / ${esc(r.name)}</div>`).join('')}${d.notes.map(x => `<p>${esc(x)}</p>`).join('')}</details>`;
    }
  });
})();
