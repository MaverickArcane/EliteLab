(() => {
  const {esc, fmt} = Lab.util;
  const coord = n => Number.isFinite(n) ? n.toFixed(4) : '--';
  const place = s => s.body.startsWith(s.system + ' ') ? s.body : `${s.system} / ${s.body}`;
  const distance = n => n < 1000 ? `${fmt(Math.round(n))} m` : `${(n / 1000).toFixed(2)} km`;
  const recent = p => {
    const age = (Date.now() - Date.parse(p?.timestamp)) / 1000;
    return p?.body && p?.system && Number.isFinite(p.latitude) && Number.isFinite(p.longitude)
      && Number.isFinite(age) && age >= -5 && age <= 120;
  };

  Lab.card({
    id: 'rhino', requires: ['rhino'],
    mount(el) {
      el.innerHTML = `<div class="rhino-desk">
        <div class="rhino-tabs" role="tablist" aria-label="Rhino mining">
          <button role="tab" id="rhino-tab-spots" aria-controls="rhino-spots" aria-selected="true" data-rhino-tab="spots">Saved spots</button>
          <button role="tab" id="rhino-tab-guide" aria-controls="rhino-guide" aria-selected="false" tabindex="-1" data-rhino-tab="guide">How to mine</button>
        </div>
        <div class="note" data-rhino-message role="status" aria-live="polite"></div>
        <div id="rhino-spots" role="tabpanel" aria-labelledby="rhino-tab-spots">
          <div data-rhino-navigation></div>
          <div class="rhino-toolbar"><span class="muted">Keep the places worth returning to.</span><button data-rhino-new>Add a spot</button></div>
          <form data-rhino-site-form class="rhino-form" hidden>
            <h3 data-rhino-form-title>Save a spot</h3>
            <input type="hidden" name="id"><input type="hidden" name="radius_m">
            <button type="button" data-rhino-capture>Use current position</button>
            <label>Name<input name="name" maxlength="160" placeholder="Tritium cluster" required></label>
            <div class="grid2"><label>System<input name="system" maxlength="160" required></label><label>Full body name<input name="body" maxlength="160" required></label></div>
            <div class="grid2"><label>Latitude<input name="latitude" type="number" min="-90" max="90" step="any" required></label><label>Longitude<input name="longitude" type="number" min="-180" max="180" step="any" required></label></div>
            <label>Commodity<input name="commodity" maxlength="160" value="Tritium" required></label>
            <label>Notes<textarea name="notes" maxlength="1200" rows="3" placeholder="What worked here, how to approach, anything worth remembering"></textarea></label>
            <div class="row"><button class="primary" type="submit">Save spot</button><button type="button" data-rhino-cancel>Cancel</button></div>
          </form>
          <div data-rhino-site-list></div>
        </div>
        <div id="rhino-guide" role="tabpanel" aria-labelledby="rhino-tab-guide" hidden>
          <div data-rhino-guide-content><p>Loading mining guide...</p></div>
        </div>
      </div>`;
      const message = (value, bad = false) => {
        const node = el.querySelector('[data-rhino-message]');
        node.textContent = value; node.classList.toggle('bad', bad);
      };
      const action = async (path, body, success) => {
        try { await Lab.post(path, body); if (el.isConnected) message(success); }
        catch (error) { if (el.isConnected) message(error.message || String(error), true); }
      };
      let guideLoaded = false, guidePending = false;
      const loadGuide = async () => {
        if (guideLoaded || guidePending) return;
        guidePending = true;
        const target = el.querySelector('[data-rhino-guide-content]');
        target.textContent = 'Loading mining guide...';
        try {
          const guide = await Lab.api('/api/rhino/guide?topic=all');
          if (!el.isConnected) return;
          target.innerHTML = `<p class="note">Reviewed ${esc(guide.reviewed_at)}. ${esc(guide.scope)}</p>` + guide.sections.map(section => `
            <details class="rhino-topic" data-rhino-topic="${esc(section.id)}" ${section.id === 'overview' ? 'open' : ''}>
              <summary>${esc(section.title)}</summary><p>${esc(section.summary)}</p>
              <ol>${section.steps.map(step => `<li>${esc(step)}</li>`).join('')}</ol>
              ${section.notes.map(note => `<p>${esc(note)}</p>`).join('')}
              <details class="rhino-evidence"><summary>Sources and evidence</summary><p>${esc(section.evidence)}</p>
                ${section.sources.map(id => {
                  const source = guide.sources[id], url = /^https:\/\//.test(source.url) ? source.url : '';
                  return `<p>${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(source.title)}</a>` : esc(source.title)}<br><span class="note">${esc(source.kind)}. ${esc(source.note)}</span></p>`;
                }).join('')}
              </details>
            </details>`).join('');
          guideLoaded = true;
        } catch (error) {
          if (el.isConnected) target.innerHTML = `<p role="alert">${esc(error.message || String(error))}</p><button data-rhino-retry>Retry guide</button>`;
        } finally { guidePending = false; }
      };
      const form = el.querySelector('[data-rhino-site-form]');
      const freshForm = () => {
        form.reset(); form.elements.id.value = ''; form.elements.radius_m.value = ''; form.hidden = false;
        el.querySelector('[data-rhino-form-title]').textContent = 'Save a spot';
      };
      const tab = name => {
        message('');
        for (const button of el.querySelectorAll('[data-rhino-tab]')) {
          const active = button.dataset.rhinoTab === name;
          button.setAttribute('aria-selected', String(active)); button.tabIndex = active ? 0 : -1;
          el.querySelector(`#rhino-${button.dataset.rhinoTab}`).hidden = !active;
        }
        if (name === 'guide') loadGuide();
      };
      el.addEventListener('click', event => {
        const button = event.target.closest('button');
        if (!button) return;
        if (button.dataset.rhinoTab) tab(button.dataset.rhinoTab);
        if (button.hasAttribute('data-rhino-retry')) loadGuide();
        const state = Lab.state.rhino?.summary || {};
        if (button.hasAttribute('data-rhino-new')) { freshForm(); form.elements.name.focus(); }
        if (button.hasAttribute('data-rhino-cancel')) form.hidden = true;
        if (button.hasAttribute('data-rhino-capture')) {
          const p = state.position;
          if (!recent(p)) { message('Approach a body and wait for recent surface coordinates.', true); return; }
          for (const field of ['system', 'body', 'latitude', 'longitude', 'radius_m']) form.elements[field].value = p[field] ?? '';
          if (!form.elements.name.value) form.elements.name.value = `${form.elements.commodity.value || 'Mining'} spot`;
          message('Position filled in. Add what you found here, then save.');
        }
        if (button.dataset.rhinoSelect) action('/api/rhino/sites/select', {id: button.dataset.rhinoSelect}, 'Destination selected.');
        if (button.hasAttribute('data-rhino-clear')) action('/api/rhino/sites/select', {id: ''}, 'Destination cleared.');
        if (button.dataset.rhinoEdit) {
          const site = state.sites?.find(s => s.id === button.dataset.rhinoEdit);
          if (site) {
            freshForm(); for (const field of form.elements) if (field.name) field.value = site[field.name] ?? '';
            el.querySelector('[data-rhino-form-title]').textContent = 'Edit spot'; form.elements.name.focus();
          }
        }
        if (button.dataset.rhinoRemove) {
          const site = state.sites?.find(s => s.id === button.dataset.rhinoRemove);
          if (site && confirm(`Remove ${site.name} from your local notebook?`)) action('/api/rhino/sites/remove', {id: site.id}, 'Spot removed.');
        }
      });
      el.querySelector('.rhino-tabs').addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        const buttons = [...el.querySelectorAll('[data-rhino-tab]')], index = buttons.indexOf(document.activeElement);
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
        event.preventDefault(); tab(buttons[next].dataset.rhinoTab); buttons[next].focus();
      });
      form.addEventListener('submit', async event => {
        event.preventDefault();
        const body = Object.fromEntries(new FormData(form));
        for (const key of ['latitude', 'longitude']) body[key] = Number(body[key]);
        if (body.radius_m) body.radius_m = Number(body.radius_m); else delete body.radius_m;
        if (!body.id) delete body.id;
        const submit = form.querySelector('[type=submit]'); submit.disabled = true;
        try {
          const result = await Lab.post('/api/rhino/sites/save', body);
          if (el.isConnected) { form.elements.id.value = result.id; form.hidden = true; message('Spot saved and selected.'); }
        } catch (error) { if (el.isConnected) message(error.message || String(error), true); }
        finally { submit.disabled = false; }
      });
      el._rhinoFreshness = setInterval(() => { if (el.isConnected && !document.hidden) Lab.emit('rhino'); }, 5000);
    },
    unmount(el) { clearInterval(el._rhinoFreshness); },
    render(el, S) {
      const r = S.rhino?.summary || {}, site = r.selected_site, position = r.position || {};
      const nav = recent(position) ? r.navigation || {} : {reason: 'Waiting for a recent surface position'};
      el.querySelector('[data-rhino-navigation]').innerHTML = site ? `<div class="rhino-navigation">
        <div class="rhino-toolbar"><strong>To ${esc(site.name)}</strong><button class="mini" data-rhino-clear>Clear</button></div>
        ${nav.distance_m != null ? `<p class="rhino-direction">${distance(nav.distance_m)}${nav.bearing != null ? ` &middot; Heading ${nav.bearing.toFixed(1)} deg` : ' &middot; At saved coordinates'}</p>` : ''}
        <div class="note">${esc(nav.reason || '')}</div>
      </div>` : '<p class="muted">Choose a spot below to get directions.</p>';
      const list = el.querySelector('[data-rhino-site-list]');
      const signature = JSON.stringify([r.sites, site?.id]);
      // Position updates must not close notes, move focus or erase a form draft.
      if (list.dataset.signature !== signature) {
        const opened = new Set([...list.querySelectorAll('details[open]')].map(d => d.dataset.siteNotes));
        list.innerHTML = (r.sites || []).map(s => `<article class="rhino-site">
          <div class="rhino-toolbar"><strong>${esc(s.name)}</strong><button class="mini" data-rhino-select="${esc(s.id)}" ${s.id === site?.id ? 'disabled' : ''}>${s.id === site?.id ? 'Selected' : 'Navigate'}</button></div>
          <div>${esc(place(s))}</div>
          <div class="rhino-coords">${coord(s.latitude)}, ${coord(s.longitude)} <button class="mini" data-copy="${esc(s.system)} | ${esc(s.body)} | ${coord(s.latitude)}, ${coord(s.longitude)}">Copy location</button></div>
          <details data-site-notes="${esc(s.id)}" ${opened.has(s.id) ? 'open' : ''}><summary>${esc(s.commodity)} &middot; ${s.reference ? 'Reference' : 'Your notes'}</summary>
            <p>${esc(s.notes || 'No notes yet.')}</p><div class="note">Reported ${esc((s.reported_at || '').slice(0, 10))}; check conditions on arrival.</div>
            <div class="row">${s.reference ? '<a href="https://www.youtube.com/watch?v=pmkU1LqwPjA&t=131s" target="_blank" rel="noopener noreferrer">Video reference at 2:11</a>' : `<button class="mini" data-rhino-edit="${esc(s.id)}">Edit</button><button class="mini" data-rhino-remove="${esc(s.id)}">Remove</button>`}</div>
          </details>
        </article>`).join('');
        list.dataset.signature = signature;
      }
    },
  });
})();
