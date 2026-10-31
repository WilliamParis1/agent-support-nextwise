"""Daily, evidence-only editorial brief. No trade or portfolio inference."""
import argparse
import csv
import email.utils
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
from html.parser import HTMLParser
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
        class TextOnly(HTMLParser):
            def __init__(self):
                super().__init__()
                self.parts = []
            def handle_data(self, text):
                self.parts.append(text)
        summary = TextOnly()
        summary.feed(item.findtext('description') or '')
        output.append({'title': title, 'url': link, 'source': source, 'published_at': stamp.isoformat(),
                       'summary': ' '.join(' '.join(summary.parts).split())[:1200]})
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


def collect_price_days(assets, days, config, fetch=get):
    """One provider request per asset, even for today's and yesterday's editions."""
    global QUOTE_INTERVAL
    QUOTE_STOP.clear()
    QUOTE_INTERVAL = 1 / max(0.1, min(config.get('quote_requests_per_second', 2), 4))
    start = datetime.combine(min(days) - timedelta(days=15), datetime.min.time(), UTC)
    end = datetime.combine(max(days) + timedelta(days=1), datetime.min.time(), UTC)

    def collect(asset):
        symbol = asset['yahoo_symbol']
        url = f'https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol, safe="")}?period1={int(start.timestamp())}&period2={int(end.timestamp())}&interval=1d'
        data, failure = None, None
        try:
            data = fetch(url)
        except Exception as error:
            failure = 'symbol_not_found' if isinstance(error, HTTPError) and error.code == 404 else 'provider_error'
        values = {}
        for day in days:
            try:
                if failure:
                    raise ValueError(failure)
                price = parse_prices(data, symbol, day)
            except Exception:
                price = {'symbol': symbol, 'date': day.isoformat(), 'status': 'unavailable', 'reason': failure or 'invalid_quote'}
            price.update({k: asset[k] for k in ['name', 'ticker', 'market', 'asset_class', 'sector']})
            values[day] = price
        return values

    prices_by_day = {day: [] for day in days}
    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, min(config.get('quote_workers', 4), 8))) as executor:
        futures = [executor.submit(collect, asset) for asset in assets]
        for future in as_completed(futures):
            result = future.result()
            if QUOTE_STOP.is_set():
                for pending in futures:
                    pending.cancel()
                raise RuntimeError('Fournisseur de cours bloqué ou limité : aucun brouillon publié.')
            for day, price in result.items():
                prices_by_day[day].append(price)
            completed += 1
            if completed % 100 == 0:
                print(f'Actifs examinés : {completed}/{len(assets)} pour {len(days)} séance(s)', flush=True)
    for day, prices in prices_by_day.items():
        prices.sort(key=lambda p: (p['market'], p['ticker']))
        covered = sum(p['status'] != 'unavailable' for p in prices)
        if covered / len(assets) < config.get('min_quote_coverage', 0.9):
            raise RuntimeError(f'Couverture insuffisante au {day} : {covered}/{len(assets)} symboles reconnus. Vérifier symbol_overrides. Aucun brouillon publié.')
    return prices_by_day


def collect_prices(assets, day, config, fetch=get):
    return collect_price_days(assets, [day], config, fetch)[day]


from automation.editorial import compose, make_editorial
from automation.pdf_report import write_pdf


def publication_dates(now, count=2):
    today = now.astimezone(PARIS).date()
    return [(today - timedelta(days=offset), today - timedelta(days=offset + 1)) for offset in range(count)]


def persist_report(report, root=ROOT):
    import tempfile
    import shutil
    target = root / 'reports' / report['date']
    # Commit complete files together; never advance the manifest before the PDF exists.
    with tempfile.TemporaryDirectory() as directory:
        staging = Path(directory)
        (staging / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        (staging / 'publication.txt').write_text(report['text'], encoding='utf-8')
        write_pdf(staging / 'fiche.pdf', report)
        target.parent.mkdir(exist_ok=True)
        shutil.copytree(staging, target, dirs_exist_ok=True)
    editions = []
    for report_path in (root / 'reports').glob('????-??-??/report.json'):
        data = json.loads(report_path.read_text(encoding='utf-8'))
        if data.get('schema_version') == 2 and (report_path.parent / 'fiche.pdf').exists():
            editions.append({'publication_date': data['publication_date'], 'date': data['date'],
                             'path': f"reports/{data['date']}", 'generated_at': data['generated_at']})
    editions.sort(key=lambda item: item['publication_date'], reverse=True)
    (root / 'reports/index.json').write_text(json.dumps({'editions': editions}, indent=2), encoding='utf-8')
    (root / 'reports/latest.json').write_text(json.dumps(editions[0], indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scheduled', action='store_true')
    parser.add_argument('--quick', action='store_true', help='Échantillon de huit actifs liquides, sans clé payante')
    parser.add_argument('--days', type=int, default=2, choices=[1, 2])
    args = parser.parse_args()
    now = datetime.now(UTC)
    if args.scheduled and not due(now):
        print('Hors créneau Paris : aucune génération.')
        return
    pending = []
    for publication, day in publication_dates(now, args.days):
        target = ROOT / 'reports' / day.isoformat()
        existing = json.loads((target / 'report.json').read_text()) if (target / 'report.json').exists() else {}
        if existing.get('schema_version') == 2 and (target / 'fiche.pdf').exists():
            continue
        pending.append((publication, day))
    if not pending:
        print('Les éditions du jour et de la veille sont déjà disponibles.')
        return
    config = json.loads((ROOT / 'automation/config.json').read_text())
    universe, selected = load_universe(config)
    if args.quick:
        symbols = set(config['quick_symbols'])
        selected = [asset for asset in selected if asset['yahoo_symbol'] in symbols]
        if len(selected) != len(symbols):
            raise ValueError('Un actif du périmètre rapide manque dans le CSV.')
        config = {**config, 'daily_scope': 'quick', 'min_quote_coverage': 0.75}
    news_by_day = {day: [] for _, day in pending}
    feed_errors = []
    for feed in config['feeds']:
        try:
            raw = get(feed['url'])
        except Exception as error:
            feed_errors.append({'source': feed['name'], 'error': type(error).__name__})
            print(f"Flux indisponible : {feed['name']} ({type(error).__name__})", flush=True)
            continue
        for day in news_by_day:
            news_by_day[day].extend(parse_news(raw, feed['name'], day, feed['macro_only']))
    for day, news in news_by_day.items():
        news_by_day[day] = sorted({n['url']: n for n in news}.values(), key=lambda n: n['published_at'], reverse=True)
    if len(feed_errors) == len(config['feeds']):
        raise RuntimeError('Tous les flux macro sont indisponibles ; aucun rapport non sourcé produit.')
    prices_by_day = collect_price_days(selected, list(news_by_day), config)
    for publication, day in pending:
        news, prices = news_by_day[day], prices_by_day[day]
        try:
            editorial = make_editorial(day, news, prices)
        except ValueError as error:
            print(f'Édition du {publication} indisponible : {error}')
            continue
        report = {'schema_version': 2, 'publication_date': publication.isoformat(), 'date': day.isoformat(),
                  'generated_at': now.isoformat(), 'timezone': 'Europe/Paris', 'status': 'draft',
                  'universe': {'source': config['universe_csv'], 'total': len(universe), 'tracked': len(selected), 'scope': config['daily_scope']},
                  'news': news, 'prices': prices, 'feed_errors': feed_errors, **editorial}
        persist_report(report)
        print(f"Édition du {publication} : {report['word_count']} mots, PDF de deux pages ; données du {day}.")


if __name__ == '__main__':
    main()
