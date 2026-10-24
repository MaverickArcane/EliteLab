/* farming card: known material farm sites nearest first, filter by material, highlight sites that cover wishlist shortfalls. Also a map layer. */
(() => {
  const { esc, fmt, inaraSys, ls } = Lab.util;
  const KEY = 'farming.filter';
  Lab.card({
    id: 'farming', requires: ['farming', 'wishlist'],
    mount(el) {
      const saved = ls.get(KEY) || {};
      el.innerHTML = `<div class="row"><input id="fm-q" placeholder="material or site, e.g. tellurium, jameson" size="26" value="${esc(saved.q || '')}">
          <select id="fm-cat"><option value="">any category</option>${['Raw', 'Manufactured', 'Encoded', 'Guardian'].map(c => `<option${saved.cat === c ? ' selected' : ''}>${c}</option>`).join('')}</select>
          <label class="chk"><input type="checkbox" id="fm-short"${saved.short ? ' checked' : ''}> only my shortfalls</label></div>
        <div class="fm-list"></div>
        <div class="note">Community-documented sites, nearest first; entries without a system are methods. Lat/long is where to land. Ask your AI: "where do I farm tellurium" and it calls find_farm_sites.</div>`;
      const rerender = () => { ls.set(KEY, { q: el.querySelector('#fm-q').value, cat: el.querySelector('#fm-cat').value, short: el.querySelector('#fm-short').checked }); Lab.emit('farming'); };
      el.querySelector('#fm-q').oninput = rerender; el.querySelector('#fm-cat').onchange = rerender; el.querySelector('#fm-short').onchange = rerender;
      el.onclick = e => { const t = e.target.closest('.fm-more'); if (t) { e.preventDefault(); const d = t.closest('.fm-site').querySelector('.fm-how'); d.style.display = d.style.display === 'none' ? '' : 'none'; } };
    },
    render(el, S) {
      const F = S.farming || {}; const q = (el.querySelector('#fm-q').value || '').trim().toLowerCase(), cat = el.querySelector('#fm-cat').value, onlyShort = el.querySelector('#fm-short').checked;
      const words = q.split(/\s+/).filter(Boolean);
      const rows = (F.sites || []).filter(s => (!cat || s.category === cat) && (!onlyShort || s.covers.length) &&
        words.every(w => (s.name + ' ' + (s.system || '') + ' ' + s.type + ' ' + s.material_names.join(' ')).toLowerCase().includes(w)));
      el.querySelector('.fm-list').innerHTML = rows.length ? rows.map(s => `<div class="fm-site" style="padding:6px 0;border-top:1px solid var(--line)">
          <div><b>${esc(s.name)}</b> <span class="muted">${esc(s.type)}${s.dist != null ? ` - ${fmt(s.dist)} Ly${s.jumps ? `, ~${s.jumps} jumps` : ''}` : s.system ? ' - distance unknown' : ''}</span>
            ${s.system ? ` <button class="mini" data-copy="${esc(s.system)}">copy</button> <a href="${inaraSys(s.system)}" target="_blank">Inara</a>` : ''} <a href="#" class="fm-more muted">how</a></div>
          <div>${s.material_names.length ? s.material_names.map(m => `<span class="tag${s.covers.includes(m) ? ' bad' : ''}">${esc(m)}</span>`).join(' ') : '<span class="muted">low and mid grade raws</span>'}</div>
          <div class="fm-how muted" style="display:none">${s.body ? `<b>${esc(s.system)} ${esc(s.body)}</b>${s.surface ? ` at ${s.surface[0]}, ${s.surface[1]}` : ''}. ` : ''}${esc(s.how)}${s.notes ? ` ${esc(s.notes)}` : ''}</div>
        </div>`).join('') : `<div class="muted" style="margin-top:8px">${onlyShort ? 'No known site covers a current shortfall (or the wishlist is empty).' : 'No site matches.'}</div>`;
    },
  });
  Lab.map.addLayer('farming', { label: 'farm sites', color: '#7ec8a0', z: 2, enabled: false,
    points: S => ((S.farming || {}).sites || []).filter(s => s.coords).map(s => ({ name: s.system, x: s.coords.x, y: s.coords.y, z: s.coords.z, r: 3, color: s.covers.length ? '#ff5a5a' : '#7ec8a0', sub: s.name + ': ' + (s.material_names.slice(0, 3).join(', ') || s.type), copy: s.system })) });
})();
