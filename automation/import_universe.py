"""Import the uploaded competition CSV as data, never as instructions.

Only public universe metadata is retained. Member names and percentage columns
are deliberately excluded: they are not confirmed holdings.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from automation.daily import normalize

ROOT = Path(__file__).resolve().parents[1]
SUFFIXES = {'Paris': '.PA', 'Amsterdam': '.AS', 'Milan': '.MI', 'Oslo': '.OL',
            'Brussels': '.BR', 'Lisbonne': '.LS', 'Dublin': '.IR'}
FIELDS = ['name', 'ticker', 'market', 'yahoo_symbol', 'asset_class', 'sector', 'description', 'priority']
REQUIRED = {'Nom', 'Ticker', 'Market [Bourse]', 'Asset class [Act°/ETF/Autre]',
            'Secteur [Tech/Sant/Fin/Conso/Ind/Ener/Autre]', 'Interest', 'Short description'}


def convert(data):
    rows = csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
    if not REQUIRED.issubset(rows.fieldnames or []):
        raise ValueError('Colonnes manquantes dans le CSV de compétition.')
    assets, seen = [], set()
    for line, row in enumerate(rows, 2):
        ticker, market = row['Ticker'].strip(), row['Market [Bourse]'].strip()
        if not ticker and not market and not row['Nom'].strip():
            continue
        if market not in SUFFIXES:
            raise ValueError(f'Place inconnue ligne {line} : {market}')
        # Dots in a local ticker are preserved. Overrides can be applied in config.
        import re
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.\-]{0,29}', ticker):
            raise ValueError(f'Ticker invalide ligne {line}')
        identity = (market, ticker)
        if identity in seen:
            raise ValueError(f'Doublon ligne {line} : {market}/{ticker}')
        seen.add(identity)
        assets.append({'name': row['Nom'].strip(), 'ticker': ticker, 'market': market,
                       'yahoo_symbol': ticker + SUFFIXES[market],
                       'asset_class': row['Asset class [Act°/ETF/Autre]'].strip(),
                       'sector': row['Secteur [Tech/Sant/Fin/Conso/Ind/Ener/Autre]'].strip(),
                       'description': row['Short description'].strip(),
                       'priority': normalize(row['Interest']).startswith('interested')})
    if not assets:
        raise ValueError('Univers vide')
    return assets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_file', type=Path)
    args = parser.parse_args()
    data = args.csv_file.read_bytes()
    assets = convert(data)
    target = ROOT / 'data'
    target.mkdir(exist_ok=True)
    with (target / 'universe.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({**asset, 'priority': str(asset['priority']).lower()} for asset in assets)
    meta = {'source': args.csv_file.name, 'source_sha256': hashlib.sha256(data).hexdigest(),
            'total': len(assets), 'priorities': sum(a['priority'] for a in assets),
            'markets': sorted({a['market'] for a in assets}),
            'mapping': 'Suffixe Yahoo par place ; correspondances à valider avec le fournisseur.',
            'assets': assets}
    (target / 'universe.json').write_text(json.dumps(meta, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'Import : {meta["total"]} actifs, {meta["priorities"]} priorités, {len(meta["markets"])} places.')


if __name__ == '__main__':
    main()
