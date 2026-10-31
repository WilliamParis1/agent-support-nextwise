"""Daily, evidence-only editorial brief. No trade or portfolio inference."""
import argparse
import csv
import email.utils
import io
import json
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PARIS = ZoneInfo('Europe/Paris')
UTC = timezone.utc
MACRO = re.compile(r'inflat|interest rate|central bank|econom|tariff|trade war|gdp|employment|unemployment|monetary|oil price|growth|federal reserve|bank of england|borrowing|budget|fiscal', re.I)


QUOTE_LOCK = threading.Lock()
QUOTE_NEXT_REQUEST = 0.0
QUOTE_INTERVAL = 0.5
QUOTE_STOP = threading.Event()


def quote_rate_limit():
    global QUOTE_NEXT_REQUEST
    with QUOTE_LOCK:
        delay = max(0, QUOTE_NEXT_REQUEST - time.monotonic())
        if delay:
            time.sleep(delay)
        QUOTE_NEXT_REQUEST = time.monotonic() + QUOTE_INTERVAL


def get(url):
    # TLS and platform proxy configuration are preserved.
    request = urllib.request.Request(url, headers={'User-Agent': 'SynapseCapitalDailyBrief/1.0'})
    for attempt in range(3):
        try:
            if 'query1.finance.yahoo.com/' in url:
                if QUOTE_STOP.is_set():
                    raise RuntimeError('Fournisseur de cours temporairement indisponible')
                quote_rate_limit()
            with urllib.request.urlopen(request, timeout=25) as response:
                data = response.read(5_000_001)
                if len(data) > 5_000_000:
                    raise ValueError('Réponse trop volumineuse')
                return data
        except HTTPError as error:
            if error.code in (401, 403, 429) and 'query1.finance.yahoo.com/' in url:
                QUOTE_STOP.set()
                raise RuntimeError(f'Accès fournisseur de cours refusé ou limité (HTTP {error.code})') from None
            if error.code == 404 or attempt == 2:
                raise
            time.sleep(2 ** attempt)
        except Exception:
            if attempt == 2 or QUOTE_STOP.is_set():
                raise
            time.sleep(2 ** attempt)


def previous_day(now):
    return now.astimezone(PARIS).date() - timedelta(days=1)


def due(now):
    local = now.astimezone(PARIS)
    # First occurrence at the autumn clock change; 03:00 on the spring day
    # where 02:00 does not exist. A date-based output also prevents duplicates.
    return (local.hour == 2 and local.fold == 0) or (
        local.hour == 3 and (now - timedelta(hours=1)).astimezone(PARIS).hour == 1)


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.lower().strip()) if not unicodedata.combining(c))


def load_universe(config):
    source = (ROOT / config['universe_csv']).resolve()
    if not source.is_relative_to(ROOT / 'data') or source.suffix != '.csv':
        raise ValueError('Le CSV doit être conservé dans data/.')
    with source.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    required = {'name', 'ticker', 'market', 'yahoo_symbol', 'priority', 'asset_class', 'sector'}
    if not rows or not required.issubset(rows[0]):
        raise ValueError('CSV normalisé invalide ; utiliser automation.import_universe.')
    if config['daily_scope'] not in ('priority', 'all'):
        raise ValueError('daily_scope doit valoir priority ou all.')
    selected = rows if config['daily_scope'] == 'all' else [r for r in rows if r['priority'] == 'true']
    if not selected or len(selected) > config['max_assets']:
        raise ValueError(f"Périmètre quotidien : {len(selected)} actifs, limite {config['max_assets']}. Adapter explicitement la configuration.")
    seen = set()
    for asset in selected:
        key = f"{asset['market']}:{asset['ticker']}"
        asset['yahoo_symbol'] = config.get('symbol_overrides', {}).get(key, asset['yahoo_symbol'])
        symbol = asset['yahoo_symbol']
        if not re.fullmatch(r'[A-Za-z0-9^][A-Za-z0-9.^=\-]{0,29}', symbol) or symbol in seen:
            raise ValueError(f'Correspondance Yahoo invalide ou ambiguë : {key}')
        seen.add(symbol)
    return rows, selected


