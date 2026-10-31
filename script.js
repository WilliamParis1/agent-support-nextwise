const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const scene = document.querySelector('#professor-scene');
const speech = document.querySelector('#professor-speech');
let animationTimer;
function tell(text, note = '') {
  speech.textContent = text;
  document.querySelector('#interaction-note').textContent = note;
  clearTimeout(animationTimer);
  scene.classList.remove('is-speaking');
  if (!reduceMotion.matches && !document.hidden) {
    void scene.offsetWidth;
    scene.classList.add('is-speaking');
    animationTimer = setTimeout(() => scene.classList.remove('is-speaking'), 3500);
  }
}
reduceMotion.addEventListener('change', () => scene.classList.remove('is-speaking'));
document.addEventListener('visibilitychange', () => { if (document.hidden) scene.classList.remove('is-speaking'); });
tell(speech.textContent);

function parisToday() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Paris', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}
function shiftDate(iso, offset) {
  const date = new Date(`${iso}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
}
function formatDate(iso, options = {}) {
  return new Intl.DateTimeFormat('fr-FR', { timeZone: 'Europe/Paris', day: 'numeric', month: 'long', ...options }).format(new Date(`${iso}T12:00:00Z`));
}
const today = parisToday();
document.querySelector('#current-date').textContent = formatDate(today, { weekday: 'long' });
const editions = {
  today: { publication: today, session: shiftDate(today, -1), report: null },
  yesterday: { publication: shiftDate(today, -1), session: shiftDate(today, -2), report: null }
};
let selectedEdition = 'today';
for (const [key, edition] of Object.entries(editions)) {
  document.getElementById(`${key}-date`).textContent = formatDate(edition.publication, { month: 'short' });
  document.getElementById(`${key}-session`).textContent = `Séance analysée : ${formatDate(edition.session)}`;
  document.getElementById(`${key}-pdf`).addEventListener('click', event => {
    if (!edition.report) event.preventDefault();
  });
  document.getElementById(`${key}-copy`).addEventListener('click', async event => {
    if (!edition.report) return;
    const button = event.currentTarget;
    try {
      await navigator.clipboard.writeText(edition.report.text);
      button.querySelector('span').textContent = 'Copié';
      setTimeout(() => { button.querySelector('span').textContent = 'Copier'; }, 2200);
    } catch {
      const range = document.createRange();
      range.selectNodeContents(document.getElementById(`${key}-text`));
      const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
      document.getElementById(`${key}-status`).textContent = 'Texte sélectionné : utilisez Copier dans votre navigateur.';
    }
  });
}
async function loadEdition(key) {
  const edition = editions[key];
  const text = document.getElementById(`${key}-text`);
  const status = document.getElementById(`${key}-status`);
  try {
    const response = await fetch(`reports/${edition.session}/report.json`, { cache: 'no-store' });
    if (!response.ok) throw new Error('missing');
    const report = await response.json();
    const words = typeof report.text === 'string' ? report.text.trim().split(/\s+/).length : 0;
    if (report.schema_version !== 2 || report.date !== edition.session || report.publication_date !== edition.publication || words < 1 || words >= 50 || !report.analysis) throw new Error('invalid');
    // A dated text never enables a broken PDF link.
    const pdf = await fetch(`reports/${edition.session}/fiche.pdf`, { method: 'HEAD', cache: 'no-store' });
    if (!pdf.ok) throw new Error('missing-pdf');
    edition.report = report;
    text.textContent = report.text;
    text.classList.remove('pending');
    status.textContent = `${words} mots · Analyse sourcée à relire`;
    const download = document.getElementById(`${key}-pdf`);
    download.href = `reports/${edition.session}/fiche.pdf`;
    download.download = `Synapse-Capital-${edition.publication}.pdf`;
    download.setAttribute('aria-disabled', 'false');
    document.getElementById(`${key}-copy`).disabled = false;
  } catch {
    text.textContent = key === 'today' ? 'Le contenu d’aujourd’hui attend encore des données vérifiées. Le texte et son analyse apparaîtront ici dès qu’ils seront prêts.' : 'La publication de cette date n’est pas disponible. Elle sera affichée ici avec son texte et son PDF dès sa génération.';
    text.classList.add('pending');
    status.textContent = 'Publication indisponible pour cette date';
  }
}
function safeLink(url) {
  try { return new URL(url).protocol === 'https:'; } catch { return false; }
}
function renderSources() {
  const container = document.querySelector('#source-list');
  container.replaceChildren();
  for (const edition of Object.values(editions)) {
    if (!edition.report) continue;
    const heading = document.createElement('h3');
    heading.textContent = `Édition du ${formatDate(edition.publication)}`;
    const list = document.createElement('ul');
    const focus = edition.report.analysis.focus;
    const sources = focus ? [{ label: `${focus.source} — ${focus.title}`, url: focus.url }] : [];
    for (const asset of edition.report.analysis.featured || []) sources.push({ label: `${asset.name || asset.symbol} — cours de la séance du ${formatDate(edition.session)}`, url: asset.source_url });
    for (const source of sources) {
      if (!safeLink(source.url)) continue;
      const item = document.createElement('li'); const link = document.createElement('a');
      link.textContent = source.label; link.href = source.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
      item.append(link); list.append(item);
    }
    const details = document.createElement('a'); details.textContent = 'Toutes les données de cette édition'; details.href = `reports/${edition.session}/report.json`; details.download = '';
    container.append(heading, list, details);
  }
  if (!container.childElementCount) {
    const paragraph = document.createElement('p'); paragraph.textContent = 'Les références de chaque édition apparaîtront ici dès que son contenu sera disponible.'; container.append(paragraph);
  }
}
Promise.allSettled([loadEdition('today'), loadEdition('yesterday')]).then(renderSources);

function navigateTo(id) {
  const target = document.getElementById(id);
  if (id === 'sources') target.open = true;
  target.scrollIntoView({ behavior: reduceMotion.matches ? 'instant' : 'smooth', block: 'start' });
  if (target.matches('[tabindex]')) target.focus({ preventScroll: true });
  document.querySelectorAll('.nav-action').forEach(button => button.classList.toggle('active', button.dataset.target === id));
  if (id === 'today-card') selectedEdition = 'today';
  if (id === 'yesterday-card') selectedEdition = 'yesterday';
}
for (const button of document.querySelectorAll('[data-target]')) button.addEventListener('click', () => navigateTo(button.dataset.target));
for (const button of document.querySelectorAll('[data-reply]')) button.addEventListener('click', () => {
  document.querySelectorAll('[data-reply]').forEach(item => item.classList.toggle('selected', item === button));
  const action = button.dataset.reply;
  if (action === 'explain') selectedEdition = 'today';
  if (action === 'previous') selectedEdition = 'yesterday';
  const edition = editions[selectedEdition];
  const report = edition.report;
  if (!report) {
    tell(`Le point du ${formatDate(edition.publication)} n’est pas encore disponible. En attendant, nous pouvons explorer ensemble les actifs de la compétition. Cliquez sur un nom dans le tableau.`, 'Je vous accompagne à partir des informations réellement disponibles.');
    return;
  }
  const note = `Édition du ${formatDate(edition.publication)} · Données du ${formatDate(edition.session)}`;
  if (action === 'risk') tell(report.analysis.theme.challenge, note);
  else if (action === 'assets') {
    const assets = report.analysis.featured || [];
    tell(assets.length ? assets.map(asset => `${asset.name || asset.symbol} (${asset.ticker || asset.symbol}) : ${asset.change_pct > 0 ? '+' : ''}${asset.change_pct.toFixed(2).replace('.', ',')} % à la clôture.`).join(' ') + ' Ce sont des exemples de l’univers autorisé ; ils ne décrivent pas nos positions.' : 'Aucune séance exploitable n’est associée à cette édition. Le PDF se concentre sur l’information macro datée.', note);
  } else {
    tell(report.analysis.theme.hypothesis, note + ' · Mécanisme possible, à confirmer');
  }
});

let universe;
let visibleAssets = 8;
let assetClass = '';
const sectors = { Tech: 'Technologie', Sant: 'Santé', Fin: 'Finance', Finance: 'Finance', Conso: 'Consommation', Ind: 'Industrie', Ener: 'Énergie', Autre: 'Autre' };
async function loadUniverse() {
  try {
    const response = await fetch('data/universe.json');
    if (!response.ok) throw new Error('universe');
    const data = await response.json();
    if (!Array.isArray(data.assets) || data.assets.length !== data.total) throw new Error('format');
    universe = data;
    document.querySelector('#universe-count').textContent = `${data.total.toLocaleString('fr-FR')} actifs · ${data.markets.length} places`;
    for (const market of data.markets) { const option = document.createElement('option'); option.value = market; option.textContent = market; document.querySelector('#market-filter').append(option); }
    renderAssets();
  } catch {
    document.querySelector('#universe-count').textContent = 'Chargement indisponible';
    const error = document.querySelector('#universe-error'); error.hidden = false; error.textContent = 'L’univers des actifs est momentanément indisponible. Réessayez après avoir rechargé la page.';
  }
}
function renderAssets() {
  if (!universe) return;
  const query = document.querySelector('#asset-search').value.trim().toLocaleLowerCase('fr');
  const market = document.querySelector('#market-filter').value;
  const filtered = universe.assets.filter(asset => (!assetClass || asset.asset_class === assetClass) && (!market || asset.market === market) && (!query || [asset.name, asset.ticker, sectors[asset.sector] || asset.sector].some(value => value.toLocaleLowerCase('fr').includes(query))));
  const body = document.querySelector('#assets-body'); body.replaceChildren();
  for (const asset of filtered.slice(0, visibleAssets)) {
    const row = document.createElement('tr');
    const first = document.createElement('td');
    const name = document.createElement('button'); name.type = 'button'; name.className = 'asset-name'; name.textContent = asset.name;
    name.setAttribute('aria-label', `Présenter ${asset.name} avec Mr Camembert`);
    name.addEventListener('click', () => {
      tell(`${asset.name} (${asset.ticker}) est ${asset.asset_class === 'ETF' ? 'un ETF' : 'une action'} coté${asset.asset_class === 'ETF' ? '' : 'e'} à ${asset.market}. Secteur indiqué : ${sectors[asset.sector] || asset.sector}. ${asset.description || 'Le CSV ne fournit pas de description détaillée pour cet actif.'}`, 'Fiche issue du CSV du club. L’appartenance à l’univers ne signifie pas que le club détient ce titre.');
      if (window.innerWidth <= 620) document.querySelector('.camembert-panel').scrollIntoView({ behavior: reduceMotion.matches ? 'instant' : 'smooth', block: 'start' });
    });
    first.append(name); row.append(first);
    for (const field of ['ticker', 'market']) { const cell = document.createElement('td'); cell.textContent = asset[field]; row.append(cell); }
    const typeCell = document.createElement('td'); const type = document.createElement('span'); type.className = 'asset-type'; type.textContent = asset.asset_class; typeCell.append(type); row.append(typeCell);
    body.append(row);
  }
  document.querySelector('#results-status').textContent = `${filtered.length.toLocaleString('fr-FR')} résultat${filtered.length === 1 ? '' : 's'}`;
  document.querySelector('#shown-assets').textContent = `${Math.min(visibleAssets, filtered.length)} sur ${filtered.length.toLocaleString('fr-FR')} actifs`;
  document.querySelector('#load-more').hidden = visibleAssets >= filtered.length;
}
for (const id of ['asset-search', 'market-filter']) document.getElementById(id).addEventListener('input', () => { visibleAssets = 8; renderAssets(); });
for (const button of document.querySelectorAll('[data-class]')) button.addEventListener('click', () => {
  assetClass = button.dataset.class; visibleAssets = 8;
  document.querySelectorAll('[data-class]').forEach(item => { item.classList.toggle('selected', item === button); item.setAttribute('aria-pressed', String(item === button)); });
  renderAssets();
});
document.querySelector('#load-more').addEventListener('click', () => { visibleAssets += 12; renderAssets(); });
loadUniverse();
