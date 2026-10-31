"""Publish authored ChatGPT reports from committed JSON, without remote calls."""
import csv
import hashlib
import json
import math
import re
import shutil
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from automation.daily import ROOT
from automation.authored_pdf import write_authored_pdf

PARIS = ZoneInfo('Europe/Paris')
VERSION = 1


def text(value, label, limit=12000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{label} : texte non vide requis, maximum {limit} caractères.')
    return value.strip()


def https(value, label):
    value = text(value, label, 2000)
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f'{label} : URL HTTPS publique, sans identifiants, requise.')
    return value


def iso_day(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError(f'{label} : date AAAA-MM-JJ requise.')
    return date.fromisoformat(value)


def sequence(value, label, minimum, maximum):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f'{label} : liste de {minimum} à {maximum} éléments requise.')
    return value


def prepare(payload, filename, root=ROOT, now=None):
    if not isinstance(payload, dict):
        raise ValueError('Le rapport doit être un objet JSON.')
    now = now or datetime.now(timezone.utc)
    publication = iso_day(payload.get('publication_date'), 'publication_date')
    day = iso_day(payload.get('date'), 'date')
    if filename != f'{publication}.json':
        raise ValueError('Le nom du fichier doit être publication_date.json.')
    if publication != day + timedelta(days=1) or publication > now.astimezone(PARIS).date():
        raise ValueError('publication_date doit être le lendemain de date, sans publication future.')
    title = text(payload.get('title'), 'title', 150)
    summary = text(payload.get('text'), 'text', 1500)
    if len(summary.split()) >= 50:
        raise ValueError('text doit contenir strictement moins de 50 mots.')
    with (root / 'data/universe.csv').open(encoding='utf-8-sig', newline='') as stream:
        universe = list(csv.DictReader(stream))
    by_symbol = {asset['yahoo_symbol']: asset for asset in universe}
    symbols = sequence(payload.get('assets'), 'assets', 2, 4)
    if any(not isinstance(symbol, str) or symbol not in by_symbol for symbol in symbols):
        raise ValueError('Chaque symbole de assets doit figurer dans data/universe.csv (yahoo_symbol).')
    if len(set(symbols)) != len(symbols):
        raise ValueError('assets contient des doublons.')

    sources = []
    source_ids = set()
    for source in sequence(payload.get('sources'), 'sources', 1, 8):
        if not isinstance(source, dict):
            raise ValueError('Chaque source doit être un objet.')
        source_id = text(source.get('id'), 'source.id', 16)
        if not re.fullmatch(r's[1-9][0-9]*', source_id) or source_id in source_ids:
            raise ValueError('Les identifiants des sources doivent être uniques : s1, s2…')
        stamp = datetime.fromisoformat(text(source.get('published_at'), 'source.published_at', 40).replace('Z', '+00:00'))
        if stamp.tzinfo is None or stamp.astimezone(PARIS).date() != day:
            raise ValueError('Chaque source d’actualité doit être datée de la journée analysée, heure de Paris.')
        sources.append({'id': source_id, 'title': text(source.get('title'), 'source.title', 300),
                        'source': text(source.get('publisher'), 'source.publisher', 100),
                        'url': https(source.get('url'), 'source.url'), 'published_at': stamp.isoformat()})
        source_ids.add(source_id)
    sections = []
    for section in sequence(payload.get('sections'), 'sections', 4, 6):
        if not isinstance(section, dict):
            raise ValueError('Chaque section doit être un objet.')
        references = sequence(section.get('source_ids'), 'section.source_ids', 1, 8)
        if any(not isinstance(ref, str) or ref not in source_ids for ref in references):
            raise ValueError('Une section cite une source inexistante.')
        sections.append({'title': text(section.get('title'), 'section.title', 100),
                         'text': text(section.get('text'), 'section.text', 8000), 'source_ids': references})
    words = sum(len(section['text'].split()) for section in sections)
    if not 250 <= words <= 700:
        raise ValueError(f'L’analyse doit contenir 250 à 700 mots dans sections (reçu : {words}).')
    diagram = [text(label, 'diagram', 60) for label in sequence(payload.get('diagram'), 'diagram', 4, 4)]

    quotes = {}
    for quote in sequence(payload.get('quotes', []), 'quotes', 0, 4):
        if not isinstance(quote, dict) or quote.get('symbol') not in symbols or quote['symbol'] in quotes:
            raise ValueError('Chaque cotation doit correspondre à un actif sélectionné, sans doublon.')
        if iso_day(quote.get('date'), 'quote.date') != day:
            raise ValueError('Une cotation est datée d’une autre journée.')
        previous = iso_day(quote.get('previous_date'), 'quote.previous_date')
        if previous >= day:
            raise ValueError('quote.previous_date doit précéder la journée analysée.')
        for field in ['close', 'previous_close']:
            value = quote.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f'quote.{field} doit être un nombre positif fini.')
        currency = text(quote.get('currency'), 'quote.currency', 3)
        if not re.fullmatch('[A-Z]{3}', currency):
            raise ValueError('quote.currency : code monétaire de trois lettres requis.')
        quotes[quote['symbol']] = {**{key: quote[key] for key in ['symbol', 'date', 'close', 'previous_close', 'previous_date']}, 'status': 'available',
            'change_pct': round((quote['close'] / quote['previous_close'] - 1) * 100, 2),
            'source_url': https(quote.get('source_url'), 'quote.source_url'), 'currency': currency}
    prices = []
    for symbol in symbols:
        asset = by_symbol[symbol]
        prices.append({**{key: asset[key] for key in ['name', 'ticker', 'market', 'asset_class', 'sector']},
                       **quotes.get(symbol, {'symbol': symbol, 'date': day.isoformat(), 'status': 'unavailable', 'reason': 'not_provided'})})
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    return {'schema_version': 2, 'origin': 'chatgpt', 'input_sha256': digest, 'ingest_version': VERSION,
            'publication_date': publication.isoformat(), 'date': day.isoformat(), 'generated_at': now.isoformat(),
            'timezone': 'Europe/Paris', 'status': 'draft', 'text': summary, 'word_count': len(summary.split()),
            'news': sources, 'prices': prices, 'analysis': None,
            'universe': {'source': 'data/universe.csv', 'total': len(universe), 'tracked': len(symbols), 'scope': 'news-selected'},
            'authored_analysis': {'title': title, 'sections': sections, 'diagram': diagram}}


