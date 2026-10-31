"""Two-page, sourced PDF extending the exact short publication.

Charts and explanatory diagrams are vector drawings. No illustrative market data
are generated, and the economic transmission is labelled as a hypothesis.
"""
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Flowable
from automation.editorial import choose_analysis, excerpt

INK = colors.HexColor('#102d4a')
MUTED = colors.HexColor('#65788a')
PALE = colors.HexColor('#edf3f7')
GREEN = colors.HexColor('#4e7f73')
RED = colors.HexColor('#af6a61')
WIDTH = A4[0] - 88


class ChangesChart(Flowable):
    width = WIDTH
    height = 146
    def __init__(self, prices):
        Flowable.__init__(self)
        self.width, self.height = WIDTH, 146
        self.prices = prices[:3]
    def draw(self):
        c = self.canv
        c.setFillColor(PALE)
        c.roundRect(0, 0, self.width, self.height, 8, fill=1, stroke=0)
        c.setFillColor(INK)
        c.setFont('Helvetica-Bold', 9)
        c.drawString(14, 128, 'VARIATIONS DE CLÔTURE (%)')
        if not self.prices:
            c.setFont('Helvetica', 10)
            c.drawString(14, 82, 'Aucune séance disponible pour cette journée.')
            return
        baseline = 305
        scale = 105 / max(max(abs(p['change_pct']) for p in self.prices), .1)
        c.setStrokeColor(colors.HexColor('#c4d1db'))
        c.line(baseline, 30, baseline, 114)
        for i, price in enumerate(self.prices):
            y = 100 - i * 29
            c.setFillColor(INK)
            c.setFont('Helvetica', 9)
            c.drawString(14, y + 1, excerpt(price.get('name') or price['symbol'], 4)[:29])
            value = price['change_pct']
            length = abs(value) * scale
            c.setFillColor(GREEN if value >= 0 else RED)
            c.rect(baseline if value >= 0 else baseline - length, y - 3, max(.6, length), 13, fill=1, stroke=0)
            c.setFillColor(INK)
            c.drawRightString(self.width - 14, y, f'{value:+.2f} %'.replace('.', ','))
        c.setFont('Helvetica', 7)
        c.setFillColor(MUTED)
        c.drawString(14, 13, 'Source : Yahoo Finance. Exemples sélectionnés ; ce graphique ne représente pas un indice.')


