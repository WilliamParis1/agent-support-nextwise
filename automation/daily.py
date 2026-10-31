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
from datetime import datetime, timedelta, timezone
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


def write_pdf(path, report):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepInFrame, Flowable
    from xml.sax.saxutils import escape
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='SmallBrief', fontName='Helvetica', fontSize=8, leading=11, textColor=colors.HexColor('#203b33'), alignment=TA_LEFT))
    style = styles['SmallBrief']
    def p(text):
        return Paragraph(escape(text), style)
    class Brand(Flowable):
        width = 465
        height = 60
        def draw(self):
            canvas = self.canv
            canvas.setFillColor(colors.HexColor('#08223f'))
            canvas.setFont('Helvetica', 31)
            canvas.drawString(0, 30, 'Synapse')
            canvas.drawString(31, 0, 'Capital')
            canvas.setStrokeColor(colors.HexColor('#a9afb5'))
            canvas.setLineWidth(2)
            curve = canvas.beginPath()
            curve.moveTo(45, 23)
            curve.curveTo(70, 38, 101, 27, 128, 39)
            canvas.drawPath(curve)
    story = [Brand(), Spacer(1, 8), p('FICHE QUALITATIVE · ' + report['date'] + ' · À RELIRE AVANT PUBLICATION'), Spacer(1, 14)]
    if report.get('universe'):
        universe = report['universe']
        story += [p(f"Périmètre : {universe['tracked']} actifs suivis sur {universe['total']} autorisés ; sélection : {universe['scope']}."), Spacer(1, 6)]
    for line in report['text'].split('\n\n'):
        story += [p(line), Spacer(1, 8)]
    moves = sorted((x for x in report['prices'] if x['status'] == 'available'), key=lambda x: abs(x['change_pct']), reverse=True)
    if moves:
        rows = [['Actif', 'Clôture', 'Variation', 'Séance précédente']]
        rows += [[x['symbol'], f'{x["close"]:.2f} {x["currency"]}', f'{x["change_pct"]:+.2f} %', x['previous_date']] for x in moves[:8]]
        table = Table(rows, colWidths=[100, 125, 80, 160])
        table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eaf0df')), ('FONTSIZE', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 7)]))
        story += [table, Spacer(1, 10)]
    missing = [x['symbol'] for x in report['prices'] if x['status'] == 'no_session']
    if missing:
        story += [p(f'Sans séance ce jour : {len(missing)} actifs. Liste dans le rapport JSON.'), Spacer(1, 8)]
    story.append(p('Sources macro (titres publiés pendant la journée civile, heure de Paris) :'))
    for item in report['news'][:3]:
        story += [p(item['source'] + ' · ' + item['published_at'] + ' · ' + item['url'])]
    story += [Spacer(1, 6), p('Cours : Yahoo Finance, clôtures brutes non ajustées, dates de séance locales. Une opération sur titre peut affecter la variation. Détail et liens de chaque actif dans le rapport JSON téléchargeable. Flux macro suivis : BCE, Federal Reserve, BBC Business ; couverture non exhaustive, titres uniquement. Univers CSV ; aucune position détenue n’est inférée.')]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=36, rightMargin=36, topMargin=30, bottomMargin=30).build([KeepInFrame(A4[0] - 84, A4[1] - 72, story, mode='shrink')])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scheduled', action='store_true')
    args = parser.parse_args()
    now = datetime.now(UTC)
    if args.scheduled and not due(now):
        print('Hors créneau Paris : aucune génération.')
        return
    day = previous_day(now)
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
              'status': 'draft', 'universe': {'source': config['universe_csv'], 'total': len(universe), 'tracked': len(selected), 'scope': config['daily_scope']}, 'news': news, 'prices': prices, 'text': compose(day, news, prices)}
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
    (ROOT / 'reports/latest.json').write_text(json.dumps({'date': day.isoformat(), 'path': f'reports/{day.isoformat()}', 'generated_at': now.isoformat()}, indent=2))
    print(f'Brouillon généré pour {day} : {len(news)} actualités, {len(prices)} actifs.')


if __name__ == '__main__':
    main()
