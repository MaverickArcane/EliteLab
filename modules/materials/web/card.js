/* materials card: totals, wishlist with shortfalls, quick add. */
(() => {
  const { esc, fmt } = Lab.util;
  Lab.card({
    id: 'materials', requires: ['materials'],
    header(h) { h.innerHTML = `<button class="mini" id="mat-clear">clear wishlist</button>`; h.querySelector('#mat-clear').onclick = () => Lab.post('/api/materials/wishlist', { items: {}, mode: 'clear' }); },
    render(el, S) {
      const M = S.materials || {}; const t = M.totals || {}; const rows = M.shortfalls || [];
      el.innerHTML = `
        <div class="grid2" style="margin-top:0">
          <div><div class="k">Raw</div><div class="v">${fmt(t.Raw)}</div></div>
          <div><div class="k">Manufactured</div><div class="v">${fmt(t.Manufactured)}</div></div>
          <div><div class="k">Encoded</div><div class="v">${fmt(t.Encoded)}</div></div>
          <div><div class="k">Wishlist</div><div class="v">${rows.length ? `${rows.filter(r => r.short > 0).length} short of ${rows.length}` : 'empty'}</div></div>
        </div>
        ${rows.length ? `<table style="margin-top:8px"><thead><tr><th>Material</th><th>G</th><th class="num">Have</th><th class="num">Need</th><th class="num">Short</th></tr></thead><tbody>` +
          rows.map(r => `<tr><td>${esc(r.name)}${r.label ? ` <span class="muted">· ${esc(r.label)}</span>` : ''}</td><td>${r.grade ?? ''}</td><td class="num">${fmt(r.count)}${r.cap ? `<span class="muted">/${r.cap}</span>` : ''}</td><td class="num">${fmt(r.need)}</td><td class="num ${r.short > 0 ? 'bad' : 'ok'}">${r.short > 0 ? fmt(r.short) : '✓'}</td></tr>`).join('') + '</tbody></table>' : ''}
        <div class="row" style="margin-top:8px"><input id="mat-name" placeholder="material" size="18"><input id="mat-qty" placeholder="qty" size="4" value="10"><button class="mini" id="mat-add">add to wishlist</button></div>
        <div class="note">Ask your AI: "set the wishlist for FSD G5 Increased Range" and it calls set_wishlist; shortfalls update live as you collect. Full blueprint planning lives in Odyssey Materials Helper.</div>`;
      el.querySelector('#mat-add').onclick = async () => {
        const name = el.querySelector('#mat-name').value.trim(), qty = +el.querySelector('#mat-qty').value || 0; if (!name) return;
        const r = await Lab.post('/api/materials/wishlist', { items: { [name]: qty }, mode: 'add' });
        if (r.unknown && r.unknown.length) alert('Unknown material: ' + r.unknown.join(', '));
      };
    },
  });
})();
