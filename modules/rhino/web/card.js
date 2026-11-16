(() => {
  const {esc, fmt} = Lab.util;
  const coord = n => Number.isFinite(n) ? n.toFixed(4) : '--';
  const place = s => s.body.startsWith(s.system + ' ') ? s.body : `${s.system} / ${s.body}`;
  const distance = n => n < 1000 ? `${fmt(Math.round(n))} m` : `${(n / 1000).toFixed(2)} km`;
  const badges = s => `<span class="rhino-badge ${s.verification === 'confirmed' ? 'confirmed' : ''}">${s.verification === 'confirmed' ? 'Confirmed' : 'Unconfirmed'}</span>${s.availability === 'reported_depleted' ? '<span class="rhino-badge depleted">Reported depleted</span>' : ''}`;
  const rigEvidence = s => [s.rigs_observed != null ? `${s.rigs_observed} rigs observed${s.personal_rigs_observed != null ? ' here (your report)' : ''}` : '', s.rigs_reported != null && s.rigs_reported !== s.rigs_observed ? `${s.rigs_reported} rigs reported` : '', s.rigs_estimated != null ? `${s.rigs_estimated} rigs estimated` : ''].filter(Boolean).join(' / ');
  const recent = p => {
    const age = (Date.now() - Date.parse(p?.timestamp)) / 1000;
    return p?.body && p?.system && Number.isFinite(p.latitude) && Number.isFinite(p.longitude)
      && Number.isFinite(age) && age >= -5 && age <= 120;
  };
  const trip = (site, fresh, selected = false) => {
    const t = site.travel || {}, jumps = t.estimated_jumps;
    if (t.stage === 'surface' && fresh) return `<div class="rhino-direction">${distance(t.surface_distance_m)}${t.bearing != null ? ` &middot; Heading ${t.bearing.toFixed(1)} deg` : ' &middot; At saved coordinates'}</div><div class="note">On this body &middot; 0 jumps</div>`;
    if (t.stage === 'surface' || t.stage === 'body') return `<div class="rhino-direction">In this system &middot; 0 jumps</div><div class="note">${selected ? `Approach ${esc(site.body)}${site.pml ? ` &middot; PML ${esc(site.pml)}` : ''} for surface directions.` : 'Surface distance available near the target body.'}</div>`;
    return `<div class="rhino-direction">${t.distance_ly != null ? `${fmt(t.distance_ly)} Ly` : 'Distance unknown'} &middot; ${jumps != null ? `est. ${fmt(jumps)}+ jump${jumps === 1 ? '' : 's'}` : 'Jumps unknown'}</div>
      <div class="note">${t.from_system ? `From ${esc(t.from_system)} &middot; different system` : 'Waiting for your system'}</div>
      ${selected ? `<p><strong>Jump to ${esc(site.system)}</strong> <button class="mini" data-copy="${esc(site.system)}">Copy system</button></p><div class="note">Then fly to ${esc(site.body)}${site.pml ? ` &middot; PML ${esc(site.pml)}` : ''}. Surface bearing appears on that body.</div>` : ''}
      ${selected && jumps != null ? '<div class="note">Jump count is a minimum estimate; plot the route in game.</div>' : ''}`;
  };

  Lab.card({
    id: 'rhino', requires: ['rhino'],
    mount(el) {
      el.innerHTML = `<div class="rhino-desk">
        <div class="rhino-tabs" role="tablist" aria-label="Rhino mining">
          <button role="tab" id="rhino-tab-mining" aria-controls="rhino-mining" aria-selected="true" data-rhino-tab="mining">Mining</button>
          <button role="tab" id="rhino-tab-spots" aria-controls="rhino-spots" aria-selected="false" tabindex="-1" data-rhino-tab="spots">Locations</button>
          <button role="tab" id="rhino-tab-guide" aria-controls="rhino-guide" aria-selected="false" tabindex="-1" data-rhino-tab="guide">How to mine</button>
        </div>
        <div class="note" data-rhino-message role="status" aria-live="polite"></div>
        <div id="rhino-mining" role="tabpanel" aria-labelledby="rhino-tab-mining">
          <div data-rhino-navigation></div>
          <div class="rhino-toolbar"><button data-rhino-tab-open="spots">Choose a spot</button><button data-rhino-save-here>Save this location</button></div>
          <div data-rhino-haul></div>
          <div data-rhino-holds class="rhino-holds"></div>
          <div data-rhino-help class="rhino-help"></div>
          <div class="rhino-shortcuts" aria-label="Mining instructions">
            <button class="mini" data-rhino-help-topic="finding">Find deposits</button>
            <button class="mini" data-rhino-help-topic="placement">Place rigs</button>
            <button class="mini" data-rhino-help-topic="collection">Collect</button>
            <button class="mini" data-rhino-help-topic="unloading">Unload</button>
            <button class="mini" data-rhino-help-topic="recovery">Pack up</button>
          </div>
        </div>
        <div id="rhino-spots" role="tabpanel" aria-labelledby="rhino-tab-spots" hidden>
          <div class="rhino-toolbar"><span class="muted">Proven visits and places to investigate.</span><button data-rhino-new>Add a spot</button></div>
          <p class="note">Confirmed means visited and reported in game. Reserves can change; rig counts retain their own evidence.</p>
          <form data-rhino-site-form class="rhino-form" hidden>
            <h3 data-rhino-form-title>Save a spot</h3>
            <input type="hidden" name="id"><input type="hidden" name="radius_m">
            <button type="button" data-rhino-capture>Use current position</button>
            <label>Name<input name="name" maxlength="160" placeholder="Tritium cluster" required></label>
            <div class="grid2"><label>System<input name="system" maxlength="160" required></label><label>Full body name<input name="body" maxlength="160" required></label></div>
            <div class="grid2"><label>Latitude<input name="latitude" type="number" min="-90" max="90" step="any" required></label><label>Longitude<input name="longitude" type="number" min="-180" max="180" step="any" required></label></div>
            <label>PML number (optional)<input name="pml" type="number" min="1" max="1000000" step="1" placeholder="Planetary Mining Location"></label>
            <label>Commodity<input name="commodity" maxlength="160" value="Tritium" required></label>
            <label>Notes<textarea name="notes" maxlength="1200" rows="3" placeholder="What worked here, how to approach, anything worth remembering"></textarea></label>
            <div class="row"><button class="primary" type="submit">Save spot</button><button type="button" data-rhino-cancel>Cancel</button></div>
          </form>
          <form data-rhino-report-form class="rhino-form" hidden>
            <h3 data-rhino-report-title>Update location report</h3><input type="hidden" name="id">
            <div class="grid2">
              <label>Location evidence<select name="verification"><option value="unconfirmed">Unconfirmed</option><option value="confirmed">Confirmed in game</option></select></label>
              <label>Deposit condition<select name="availability"><option value="unknown">Current reserves unknown</option><option value="reported_depleted">Reported depleted</option></select></label>
            </div>
            <label>Rigs observed at this deposit (optional)<input name="rigs_observed" type="number" min="0" max="6" step="1"></label>
            <label>What did you verify?<textarea name="evidence" maxlength="1200" rows="3" required placeholder="Visit date, mineral found, rigs actually placed, or source and what remains untested"></textarea></label>
            <p class="note">Saved for your commander. Include what you actually observed; saving coordinates alone does not confirm a deposit.</p>
            <div class="row"><button class="primary" type="submit">Save report</button><button type="button" data-rhino-report-cancel>Cancel</button></div>
          </form>
          <form data-rhino-circuit-form class="rhino-form" hidden>
            <h3 data-rhino-circuit-title>Report a circuit</h3><input name="id" type="hidden">
            <div class="grid2"><label>Deposits in this circuit<input name="reported_deposits" type="number" min="1" max="100" required></label>
              <label>Rigs total across the circuit<input name="rigs_observed_total" type="number" min="0" max="600" required></label></div>
            <label>What did you observe?<textarea name="evidence" rows="3" maxlength="1200" required></textarea></label>
            <p class="note">A dated report across these deposits. Individual coordinates and rig observations stay separate.</p>
            <div class="row"><button type="submit" class="primary">Save circuit report</button><button type="button" data-rhino-circuit-cancel>Cancel</button></div>
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
        try { await Lab.post(path, {...body, commander_key: Lab.state.rhino?.summary?.commander_key || ''}); if (el.isConnected) message(success); }
        catch (error) { if (el.isConnected) message(error.message || String(error), true); }
      };
      let guideLoaded = false, guidePending = false, requestedTopic = null;
      const revealTopic = () => {
        if (!requestedTopic) return;
        const node = [...el.querySelectorAll('[data-rhino-topic]')].find(n => n.dataset.rhinoTopic === requestedTopic);
        if (!node) return;
        node.open = true; node.scrollIntoView({block:'nearest'}); node.querySelector('summary').focus(); requestedTopic = null;
      };
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
          revealTopic();
        } catch (error) {
          if (el.isConnected) target.innerHTML = `<p role="alert">${esc(error.message || String(error))}</p><button data-rhino-retry>Retry guide</button>`;
        } finally { guidePending = false; }
      };
      const form = el.querySelector('[data-rhino-site-form]');
      const reportForm = el.querySelector('[data-rhino-report-form]');
      const circuitForm = el.querySelector('[data-rhino-circuit-form]');
      const freshForm = () => {
        reportForm.hidden = true; circuitForm.hidden = true;
        form._rhinoCommander = Lab.state.rhino?.summary?.commander_key || '';
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
        if (button.dataset.rhinoTabOpen) tab(button.dataset.rhinoTabOpen);
        if (button.dataset.rhinoHelpTopic) {
          requestedTopic = button.dataset.rhinoHelpTopic; tab('guide'); if (guideLoaded) revealTopic();
        }
        if (button.hasAttribute('data-rhino-retry')) loadGuide();
        const state = Lab.state.rhino?.summary || {};
        if (button.hasAttribute('data-rhino-circuit-cancel')) circuitForm.hidden = true;
        if (button.dataset.rhinoCircuitReport) {
          const group = state.groups?.find(g => g.id === button.dataset.rhinoCircuitReport);
          if (group) {
            form.hidden = true; reportForm.hidden = true; circuitForm.reset(); circuitForm.hidden = false;
            circuitForm._rhinoCommander = state.commander_key || '';
            for (const key of ['id', 'reported_deposits', 'rigs_observed_total', 'evidence']) circuitForm.elements[key].value = group[key] ?? '';
            el.querySelector('[data-rhino-circuit-title]').textContent = `${group.body} / PML ${group.pml}`;
            circuitForm.elements.reported_deposits.focus();
          }
        }
        if (button.dataset.rhinoAddDeposit) {
          const group = state.groups?.find(g => g.id === button.dataset.rhinoAddDeposit);
          if (group) {
            freshForm();
            for (const key of ['system', 'body', 'pml']) form.elements[key].value = group[key] ?? '';
            const first = state.sites?.find(s => group.site_ids.includes(s.id));
            form.elements.commodity.value = first?.commodity || 'Tritium';
            form.elements.name.value = `PML ${group.pml} / deposit ${group.mapped_deposits + 1}`;
            message('Use current position when at the next deposit, then save.');
            form.elements.name.focus();
          }
        }
        if (button.hasAttribute('data-rhino-new')) { freshForm(); form.elements.name.focus(); }
        if (button.hasAttribute('data-rhino-save-here')) {
          tab('spots'); freshForm(); el.querySelector('[data-rhino-capture]').click(); form.elements.name.focus();
        }
        if (button.hasAttribute('data-rhino-cancel')) form.hidden = true;
        if (button.hasAttribute('data-rhino-report-cancel')) reportForm.hidden = true;
        if (button.dataset.rhinoConfirm) {
          const site = state.sites?.find(s => s.id === button.dataset.rhinoConfirm);
          if (site && site.verification !== 'confirmed') {
            button.disabled = true;
            action('/api/rhino/sites/confirm', {id: site.id}, 'Location confirmed. You can add details or change its status in Evidence and notes.')
              .finally(() => { button.disabled = false; });
          }
        }
        if (button.dataset.rhinoReport) {
          const site = state.sites?.find(s => s.id === button.dataset.rhinoReport);
          if (site) {
            form.hidden = true; circuitForm.hidden = true; reportForm.reset(); reportForm.hidden = false;
            reportForm._rhinoCommander = state.commander_key || '';
            for (const key of ['id', 'verification', 'availability']) reportForm.elements[key].value = site[key];
            reportForm.elements.evidence.value = site.personal_report ? site.evidence : '';
            reportForm.elements.rigs_observed.value = site.personal_rigs_observed ?? '';
            el.querySelector('[data-rhino-report-title]').textContent = `Report: ${site.name}`;
            reportForm.elements.evidence.focus();
          }
        }
        if (button.hasAttribute('data-rhino-capture')) {
          const p = state.position;
          if (!recent(p)) { message('Approach a body and wait for recent surface coordinates.', true); return; }
          if (form.elements.system.value.toLowerCase() !== p.system.toLowerCase() ||
              form.elements.body.value.toLowerCase() !== p.body.toLowerCase()) form.elements.pml.value = '';
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
        const body = {...Object.fromEntries(new FormData(form)), commander_key: form._rhinoCommander};
        for (const key of ['latitude', 'longitude']) body[key] = Number(body[key]);
        if (body.radius_m) body.radius_m = Number(body.radius_m); else delete body.radius_m;
        if (!body.id) delete body.id;
        body.pml = body.pml ? Number(body.pml) : null;
        const submit = form.querySelector('[type=submit]'); submit.disabled = true;
        try {
          const result = await Lab.post('/api/rhino/sites/save', body);
          if (el.isConnected) { form.elements.id.value = result.id; form.hidden = true; message('Spot saved and selected.'); }
        } catch (error) { if (el.isConnected) message(error.message || String(error), true); }
        finally { submit.disabled = false; }
      });
      reportForm.addEventListener('submit', async event => {
        event.preventDefault();
        const submit = reportForm.querySelector('[type=submit]'); submit.disabled = true;
        try {
          const body = {...Object.fromEntries(new FormData(reportForm)), commander_key: reportForm._rhinoCommander};
          body.rigs_observed = body.rigs_observed === '' ? null : Number(body.rigs_observed);
          await Lab.post('/api/rhino/sites/report', body);
          if (el.isConnected) { reportForm.hidden = true; message('Location report saved for your commander.'); }
        } catch (error) { if (el.isConnected) message(error.message || String(error), true); }
        finally { submit.disabled = false; }
      });
      circuitForm.addEventListener('submit', async event => {
        event.preventDefault();
        const submit = circuitForm.querySelector('[type=submit]'); submit.disabled = true;
        const body = {...Object.fromEntries(new FormData(circuitForm)), commander_key: circuitForm._rhinoCommander};
        for (const key of ['reported_deposits', 'rigs_observed_total']) body[key] = Number(body[key]);
        try {
          await Lab.post('/api/rhino/groups/report', body);
          if (el.isConnected) { circuitForm.hidden = true; message('Circuit report saved.'); }
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
        ${trip(site, recent(position), true)}
        <div>${esc(place(site))}</div><div class="rhino-coords">${coord(site.latitude)}, ${coord(site.longitude)} <button class="mini" data-copy="${esc(site.system)} | ${esc(site.body)} | ${coord(site.latitude)}, ${coord(site.longitude)}">Copy location</button></div>
        <div class="rhino-badges">${badges(site)}</div>
        ${site.travel?.stage === 'surface' ? `<div class="note">${esc(nav.reason || '')}</div>` : ''}
      </div>` : '<div class="rhino-navigation"><strong>Find your next worthwhile spot</strong><p class="muted">Choose a saved location for directions, or save what you find here.</p></div>';
      const run = r.session, total = run?.total_t || 0, points = run?.points || [];
      const elapsed = Math.max(1, run?.elapsed_seconds || 0), top = Math.max(1, total);
      let previousY = 76;
      const line = ['0,76', ...points.map(p => {
        const x = Math.min(400, p.seconds / elapsed * 400).toFixed(1), y = (76 - p.tonnes / top * 68).toFixed(1);
        const step = `${x},${previousY} ${x},${y}`; previousY = y; return step;
      }), `400,${previousY}`].join(' ');
      const haul = el.querySelector('[data-rhino-haul]'), signatureHaul = JSON.stringify(run);
      if (haul.dataset.signature !== signatureHaul) {
        const detailOpen = haul.querySelector('details')?.open;
        haul.innerHTML = `<section class="rhino-haul">
          <div class="rhino-toolbar"><span>${run?.active ? 'This deployment' : run ? 'Last deployment' : 'Ready for a mining run'}</span><span class="note">${run?.partial ? 'Observed since login' : run?.active ? 'Tracking collections' : run ? 'Completed' : 'Starts when you launch the Rhino'}</span></div>
          <div class="rhino-yield"><strong>${fmt(total)}</strong><span>t refined</span></div>
          <div class="rhino-breakdown">${run?.commodities?.length ? run.commodities.map(c => `<span>${esc(c.name)} <b>${fmt(c.tonnes)} t</b></span>`).join('') : '<span class="muted">Your first collection will appear here.</span>'}</div>
          <svg class="rhino-chart" viewBox="0 0 400 82" preserveAspectRatio="none" role="img" aria-label="Cumulative refined cargo this deployment: ${total} tonnes"><path d="M0 76 H400" class="rhino-chart-grid"/><polygon points="${line} 400,82 0,82"/><polyline points="${line}"/></svg>
          <div class="note">Collected cargo over this deployment. Rigs still working in the ground are not measured.</div>
          ${run ? `<details ${detailOpen ? 'open' : ''}><summary>Run details &middot; ${fmt(run.unloaded_t)} t unloaded</summary>
            <p>${fmt(run.unloads)} unload${run.unloads === 1 ? '' : 's'} &middot; ${Math.floor(elapsed / 60)} min observed${run.average_tph != null ? ` &middot; ${fmt(run.average_tph)} t/h average` : ''}</p>
            <p class="note">Average includes setup, driving and idle time through the latest recorded event. Transfers do not reset the collection total.</p>
            ${run.last_collection ? `<p class="note">Latest receipt: ${esc(run.last_collection.name)} at ${esc(new Date(run.last_collection.timestamp).toLocaleTimeString())}</p>` : ''}</details>` : ''}
        </section>`;
        haul.dataset.signature = signatureHaul;
      }
      el.querySelector('[data-rhino-holds]').innerHTML = ['rhino','ship'].map(key => {
        const h = r.cargo?.[key] || {}, known = h.count != null && h.capacity != null, percentage = known ? Math.min(100, 100*h.count/Math.max(1,h.capacity)) : 0;
        return `<div class="rhino-hold"><div class="rhino-toolbar"><strong>${key === 'rhino' ? 'Rhino hold' : 'Ship hold'}</strong><span>${h.count == null ? 'Unknown' : `${fmt(h.count)} t`}${h.capacity != null ? ` / ${fmt(h.capacity)} t` : ''}</span></div>
          <div class="rhino-hold-bar" role="img" aria-label="${key} hold ${known ? `${Math.round(percentage)} percent full` : 'capacity unknown'}"><span style="width:${percentage}%"></span></div>
          <div class="note">${h.free != null ? `${fmt(h.free)} t free at last report` : 'Waiting for cargo report'}</div></div>`;
      }).join('');
      const gear = r.equipment || {}, lowSpace = r.cargo?.rhino?.free != null && r.cargo.rhino.free < 12;
      let help = run?.active ? ['unloading', 'Keep the circuit running', 'Transfer cargo under the ship\'s bay without boarding. Leave the rigs deployed between collections.'] : ['equipment', 'Before the next trip', 'Check the Rhino is fitted, then confirm the scanner and hangar before leaving outfitting.'];
      if (run?.active && lowSpace) help = ['unloading', 'Make room before the next collection', 'Your last Rhino cargo report had less than 12 t free. Check space and transfer to the ship.'];
      if (!run?.active && (gear.dss === false || gear.large_hangar === false)) help = ['equipment', 'Check your fitted modules', `${gear.dss === false ? 'No Detailed Surface Scanner in the last loadout. ' : ''}${gear.large_hangar === false ? 'No Large Planetary Vehicle Hangar in the last loadout.' : ''}`];
      el.querySelector('[data-rhino-help]').innerHTML = `<strong>${esc(help[1])}</strong><p>${esc(help[2])}</p><button class="mini" data-rhino-help-topic="${help[0]}">Show steps</button><button class="mini" data-rhino-help-topic="troubleshooting">Rig stopped / depleted?</button>`;
      const list = el.querySelector('[data-rhino-site-list]');
      const signature = JSON.stringify([(r.sites || []).map(({travel, ...s}) => s), r.groups, site?.id]);
      // Position updates must not close notes, move focus or erase a form draft.
      if (list.dataset.signature !== signature) {
        const opened = new Set([...list.querySelectorAll('details[open]')].map(d => d.dataset.siteNotes));
        const renderSite = s => `<article class="rhino-site" data-verification="${esc(s.verification)}">
          <div class="rhino-toolbar"><strong>${esc(s.name)}</strong><button class="mini" data-rhino-select="${esc(s.id)}" ${s.id === site?.id ? 'disabled' : ''}>${s.id === site?.id ? 'Selected' : 'Navigate'}</button></div>
          <div data-rhino-travel="${esc(s.id)}">${trip(s, recent(position))}</div>
          <div class="rhino-coords">${coord(s.latitude)}, ${coord(s.longitude)} <button class="mini" data-copy="${esc(s.system)} | ${esc(s.body)} | ${coord(s.latitude)}, ${coord(s.longitude)}">Copy location</button></div>
          <div class="rhino-badges">${badges(s)}${s.verification !== 'confirmed' ? `<button class="mini" data-rhino-confirm="${esc(s.id)}" title="Confirm that you visited and verified this location in game">Mark confirmed</button>` : ''}</div>
          <div class="note">${esc(s.commodity)}${rigEvidence(s) ? ` &middot; ${esc(rigEvidence(s))}` : ''}</div>
          <details data-site-notes="${esc(s.id)}" ${opened.has(s.id) ? 'open' : ''}><summary>Evidence and notes${s.personal_report ? ' / your report' : ''}</summary>
            <p>${esc(s.evidence || '')}</p><div class="note">Recorded ${esc((s.reported_at || '').slice(0, 10))}; current reserves are not measured.</div>
            ${s.confirmed_at ? `<div class="note">Visit confirmed ${esc(s.confirmed_at.slice(0, 10))}.</div>` : ''}
            ${s.reference_rigs_observed != null ? `<p class="note">Original observation: ${esc(s.reference_rigs_observed)} rigs.</p>` : ''}
            ${s.reference_evidence ? `<p class="note">Original evidence: ${esc(s.reference_evidence)}</p>` : ''}
            ${s.notes ? `<p>${esc(s.notes)}</p>` : ''}
            ${(s.sources || []).filter(source => /^https:\/\//.test(source.url)).map(source => `<p><a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.title)}</a></p>`).join('')}
            <div class="row"><button class="mini" data-rhino-report="${esc(s.id)}">Update report</button>${s.reference ? '' : `<button class="mini" data-rhino-edit="${esc(s.id)}">Edit</button><button class="mini" data-rhino-remove="${esc(s.id)}">Remove</button>`}</div>
          </details>
        </article>`;
        const renderGroup = g => {
          const deposits = (r.sites || []).filter(s => g.site_ids.includes(s.id));
          return `<section class="rhino-pml" data-rhino-pml="${esc(g.id)}">
            <h4>${esc(place(g))}${g.pml ? ` &middot; PML ${esc(g.pml)}` : ''}</h4>
            <div class="note">${g.reported_deposits != null ? `${fmt(g.reported_deposits)} deposits reported &middot; ` : ''}${fmt(g.mapped_deposits)} mapped &middot; ${fmt(g.confirmed_deposits)} confirmed</div>
            ${g.rigs_observed_total != null ? `<p><strong>${fmt(g.rigs_observed_total)} rigs total across the circuit</strong> <span class="note">(your report, ${esc(g.reported_at.slice(0,10))})</span></p>` : ''}
            ${g.unmapped_deposits ? `<p class="note">${fmt(g.unmapped_deposits)} deposit coordinates still to capture.</p>` : ''}
            ${deposits.map(renderSite).join('')}
            ${g.pml ? `<details data-site-notes="group-${esc(g.id)}" ${opened.has('group-' + g.id) ? 'open' : ''}><summary>Circuit notes and actions</summary>
              ${g.evidence ? `<p>${esc(g.evidence)}</p>` : '<p class="note">Record the circuit total after checking the deposits.</p>'}
              <div class="row"><button class="mini" data-rhino-add-deposit="${esc(g.id)}">Add deposit here</button><button class="mini" data-rhino-circuit-report="${esc(g.id)}">Report circuit</button></div>
            </details>` : ''}
          </section>`;
        };
        list.innerHTML = '<div class="rhino-catalog-grid">' + ['confirmed', 'unconfirmed'].map(status => {
          const groups = (r.groups || []).filter(g => (g.confirmed_deposits > 0) === (status === 'confirmed'))
            .sort((a, b) => Number(b.site_ids.includes(site?.id)) - Number(a.site_ids.includes(site?.id)));
          return `<section data-rhino-group="${status}" class="rhino-location-group"><h3>${status === 'confirmed' ? 'Visited locations' : 'Unconfirmed locations'} <span class="note">${groups.length}</span></h3><p class="note">${status === 'confirmed' ? 'At least one confirmed deposit; check each deposit below.' : 'Research leads and bookmarks awaiting a visit.'}</p><div class="rhino-locations">${groups.map(renderGroup).join('') || '<p class="muted">No locations yet.</p>'}</div></section>`;
        }).join('') + '</div>';
        list.dataset.signature = signature;
      }
      // Telemetry changes only the distance line, preserving open notes and focus.
      list.querySelectorAll('[data-rhino-travel]').forEach(node => {
        const entry = r.sites?.find(s => s.id === node.dataset.rhinoTravel);
        if (!entry) return;
        const html = trip(entry, recent(position));
        if (node.innerHTML !== html) node.innerHTML = html;
      });
    },
  });
})();
