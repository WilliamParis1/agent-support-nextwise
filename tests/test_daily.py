import json
import unittest
from datetime import date, datetime, timezone
from automation.daily import compose, due, parse_news, parse_prices, previous_day

class DailyTests(unittest.TestCase):
    def test_schedule_and_dst(self):
        for instant in ['2026-07-02T00:00:00+00:00', '2026-12-02T01:00:00+00:00', '2026-10-25T00:00:00+00:00', '2026-03-29T01:00:00+00:00']:
            self.assertTrue(due(datetime.fromisoformat(instant)), instant)
        self.assertFalse(due(datetime.fromisoformat('2026-10-25T01:00:00+00:00')))
        self.assertEqual(previous_day(datetime.fromisoformat('2026-07-01T23:30:00+00:00')), date(2026, 7, 1))

    def test_only_yesterday_in_paris(self):
        feed = b'''<rss><channel>
        <item><title>Inflation yesterday</title><link>https://example.org/one</link><pubDate>Fri, 30 Oct 2026 10:00:00 +0000</pubDate></item>
        <item><title>Inflation today in Paris</title><link>https://example.org/two</link><pubDate>Fri, 30 Oct 2026 23:30:00 +0000</pubDate></item>
        <item><title>Inflation older</title><link>https://example.org/three</link><pubDate>Thu, 29 Oct 2026 12:00:00 +0000</pubDate></item>
        </channel></rss>'''
        news = parse_news(feed, 'test', date(2026, 10, 30), True)
        self.assertEqual([n['title'] for n in news], ['Inflation yesterday'])

    def test_market_session_and_no_stale_relabel(self):
        stamps = [int(datetime(2026, 10, d, 14, tzinfo=timezone.utc).timestamp()) for d in [29, 30]]
        data = json.dumps({'chart': {'result': [{'meta': {'exchangeTimezoneName': 'America/New_York', 'currency': 'USD'}, 'timestamp': stamps, 'indicators': {'quote': [{'close': [100, 102]}]}}]}}).encode()
        self.assertEqual(parse_prices(data, 'AAPL', date(2026, 10, 30))['change_pct'], 2)
        self.assertEqual(parse_prices(data, 'AAPL', date(2026, 10, 31))['status'], 'no_session')

    def test_no_news_or_session_is_explicit(self):
        text = compose(date(2026, 10, 31), [], [{'symbol': 'AAPL', 'status': 'no_session'}])
        self.assertIn('Aucune actualité macro', text)
        self.assertIn('Aucune séance', text)
        self.assertIn('ni nos positions', text)

if __name__ == '__main__':
    unittest.main()

class PDFTests(unittest.TestCase):
    def test_two_page_pdf_with_long_inputs(self):
        from automation.daily import write_pdf
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from pypdf import PdfReader
        news = [{'title': 'Inflation et croissance ' * 30, 'source': 'BCE', 'published_at': '2026-10-30T12:00:00+00:00', 'url': 'https://example.org/' + 'long-url-' * 30} for _ in range(3)]
        prices = [{'symbol': f'ASSET{i}', 'status': 'available', 'close': 102, 'currency': 'EUR', 'change_pct': 2, 'previous_date': '2026-10-29'} for i in range(10)]
        report = {'date': '2026-10-30', 'news': news, 'prices': prices, 'text': compose(date(2026, 10, 30), news, prices)}
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'brief.pdf'
            write_pdf(path, report)
            self.assertEqual(len(PdfReader(path).pages), 2)

class EditionTests(unittest.TestCase):
    def test_summary_under_50_words_and_only_available_assets(self):
        from automation.daily import summarize
        prices = [{'symbol': 'AI.PA', 'status': 'available', 'change_pct': 2},
                  {'symbol': 'BNP.PA', 'status': 'available', 'change_pct': -1},
                  {'symbol': 'OR.PA', 'status': 'available', 'change_pct': 0.5},
                  {'symbol': 'MISSING', 'status': 'unavailable'}]
        text = summarize(date(2026, 10, 30), prices)
        self.assertLess(len(text.split()), 50)
        self.assertIn('contrastés', text)
        for symbol in ['AI.PA', 'BNP.PA', 'OR.PA']:
            self.assertIn(symbol, text)
        self.assertNotIn('MISSING', text)
        self.assertLess(len(summarize(date(2026, 10, 30), []).split()), 50)

    def test_analysis_and_pdf_preserve_source_and_conditional_reading(self):
        from automation.daily import analyze, summarize, write_pdf
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from pypdf import PdfReader
        news = [{'title': 'Interest rate decision', 'source': 'BCE',
                 'published_at': '2026-10-30T12:00:00+00:00', 'url': 'https://example.org/decision'}]
        prices = [{'symbol': 'AI.PA', 'status': 'available', 'close': 102,
                   'currency': 'EUR', 'change_pct': 2, 'previous_date': '2026-10-29',
                   'source_url': 'https://finance.yahoo.com/quote/AI.PA/history/'}]
        analysis = analyze(news, prices)
        self.assertEqual(analysis['source'], news[0])
        self.assertIn('actualisation', analysis['mechanism'])
        self.assertIn('pas une lecture intégrale', analysis['limits'])
        self.assertIsNone(analyze([], prices))
        report = {'date': '2026-10-30', 'news': news, 'prices': prices,
                  'summary': summarize(date(2026, 10, 30), prices), 'analysis': analysis}
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'analysis.pdf'
            write_pdf(path, report)
            pdf = PdfReader(path)
            self.assertEqual(len(pdf.pages), 2)
            text = '\n'.join(page.extract_text() for page in pdf.pages)
            for expected in ['https://example.org/decision', 'AI.PA', 'actualisation', 'Points de vigilance', 'Anticipations', 'Variations entre deux clôtures (%)']:
                self.assertIn(expected, text)
