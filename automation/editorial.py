"""Evidence-bound summaries and a deeper, explicitly conditional market reading."""
import re
from datetime import datetime

THEMES = [
    {'key': 'rates', 'label': 'les taux et l’inflation', 'pattern': r'inflat|interest rate|monetary|central bank|taux|price stability',
     'sectors': ['Tech', 'Finance'], 'watch': 'le coût du financement',
     'channel': ['Publication macro', 'Anticipations de taux', 'Coût du capital', 'Valorisation des actifs'],
     'hypothesis': 'Une évolution des anticipations de taux peut modifier le coût de financement et la valeur actualisée des bénéfices futurs. La sensibilité dépend de la dette, de la durée des flux et du pouvoir de fixation des prix. La réaction des banques peut différer de celle des valeurs de croissance.',
     'confirm': 'Une réaction cohérente des rendements obligataires et de plusieurs valeurs sensibles aux taux renforcerait cette piste. Comparer la direction du mouvement à la surprise contenue dans la publication.',
     'challenge': 'Une nouvelle propre à une entreprise, un mouvement de devise ou une hausse déjà anticipée peut expliquer les cours sans lien direct avec la publication macro.'},
    {'key': 'energy', 'label': 'l’énergie et les coûts', 'pattern': r'oil|gas price|energy|petrol|énergie|crude',
     'sectors': ['Ener', 'Ind'], 'watch': 'les coûts et les marges',
     'channel': ['Signal sur l’énergie', 'Coûts de production', 'Transmission aux prix', 'Marges des entreprises'],
     'hypothesis': 'Un changement des prix de l’énergie peut affecter différemment producteurs et consommateurs industriels. Son effet sur les marges dépend des couvertures, des contrats et de la capacité à répercuter les coûts. Une hausse des prix n’implique donc pas une réaction uniforme des actions.',
     'confirm': 'Comparer producteurs d’énergie et entreprises consommatrices, puis vérifier la réaction du pétrole ou du gaz autour de la nouvelle. Les informations sur les marges éclairent la transmission.',
     'challenge': 'Les couvertures de prix, la devise de facturation ou une annonce de résultats peuvent neutraliser ou masquer ce mécanisme. Un seul mouvement de cours ne suffit pas.'},
    {'key': 'trade', 'label': 'le commerce international', 'pattern': r'tariff|trade|export|import|douane|commerce|sanction',
     'sectors': ['Ind', 'Tech', 'Conso'], 'watch': 'les chaînes d’approvisionnement',
     'channel': ['Annonce commerciale', 'Flux et droits de douane', 'Coûts / débouchés', 'Résultats attendus'],
     'hypothesis': 'Une modification des échanges peut changer les coûts d’approvisionnement et l’accès aux marchés. La localisation des ventes et de la production importe davantage que la seule place de cotation. Les effets peuvent se compenser pour une entreprise présente dans plusieurs régions.',
     'confirm': 'Vérifier les zones réellement exposées, les dates d’application et la réaction d’entreprises comparables. Distinguer une annonce politique d’une mesure entrée en vigueur.',
     'challenge': 'Des exemptions, une production locale ou une évolution de change peuvent atténuer le choc. Sans données géographiques, l’exposition d’un titre reste à confirmer.'},
    {'key': 'growth', 'label': 'la croissance et la demande', 'pattern': r'gdp|growth|employment|jobs|unemployment|econom|croissance|emploi|pmi|consum',
     'sectors': ['Ind', 'Conso', 'Finance'], 'watch': 'la demande et les bénéfices',
     'channel': ['Indicateur d’activité', 'Demande attendue', 'Chiffre d’affaires', 'Bénéfices et valorisation'],
     'hypothesis': 'Un indicateur d’activité peut modifier les attentes de demande et de bénéfices. Son effet dépend surtout de l’écart aux anticipations, de la composition sectorielle et du caractère provisoire ou révisé du chiffre. Une économie plus solide peut aussi modifier les attentes de taux.',
     'confirm': 'Comparer valeurs cycliques et défensives, vérifier les composantes de l’indicateur et sa surprise par rapport au consensus. Une réaction partagée par plusieurs titres serait plus informative.',
     'challenge': 'Un chiffre déjà anticipé, une révision statistique ou des annonces d’entreprises simultanées peuvent limiter cette lecture. La séance ne permet pas d’isoler ces facteurs.'},
]
GENERAL = {'key': 'market', 'label': 'les écarts entre actifs', 'sectors': [], 'watch': 'la dispersion des performances',
    'channel': ['Information datée', 'Attentes des investisseurs', 'Réaction des cours', 'Hypothèse à vérifier'],
    'hypothesis': 'Les écarts entre actifs constituent un point de départ pour distinguer un facteur commun d’une information propre à une entreprise. Il faut ensuite comparer des expositions économiques pertinentes, plutôt que déduire un mécanisme du seul classement des variations.',
    'confirm': 'Vérifier si des actifs comparables réagissent dans le même sens, puis examiner les annonces et volumes disponibles à l’heure du mouvement.',
    'challenge': 'Une opération sur titre, une liquidité réduite ou une annonce isolée peut produire une variation inhabituelle. Un classement de clôtures ne décrit pas à lui seul le marché dans son ensemble.'}