def parse_news(data, source, day, macro_only=False):
    root = ET.fromstring(data)
    output = []
    for item in root.findall('.//item'):
        title = ' '.join((item.findtext('title') or '').split())
        link = (item.findtext('link') or '').strip()
        raw = item.findtext('pubDate') or item.findtext('{http://purl.org/dc/elements/1.1/}date')
        if not raw:
            continue
        try:
            stamp = email.utils.parsedate_to_datetime(raw)
        except (ValueError, TypeError):
            stamp = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if stamp.tzinfo is None or stamp.astimezone(PARIS).date() != day:
            continue
        if not title or not link.startswith('https://') or (macro_only and not MACRO.search(title)):
            continue
        output.append({'title': title, 'url': link, 'source': source, 'published_at': stamp.isoformat()})
    return output


def parse_prices(data, symbol, day):
    payload = json.loads(data)
    chart = payload.get('chart', {})
    if chart.get('error') or not chart.get('result'):
        raise ValueError(f'Cours indisponible pour {symbol}')
    result = chart['result'][0]
    market_tz = ZoneInfo(result['meta']['exchangeTimezoneName'])
    quotes = result['indicators']['quote'][0]['close']
    # Daily bars are labelled in exchange-local trading dates, not Paris dates.
    bars = [(datetime.fromtimestamp(t, market_tz).date(), close) for t, close in zip(result.get('timestamp', []), quotes)
            if close is not None and datetime.fromtimestamp(t, market_tz).date() <= day]
    bars.sort()
    matching = [i for i, (date, _) in enumerate(bars) if date == day]
    if not matching:
        return {'symbol': symbol, 'status': 'no_session', 'date': day.isoformat()}
    index = matching[-1]
    if index == 0 or bars[index - 1][1] <= 0:
        raise ValueError(f'Clôture précédente absente pour {symbol}')
    close = bars[index][1]
    previous = bars[index - 1]
    return {'symbol': symbol, 'status': 'available', 'date': day.isoformat(),
            'close': round(close, 6), 'currency': result['meta'].get('currency', ''),
            'previous_date': previous[0].isoformat(), 'previous_close': round(previous[1], 6),
            'change_pct': round((close / previous[1] - 1) * 100, 2),
            'source_url': f'https://finance.yahoo.com/quote/{urllib.parse.quote(symbol, safe="")}/history/'}


def collect_prices(assets, day, config, fetch=get):
    global QUOTE_INTERVAL
    QUOTE_STOP.clear()
    QUOTE_INTERVAL = 1 / max(0.1, min(config.get('quote_requests_per_second', 2), 4))
    start = datetime.combine(day - timedelta(days=15), datetime.min.time(), UTC)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), UTC)

    def collect(asset):
        symbol = asset['yahoo_symbol']
        url = f'https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol, safe="")}?period1={int(start.timestamp())}&period2={int(end.timestamp())}&interval=1d'
        try:
            price = parse_prices(fetch(url), symbol, day)
        except Exception as error:
            # Do not leak response bodies or URLs into public reports.
            price = {'symbol': symbol, 'date': day.isoformat(), 'status': 'unavailable',
                     'reason': 'symbol_not_found' if isinstance(error, HTTPError) and error.code == 404 else 'provider_error'}
        price.update({k: asset[k] for k in ['name', 'ticker', 'market', 'asset_class', 'sector']})
        return price

    prices = []
    with ThreadPoolExecutor(max_workers=max(1, min(config.get('quote_workers', 4), 8))) as executor:
        futures = [executor.submit(collect, asset) for asset in assets]
        for future in as_completed(futures):
            prices.append(future.result())
            if QUOTE_STOP.is_set():
                for pending in futures:
                    pending.cancel()
                raise RuntimeError('Fournisseur de cours bloqué ou limité : aucun brouillon publié. Réessayer après résolution ou changer de fournisseur.')
            if len(prices) % 100 == 0:
                print(f'Cotations traitées : {len(prices)}/{len(assets)}', flush=True)
    prices.sort(key=lambda p: (p['market'], p['ticker']))
    covered = sum(p['status'] != 'unavailable' for p in prices)
    if covered / len(assets) < config.get('min_quote_coverage', 0.9):
        raise RuntimeError(f'Couverture insuffisante : {covered}/{len(assets)} symboles reconnus. Vérifier les correspondances et symbol_overrides. Aucun brouillon publié.')
    return prices


