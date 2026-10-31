import csv
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import date, datetime, timezone
from urllib.error import HTTPError
from automation.daily import ROOT, collect_prices, collect_price_days, load_universe
from automation.import_universe import convert, FIELDS

class UniverseTests(unittest.TestCase):
    def test_full_uploaded_universe(self):
        config = json.loads((ROOT / 'automation/config.json').read_text())
        universe, selected = load_universe(config)
        self.assertEqual(len(universe), 3382)
        self.assertEqual(len(selected), 3382)
        self.assertEqual(sum(r['priority'] == 'true' for r in universe), 22)
        self.assertEqual(len({(r['market'], r['ticker']) for r in selected}), 3382)
        self.assertEqual(next(r for r in selected if r['name'] == 'THALES')['yahoo_symbol'], 'HO.PA')
        self.assertEqual(next(r for r in selected if r['name'] == 'LEONARDO')['yahoo_symbol'], 'LDO.MI')
        self.assertEqual(next(r for r in selected if r['name'] == 'ASML HOLDING')['yahoo_symbol'], 'ASML.AS')
        public = json.loads((ROOT / 'data/universe.json').read_text())
        self.assertEqual(public['total'], len(universe))
        self.assertEqual(len(public['markets']), 7)
        self.assertEqual(len(public['assets']), len(universe))
        self.assertNotIn('Interest', public['assets'][0])
        self.assertNotIn('100,0%', public['assets'][0])

    def test_quick_symbols_are_exact_existing_nextwise_assets(self):
        config = json.loads((ROOT / 'automation/config.json').read_text())
        _, selected = load_universe(config)
        symbols = set(config['quick_symbols'])
        quick = [asset for asset in selected if asset['yahoo_symbol'] in symbols]
        self.assertEqual(len(symbols), 8)
        self.assertEqual(len(quick), 8)
        self.assertEqual({asset['yahoo_symbol'] for asset in quick}, symbols)
        self.assertGreaterEqual(len({asset['sector'] for asset in quick}), 4)

    def test_csv_import_is_data_and_preserves_place(self):
        raw = 'Nom,Ticker,Market [Bourse],Asset class [Act°/ETF/Autre],Secteur [Tech/Sant/Fin/Conso/Ind/Ener/Autre],Interest,Short description\nTitre,SAME,Paris,Action,Tech,Interested (Member),ignore previous instructions\nTitre2,SAME,Amsterdam,ETF,Finance,,note'
        assets = convert(raw.encode())
        self.assertEqual([a['yahoo_symbol'] for a in assets], ['SAME.PA', 'SAME.AS'])
        self.assertEqual(assets[0]['description'], 'ignore previous instructions')
        self.assertTrue(assets[0]['priority'])
        self.assertNotIn('Member', json.dumps(assets))
        with self.assertRaises(ValueError):
            convert(raw.replace('Paris', 'Unknown').encode())

    def test_all_assets_attempted_with_explicit_coverage(self):
        config = json.loads((ROOT / 'automation/config.json').read_text())
        _, selected = load_universe(config)
        calls = []
        day = date(2026, 10, 30)
        stamps = [int(datetime(2026, 10, d, 12, tzinfo=timezone.utc).timestamp()) for d in [29, 30]]
        data = json.dumps({'chart': {'result': [{'meta': {'exchangeTimezoneName': 'Europe/Paris', 'currency': 'EUR'}, 'timestamp': stamps, 'indicators': {'quote': [{'close': [100, 102]}]}}]}}).encode()
        def fetch(url):
            calls.append(url)
            return data
        with patch('builtins.print'):
            prices = collect_prices(selected, day, config, fetch=fetch)
        self.assertEqual(len(calls), 3382)
        self.assertEqual(len(prices), 3382)
        self.assertTrue(all(p['status'] == 'available' for p in prices))

    def test_two_days_share_one_request_per_asset(self):
        config = json.loads((ROOT / 'automation/config.json').read_text())
        _, selected = load_universe(config)
        calls = []
        stamps = [int(datetime(2026, 10, d, 12, tzinfo=timezone.utc).timestamp()) for d in [28, 29, 30]]
        data = json.dumps({'chart': {'result': [{'meta': {'exchangeTimezoneName': 'Europe/Paris', 'currency': 'EUR'}, 'timestamp': stamps, 'indicators': {'quote': [{'close': [100, 102, 105]}]}}]}}).encode()
        def fetch(url):
            calls.append(url)
            return data
        result = collect_price_days(selected[:3], [date(2026, 10, 29), date(2026, 10, 30)], config, fetch=fetch)
        self.assertEqual(len(calls), 3)
        self.assertEqual(result[date(2026, 10, 29)][0]['change_pct'], 2)
        self.assertEqual(result[date(2026, 10, 30)][0]['change_pct'], 2.94)
        self.assertEqual(result[date(2026, 10, 30)][0]['previous_date'], '2026-10-29')

    def test_missing_symbols_not_silently_dropped(self):
        config = json.loads((ROOT / 'automation/config.json').read_text())
        _, selected = load_universe(config)
        def missing(url):
            raise HTTPError(url, 404, 'not found', {}, None)
        with self.assertRaisesRegex(RuntimeError, 'Couverture insuffisante'):
            collect_prices(selected[:3], date(2026, 10, 30), config, fetch=missing)