def word_count(text):
    return len(text.split())


def excerpt(text, limit=10):
    words = ' '.join(text.split()).split(' ')
    return ' '.join(words[:limit]) + ('…' if len(words) > limit else '')


def choose_analysis(news, prices):
    available = [p for p in prices if p['status'] == 'available']
    focus = next((n for n in news if any(re.search(t['pattern'], n['title'], re.I) for t in THEMES)), news[0] if news else None)
    theme = next((t for t in THEMES if focus and re.search(t['pattern'], focus['title'], re.I)), GENERAL)
    relevant = [p for p in available if p.get('sector') in theme['sectors']]
    ranked = sorted(relevant or available, key=lambda p: abs(p['change_pct']), reverse=True)
    featured = []
    # Distinct issuers where possible, and up to three examples, not an index.
    for price in ranked:
        if all(price.get('name', price['symbol']) != item.get('name', item['symbol']) for item in featured):
            featured.append(price)
        if len(featured) == 3:
            break
    if len(featured) < 2:
        for price in sorted(available, key=lambda p: abs(p['change_pct']), reverse=True):
            if price not in featured:
                featured.append(price)
            if len(featured) == 3:
                break
    return {'theme': {k: v for k, v in theme.items() if k != 'pattern'}, 'focus': focus,
            'featured': featured, 'selection': 'Exemples de variations marquées dans les secteurs associés au thème, sans pondération de portefeuille.'}


def compose(day, news, prices):
    analysis = choose_analysis(news, prices)
    focus, featured, theme = analysis['focus'], analysis['featured'], analysis['theme']
    opening = f'Le {day.strftime("%d/%m")}, '
    if focus:
        opening += f'« {excerpt(focus["title"], 8)} » retient notre attention [1].'
    else:
        opening += 'aucune actualité macro datée dans les flux suivis.'
    if featured:
        pairs = [f"{p.get('ticker', p['symbol'])} ({format(p['change_pct'], '+.2f').replace('.', ',')}%)" for p in featured[:2]]
        moves = 'Variations : ' + ' ; '.join(pairs) + '.'
        outlook = f"Vigilance sur {theme['watch']}. Le lien avec l’annonce reste une hypothèse." if focus else 'Ces écarts invitent à distinguer facteurs communs et nouvelles propres aux titres.'
    else:
        moves = 'Aucune séance disponible pour cette journée.'
        outlook = 'Nous suivons cette information sans lui attribuer de mouvement antérieur.' if focus else 'Aucun cours ancien n’est présenté comme un mouvement du jour.'
    text = ' '.join([opening, moves, outlook])
    if word_count(text) >= 50:
        # Always shorten complete sentences; never cut a claim mid-sentence.
        text = ' '.join([opening, moves, 'Interprétation à confirmer ; sources et détails dans le PDF.'])
    if word_count(text) >= 50:
        raise ValueError('Le texte doit contenir strictement moins de 50 mots.')
    return text


def make_editorial(day, news, prices):
    # The generator never republishes a dated source as another day's evidence.
    from zoneinfo import ZoneInfo
    for item in news:
        stamp = datetime.fromisoformat(item['published_at'].replace('Z', '+00:00'))
        if stamp.tzinfo is None or stamp.astimezone(ZoneInfo('Europe/Paris')).date() != day:
            raise ValueError('Actualité hors de la journée analysée.')
    for price in prices:
        if price.get('date') != day.isoformat():
            raise ValueError('Cotation hors de la journée analysée.')
    if not news and not any(p['status'] == 'available' or (p['status'] == 'no_session' and p.get('last_session_date')) for p in prices):
        raise ValueError('Aucune information ni séance exploitable pour produire cette édition.')
    text = compose(day, news, prices)
    return {'text': text, 'word_count': word_count(text), 'analysis': choose_analysis(news, prices)}