def ingest(root=ROOT, now=None):
    root = Path(root)
    reports = []
    # Validate the whole batch and build every changed PDF before publishing any output.
    for file in sorted((root / 'content/inbox').glob('*.json')):
        if file.is_symlink() or file.stat().st_size > 100000:
            raise ValueError(f'{file.name} : fichier JSON local de 100 Ko maximum requis.')
        try:
            report = prepare(json.loads(file.read_text(encoding='utf-8')), file.name, root, now)
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError(f'{file.name} : {error}') from error
        target = root / 'reports' / report['date']
        existing = json.loads((target / 'report.json').read_text()) if (target / 'report.json').exists() else {}
        if (existing.get('input_sha256') == report['input_sha256'] and existing.get('ingest_version') == VERSION
                and all((target / name).is_file() for name in ['report.json', 'publication.txt', 'fiche.pdf'])):
            continue
        reports.append(report)
    if not reports:
        print('Aucun nouveau rapport ChatGPT à publier.')
        return 0
    from pypdf import PdfReader
    with tempfile.TemporaryDirectory() as directory:
        staging = Path(directory)
        for report in reports:
            output = staging / report['date']
            output.mkdir()
            (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            (output / 'publication.txt').write_text(report['text'], encoding='utf-8')
            write_authored_pdf(output / 'fiche.pdf', report)
            if len(PdfReader(output / 'fiche.pdf').pages) != 2:
                raise ValueError('Le PDF doit contenir exactement deux pages.')
        for report in reports:
            target = root / 'reports' / report['date']
            shutil.copytree(staging / report['date'], target, dirs_exist_ok=True)
            print(f"Publié : édition du {report['publication_date']}, {report['word_count']} mots, PDF de deux pages.")
    editions = []
    for file in (root / 'reports').glob('????-??-??/report.json'):
        data = json.loads(file.read_text(encoding='utf-8'))
        if data.get('schema_version') == 2 and (file.parent / 'fiche.pdf').is_file():
            editions.append({key: data[key] for key in ['publication_date', 'date', 'generated_at']} | {'path': f"reports/{data['date']}"})
    editions.sort(key=lambda entry: entry['publication_date'], reverse=True)
    (root / 'reports/index.json').write_text(json.dumps({'editions': editions}, indent=2), encoding='utf-8')
    (root / 'reports/latest.json').write_text(json.dumps(editions[0], indent=2), encoding='utf-8')
    return len(reports)


if __name__ == '__main__':
    ingest()
