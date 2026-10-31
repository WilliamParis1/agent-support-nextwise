"""Daily, evidence-only editorial brief. No trade or portfolio inference."""
import argparse
import csv
import email.utils
import io
import json
import os
import re
import time
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


def get(url):
    # TLS and platform proxy configuration are preserved.
    request = urllib.request.Request(url, headers={'User-Agent': 'SynapseCapitalDailyBrief/1.0'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                data = response.read(5_000_001)
                if len(data) > 5_000_000:
                    raise ValueError('Réponse trop volumineuse')
                return data
        except Exception:
            if attempt == 2:
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


def parse_assets(data, column='', max_assets=100):
    text = data.decode('utf-8-sig')
    if text.lstrip().startswith('<'):
        raise ValueError('Le Sheet ne renvoie pas de CSV. Vérifier le partage ou SHEET_CSV_URL.')
    rows = csv.DictReader(io.StringIO(text))
    fields = rows.fieldnames or []
    aliases = {'ticker yahoo', 'yahoo ticker', 'yahoo symbol', 'symbole yahoo', 'ticker', 'symbol', 'symbole'}
    matches = [f for f in fields if normalize(f) in aliases]
    if column:
        matches = [f for f in fields if f == column]
    else:
        preferred = [f for f in matches if 'yahoo' in normalize(f)]
        matches = preferred or matches
    if len(matches) != 1:
        raise ValueError('Définir ticker_column dans automation/config.json : une colonne de symboles Yahoo Finance est requise (ex. AIR.PA, AAPL, BTC-USD).')
    symbols = []
    for row in rows:
        symbol = (row.get(matches[0]) or '').strip()
        if not symbol:
            continue
        if not re.fullmatch(r'[A-Za-z0-9^][A-Za-z0-9.^=\-]{0,29}', symbol):
            raise ValueError('Symbole invalide : utiliser une colonne de tickers Yahoo, pas des noms ni des ISIN.')
        if symbol not in symbols:
            symbols.append(symbol)
    if not symbols or len(symbols) > max_assets:
        raise ValueError(f'Nombre de symboles invalide : {len(symbols)} (limite {max_assets}).')
    return symbols


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


def compose(day, news, prices):
    french_date = day.strftime('%d/%m/%Y')
    lines = [f'Synapse Capital | Le point marché du {french_date}', '']
    if news:
        headlines = news[:3]
        lines.append('Macro de la veille : ' + ' ; '.join(f'{n["title"]} ({n["source"]})' for n in headlines) + '.')
    else:
        lines.append('Aucune actualité macro datée de cette journée dans les flux suivis. Nous ne reprenons pas de nouvelle plus ancienne.')
    moves = sorted((p for p in prices if p['status'] == 'available'), key=lambda p: abs(p['change_pct']), reverse=True)
    if moves:
        lines.append('Sur les actifs de notre univers Nextwise, les variations les plus marquées à la clôture sont : ' + ', '.join(f'{p["symbol"]} ({p["change_pct"]:+.2f} %)' for p in moves[:4]) + '. Les variations comparent la clôture du jour à celle de la séance précédente.')
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
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepInFrame
    from xml.sax.saxutils import escape
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='SmallBrief', fontName='Helvetica', fontSize=8, leading=11, textColor=colors.HexColor('#203b33'), alignment=TA_LEFT))
    style = styles['SmallBrief']
    def p(text):
        return Paragraph(escape(text), style)
    story = [Paragraph('SYNAPSE CAPITAL', styles['Title']), p('FICHE QUALITATIVE · ' + report['date'] + ' · À RELIRE AVANT PUBLICATION'), Spacer(1, 14)]
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
        story += [p('Sans séance ce jour : ' + ', '.join(missing)), Spacer(1, 8)]
    story.append(p('Sources macro (titres publiés pendant la journée civile, heure de Paris) :'))
    for item in report['news'][:3]:
        story += [p(item['source'] + ' · ' + item['published_at'] + ' · ' + item['url'])]
    story += [Spacer(1, 6), p('Cours : Yahoo Finance, clôtures brutes non ajustées, dates de séance locales. Une opération sur titre peut affecter la variation. Détail et liens de chaque actif dans le rapport JSON téléchargeable. Flux macro suivis : BCE, Federal Reserve, BBC Business ; couverture non exhaustive, titres uniquement. Aucun portefeuille n’est inféré du Sheet.')]
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
    sheet_url = os.environ.get('SHEET_CSV_URL') or f'https://docs.google.com/spreadsheets/d/{config["sheet_id"]}/export?format=csv&gid={config["sheet_gid"]}'
    if not sheet_url.startswith('https://'):
        raise ValueError('SHEET_CSV_URL doit utiliser HTTPS')
    assets = parse_assets(get(sheet_url), config['ticker_column'], config['max_assets'])
    news = []
    # Any failed provider fails the run. An empty day is distinct from a failed request.
    for feed in config['feeds']:
        news.extend(parse_news(get(feed['url']), feed['name'], day, feed['macro_only']))
    news = list({n['url']: n for n in news}.values())
    news.sort(key=lambda n: n['published_at'], reverse=True)
    start = datetime.combine(day - timedelta(days=15), datetime.min.time(), UTC)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), UTC)
    prices = []
    for symbol in assets:
        url = f'https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol, safe="")}?period1={int(start.timestamp())}&period2={int(end.timestamp())}&interval=1d'
        prices.append(parse_prices(get(url), symbol, day))
        time.sleep(.3)
    report = {'date': day.isoformat(), 'generated_at': now.isoformat(), 'timezone': 'Europe/Paris',
              'status': 'draft', 'news': news, 'prices': prices, 'text': compose(day, news, prices)}
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
