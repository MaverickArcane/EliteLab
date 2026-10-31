(() => {
  'use strict';
  const form = document.querySelector('[data-setup-form]'), status = document.querySelector('[data-status]');
  const restart = document.querySelector('[data-restart]');
  let loaded;
  async function api(path, body) {
    const response = await fetch(path, body === undefined ? {cache:'no-store'} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not reach EliteLab.');
    return result;
  }
  function render(state) {
    loaded = state;
    const values = {...state.values, ...state.pending};
    for (const key of ['journal_dir', 'port', 'data_dir']) {
      form.elements[key].value = values[key];
      const source = {env:'environment variable', flag:'command-line flag', file:'settings file', default:'default'}[state.sources[key]];
      document.querySelector(`[data-source="${key}"]`).textContent = `Running value from ${source}.`;
    }
    const list = document.querySelector('[data-candidates]'); list.replaceChildren();
    for (const candidate of state.journal_candidates) {
      const item = document.createElement('li'), label = document.createElement('label'), radio = document.createElement('input');
      radio.type = 'radio'; radio.name = 'candidate'; radio.value = candidate.path;
      radio.checked = candidate.path === values.journal_dir;
      radio.onchange = () => { form.elements.journal_dir.value = candidate.path; };
      label.append(radio, document.createTextNode(`${candidate.path} - ${candidate.exists ? `${candidate.journals} journals, newest ${candidate.newest || 'none'}` : 'not found'}`));
      item.append(label); list.append(item);
    }
    restart.hidden = !state.restart_required;
  }
  form.onsubmit = async event => {
    event.preventDefault(); if (!loaded) return;
    const changes = {}, baseline = {...loaded.values, ...loaded.pending};
    for (const key of ['journal_dir', 'port', 'data_dir']) {
      const value = key === 'port' ? Number(form.elements[key].value) : form.elements[key].value;
      if (value !== baseline[key]) changes[key] = value;
    }
    const button = form.querySelector('button'); button.disabled = true;
    try {
      const state = await api('/api/setup', changes); render(state);
      status.textContent = (state.restart_required ? 'Saved. Restart EliteLab to apply changes. ' : 'No restart needed. ') + state.warnings.join(' ');
    } catch (error) { status.textContent = error.message; }
    finally { button.disabled = false; }
  };
  restart.onclick = async () => {
    restart.disabled = true;
    try {
      await api('/api/restart', {});
      const target = new URL('/', location.href);
      if (loaded.pending.port && !['env','flag'].includes(loaded.sources.port)) target.port = loaded.pending.port;
      const link = document.querySelector('[data-dashboard]'); link.href = target.href;
      // Changed ports are different origins; do not weaken CORS to poll them.
      if (target.origin !== location.origin) {
        status.textContent = 'Restart requested. Open dashboard at the new address once your launcher restarts EliteLab.';
        return;
      }
      status.textContent = 'Waiting for EliteLab to restart...';
      await new Promise(resolve => setTimeout(resolve, 1500));
      for (let attempt = 0; attempt < 60; attempt++) {
        try { await api('/api/health'); location.assign(target.href); return; } catch (_) {}
        await new Promise(resolve => setTimeout(resolve, 500));
      }
      status.textContent = 'EliteLab did not come back. Start it again from your launcher.';
    } catch (error) { status.textContent = error.message; restart.disabled = false; }
  };
  api('/api/setup').then(render).catch(error => { status.textContent = error.message + ' Open the dashboard to sign in if authentication is enabled.'; });
})();
