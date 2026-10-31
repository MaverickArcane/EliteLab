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
    if (!form.elements.port.value.trim()) { say('Enter a port between 1024 and 65535.', 'warn'); return; }
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

  // Wait for a restart under one budget. Phase 1: the CURRENT origin must stop answering (or answer non-OK), which proves the old
  // process is gone whether or not the port changed. Phase 2: the target must be healthy. Same origin: require HTTP OK and a JSON
  // body with ok === true. New port: the server sends no CORS headers, so a normal fetch would reject even when it is up; the
  // no-cors fetch resolves as an opaque response when something is listening, which is only a reachability signal.
  // fetchImpl and clock ({now, sleep}) are injectable so the browser suite can drive this without restarting the lab.
  async function waitForRestart(fetchImpl, targetBase, clock, budgetMs = 30000, stepMs = 500) {
    const started = clock.now();
    const left = () => clock.now() - started < budgetMs;
    const sameOrigin = targetBase === '';
    while (left()) {                                   // phase 1: old server must go away
      let gone = false;
      try { const r = await fetchImpl('/api/health', { cache: 'no-store' }); gone = !r.ok; } catch (e) { gone = true; }
      if (gone) break;
      await clock.sleep(stepMs);
      if (!left()) return 'timeout';
    }
    while (left()) {                                   // phase 2: target must be healthy
      try {
        if (sameOrigin) {
          const r = await fetchImpl('/api/health', { cache: 'no-store' });
          if (r.ok) { const j = await r.json(); if (j && j.ok === true && j.ready !== false) return 'up'; }   // ready:false = still loading
        } else {
          await fetchImpl(targetBase + '/api/health', { cache: 'no-store', mode: 'no-cors' });
          return 'up';
        }
      } catch (e) { /* not back yet */ }
      await clock.sleep(stepMs);
    }
    return 'timeout';
  }
  window.SetupPage = { waitForRestart };

  restartBtn.addEventListener('click', async () => {
    restartBtn.disabled = true;
    const port = (loaded.pending && loaded.pending.port) || loaded.values.port;
    const same = Number(port) === Number(location.port || (location.protocol === 'https:' ? 443 : 80));
    const base = same ? '' : `${location.protocol}//${location.hostname}:${port}`;
    try { await api('/api/restart', {}); } catch (err) {
      if (!(err instanceof TypeError)) { restartBtn.disabled = false; say(err.message, 'bad'); return; }   // HTTP refusal: show it now
      /* a dropped connection is the server exiting */
    }
    say('Restarting. This page will open the dashboard when EliteLab is back.');
    const clock = { now: () => Date.now(), sleep: ms => new Promise(r => setTimeout(r, ms)) };
    if (await waitForRestart((u, o) => fetch(u, o), base, clock) === 'up') { location.href = base + '/'; return; }
    restartBtn.disabled = false;
    say('EliteLab did not come back. Start it again from your launcher.', 'bad');
  });

  // Test the typed folder without saving it.
  const testBtn = $('[data-test-journal]');
  const testOut = $('[data-result="journal_test"]');
  testBtn.addEventListener('click', async () => {
    const typed = form.elements.journal_dir_custom.value.trim();
    if (!typed) { testOut.textContent = 'Type a folder path first.'; return; }
    testBtn.disabled = true;
    testOut.textContent = 'Checking...';
    try {
      const d = await api('/api/setup/journals', { path: typed });
      testOut.textContent = d.exists && d.journals ? `${d.journals} journals, newest ${d.newest || 'unknown'}` : 'not found';
    } catch (err) { testOut.textContent = err.message; }
    testBtn.disabled = false;
  });

  // The last interaction wins between the radios and the custom folder.
  $('[data-candidates]').addEventListener('change', e => { if (e.target.type === 'radio') form.elements.journal_dir_custom.value = ''; });
  form.elements.journal_dir_custom.addEventListener('input', e => {
    testOut.textContent = '';
    if (e.target.value.trim()) for (const r of form.querySelectorAll('[data-candidates] input:checked')) r.checked = false;
  });

  api('/api/setup').then(render).catch(err => say(`Could not load settings. ${err.message}`, 'bad'));
})();
