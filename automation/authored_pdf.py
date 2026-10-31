"""Render the author's actual prose, including citations, without generic rewrites."""
from xml.sax.saxutils import escape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepInFrame
from automation.pdf_report import INK, MUTED, PALE, ChangesChart, ChannelDiagram


def write_authored_pdf(path, report):
    analysis = report['authored_analysis']
    body = ParagraphStyle('author-body', fontName='Helvetica', fontSize=10, leading=14, textColor=INK, spaceAfter=9)
    small = ParagraphStyle('author-small', parent=body, fontSize=8, leading=10, textColor=MUTED, spaceAfter=5)
    heading = ParagraphStyle('author-heading', parent=body, fontName='Helvetica-Bold', fontSize=12, leading=16, spaceBefore=11)
    title = ParagraphStyle('author-title', parent=heading, fontSize=20, leading=24, spaceAfter=13)
    summary = ParagraphStyle('author-summary', parent=body, backColor=PALE, borderPadding=10, spaceBefore=10, spaceAfter=16)
    def p(value, style=body):
        return Paragraph(escape(value).replace('\n', '<br/>'), style)
    def link(label, url):
        return Paragraph(f'<link href="{escape(url, {chr(34): "&quot;"})}" color="#315f87">{escape(label)}</link>', small)
    def section(item):
        return [p(item['title'], heading), p(item['text']), p('Sources : ' + ', '.join(item['source_ids']), small)]
    selected = ', '.join(price['name'] for price in report['prices'])
    first = [p('MR SYNAPSE · SYNAPSE CAPITAL', heading),
             p(f"Édition du {report['publication_date']} · Informations du {report['date']}", small),
             p(analysis['title'], title), p(report['text'], summary), p(selected, small)]
    second = [p(analysis['title'], heading)]
    # Balance the prose, reserving space for the visual on page one and sources on page two.
    sections = analysis['sections']
    split = max(2, len(sections) // 2)
    for item in sections[:split]:
        first += section(item)
    featured = [price for price in report['prices'] if price['status'] == 'available']
    if featured:
        # The data may originate from another verified provider, not necessarily Yahoo.
        chart = ChangesChart(featured, source_label='Sources : références des cotations ci-dessous. Exemples sélectionnés, sans pondération.')
        first += [Spacer(1, 6), chart, p('Cotations fournies par l’auteur ; références ci-dessous. Les actifs sans cours ne figurent pas dans le graphique.', small)]
    else:
        first += [ChannelDiagram(analysis['diagram']), p('Schéma de lecture proposé par l’auteur. Aucun cours non vérifié n’est ajouté.', small)]
    for item in sections[split:]:
        second += section(item)
    second += [p('Sources', heading)]
    for source in report['news']:
        second += [link(f"[{source['id']}] {source['source']} — {source['title']} · {source['published_at']}", source['url'])]
    for price in featured:
        second += [link(price['symbol'] + ' — historique des cours', price['source_url'])]
    second += [p('Actifs de l’univers autorisé Nextwise ; aucune détention n’est déduite. Les références sont fournies par l’auteur ; la validation automatique contrôle le format, les dates et les calculs, sans certifier les faits des sources.', small)]
    def footer(canvas, doc):
        canvas.setTitle('Mr Synapse — ' + analysis['title'])
        canvas.setAuthor('Synapse Capital')
        canvas.setFillColor(MUTED)
        canvas.setFont('Helvetica', 8)
        canvas.drawString(44, 27, f"MR SYNAPSE · {report['publication_date']}")
        canvas.drawRightString(A4[0] - 44, 27, f'{doc.page} / 2')
    width, height = A4[0] - 100, A4[1] - 96
    frames = [KeepInFrame(width, height, page, mode='shrink') for page in [first, second]]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=44, rightMargin=44, topMargin=32, bottomMargin=52).build(
        [frames[0], PageBreak(), frames[1]], onFirstPage=footer, onLaterPages=footer)
    if any(getattr(frame, '_scale', 1) > 1.25 for frame in frames):
        raise ValueError('Analyse trop dense pour deux pages lisibles : raccourcir les sections ou les références.')