def compose(day, news, prices):
    french_date = day.strftime('%d/%m/%Y')
    lines = [f'Synapse Capital | Le point marché du {french_date}', '']
    covered = sum(p['status'] != 'unavailable' for p in prices)
    lines.append(f'Univers : {len(prices)} actifs examinés ; {covered} symboles reconnus par le fournisseur. Les mouvements ci-dessous concernent les cotations disponibles, sans pondération de portefeuille.')
    unavailable = len(prices) - covered
    if unavailable:
        lines.append(f'{unavailable} actifs sans donnée exploitable : ils sont exclus du classement et détaillés dans les données jointes.')
    if news:
        headlines = news[:3]
        lines.append('Macro de la veille : ' + ' ; '.join(f'{n["title"]} ({n["source"]})' for n in headlines) + '.')
    else:
        lines.append('Aucune actualité macro datée de cette journée dans les flux suivis. Nous ne reprenons pas de nouvelle plus ancienne.')
    moves = sorted((p for p in prices if p['status'] == 'available'), key=lambda p: abs(p['change_pct']), reverse=True)
    if moves:
        lines.append('Parmi les actifs suivis de notre univers Nextwise, les variations les plus marquées à la clôture sont : ' + ', '.join(f'{p["symbol"]} ({p["change_pct"]:+.2f} %)' for p in moves[:4]) + '. Les variations comparent la clôture du jour à celle de la séance précédente.')
    else:
        lines.append('Aucune séance datée de cette journée dans les cotations reçues : aucun mouvement antérieur n’est présenté comme celui d’hier.')
    if news and moves:
        lines.append('Notre grille de lecture : confronter ces annonces aux écarts entre actifs pour distinguer un mouvement général d’un facteur propre à une valeur. Leur concomitance ne suffit pas à établir un lien de causalité.')
    lines.append('Pour naviguer le marché, notre point de vigilance est la sensibilité des actifs aux taux, à la croissance et aux devises. Cette lecture propose des axes de surveillance ; elle ne décrit ni nos positions ni des arbitrages réalisés.')
    lines.append('Sources et détail dans la fiche jointe. Données de la veille uniquement ; analyse à relire par le club avant publication.')
    return '\n\n'.join(line for line in lines if line)


def summarize(day, prices):
    """Under 50 whitespace-delimited words, based only on observed closes."""
    moves = sorted((p for p in prices if p['status'] == 'available'), key=lambda p: abs(p['change_pct']), reverse=True)[:3]
    if not moves:
        return (f"Au {day:%d/%m/%Y}, aucune séance exploitable dans les données reçues pour les actifs Nextwise. "
                "Aucune tendance de marché ne peut être établie ; aucun cours ancien n’est présenté comme celui d’hier.")
    positive = sum(p['change_pct'] > 0 for p in moves)
    negative = sum(p['change_pct'] < 0 for p in moves)
    tone = 'contrastés' if positive and negative else 'en hausse' if positive else 'en baisse' if negative else 'stables'
    values = ', '.join(f"{p['symbol']} ({p['change_pct']:+.2f} %)" for p in moves)
    return (f"Au {day:%d/%m/%Y}, les actifs Nextwise retenus sont {tone} : {values}. "
            "Variations entre clôtures de séances consécutives. Cet échantillon ne représente ni tout le marché ni les positions du club.")


