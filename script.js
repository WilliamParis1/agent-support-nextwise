const topics = {
  structure: { intro: 'Commençons par une trame claire. Une bonne analyse qualitative relie chaque conviction à des faits observables.', steps: ['Décrire l’activité et la proposition de valeur.', 'Évaluer le marché, les avantages concurrentiels et l’équipe.', 'Synthétiser les risques, les preuves et les points à vérifier.'], prompt: 'Pour votre analyse, commencez par ces trois questions :', questions: ['Quel problème résout cette entreprise et pour quels clients ?', 'Qu’est-ce qui rend son avantage durable ? Quelles preuves avez-vous ?', 'Quel risque pourrait remettre en cause votre conclusion ?'] },
  questions: { intro: 'Allons au-delà de la première impression. L’objectif : transformer une idée générale en questions vérifiables.', steps: ['Identifier ce que vous savez et ce que vous supposez.', 'Chercher des éléments concrets et des sources datées.', 'Repérer les informations encore manquantes.'], prompt: 'Voici trois pistes à approfondir :', questions: ['Pourquoi les clients choisissent-ils cette offre plutôt qu’une autre ?', 'Quels éléments montrent que la stratégie produit des résultats ?', 'Quelle information manque encore pour vous prononcer ?'] },
  review: { intro: 'Une conviction devient plus solide quand elle résiste à la contradiction. Prenons un peu de recul sur votre raisonnement.', steps: ['Formuler votre conviction principale en une phrase.', 'Chercher les faits qui la soutiennent et ceux qui la contredisent.', 'Définir ce qui vous ferait changer d’avis.'], prompt: 'Mettez votre conviction à l’épreuve avec ces questions :', questions: ['Quel est le meilleur argument contre votre thèse ?', 'Votre conclusion repose-t-elle sur des faits ou sur des hypothèses ?', 'Quel indicateur suivrez-vous pour réviser votre jugement ?'] }
};
let selected = 'structure';
const answer = document.querySelector('#answer');
function show(topic, subject = '') {
  answer.replaceChildren();
  const intro = document.createElement('p');
  intro.textContent = subject ? `Sujet : ${subject}. ${topic.prompt}` : topic.intro;
  const list = document.createElement('ol');
  for (const text of subject ? topic.questions : topic.steps) {
    const item = document.createElement('li'); item.textContent = text; list.append(item);
  }
  answer.append(intro, list);
  if (subject) { const note = document.createElement('p'); note.textContent = 'Consignez vos réponses avec leurs sources, puis adaptez cette trame aux critères demandés dans votre espace Nextwise.'; answer.append(note); }
}
document.querySelectorAll('[data-topic]').forEach(button => button.addEventListener('click', () => {
  selected = button.dataset.topic;
  document.querySelectorAll('[data-topic]').forEach(item => { const active = item === button; item.classList.toggle('active', active); item.setAttribute('aria-pressed', String(active)); });
  show(topics[selected], document.querySelector('#context').value.trim());
}));
document.querySelector('#context-form').addEventListener('submit', event => { event.preventDefault(); const input = document.querySelector('#context'); const subject = input.value.trim(); if (!subject) { input.setCustomValidity('Indiquez un sujet pour préparer votre trame.'); input.reportValidity(); return; } input.setCustomValidity(''); show(topics[selected], subject); });
document.querySelector('#context').addEventListener('input', event => event.target.setCustomValidity(''));
show(topics[selected]);

async function loadBrief() {
  const status = document.querySelector('#brief-status');
  try {
    const response = await fetch('reports/latest.json', { cache: 'no-store' });
    if (!response.ok) throw new Error('manifest');
    const latest = await response.json();
    if (!latest.date) { status.textContent = 'Le premier brouillon n’est pas encore disponible. Il apparaîtra ici après activation et exécution de la génération quotidienne.'; return; }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(latest.date) || latest.path !== `reports/${latest.date}`) throw new Error('path');
    const result = await fetch(`${latest.path}/report.json`, { cache: 'no-store' });
    if (!result.ok) throw new Error('report');
    const report = await result.json();
    if (report.date !== latest.date || typeof report.text !== 'string') throw new Error('format');
    const yesterday = new Date(Date.now() - 86400000).toLocaleDateString('en-CA', { timeZone: 'Europe/Paris' });
    status.textContent = report.date === yesterday ? 'Brouillon de la veille — à relire avant publication' : 'Dernier brouillon disponible — il ne couvre pas la veille actuelle.';
    document.querySelector('#brief-date').textContent = `Journée analysée : ${report.date} · Heure de référence : Paris`;
    document.querySelector('#brief-text').textContent = report.text;
    document.querySelector('#download-pdf').href = `${latest.path}/fiche.pdf`;
    document.querySelector('#download-evidence').href = `${latest.path}/report.json`;
    document.querySelector('#brief-content').hidden = false;
    document.querySelector('#copy-brief').addEventListener('click', async event => {
      try { await navigator.clipboard.writeText(report.text); event.target.textContent = 'Texte copié'; }
      catch { status.textContent = 'La copie automatique est indisponible. Sélectionnez le texte ci-dessus pour le copier.'; }
    });
  } catch { status.textContent = 'Le brouillon est momentanément indisponible. Réessayez plus tard.'; }
}
loadBrief();
