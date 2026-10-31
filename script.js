const speech = document.querySelector('#professor-speech');
const scene = document.querySelector('#professor-scene');
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const phrases = [
  'Bonjour ! Moi, c’est Mr Camembert.',
  'On regarde le contenu qualitatif du jour ensemble ?',
  'Un petit texte, une fiche PDF. À vous de jouer !',
  'Une question ? Je vous écoute.'
];
let speechTimer;
let phraseIndex = 0;
let animationPaused = reduceMotion.matches;
let chatInteracting = false;
function speakAnimation() {
  clearTimeout(speechTimer);
  if (animationPaused || document.hidden || chatInteracting) { scene.classList.remove('is-speaking'); return; }
  const phrase = phrases[phraseIndex++ % phrases.length];
  scene.classList.add('is-speaking');
  let cursor = 0;
  const type = () => {
    if (animationPaused || document.hidden || chatInteracting) return;
    speech.textContent = phrase.slice(0, ++cursor);
    if (cursor < phrase.length) speechTimer = setTimeout(type, 44);
    else { scene.classList.remove('is-speaking');  }
  };
  type();
}
function setPause(paused) {
  animationPaused = paused;
  clearTimeout(speechTimer);
  document.body.classList.toggle('animations-paused', paused);
  if (paused) { scene.classList.remove('is-speaking'); speech.textContent = phrases[0]; }
  else speakAnimation();
}
reduceMotion.addEventListener('change', event => setPause(event.matches));
document.addEventListener('visibilitychange', () => {
  clearTimeout(speechTimer);
  if (document.hidden) { scene.classList.remove('is-speaking'); }
  else if (!animationPaused) speakAnimation();
});
setPause(animationPaused);

function parisDateOffset(offset) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Paris', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map(p => [p.type, p.value]));
  const date = new Date(Date.UTC(Number(values.year), Number(values.month) - 1, Number(values.day) + offset));
  return date.toISOString().slice(0, 10);
}
function displayDate(date) {
  return new Intl.DateTimeFormat('fr-FR', { dateStyle: 'long', timeZone: 'UTC' }).format(new Date(`${date}T12:00:00Z`));
}
const editions = {};
async function loadEdition(id, offset) {
  const card = document.getElementById(id);
  const day = parisDateOffset(offset - 1);
  const edition = parisDateOffset(offset);
  card.querySelector('[data-date]').textContent = `Édition du ${displayDate(edition)} · Journée analysée : ${displayDate(day)}`;
  const status = card.querySelector('[data-status]');
  try {
    const path = `reports/${day}`;
    const response = await fetch(`${path}/report.json`, { cache: 'no-store' });
    if (response.status === 404) { status.textContent = 'Cette édition n’est pas encore disponible. Aucun ancien point n’est présenté à sa place.'; return; }
    if (!response.ok) throw new Error('report');
    const report = await response.json();
    if (report.date !== day) throw new Error('date');
    const text = report.summary || report.text;
    if (typeof text !== 'string' || !text.trim() || text.trim().split(/\s+/u).length >= 50) {
      status.textContent = 'La synthèse courte de cette édition doit être régénérée.';
      return;
    }
    const paragraph = card.querySelector('[data-text]');
    paragraph.textContent = text;
    paragraph.hidden = false;
    status.textContent = 'Brouillon · À relire avant publication';
    editions[id] = report;
    card.querySelector('[data-copy]').disabled = false;
    card.querySelector('[data-evidence]').hidden = false;
    card.querySelector('[data-evidence]').href = `${path}/report.json`;
    card.querySelector('[data-copy]').addEventListener('click', async event => {
      try { await navigator.clipboard.writeText(text); event.target.textContent = 'Texte copié'; }
      catch { status.textContent = 'Sélectionnez le texte ci-dessus pour le copier.'; }
    });
    try {
      const pdf = await fetch(`${path}/fiche.pdf`, { method: 'HEAD' });
      if (pdf.ok) {
        const link = card.querySelector('[data-pdf]'); link.href = `${path}/fiche.pdf`; link.removeAttribute('aria-disabled'); link.setAttribute('download', '');
        card.querySelector('[data-analysis-title]').textContent = 'Le point de marché, en profondeur';
        card.querySelector('[data-analysis-status]').textContent = 'Deux pages : graphique des actifs, analyse, schéma et sources.';
      } else card.querySelector('[data-analysis-status]').textContent = 'Le PDF est momentanément indisponible.';
    } catch { card.querySelector('[data-analysis-status]').textContent = 'Le PDF est momentanément indisponible.'; }

  } catch { status.textContent = 'Cette édition est momentanément indisponible. Réessayez plus tard.'; }
}
let universe;
let universePromise;
let visibleAssets = 50;
async function fetchUniverse() {
  if (!universePromise) universePromise = fetch('data/universe.json').then(async response => {
    if (!response.ok) throw new Error('universe');
    const data = await response.json();
    if (!Array.isArray(data.assets) || data.assets.length !== data.total) throw new Error('format');
    universe = data;
    document.querySelector('#universe-summary').textContent = `${data.total.toLocaleString('fr-FR')} actifs · ${data.markets.length} places européennes`;
    return data;
  }).catch(error => { universePromise = undefined; throw error; });
  return universePromise;
}
async function loadUniverse() {
  try {
    const data = await fetchUniverse();
    document.querySelector('#universe-count').textContent = `${data.total.toLocaleString('fr-FR')} actifs autorisés, sur ${data.markets.length} places européennes. Tous font partie du périmètre du point quotidien.`;
    const select = document.querySelector('#market-filter');
    if (select.options.length === 1) for (const market of data.markets) { const option = document.createElement('option'); option.value = market; option.textContent = market; select.append(option); }
    renderAssets();
  } catch { document.querySelector('#universe-count').textContent = 'L’univers est momentanément indisponible. Réessayez plus tard.'; }
}
function renderAssets() {
  if (!universe) return;
  const query = document.querySelector('#asset-search').value.trim().toLocaleLowerCase('fr');
  const market = document.querySelector('#market-filter').value;
  const filtered = universe.assets.filter(asset => (!market || asset.market === market) && (!query || [asset.name, asset.ticker, asset.sector].some(value => value.toLocaleLowerCase('fr').includes(query))));
  const body = document.querySelector('#assets-body');
  body.replaceChildren();
  for (const asset of filtered.slice(0, visibleAssets)) {
    const row = document.createElement('tr');
    for (const field of ['name', 'ticker', 'market', 'asset_class']) { const cell = document.createElement('td'); cell.textContent = asset[field]; row.append(cell); }
    body.append(row);
  }
  document.querySelector('#results-status').textContent = `${filtered.length.toLocaleString('fr-FR')} résultat${filtered.length === 1 ? '' : 's'} · ${Math.min(filtered.length, visibleAssets)} affichés`;
  document.querySelector('#load-more').hidden = visibleAssets >= filtered.length;
}
for (const id of ['asset-search', 'market-filter']) document.getElementById(id).addEventListener('input', () => { visibleAssets = 50; renderAssets(); });
document.querySelector('#load-more').addEventListener('click', () => { visibleAssets += 50; renderAssets(); });
loadEdition('today-edition', 0);
loadEdition('previous-edition', -1);
loadUniverse();