def analyze(news, prices):
    """A conditional reading of a sourced headline, never an invented article summary."""
    if not news:
        return None
    source = news[0]
    title = normalize(source['title'])
    if re.search(r'inflat|rate|taux|monetary|monetaire', title):
        mechanism = ("Un changement de perspective sur les taux peut modifier le taux d’actualisation des bénéfices futurs et le coût du financement. "
                     "Une hausse des taux attendus pèserait, toutes choses égales par ailleurs, sur les valorisations ; une baisse pourrait les soutenir. "
                     "L’effet sur une banque dépend aussi de sa marge d’intérêt, du coût des dépôts et du risque de crédit.")
        watch = "Vérifier le niveau des taux et les anticipations, puis l’endettement et les prochaines publications des entreprises concernées."
    elif re.search(r'oil|energy|petrol|energie', title):
        mechanism = ("Une hausse durable du coût de l’énergie peut soutenir les revenus des producteurs et réduire les marges des entreprises consommatrices. "
                     "L’effet dépend des couvertures, des devises et de la capacité à répercuter les coûts ; ces paramètres ne sont pas documentés ici.")
        watch = "Vérifier le prix de l’énergie, les couvertures et les commentaires de marge avant d’appliquer cette lecture à un actif."
    elif re.search(r'growth|gdp|econom|emploi|employment|trade|croissance', title):
        mechanism = ("Une évolution de l’activité peut modifier les perspectives de demande, les bénéfices attendus et le risque de crédit. "
                     "Les entreprises cycliques pourraient être plus sensibles, mais leurs expositions géographiques et leurs carnets de commandes doivent être vérifiés.")
        watch = "Comparer la publication complète aux attentes, puis examiner les expositions sectorielles et géographiques des entreprises."
    else:
        mechanism = ("Le titre seul ne permet pas d’établir un canal de transmission précis aux actifs. "
                     "Il faut lire la publication complète, identifier ce qui change par rapport aux attentes et vérifier quelles entreprises sont effectivement exposées.")
        watch = "Lire la source primaire et vérifier les chiffres, les dates et les hypothèses avant toute conclusion."
    moves = sorted((p for p in prices if p['status'] == 'available'), key=lambda p: abs(p['change_pct']), reverse=True)[:3]
    return {'title': source['title'], 'source': source, 'mechanism': mechanism, 'watch': watch,
            'assets': moves,
            'limits': "L’information disponible est le titre d’un flux RSS, pas une lecture intégrale de l’article. Les clôtures sont brutes, non ajustées. La simultanéité d’une annonce et d’une variation ne démontre pas de causalité. Aucun conseil d’investissement ni position détenue n’est déduit."}


