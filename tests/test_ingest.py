import copy
import csv
import json
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from pypdf import PdfReader
from automation.ingest import ingest, prepare, ROOT

NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)


def payload(publication='2026-10-31'):
    day = (date.fromisoformat(publication) - timedelta(days=1)).isoformat()
    paragraphs = [
        'CONTENU AUTEUR CONSERVÉ. Cette publication de test décrit une évolution des ventes sans annoncer de variation boursière. Les entreprises retenues servent uniquement à exercer le format de réception. Le texte est une donnée de test, pas une information de marché destinée au public. Les chiffres éventuels doivent être rapprochés des définitions et de la période retenues dans la source avant toute interprétation. Ce contrôle vérifie la cohérence des informations reçues et de leurs références.',
        'La lecture proposée sépare les faits des hypothèses. Un changement de demande pourrait affecter les marges, mais son effet dépendrait des coûts et du calendrier des contrats. Il faut comparer les annonces aux attentes déjà connues et aux publications des entreprises comparables. Aucun lien mécanique entre une annonce et une performance boursière ne peut être déduit de cette seule observation de test.',
        'Pour confirmer cette lecture, il faudrait retrouver une évolution cohérente du carnet de commandes et des indications de rentabilité. Les prochaines communications peuvent préciser la durée des contrats et leur calendrier de reconnaissance. Les différences de périmètre et les effets de change doivent être vérifiés avant de comparer les périodes. Ce scénario reste une piste conditionnelle et ne constitue pas une prévision de cours.',
        'Une évolution des coûts, une acquisition ou une révision comptable pourrait contredire cette première explication. Les documents complets restent nécessaires pour apprécier ces facteurs. La prochaine publication est un point de contrôle plutôt qu’une certitude sur le sens du marché. Cette analyse de test ne décrit aucune position détenue et ne contient aucune cotation présentée comme vérifiée sans référence consultable.'
    ]
    return {'publication_date': publication, 'date': day, 'title': 'Analyse de test — ne pas publier',
            'text': 'Synthèse de test pour deux actifs autorisés, sans cours inventé.',
            'assets': ['CAP.PA', 'SCR.PA'],
            'sources': [{'id': 's1', 'title': 'Source de test, sans information réelle',
                         'publisher': 'Éditeur de test', 'url': 'https://example.org/test', 'published_at': day + 'T12:00:00+01:00'}],
            'sections': [{'title': heading, 'text': body, 'source_ids': ['s1']} for heading, body in zip(
                ['Faits vérifiés', 'Interprétation', 'Confirmation', 'Contradiction et échéances'], paragraphs)],
            'diagram': ['Annonce', 'Demande attendue', 'Marges', 'À confirmer'], 'quotes': []}


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'data').mkdir()
        (self.root / 'content/inbox').mkdir(parents=True)
        with (ROOT / 'data/universe.csv').open() as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames
            rows = [row for row in reader if row['yahoo_symbol'] in ['CAP.PA', 'SCR.PA']]
        self.assertEqual(len(rows), 2)
        with (self.root / 'data/universe.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def submit(self, data):
        file = self.root / 'content/inbox' / (data['publication_date'] + '.json')
        file.write_text(json.dumps(data), encoding='utf-8')
        return file

    def test_authored_text_pdf_and_sources_survive_without_quotes(self):
        data = payload()
        self.submit(data)
        self.assertEqual(ingest(self.root, NOW), 1)
        target = self.root / 'reports' / data['date']
        report = json.loads((target / 'report.json').read_text())
        self.assertEqual(report['origin'], 'chatgpt')
        self.assertEqual(report['text'], data['text'])
        self.assertEqual(report['authored_analysis']['sections'], data['sections'])
        self.assertEqual((target / 'publication.txt').read_text(), data['text'])
        self.assertTrue(all(p['status'] == 'unavailable' for p in report['prices']))
        pdf = PdfReader(target / 'fiche.pdf')
        self.assertEqual(len(pdf.pages), 2)
        content = ' '.join(page.extract_text() for page in pdf.pages)
        self.assertIn('CONTENU AUTEUR CONSERVÉ', content)
        self.assertIn('Éditeur de test', content)
        self.assertIn('Aucun cours non vérifié', content)
        self.assertGreater(len(pdf.pages[1].get('/Annots', [])), 0)
        self.assertNotIn('Source : Yahoo Finance', content)

    def test_quotes_are_checked_and_percentage_recomputed(self):
        data = payload()
        data['quotes'] = [{'symbol': 'CAP.PA', 'date': data['date'], 'close': 102,
                           'previous_close': 100, 'previous_date': '2026-10-29', 'currency': 'EUR',
                           'source_url': 'https://example.org/verified-price', 'change_pct': 999}]
        report = prepare(data, '2026-10-31.json', self.root, NOW)
        self.assertEqual(report['prices'][0]['change_pct'], 2)
        self.assertEqual(report['prices'][1]['status'], 'unavailable')
        for bad in [float('nan'), float('inf'), -1, True]:
            data['quotes'][0]['close'] = bad
            with self.assertRaises(ValueError):
                prepare(data, '2026-10-31.json', self.root, NOW)

    def test_bad_contracts_rejected(self):
        cases = [
            ('long summary', lambda x: x.update(text='mot ' * 50)),
            ('unknown asset', lambda x: x.update(assets=['FAKE.PA', 'SCR.PA'])),
            ('wrong source day', lambda x: x['sources'][0].update(published_at='2026-10-29T12:00:00+01:00')),
            ('unknown citation', lambda x: x['sections'][0].update(source_ids=['s99'])),
            ('short analysis', lambda x: x['sections'][0].update(text='Court.')),
            ('bad URL', lambda x: x['sources'][0].update(url='javascript:alert(1)')),
            ('future edition', lambda x: x.update(publication_date='2027-01-02', date='2027-01-01')),
            ('duplicate asset', lambda x: x.update(assets=['CAP.PA', 'CAP.PA']))
        ]
        for label, mutate in cases:
            with self.subTest(label):
                data = copy.deepcopy(payload())
                mutate(data)
                with self.assertRaises(ValueError):
                    prepare(data, data['publication_date'] + '.json', self.root, NOW)
        with self.assertRaisesRegex(ValueError, 'nom du fichier'):
            prepare(payload(), 'wrong.json', self.root, NOW)

    def test_invalid_batch_or_pdf_keeps_existing_outputs_unchanged(self):
        first = payload()
        self.submit(first)
        ingest(self.root, NOW)
        latest = self.root / 'reports/latest.json'
        old = latest.read_bytes()
        invalid = payload('2026-11-01')
        invalid['sections'][0]['source_ids'] = ['unknown']
        self.submit(invalid)
        with self.assertRaises(ValueError):
            ingest(self.root, NOW)
        self.assertEqual(latest.read_bytes(), old)
        self.assertFalse((self.root / 'reports/2026-10-31').exists())
        self.submit(payload('2026-11-01'))
        with patch('automation.ingest.write_authored_pdf', side_effect=ValueError('PDF invalide')):
            with self.assertRaises(ValueError):
                ingest(self.root, NOW)
        self.assertEqual(latest.read_bytes(), old)
        self.assertFalse((self.root / 'reports/2026-10-31').exists())

    def test_retries_updates_and_backfills(self):
        newer = payload('2026-11-01')
        self.submit(newer)
        self.assertEqual(ingest(self.root, NOW), 1)
        pdf = self.root / 'reports' / newer['date'] / 'fiche.pdf'
        previous_bytes = pdf.read_bytes()
        self.assertEqual(ingest(self.root, NOW), 0)
        self.assertEqual(pdf.read_bytes(), previous_bytes)
        self.submit(payload('2026-10-31'))
        ingest(self.root, NOW)
        latest = json.loads((self.root / 'reports/latest.json').read_text())
        self.assertEqual(latest['publication_date'], '2026-11-01')
        newer['text'] = 'Synthèse corrigée, uniquement pour tester la mise à jour.'
        self.submit(newer)
        self.assertEqual(ingest(self.root, NOW), 1)
        self.assertEqual((pdf.parent / 'publication.txt').read_text(), newer['text'])


if __name__ == '__main__':
    unittest.main()
