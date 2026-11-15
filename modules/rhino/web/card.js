(() => {
  const {esc, fmt, bar} = Lab.util;
  const quantity = n => n == null ? 'Unknown' : `${fmt(n)} t`;
  const coord = n => Number.isFinite(n) ? n.toFixed(4) : '--';
  const timeLabel = value => value ? new Date(value).toLocaleTimeString() : 'Not observed';
  const distance = n => n == null ? '--' : n < 1000 ? `${fmt(Math.round(n))} m` : `${(n / 1000).toFixed(2)} km`;
  const metric = (label, value, detail = '') => `<div class="rhino-metric"><div class="k">${esc(label)}</div><div class="rhino-value">${esc(value)}</div><div class="muted">${esc(detail)}</div></div>`;

  Lab.card({
    id: 'rhino', requires: ['rhino'],
    mount(el) {
      el.innerHTML = `<div class="rhino-desk">
        <div class="rhino-tabs" role="tablist" aria-label="Rhino mining">
          <button role="tab" id="rhino-tab-mine" aria-controls="rhino-mine" aria-selected="true" data-rhino-tab="mine">Mining run</button>
          <button role="tab" id="rhino-tab-sites" aria-controls="rhino-sites" aria-selected="false" tabindex="-1" data-rhino-tab="sites">Saved sites</button>
          <button role="tab" id="rhino-tab-guide" aria-controls="rhino-guide" aria-selected="false" tabindex="-1" data-rhino-tab="guide">Field guide</button>
        </div>
        <div class="note" data-rhino-message role="status" aria-live="polite"></div>
        <div id="rhino-mine" role="tabpanel" aria-labelledby="rhino-tab-mine">
          <div class="rhino-reminder"><strong>Unload cargo. Keep the rigs working.</strong><span>Recall ship nearby, drive underneath, then Inventory &gt; Transfer &gt; Transfer all to ship. Stay in the Rhino.</span></div>
          <div class="rhino-metrics" data-rhino-metrics></div>
          <div class="rhino-columns">
            <div><div class="rhino-section"><h3>Hold space</h3><div data-rhino-cargo></div></div>
              <div class="rhino-section"><h3>Return to a site</h3>
                <label class="rhino-label">Destination<select data-rhino-destination><option value="">Choose a saved site</option></select></label>
                <div data-rhino-navigation></div>
              </div>
            </div>
            <div><div class="rhino-section"><h3>Collected this deployment</h3><div data-rhino-output></div></div>
              <div class="rhino-section"><h3>Working rigs</h3>
                <form data-rhino-rigs class="row"><label>Confirmed by you <input type="number" name="count" min="0" max="6" step="1" value="3" required aria-label="Working rig count"></label><button type="submit">Record count</button></form>
                <div class="note" data-rhino-rig-note></div>
              </div>
            </div>
          </div>
          <div class="note" data-rhino-timing></div>
        </div>
        <div id="rhino-sites" role="tabpanel" aria-labelledby="rhino-tab-sites" hidden>
          <div class="rhino-columns"><div class="rhino-section"><h3>Site notebook</h3><div data-rhino-site-list></div></div>
            <div class="rhino-section"><h3 data-rhino-form-title>Save a site</h3>
              <form data-rhino-site-form class="rhino-form">
                <input type="hidden" name="id"><input type="hidden" name="radius_m">
                <button type="button" data-rhino-capture>Use current position</button>
                <label>Name<input name="name" maxlength="160" placeholder="Tritium cluster" required></label>
                <label>System<input name="system" maxlength="160" required></label>
                <label>Body<input name="body" maxlength="160" placeholder="Full body name" required></label>
                <div class="grid2"><label>Latitude<input name="latitude" type="number" min="-90" max="90" step="any" required></label><label>Longitude<input name="longitude" type="number" min="-180" max="180" step="any" required></label></div>
                <div class="grid2"><label>Commodity<input name="commodity" maxlength="160" value="Tritium" required></label><label>Reported rig fit<input name="rigs" type="number" min="0" max="6" step="1" value="3" required></label></div>
                <label>Notes<textarea name="notes" maxlength="1200" rows="3" placeholder="Terrain, deposit amount, spacing or collection route"></textarea></label>
                <div class="row"><button class="primary" type="submit">Save site</button><button type="button" data-rhino-new>New site</button></div>
                <div class="note">Saved locally for this commander. Rig fit and reserves are your observations.</div>
              </form>
            </div>
          </div>
        </div>
        <div id="rhino-guide" role="tabpanel" aria-labelledby="rhino-tab-guide" hidden>
          <div class="rhino-columns"><div class="rhino-section"><h3>The collection loop</h3>
            <ol><li>Scan the deposit and confirm its commodity before placing rigs.</li><li>Collect minerals from a rig, leaving it deployed for the next cycle.</li><li>When the 72 t hold fills, recall your ship nearby and transfer cargo from the Inventory panel while staying in the Rhino.</li><li>Return to collecting. Recover the rigs before boarding your ship or leaving.</li></ol>
            <p>A compact route matters. Add rigs when the extra production saves more time than servicing them costs.</p>
          </div><div class="rhino-section"><h3>What to check in game</h3>
            <p>Use the Energylink on foot to recharge rig efficiency. Check efficiency and hopper contents on the rigs; EliteLab cannot read them.</p>
            <p>Replacement rigs can be synthesized using materials. Selling and re-equipping the Rhino is a reported restocking workaround.</p>
            <p>Keep transfers close to your rigs. Leaving their operating range or boarding your ship can lose the deployed rigs.</p>
            <h3>Surface coordinates</h3><p>Latitude comes first. North (000) raises latitude; south (180) lowers it. East (090) raises longitude; west (270) lowers it.</p>
            <p>Saved coordinates locate a place, not guaranteed stock. Reserves can change. Leaving and returning is not a reliable reroll method.</p>
          </div></div>
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
      const form = el.querySelector('[data-rhino-site-form]');
      const fill = site => { for (const field of form.elements) if (field.name) field.value = site[field.name] ?? ''; };
      const freshForm = () => { form.reset(); form.elements.id.value = ''; form.elements.radius_m.value = ''; el.querySelector('[data-rhino-form-title]').textContent = 'Save a site'; };
      const tab = name => {
        for (const button of el.querySelectorAll('[data-rhino-tab]')) {
          const active = button.dataset.rhinoTab === name;
          button.setAttribute('aria-selected', String(active)); button.tabIndex = active ? 0 : -1;
          el.querySelector(`#rhino-${button.dataset.rhinoTab}`).hidden = !active;
        }
      };
      el.addEventListener('click', event => {
        const button = event.target.closest('button');
        if (!button) return;
        if (button.dataset.rhinoTab) tab(button.dataset.rhinoTab);
        const state = Lab.state.rhino?.summary || {};
        if (button.hasAttribute('data-rhino-capture')) {
          const p = state.position || {}, age = (Date.now() - Date.parse(p.timestamp)) / 1000;
          if (!p.body || !p.system || !Number.isFinite(p.latitude) || !Number.isFinite(p.longitude) || !Number.isFinite(age) || age > 120 || age < -5) {
            message('Approach a body and wait for recent surface coordinates.', true); return;
          }
          for (const field of ['system', 'body', 'latitude', 'longitude', 'radius_m']) form.elements[field].value = p[field] ?? '';
          if (!form.elements.name.value) form.elements.name.value = `${form.elements.commodity.value || 'Mining'} site`;
          message('Position copied into the form. Check the commodity and rig fit, then save.');
        }
        if (button.hasAttribute('data-rhino-new')) freshForm();
        if (button.dataset.rhinoSelect) action('/api/rhino/sites/select', {id: button.dataset.rhinoSelect}, 'Destination selected.');
        if (button.dataset.rhinoEdit) {
          const site = state.sites?.find(s => s.id === button.dataset.rhinoEdit);
          if (site) { fill(site); el.querySelector('[data-rhino-form-title]').textContent = 'Edit saved site'; }
        }
        if (button.dataset.rhinoRemove) {
          const site = state.sites?.find(s => s.id === button.dataset.rhinoRemove);
          if (site && confirm(`Remove ${site.name} from your local notebook?`)) action('/api/rhino/sites/remove', {id: site.id}, 'Site removed.');
        }
      });
      el.querySelector('.rhino-tabs').addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        const buttons = [...el.querySelectorAll('[data-rhino-tab]')], index = buttons.indexOf(document.activeElement);
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
        event.preventDefault(); tab(buttons[next].dataset.rhinoTab); buttons[next].focus();
      });
      el.querySelector('[data-rhino-destination]').addEventListener('change', event => action('/api/rhino/sites/select', {id: event.target.value}, 'Destination updated.'));
      form.addEventListener('submit', async event => {
        event.preventDefault();
        const body = Object.fromEntries(new FormData(form));
        for (const key of ['latitude', 'longitude', 'rigs']) body[key] = Number(body[key]);
        if (body.radius_m) body.radius_m = Number(body.radius_m); else delete body.radius_m;
        if (!body.id) delete body.id;
        const submit = form.querySelector('[type=submit]'); submit.disabled = true;
        try { const result = await Lab.post('/api/rhino/sites/save', body); if (el.isConnected) { form.elements.id.value = result.id; message('Site saved and selected.'); } }
        catch (error) { if (el.isConnected) message(error.message || String(error), true); }
        finally { submit.disabled = false; }
      });
      el.querySelector('[data-rhino-rigs]').addEventListener('submit', event => {
        event.preventDefault(); action('/api/rhino/rigs', {count: Number(event.target.elements.count.value)}, 'Working rig count recorded.');
      });
      el._rhinoFreshness = setInterval(() => { if (el.isConnected && !document.hidden) Lab.emit('rhino'); }, 5000);
    },
    unmount(el) { clearInterval(el._rhinoFreshness); },
    render(el, S) {
      const r = S.rhino?.summary || {}, session = r.session, site = r.selected_site, position = r.position || {};
      const age = (Date.now() - Date.parse(position.timestamp)) / 1000;
      const nav = site && (!Number.isFinite(age) || age > 120 || age < -5)
        ? {reason:'Waiting for a recent surface position'} : r.navigation || {};
      const elapsed = session?.elapsed_seconds;
      el.querySelector('[data-rhino-metrics]').innerHTML = metric('Collected', quantity(session?.refined_tons), session?.active ? 'Current Rhino deployment' : session?.ended_reason || 'Deploy your Rhino to begin')
        + metric('Measured yield', session?.tons_per_hour == null ? '--' : `${fmt(session.tons_per_hour)} t/h`, elapsed == null ? 'Includes setup and unloading' : `${Math.floor(elapsed / 60)}m ${Math.floor(elapsed % 60)}s recorded`)
        + metric('Transferred to ship', quantity(session?.transferred_tons), `${session?.unloads || 0} recorded unloads`);
      el.querySelector('[data-rhino-cargo]').innerHTML = ['srv', 'ship'].map(vessel => {
        const c = r.cargo?.[vessel] || {}, pct = c.count != null && c.capacity ? c.count / c.capacity * 100 : 0;
        return `<div class="rhino-hold">${bar(vessel === 'srv' ? 'Rhino' : 'Ship', Math.min(100, pct), `${quantity(c.count)} / ${quantity(c.capacity)}`, pct >= 90 ? 'var(--warn)' : 'var(--accent-2)')}
          <div class="note">${c.free == null ? 'Free space unknown' : `${fmt(c.free)} t free`} &middot; ${esc(timeLabel(c.timestamp))}${c.source ? ` &middot; ${esc(c.source)}` : ''}</div></div>`;
      }).join('');
      const select = el.querySelector('[data-rhino-destination]');
      const options = JSON.stringify((r.sites || []).map(s => [s.id, s.name]));
      if (select.dataset.options !== options) {
        select.innerHTML = '<option value="">Choose a saved site</option>' + (r.sites || []).map(s => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join(''); select.dataset.options = options;
      }
      if (document.activeElement !== select) select.value = site?.id || '';
      el.querySelector('[data-rhino-navigation]').innerHTML = `<div class="rhino-nav">${metric('Surface distance', distance(nav.distance_m))}${metric('Heading', nav.bearing == null ? '--' : `${nav.bearing.toFixed(1)} deg`)}</div>
        <div class="note">${esc(nav.reason || 'Choose a saved site')}</div>
        ${site ? `<p><strong>${esc(site.body)}</strong><br><span class="rhino-coords">${coord(site.latitude)}, ${coord(site.longitude)}</span> <button class="mini" data-copy="${coord(site.latitude)}, ${coord(site.longitude)}">Copy</button></p>` : ''}
        <div class="note">Your position: ${esc(position.body || 'not on a mapped surface')}<br>${coord(position.latitude)}, ${coord(position.longitude)}</div>`;
      el.querySelector('[data-rhino-output]').innerHTML = session?.commodities?.length ? `<table><thead><tr><th>Commodity</th><th class="num">Collected</th><th class="num">t/h</th></tr></thead><tbody>${session.commodities.map(row => `<tr><td>${esc(row.name)}</td><td class="num">${fmt(row.tons)} t</td><td class="num">${row.tons_per_hour == null ? '--' : fmt(row.tons_per_hour)}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">No refined cargo recorded for a Rhino deployment yet.</p>';
      el.querySelector('[data-rhino-rig-note]').textContent = r.rigs?.count == null ? 'Not reported for this deployment. EliteLab cannot detect placed rigs.' : `${r.rigs.count} working rigs reported by you at ${timeLabel(r.rigs.reported_at)}. Clear or update this when your setup changes.`;
      el.querySelector('[data-rhino-rigs] button').disabled = !session?.active;
      el.querySelector('[data-rhino-timing]').textContent = r.rate_note || '';
      el.querySelector('[data-rhino-site-list]').innerHTML = (r.sites || []).map(s => `<article class="rhino-site">
        <div class="row"><strong>${esc(s.name)}</strong><span class="tag">${s.reference ? 'Reference' : 'Your report'}</span></div>
        <div>${esc(s.body)}</div><div class="rhino-coords">${coord(s.latitude)}, ${coord(s.longitude)}</div>
        <div class="note">${esc(s.commodity)} &middot; ${esc(s.rigs ?? '?')} rigs reported &middot; ${esc((s.reported_at || '').slice(0, 10))}</div>
        <p>${esc(s.notes || '')}</p><div class="row"><button class="mini" data-rhino-select="${esc(s.id)}">${s.id === site?.id ? 'Selected' : 'Navigate here'}</button><button class="mini" data-copy="${esc(s.body)} | ${coord(s.latitude)}, ${coord(s.longitude)}">Copy location</button>${s.reference ? '<a href="https://www.youtube.com/watch?v=pmkU1LqwPjA&t=131s" target="_blank" rel="noopener noreferrer">Video at 2:11</a>' : `<button class="mini" data-rhino-edit="${esc(s.id)}">Edit</button><button class="mini" data-rhino-remove="${esc(s.id)}">Remove</button>`}</div>
      </article>`).join('');
    },
  });
})();
