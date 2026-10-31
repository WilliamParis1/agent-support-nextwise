let lastSpokenReply = "";
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
let voiceOn = false;
let chatBusy = false;
let chatInteracting = false;
function speakAnimation() {
  clearTimeout(speechTimer);
  if (animationPaused || document.hidden || voiceOn || chatBusy || chatInteracting) { scene.classList.remove('is-speaking'); return; }
  const phrase = phrases[phraseIndex++ % phrases.length];
  scene.classList.add('is-speaking');
  let cursor = 0;
  const type = () => {
    if (animationPaused || document.hidden || voiceOn || chatBusy || chatInteracting) return;
    speech.textContent = phrase.slice(0, ++cursor);
    if (cursor < phrase.length) speechTimer = setTimeout(type, 44);
    else { scene.classList.remove('is-speaking'); speechTimer = setTimeout(speakAnimation, 4200); }
  };
  type();
}
function stopVoice() {
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  voiceOn = false;
  document.querySelector('#voice-toggle').setAttribute('aria-pressed', 'false');
  document.querySelector('#voice-label').textContent = 'Écouter';
  scene.classList.remove('is-speaking');
}
function setPause(paused) {
  animationPaused = paused;
  clearTimeout(speechTimer);
  document.body.classList.toggle('animations-paused', paused);
  document.querySelector('#animation-toggle').setAttribute('aria-pressed', String(paused));
  document.querySelector('#animation-toggle').textContent = paused ? 'Reprendre l’animation' : 'Mettre l’animation en pause';
  if (paused) { scene.classList.remove('is-speaking'); speech.textContent = phrases[0]; stopVoice(); }
  else speakAnimation();
}
document.querySelector('#animation-toggle').addEventListener('click', () => setPause(!animationPaused));
reduceMotion.addEventListener('change', event => setPause(event.matches));
document.addEventListener('visibilitychange', () => {
  clearTimeout(speechTimer);
  if (document.hidden) { stopVoice(); scene.classList.remove('is-speaking'); }
  else if (!animationPaused) speakAnimation();
});
const voiceButton = document.querySelector('#voice-toggle');
if (!('speechSynthesis' in window)) voiceButton.hidden = true;
voiceButton.addEventListener('click', () => {
  if (voiceOn) { stopVoice(); if (!animationPaused) speakAnimation(); return; }
  clearTimeout(speechTimer);
  voiceOn = true;
  voiceButton.setAttribute('aria-pressed', 'true');
  document.querySelector('#voice-label').textContent = 'Couper le son';
  const introduction = lastSpokenReply || 'Bonjour ! Moi, c’est Mr Camembert. Je vous aide à préparer le qualitatif sur Nextwise. Je relie les nouvelles de la veille aux mouvements des actifs autorisés. Chaque jour, je prépare un texte et une fiche PDF. Vous gardez la main sur la publication.';
  speech.textContent = lastSpokenReply ? 'Je vous explique…' : 'On regarde le contenu qualitatif du jour ensemble ?';
  const utterance = new SpeechSynthesisUtterance(introduction);
  utterance.lang = 'fr-FR'; utterance.rate = 0.95;
  const frenchVoice = speechSynthesis.getVoices().find(voice => voice.lang.startsWith('fr'));
  if (frenchVoice) utterance.voice = frenchVoice;
  utterance.onstart = () => { if (!animationPaused) scene.classList.add('is-speaking'); };
  utterance.onend = utterance.onerror = () => { stopVoice(); if (!animationPaused) speakAnimation(); };
  speechSynthesis.speak(utterance);
});
setPause(animationPaused);

for (const button of document.querySelectorAll('[data-open]')) button.addEventListener('click', () => {
  stopVoice();
  const dialog = document.getElementById(button.dataset.open);
  dialog.showModal();
  if (dialog.id === 'universe-dialog') loadUniverse();
});
for (const button of document.querySelectorAll('[data-close]')) button.addEventListener('click', () => button.closest('dialog').close());
for (const dialog of document.querySelectorAll('dialog')) dialog.addEventListener('click', event => {
  if (event.target !== dialog) return;
  const rect = dialog.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
});