def write_pdf(path, report):
    """Two-page analysis: observed moves, then conditional interpretation and sources."""
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepInFrame, PageBreak
    from reportlab.graphics.shapes import Drawing, Rect, Line, String, Polygon
    from xml.sax.saxutils import escape
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import reportlab
    font_dir = Path(reportlab.__file__).parent / 'fonts'
    pdfmetrics.registerFont(TTFont('BriefSans', str(font_dir / 'Vera.ttf')))
    pdfmetrics.registerFont(TTFont('BriefSansBold', str(font_dir / 'VeraBd.ttf')))
    ink = colors.HexColor('#0b2541')
    muted = colors.HexColor('#687582')
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='BodyAnalysis', fontName='BriefSans', fontSize=10, leading=15, textColor=ink, spaceAfter=8))
    styles.add(ParagraphStyle(name='SectionAnalysis', fontName='BriefSansBold', fontSize=13, leading=18, textColor=ink, spaceBefore=12, spaceAfter=10))
    styles.add(ParagraphStyle(name='TitleAnalysis', fontName='BriefSans', fontSize=26, leading=30, textColor=ink, spaceAfter=14))
    def p(text, style='BodyAnalysis'):
        return Paragraph(escape(str(text)), styles[style])
    moves = sorted((x for x in report['prices'] if x['status'] == 'available'), key=lambda x: abs(x['change_pct']), reverse=True)[:3]
    summary = report.get('summary') or summarize(date.fromisoformat(report['date']), report['prices'])
    analysis = report.get('analysis') or analyze(report['news'], report['prices'])
    first = [p('Synapse Capital', 'TitleAnalysis'), p('Le point de marché · ' + report['date']),
             p('01 / Comprendre les mouvements', 'SectionAnalysis'), p(summary)]
    if report.get('universe'):
        u = report['universe']
        first += [p(f"Périmètre : {u['tracked']} actifs examinés sur {u['total']} autorisés. Les trois mouvements les plus marqués sont retenus pour la synthèse.")]
    if moves:
        chart = Drawing(465, 155)
        center, scale = 240, 155 / max(1, max(abs(m['change_pct']) for m in moves))
        chart.add(String(0, 140, 'Variations entre deux clôtures (%)', fontName='BriefSansBold', fontSize=10, fillColor=ink))
        chart.add(Line(center, 15, center, 125, strokeColor=muted, strokeWidth=.6))
        for i, m in enumerate(moves):
            y = 105 - i * 36
            change = m['change_pct']
            width = abs(change) * scale
            chart.add(String(0, y, m['symbol'], fontSize=10, fillColor=ink))
            chart.add(Rect(center if change >= 0 else center - width, y - 5, max(width, 1), 18,
                           fillColor=colors.HexColor('#345f75' if change >= 0 else '#a67856'), strokeColor=None))
            chart.add(String(412, y, f'{change:+.2f} %', fontSize=9, fillColor=ink))
        first += [Spacer(1, 12), chart]
        rows = [[p('Actif'), p('Clôture'), p('Séance précédente')]]
        rows += [[p(m['symbol']), p(f"{m['close']:.2f} {m['currency']}"), p(m['previous_date'])] for m in moves]
        table = Table(rows, colWidths=[135, 150, 180])
        table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#edf1f3')), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
        first += [table, p('Lecture du graphique', 'SectionAnalysis')]
        gains = sum(m['change_pct'] > 0 for m in moves)
        losses = sum(m['change_pct'] < 0 for m in moves)
        first += [p(f"Sur ces {len(moves)} actifs, {gains} progressent et {losses} reculent. Un écart de variation montre une dispersion, pas sa cause. La sélection par amplitude privilégie les extrêmes et ne mesure pas la tendance de l’ensemble du marché.")]
        for m in moves:
            first += [p(f"{m.get('name', m['symbol'])} ({m['symbol']}) : {m['change_pct']:+.2f} % ; secteur : {m.get('sector', 'non renseigné')}. Vérifier les résultats, annonces propres à l’entreprise et opérations sur titres avant d’attribuer ce mouvement à la conjoncture.")]
    else:
        first += [p('Aucune séance exploitable : aucun graphique de cours ni variation historique ne sont présentés comme des données de cette journée.')]
    first += [p('Méthode et couverture', 'SectionAnalysis'),
              p('Clôtures brutes de la journée analysée comparées à la séance précédente, en dates locales de cotation. Les jours sans séance et les données indisponibles sont exclus. Splits et dividendes peuvent influencer les écarts. Les actifs autorisés ne sont pas des positions détenues.')]
    second = [p('02 / Aller au-delà du résumé', 'TitleAnalysis')]
    if analysis:
        source = analysis['source']
        second += [p('Une information à mettre en perspective', 'SectionAnalysis'), p(analysis['title']),
                   p(f"Source : {source['source']} · {source['published_at']}. Fait rapporté : le titre du flux, sans lecture intégrale de l’article."),
                   p('Canal de transmission possible', 'SectionAnalysis'), p(analysis['mechanism'])]
    else:
        second += [p('Aucune actualité sourcée pour cette journée. Sans information vérifiée, aucun événement n’est inventé pour expliquer les cours.')]
    diagram = Drawing(465, 85)
    labels = ['Information', 'Anticipations', 'Valorisations']
    for i, label in enumerate(labels):
        x = i * 160
        diagram.add(Rect(x, 24, 140, 36, fillColor=colors.HexColor('#edf1f3'), strokeColor=None, rx=4, ry=4))
        diagram.add(String(x + 70, 38, label, textAnchor='middle', fontSize=10, fillColor=ink))
        if i < 2:
            diagram.add(Line(x + 143, 42, x + 157, 42, strokeColor=ink))
            diagram.add(Polygon([x + 157, 42, x + 152, 45, x + 152, 39], fillColor=ink, strokeColor=None))
    diagram.add(String(0, 5, 'Schéma conceptuel : une hypothèse de transmission, pas une causalité démontrée.', fontSize=8, fillColor=muted))
    second += [diagram]
    if analysis:
        second += [p('Ce que cela change dans la lecture des trois actifs', 'SectionAnalysis'),
                   p('Les actifs de la première page illustrent la réaction observée des prix. Pour relier cette information à chacun, vérifier son exposition économique, la chronologie de l’annonce et ce que le marché anticipait déjà. Un secteur ou une variation ne suffisent pas à établir ce lien.'),
                   p('Points de vigilance', 'SectionAnalysis'), p(analysis['watch']), p(analysis['limits']),
                   p('Source de l’information', 'SectionAnalysis'), p(source['url'])]
    second += [p('Sources des cotations', 'SectionAnalysis')]
    for m in moves:
        second += [p(m['symbol'] + ' · ' + m.get('source_url', 'Lien indisponible ; consulter le rapport JSON.'))]
    second += [p('Yahoo Finance · clôtures brutes, non ajustées. Détail, couverture et indisponibilités dans le rapport JSON. Analyse conditionnelle, sans conseil d’investissement. À relire avant publication.')]
    def footer(canvas, doc):
        canvas.setFont('BriefSans', 8)
        canvas.setFillColor(muted)
        canvas.drawString(42, 22, 'Synapse Capital · ' + report['date'] + ' · Brouillon sourcé')
        canvas.drawRightString(A4[0] - 42, 22, f'{doc.page} / 2')
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=42, rightMargin=42, topMargin=34, bottomMargin=40)
    doc.build([KeepInFrame(A4[0] - 96, A4[1] - 86, first, mode='shrink'), PageBreak(),
               KeepInFrame(A4[0] - 96, A4[1] - 86, second, mode='shrink')], onFirstPage=footer, onLaterPages=footer)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scheduled', action='store_true')
    parser.add_argument('--date', type=date.fromisoformat, help='Journée analysée YYYY-MM-DD, antérieure à aujourd’hui à Paris')
    args = parser.parse_args()
    now = datetime.now(UTC)
    if args.scheduled and not due(now):
        print('Hors créneau Paris : aucune génération.')
        return
    day = args.date or previous_day(now)
    if day > previous_day(now):
        parser.error('La journée analysée doit être terminée en heure de Paris.')
    target = ROOT / 'reports' / day.isoformat()
    if (target / 'report.json').exists():
        print('Rapport déjà généré : aucune duplication.')
        return
    config = json.loads((ROOT / 'automation/config.json').read_text())
    universe, selected = load_universe(config)
    news = []
    # Any failed provider fails the run. An empty day is distinct from a failed request.
    for feed in config['feeds']:
        news.extend(parse_news(get(feed['url']), feed['name'], day, feed['macro_only']))
    news = list({n['url']: n for n in news}.values())
    news.sort(key=lambda n: n['published_at'], reverse=True)
    prices = collect_prices(selected, day, config)
    report = {'date': day.isoformat(), 'generated_at': now.isoformat(), 'timezone': 'Europe/Paris',
              'status': 'draft', 'universe': {'source': config['universe_csv'], 'total': len(universe), 'tracked': len(selected), 'scope': config['daily_scope']}, 'news': news, 'prices': prices, 'text': summarize(day, prices),
              'summary': summarize(day, prices), 'analysis': analyze(news, prices)}
    # Stage complete outputs before making the report discoverable.
    import tempfile
    import shutil
    with tempfile.TemporaryDirectory() as directory:
        staging = Path(directory)
        (staging / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        (staging / 'publication.txt').write_text(report['text'])
        write_pdf(staging / 'fiche.pdf', report)
        target.parent.mkdir(exist_ok=True)
        shutil.copytree(staging, target, dirs_exist_ok=True)
    latest_path = ROOT / 'reports/latest.json'
    latest = json.loads(latest_path.read_text()) if latest_path.exists() else {}
    if not latest.get('date') or latest['date'] <= day.isoformat():
        latest_path.write_text(json.dumps({'date': day.isoformat(), 'path': f'reports/{day.isoformat()}', 'generated_at': now.isoformat()}, indent=2))
    print(f'Brouillon généré pour {day} : {len(news)} actualités, {len(prices)} actifs.')


if __name__ == '__main__':
    main()
