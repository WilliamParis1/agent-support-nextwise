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
    if (response.status === 404) { status.textContent = 'Édition pas encore disponible.'; return; }
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
    status.textContent = 'Brouillon';
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
        card.querySelector('[data-analysis-status]').textContent = report.origin === 'chatgpt'
          ? 'Deux pages : analyse de l’auteur, visuel et sources.'
          : 'Deux pages : graphique des actifs, analyse, schéma et sources.';
      } else card.querySelector('[data-analysis-status]').textContent = 'Le PDF est momentanément indisponible.';
    } catch { card.querySelector('[data-analysis-status]').textContent = 'Le PDF est momentanément indisponible.'; }

  } catch { status.textContent = 'Cette édition est momentanément indisponible. Réessayez plus tard.'; }
}
loadEdition('today-edition', 0);
loadEdition('previous-edition', -1);