function yesterdayInParis() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Paris', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map(p => [p.type, p.value]));
  const date = new Date(Date.UTC(Number(values.year), Number(values.month) - 1, Number(values.day)));
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}
async function loadBrief() {
  const status = document.querySelector('#brief-status');
  try {
    const response = await fetch('reports/latest.json', { cache: 'no-store' });
    if (!response.ok) throw new Error('manifest');
    const latest = await response.json();
    if (!latest.date) { status.textContent = 'Le premier point n’est pas encore disponible. Revenez après la première génération quotidienne.'; return; }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(latest.date) || latest.path !== `reports/${latest.date}`) throw new Error('path');
    const result = await fetch(`${latest.path}/report.json`, { cache: 'no-store' });
    if (!result.ok) throw new Error('report');
    const report = await result.json();
    if (report.date !== latest.date || typeof report.text !== 'string') throw new Error('format');
    status.textContent = report.date === yesterdayInParis() ? 'Brouillon de la veille — à relire avant publication.' : 'Ce dernier brouillon ne couvre pas la veille actuelle. Vérifiez sa date avant de le publier.';
    document.querySelector('#brief-date').textContent = `Journée analysée : ${report.date} · Heure de Paris`;
    document.querySelector('#brief-text').textContent = report.text;
    document.querySelector('#download-pdf').href = `${latest.path}/fiche.pdf`;
    document.querySelector('#download-evidence').href = `${latest.path}/report.json`;
    document.querySelector('#brief-content').hidden = false;
    document.querySelector('#copy-brief').addEventListener('click', async event => {
      try { await navigator.clipboard.writeText(report.text); event.target.textContent = 'Texte copié'; }
      catch { status.textContent = 'Sélectionnez le texte ci-dessus pour le copier : la copie automatique est indisponible.'; }
    });
  } catch { status.textContent = 'Le point est momentanément indisponible. Réessayez plus tard.'; }
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
loadBrief();
fetchUniverse().catch(() => {});

const history = [];
const chatForm = document.querySelector('#chat-form');
const chatInput = document.querySelector('#chat-input');
const chatStatus = document.querySelector('#chat-status');
function addMessage(role, content) {
  const article = document.createElement('div');
  article.className = `chat-message ${role}`;
  const author = document.createElement('span'); author.className = 'chat-author'; author.textContent = role === 'user' ? 'Vous' : 'Mr Camembert';
  const text = document.createElement('p'); text.textContent = content;
  article.append(author, text);
  document.querySelector('#chat-messages').append(article);
  article.scrollIntoView({ block: 'nearest', behavior: reduceMotion.matches ? 'instant' : 'smooth' });
  return article;
}
chatInput.addEventListener('focus', () => { document.querySelector('#chat-privacy').hidden = false; });
chatForm.addEventListener('submit', async event => {
  event.preventDefault();
  const content = chatInput.value.trim();
  if (!content || chatBusy) return;
  stopVoice(); clearTimeout(speechTimer);
  chatBusy = true; chatInteracting = true;
  const userMessage = addMessage('user', content);
  chatInput.value = '';
  document.querySelector('#send-message').disabled = true;
  chatStatus.textContent = 'Mr Camembert réfléchit…';
  speech.textContent = 'Je regarde ça avec vous…';
  if (!animationPaused) scene.classList.add('is-speaking');
  const messages = [...history, { role: 'user', content }].slice(-11);
  while (messages.length > 1 && messages.reduce((sum, m) => sum + m.content.length, 0) > 14000) messages.shift();
  if (messages[0].role === 'assistant') messages.shift();
  try {
    const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ messages }), signal: AbortSignal.timeout(55000) });
    let data;
    try { data = await response.json(); } catch { throw new Error('La conversation nécessite le serveur Vercel. Réessayez depuis le site déployé.'); }
    if (!response.ok) throw new Error(data.error || 'La conversation est indisponible.');
    if (typeof data.reply !== 'string' || !data.reply.trim()) throw new Error('La réponse est indisponible. Réessayez.');
    history.push({ role: 'user', content }, { role: 'assistant', content: data.reply });
    if (history.length > 10) history.splice(0, history.length - 10);
    addMessage('assistant', data.reply);
    lastSpokenReply = data.reply;
    speech.textContent = 'Voilà mon éclairage. On continue ?';
    chatStatus.textContent = '';
  } catch (error) {
    userMessage.classList.add('failed');
    chatInput.value = content;
    chatStatus.textContent = error.name === 'TimeoutError' ? 'La réponse a pris trop de temps. Réessayez.' : error.message;
    speech.textContent = 'Je n’ai pas pu vous répondre pour le moment.';
  } finally {
    chatBusy = false;
    document.querySelector('#send-message').disabled = false;
    if (!animationPaused && !reduceMotion.matches) speechTimer = setTimeout(() => scene.classList.remove('is-speaking'), 1600);
    else scene.classList.remove('is-speaking');
  }
});