for (const button of document.querySelectorAll('[data-reply]')) {
  button.addEventListener('click', () => {
    clearTimeout(speechTimer);
    chatInteracting = true;
    scene.classList.remove('is-speaking');
    const report = editions['today-edition'];
    let answer;
    if (button.dataset.reply === 'explain') {
      answer = report ? `${report.summary || report.text} Les actifs sont choisis parmi les secteurs associés au thème et leurs variations marquées : c’est un échantillon, pas un indice de marché.` : 'Le point du jour n’est pas encore disponible. Je préfère attendre des données vérifiées avant de commenter les marchés.';
    } else if (button.dataset.reply === 'pdf') {
      answer = 'Commencez par le résumé et le graphique des trois actifs. La seconde page approfondit une information sourcée : mécanisme possible, points à vérifier et limites. Les variations ne prouvent pas que cette information les a causées.';
    } else if (button.dataset.reply === 'assets') {
      answer = 'L’univers est juste à gauche, sous les deux éditions. Recherchez un nom ou un ticker, puis filtrez par place. Ces actifs sont autorisés sur Nextwise : cela ne signifie pas que le club les détient.';
      document.querySelector('#asset-search').focus({ preventScroll: true });
      document.querySelector('#universe').scrollIntoView({ behavior: reduceMotion.matches ? 'instant' : 'smooth', block: 'start' });
    } else {
      answer = report?.analysis?.theme ? report.analysis.theme.confirm + ' ' + report.analysis.theme.challenge : 'Vérifiez la date du point, les sources et la disponibilité des cours. Une variation entre deux clôtures n’est pas une cotation en direct. Un lien entre une annonce et un prix reste une hypothèse à vérifier.';
    }
    speech.textContent = 'Regardons cela ensemble.';
    document.querySelector('#camembert-answer').textContent = answer;
    for (const option of document.querySelectorAll('[data-reply]')) option.setAttribute('aria-pressed', String(option === button));
  });
}
