/* One catalog and launcher for every workspace. Opening a HUD is always a click. */
let catalog = [];
const ready = fetch('/hud-modes.json').then(response => {
  if (!response.ok) throw Error('HUD activities could not load.');
  return response.json();
}).then(rows => { catalog = rows; return rows; });
ready.catch(() => {});

export function hudUri(mode = '') {
  if (mode && !catalog.some(row => row.id === mode)) throw Error('Unknown HUD activity');
  return 'elitelab-hud:open' + (mode ? '?mode=' + encodeURIComponent(mode) : '');
}

export function initHud(toast) {
  const select = document.getElementById('hud-activity');
  const link = document.getElementById('hud-open');
  if (!select || !link) return;
  ready.then(rows => {
    const groups = new Map();
    for (const row of rows) {
      if (!groups.has(row.group)) {
        const group = document.createElement('optgroup'); group.label = row.group;
        groups.set(row.group, group); select.append(group);
      }
      const option = document.createElement('option'); option.value = row.id; option.textContent = row.label;
      groups.get(row.group).append(option);
    }
    // A page refresh leaves the running HUD's selected mode alone.
    select.disabled = false;
  }).catch(error => toast(error.message, 'bad'));
  select.addEventListener('change', () => { link.href = hudUri(select.value); });
  link.addEventListener('click', () => toast('Allow EliteLab HUD to open if asked. The desktop shortcut also opens or recovers it.'));
}

export function addHudButton(card) {
  ready.then(rows => {
    if (!card.isConnected || card.querySelector('[data-hud-mode]')) return;
    const mode = rows.find(row => row.cards.includes(card.dataset.id));
    if (!mode) return;
    const link = document.createElement('a');
    link.className = 'mini hud-card-launch'; link.dataset.hudMode = mode.id;
    link.href = hudUri(mode.id); link.textContent = 'HUD';
    link.title = 'Open ' + mode.label + ' in the transparent Windows HUD';
    link.setAttribute('aria-label', link.title);
    card.querySelector('h2 .tools').before(link);
  }).catch(() => {});
}
