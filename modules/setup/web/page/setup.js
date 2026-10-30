/* First-run setup page: reads /api/setup, saves changed fields, restarts and waits for the lab to come back. */
(() => {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const $ = sel => document.querySelector(sel);
  const form = $('[data-setup-form]');
  const statusEl = $('[data-status]');
  const restartBtn = $('[data-restart]');
  const SOURCE = { flag: 'from command line flag', env: 'from environment variable', file: 'from settings file', default: 'default' };
  let loaded = null;

  const say = (lines, cls) => {
    statusEl.className = 'note' + (cls ? ' ' + cls : '');
    statusEl.textContent = [].concat(lines).filter(Boolean).join(' ');
  };
  const hint = (key, sources) => { const el = $(`[data-hint="${key}"]`); if (el) el.textContent = SOURCE[sources[key]] || ''; };
  const api = async (path, body) => {
    const opts = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    const r = await fetch(path, opts);
    let data = null;
    try { data = await r.json(); } catch (e) { data = null; }
    if (!r.ok) throw new Error((data && (data.error || data.message)) || `Request failed (${r.status}).`);
    return data;
  };

  function render(d) {
    loaded = d;
    const v = d.values;
    const list = $('[data-candidates]');
    const known = d.journal_candidates.some(c => c.selected);
    list.innerHTML = d.journal_candidates.map((c, i) => {
      const info = c.exists && c.journals ? `${c.journals} journals, newest ${c.newest || 'unknown'}` : 'not found';
      return `<li><label class="chk"><input type="radio" name="journal_dir" value="${esc(c.path)}" ${c.selected ? 'checked' : ''}>
        <span class="n"><b>${esc(c.path)}</b><br><span class="muted">${esc(info)}</span></span></label></li>`;
    }).join('');
    form.elements.journal_dir_custom.value = known ? '' : v.journal_dir;
    form.elements.port.value = v.port;
    form.elements.data_dir.value = v.data_dir;
    $('[data-browser]').textContent = v.browser || 'not set';
    for (const k of ['journal_dir', 'port', 'data_dir']) hint(k, d.sources);
    restartBtn.hidden = !d.restart_required;
  }

  function changes() {
    const custom = form.elements.journal_dir_custom.value.trim();
    const picked = form.querySelector('[data-candidates] input:checked');
    const now = {
      journal_dir: custom || (picked ? picked.value : loaded.values.journal_dir),
      port: form.elements.port.value.trim(),
      data_dir: form.elements.data_dir.value.trim(),
    };
    const out = {};
    for (const k of Object.keys(now)) if (String(now[k]) !== String(loaded.values[k])) out[k] = k === 'port' ? Number(now[k]) : now[k];
    return out;
  }

  form.addEventListener('submit', async e => {
    e.preventDefault();
    let diff;
    try { diff = changes(); } catch (err) { say(err.message, 'warn'); return; }
    if (!Object.keys(diff).length) { say(loaded.restart_required ? 'Nothing new to save. A saved change is waiting for a restart.' : 'Nothing changed.'); return; }
    try {
      const d = await api('/api/setup', diff);
      render(d);
      const lines = [`Saved ${d.saved.join(', ') || 'nothing'}.`].concat(d.warnings || []);
      if (d.restart_required) lines.push('Restart EliteLab to apply the change.');
      say(lines, (d.warnings || []).length ? 'warn' : 'ok');
    } catch (err) { say(err.message, 'bad'); }
  });

  restartBtn.addEventListener('click', async () => {
    restartBtn.disabled = true;
    const port = (loaded.pending && loaded.pending.port) || loaded.values.port;
    const same = Number(port) === Number(location.port || (location.protocol === 'https:' ? 443 : 80));
    const base = same ? '' : `${location.protocol}//${location.hostname}:${port}`;
    say('Restarting. This page will open the dashboard when EliteLab is back.');
    try { await api('/api/restart', {}); } catch (err) { /* the server may drop the connection as it exits */ }
    const started = Date.now();
    const timer = setInterval(async () => {
      try {
        await fetch(base + '/api/health', { cache: 'no-store', mode: same ? 'same-origin' : 'no-cors' });
        clearInterval(timer);
        location.href = base + '/';
      } catch (err) {
        if (Date.now() - started > 30000) {
          clearInterval(timer);
          restartBtn.disabled = false;
          say('EliteLab did not come back. Start it again from your launcher.', 'bad');
        }
      }
    }, 500);
  });

  api('/api/setup').then(render).catch(err => say(`Could not load settings. ${err.message}`, 'bad'));
})();