class ChannelDiagram(Flowable):
    width = WIDTH
    height = 84
    def __init__(self, labels):
        Flowable.__init__(self)
        self.width, self.height = WIDTH, 84
        self.labels = labels
    def draw(self):
        c = self.canv
        box = 112
        for i, label in enumerate(self.labels):
            x = i * (WIDTH / 4)
            c.setFillColor(PALE)
            c.roundRect(x, 13, box, 54, 6, stroke=0, fill=1)
            c.setFillColor(INK)
            c.setFont('Helvetica', 8)
            words = label.split()
            midpoint = max(1, len(words) // 2)
            c.drawCentredString(x + box / 2, 44, ' '.join(words[:midpoint]))
            c.drawCentredString(x + box / 2, 31, ' '.join(words[midpoint:]))
            if i < len(self.labels) - 1:
                c.setStrokeColor(MUTED)
                end = x + WIDTH / 4 - 3
                c.line(x + box + 2, 40, end, 40)
                c.line(end - 3, 43, end, 40)
                c.line(end - 3, 37, end, 40)


def write_pdf(path, report):
    analysis = report.get('analysis') or choose_analysis(report['news'], report['prices'])
    focus, featured, theme = analysis['focus'], analysis['featured'], analysis['theme']
    body = ParagraphStyle('body', fontName='Helvetica', fontSize=9.5, leading=14, textColor=INK, spaceAfter=9)
    small = ParagraphStyle('small', parent=body, fontSize=8, leading=11, textColor=MUTED, spaceAfter=7)
    heading = ParagraphStyle('heading', parent=body, fontName='Helvetica-Bold', fontSize=12, leading=16, spaceBefore=13, spaceAfter=8)
    title = ParagraphStyle('title', parent=heading, fontSize=23, leading=28, spaceBefore=2, spaceAfter=14)
    callout = ParagraphStyle('callout', parent=body, backColor=PALE, borderPadding=12, spaceBefore=8, spaceAfter=20)
    def p(text, style=body):
        return Paragraph(escape(str(text)), style)
    def link(label, url):
        # Escape attributes too; only HTTPS sources become clickable.
        if not url.startswith('https://'):
            return p(label, small)
        return Paragraph(f'<link href="{escape(url, {chr(34): "&quot;"})}" color="#315f87">{escape(label)}</link>', small)
    def footer(canvas, doc):
        canvas.setTitle(f'Synapse Capital — Qualitatif du {report.get("publication_date", report["date"])}')
        canvas.setAuthor('Synapse Capital')
        canvas.setStrokeColor(colors.HexColor('#d8e2e9'))
        canvas.line(44, 42, A4[0] - 44, 42)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(44, 28, 'SYNAPSE CAPITAL  /  LE CARNET DE MR SYNAPSE')
        canvas.drawRightString(A4[0] - 44, 28, f'{doc.page} / 2')

    publication = report.get('publication_date', report['date'])
    story = [p('SYNAPSE CAPITAL', heading), p(f'Publication du {publication} · Séance analysée : {report["date"]}', small),
             p('Un fait. Plusieurs angles de lecture.', title), p(report['text'], callout),
             p('01  /  L’information retenue', heading)]
    if focus:
        story += [p(excerpt(focus['title'], 40)), link(f"[1] {focus['source']} · publication {focus['published_at']}", focus['url'])]
        if focus.get('summary'):
            story += [p(excerpt(focus['summary'], 65))]
        else:
            story += [p('Le flux fournit le titre, sans détail exploitable. Le mécanisme présenté ensuite est une grille de lecture à vérifier dans la publication originale.', small)]
    else:
        story += [p('Le fait retenu est la dispersion des clôtures des actifs ci-dessous. Aucune publication macro datée de cette journée n’a été retenue dans les flux suivis.'),
                  p('L’analyse porte donc sur les cours observés ; elle n’attribue pas ces mouvements à une actualité absente.', small)]
    story += [p('02  /  Ce que montrent quelques actifs Nextwise', heading), ChangesChart(featured), Spacer(1, 10),
              p(analysis['selection'], small)]
    if featured:
        observed = ' ; '.join(f"{item.get('ticker', item['symbol'])} : {item['close']:.2f} {item.get('currency', '')} contre {item['previous_close']:.2f} le {item['previous_date']}" for item in featured)
        story += [p(observed + '.', small)]
    story += [PageBreak(), p('Du fait à l’interprétation.', title),
              p('03  /  Le mécanisme à examiner', heading), p(theme['hypothesis']),
              ChannelDiagram(theme['channel']), p('Schéma explicatif : transmission possible, non démontrée par les seules clôtures.', small),
              p('Ce qui renforcerait cette lecture', heading), p(theme['confirm']),
              p('Ce qui pourrait l’infirmer', heading), p(theme['challenge']),
              p('04  /  Notre question pour le club', heading),
              p(f"Comment vérifier {theme['watch']} sur les actifs cités ? Comparer leurs expositions réelles, leurs dernières annonces et les attentes déjà intégrées aux cours avant de formuler une conviction. L’univers autorisé ne décrit ni les positions détenues ni les opérations du club."),
              p('Sources et méthode', heading)]
    if focus:
        story += [link(f"[1] {focus['source']} — publication d’origine", focus['url'])]
    for i, item in enumerate(featured, 2):
        story += [link(f"[{i}] {item.get('name', item['symbol'])} ({item['symbol']}) — historique des cours", item['source_url'])]
    if report.get('feed_errors'):
        story += [p('Flux non disponibles lors de la collecte : ' + ', '.join(item['source'] for item in report['feed_errors']) + '. Ces sources ne sont pas remplacées par des informations anciennes.', small)]
    if not featured:
        for item in [p for p in report['prices'] if p.get('last_session_date')][:3]:
            story += [link(item['symbol'] + ' — aucune séance ce jour ; dernière séance reçue : ' + item['last_session_date'], item['source_url'])]
    total = len(report['prices'])
    covered = sum(item['status'] != 'unavailable' for item in report['prices'])
    story += [p(f"Couverture : {covered}/{total} symboles reconnus. Variations calculées entre deux clôtures brutes, dates de séance locales. Dividendes et opérations sur titres peuvent affecter ces valeurs. Titres et résumés RSS uniquement, couverture macro non exhaustive. Les exemples ne représentent pas une performance du club. À relire avant publication.", small)]
    document = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=44, rightMargin=44, topMargin=35, bottomMargin=58)
    document.build(story, onFirstPage=footer, onLaterPages=footer)
