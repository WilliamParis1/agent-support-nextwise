import json
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from pypdf import PdfReader
from automation.daily import due, parse_news, parse_prices, previous_day, publication_dates, persist_report
from automation.editorial import compose, make_editorial
from automation.pdf_report import write_pdf


def fixture(day=date(2026, 10, 30), long=False):
    news = [{'title': 'Inflation et croissance ' * (30 if long else 1), 'summary': 'Le communiqué détaille les conditions économiques. ' * (25 if long else 1),
             'source': 'Source de test', 'published_at': f'{day.isoformat()}T12:00:00+00:00', 'url': 'https://example.org/publication'}]
    prices = [{'symbol': f'ASSET{i}.PA', 'ticker': f'ASSET{i}', 'name': f'Actif de test {i}', 'sector': 'Tech',
               'date': day.isoformat(), 'status': 'available', 'close': 102 + i, 'previous_close': 100,
               'currency': 'EUR', 'change_pct': 2 + i, 'previous_date': '2026-10-29',
               'source_url': f'https://example.org/quote/{i}'} for i in range(3)]
    editorial = make_editorial(day, news, prices)
    return {'schema_version': 2, 'date': day.isoformat(), 'publication_date': '2026-10-31', 'generated_at': '2026-10-31T01:00:00+00:00', 'news': news, 'prices': prices, **editorial}


class DailyTests(unittest.TestCase):
    def test_schedule_and_dst(self):
        for instant in ['2026-07-02T00:00:00+00:00', '2026-12-02T01:00:00+00:00', '2026-10-25T00:00:00+00:00', '2026-03-29T01:00:00+00:00']:
            self.assertTrue(due(datetime.fromisoformat(instant)), instant)
        self.assertFalse(due(datetime.fromisoformat('2026-10-25T01:00:00+00:00')))
        self.assertEqual(previous_day(datetime.fromisoformat('2026-07-01T23:30:00+00:00')), date(2026, 7, 1))

    def test_publication_and_session_dates_across_dst_and_new_year(self):
        self.assertEqual(publication_dates(datetime.fromisoformat('2026-10-25T01:30:00+00:00')),
                         [(date(2026, 10, 25), date(2026, 10, 24)), (date(2026, 10, 24), date(2026, 10, 23))])
        self.assertEqual(publication_dates(datetime.fromisoformat('2026-12-31T23:30:00+00:00'))[0],
                         (date(2027, 1, 1), date(2026, 12, 31)))

    def test_only_yesterday_in_paris(self):
        feed = b'''<rss><channel>
        <item><title>Inflation yesterday</title><description>&lt;p&gt;A dated summary.&lt;/p&gt;</description><link>https://example.org/one</link><pubDate>Fri, 30 Oct 2026 10:00:00 +0000</pubDate></item>
        <item><title>Inflation today in Paris</title><link>https://example.org/two</link><pubDate>Fri, 30 Oct 2026 23:30:00 +0000</pubDate></item>
        <item><title>Inflation older</title><link>https://example.org/three</link><pubDate>Thu, 29 Oct 2026 12:00:00 +0000</pubDate></item>
        </channel></rss>'''
        news = parse_news(feed, 'test', date(2026, 10, 30), True)
        self.assertEqual([n['title'] for n in news], ['Inflation yesterday'])
        self.assertEqual(news[0]['summary'], 'A dated summary.')

    def test_market_session_and_no_stale_relabel(self):
        stamps = [int(datetime(2026, 10, d, 14, tzinfo=timezone.utc).timestamp()) for d in [29, 30]]
        data = json.dumps({'chart': {'result': [{'meta': {'exchangeTimezoneName': 'America/New_York', 'currency': 'USD'}, 'timestamp': stamps, 'indicators': {'quote': [{'close': [100, 102]}]}}]}}).encode()
        self.assertEqual(parse_prices(data, 'AAPL', date(2026, 10, 30))['change_pct'], 2)
        self.assertEqual(parse_prices(data, 'AAPL', date(2026, 10, 31))['status'], 'no_session')

    def test_short_text_and_dates_are_enforced(self):
        report = fixture(long=True)
        self.assertLess(len(report['text'].split()), 50)
        self.assertEqual(report['word_count'], len(report['text'].split()))
        self.assertIn('ASSET2', report['text'])
        self.assertIn('hypothèse', report['text'])
        with self.assertRaisesRegex(ValueError, 'Actualité hors'):
            make_editorial(date(2026, 10, 29), report['news'], report['prices'])
        with self.assertRaisesRegex(ValueError, 'Cotation hors'):
            make_editorial(date(2026, 10, 29), [], report['prices'])

    def test_no_fabricated_edition_without_evidence(self):
        with self.assertRaisesRegex(ValueError, 'Aucune information'):
            make_editorial(date(2026, 10, 31), [], [{'symbol': 'AAPL', 'status': 'no_session', 'date': '2026-10-31'}])
        text = compose(date(2026, 10, 31), [], [{'symbol': 'AAPL', 'status': 'no_session'}])
        self.assertIn('aucune actualité macro', text)
        self.assertIn('Aucune séance', text)
        self.assertLess(len(text.split()), 50)

    def test_closed_market_day_can_publish_only_with_provider_evidence(self):
        prices = [{'symbol': 'AI.PA', 'date': '2026-10-31', 'status': 'no_session',
                   'last_session_date': '2026-10-30', 'source_url': 'https://finance.yahoo.com/quote/AI.PA/history/'}]
        editorial = make_editorial(date(2026, 10, 31), [], prices)
        self.assertIn('Aucune séance', editorial['text'])
        self.assertLess(editorial['word_count'], 50)

    def test_two_page_pdf_extends_same_summary_and_contains_sources_and_diagrams(self):
        report = fixture(long=True)
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'brief.pdf'
            write_pdf(path, report)
            reader = PdfReader(path)
            self.assertEqual(len(reader.pages), 2)
            text = ' '.join(page.extract_text() for page in reader.pages)
            self.assertIn('VARIATIONS DE CLÔTURE', text)
            self.assertIn('Ce qui pourrait', text)
            self.assertIn('ASSET2', text)
            self.assertIn('Source de test', text)
            self.assertGreater(len(reader.pages[1].get('/Annots', [])), 0)
            self.assertGreater(sum(len(page.get_contents().get_data()) for page in reader.pages), 4000)

    def test_two_editions_are_retained_without_moving_latest_backwards(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            current = fixture()
            prior = fixture(date(2026, 10, 29))
            prior['publication_date'] = '2026-10-30'
            persist_report(current, root)
            persist_report(prior, root)
            manifest = json.loads((root / 'reports/latest.json').read_text())
            self.assertEqual(manifest['publication_date'], '2026-10-31')
            index = json.loads((root / 'reports/index.json').read_text())
            self.assertEqual(len(index['editions']), 2)
            self.assertTrue((root / 'reports/2026-10-29/fiche.pdf').exists())
            self.assertTrue((root / 'reports/2026-10-30/fiche.pdf').exists())


if __name__ == '__main__':
    unittest.main()
