# Synapse Capital — Le carnet de Mr Camembert

Toutes les activités restent sur la home : menu d’actions à gauche, publications d’aujourd’hui et de la veille directement visibles, univers des actifs dessous, et Mr Camembert à droite avec des réponses à cliquer. Les échanges guidés utilisent les publications et le CSV disponibles, sans clé IA. Pas de barre de saisie ni de lecture vocale. Les animations durent moins de cinq secondes et respectent la préférence de réduction des mouvements.

## Lancer et publier

```sh
python3 -m http.server 3000
```

Site statique, sans compilation. Vercel utilise le preset Other et la racine du dépôt (`vercel.json`). Le dépôt lié à Vercel reçoit les changements sur `main`. L’ancienne route facultative `/api/chat` reste disponible côté serveur, mais la home ne l’appelle plus ; ses variables `OPENAI_API_KEY` / `AI_GATEWAY_API_KEY` ne sont pas nécessaires aux interactions guidées.

## Deux publications, deux dates de séance

L’édition publiée le jour J analyse uniquement la journée J−1, heure de Paris. L’édition de la veille (J−1) analyse J−2. Exemple : la carte du 31 octobre reprend la séance du 30 ; celle du 30 reprend la séance du 29. Les dates figurent sur chaque carte et dans chaque PDF. Un rapport plus ancien n’est jamais présenté à la place d’une de ces deux éditions.

Chaque édition contient :

- **Un texte de moins de 50 mots** : une information datée, quelques actifs autorisés et une lecture conditionnelle. Le bouton Copier copie exactement ce texte, sans les métadonnées de la carte.
- **Un PDF de deux pages** qui reprend le même texte et approfondit une seule information : titre et résumé sourcés, graphique des variations des actifs cités, explication économique, schéma de transmission, hypothèse, éléments de confirmation et de contradiction, références cliquables.
- **Les données sources** complètes dans `report.json`. La section Sources de la home donne accès aux références des deux éditions.

Le texte court est déterministe : aucun modèle IA n’invente de faits. Les sources ne sont jamais traitées comme des instructions. Les transmissions économiques sont des hypothèses, pas des causes établies par les seuls cours. Les titres et résumés RSS peuvent être en anglais ; les analyses et explications sont en français.

### Fichiers produits

Le chemin utilise la **date analysée**, et `publication_date` la date de l’édition :

```text
reports/AAAA-MM-JJ/report.json
reports/AAAA-MM-JJ/publication.txt
reports/AAAA-MM-JJ/fiche.pdf
reports/index.json
reports/latest.json
```

Le schéma de rapport version 2 contient `date`, `publication_date`, `text`, `word_count`, `analysis` (thème, information retenue, actifs illustrés), `news`, `prices` et la couverture de l’univers. Les cartes exigent une date correcte, moins de 50 mots et un PDF présent avant d’activer Copier et Télécharger. Une édition manquante est annoncée comme indisponible. Aucune fausse publication de démonstration n’est exposée.

## Génération quotidienne

`.github/workflows/daily-brief.yml` démarre à **02:00 Europe/Paris** grâce à deux horaires UTC filtrés. Au passage à l’heure d’été, 02:00 n’existe pas : départ à 03:00. Au passage à l’heure d’hiver, seule la première occurrence est retenue. GitHub Actions peut retarder ou omettre une exécution ; l’heure de disponibilité n’est pas garantie.

Le générateur prépare les deux éditions si elles manquent. Les historiques sont téléchargés **une seule fois par actif**, même pour deux dates. Les rapports valides existants sont conservés, les anciennes versions de format sont régénérées, et un rattrapage ne remplace jamais le manifeste du dernier rapport par un plus ancien.

```sh
python3 -m pip install -r automation/requirements.txt
python3 -m automation.daily                # éditions du jour et de la veille
python3 -m automation.daily --days 1       # seulement l’édition du jour
python3 -m automation.daily --scheduled   # respecte le créneau de Paris
```

Activer GitHub Actions avec permission d’écriture sur la branche par défaut. Les changements de données ou du générateur sur `main` déclenchent aussi le workflow. Une exécution manuelle est possible dans Actions. Les protections de branche peuvent empêcher le push du bot. Vercel doit suivre la branche et accepter ces commits ; vérifier le déploiement après la première génération. Les fichiers publiés sont publics avec le site.

## Univers et collecte

Le CSV fourni a été importé dans `data/universe.csv` et `data/universe.json` : **3 382 actifs**, **7 places européennes**, dont 22 marqués Interested. La collecte examine **tous les actifs**, conformément au choix du club. Quelques exemples seulement sont retenus pour le texte et le graphique, selon le thème et les variations observées. Les filtres de la home ne changent pas ce périmètre.

Aucun appel Google Sheets n’est nécessaire. Les noms de membres et pourcentages d’origine sont exclus de l’import public ; ils ne sont pas des preuves de positions détenues. Pour actualiser le CSV :

```sh
python3 -m automation.import_universe '/chemin/vers/le-fichier.csv'
```

Commiter les deux fichiers générés ensemble. Les tickers locaux sont associés à leur place (.PA, .AS, .MI, .OL, .BR, .LS, .IR). Corriger les exceptions dans `symbol_overrides` de `automation/config.json` (clé `Place:Ticker`). Ces correspondances conventionnelles ne garantissent pas la disponibilité de chaque symbole.

Quatre workers et deux requêtes par seconde : environ 30 minutes au minimum pour l’univers complet, dans une limite de job de 60 minutes. Au moins 90 % des symboles doivent être reconnus ; les absents sont comptabilisés. Un refus d’accès ou une limitation du fournisseur interrompt la génération. Yahoo Finance est un endpoint public sans garantie de service ; un fournisseur contractuel peut être nécessaire à cette échelle.

Sources macro : RSS BCE, Federal Reserve et BBC Business (filtre macro pour BBC). Seuls les titres et résumés publiés pendant la journée analysée, heure de Paris, sont retenus. Les flux ne sont ni exhaustifs ni des archives : le rattrapage dépend des éléments encore présents. Un flux inaccessible provoque une erreur ; une journée sans information ni séance ne produit pas de publication. Les variations sont calculées entre clôtures brutes datées de la place, non ajustées des dividendes ou splits. Aucune ancienne séance n’est réétiquetée comme récente.

## Vérification et limites actuelles

```sh
python3 -m unittest discover -s tests -v
node tests/chat.test.cjs
node --check script.js
```

Les tests vérifient le CSV réel, les deux dates de publication (y compris les changements d’heure), la contrainte de mots, la mutualisation des requêtes, la conservation des archives et le PDF de deux pages avec liens et graphiques. Les contrôles navigateur couvrent les deux cartes, copie, téléchargement, navigation sur la home, filtres, réponses guidées et mobile.

**L’accès réel aux flux reste bloqué dans l’environnement cloud (HTTP 403).** Les cartes restent indisponibles tant que la collecte n’a pas réussi ; les données de test servent uniquement aux vérifications locales. Domaines nécessaires : `www.ecb.europa.eu`, `www.federalreserve.gov`, `feeds.bbci.co.uk`, `query1.finance.yahoo.com`. Le runner GitHub a son propre réseau : son exécution reste à vérifier. Le site n’effectue aucune publication automatique sur le compte Nextwise ; un membre relit puis publie le texte et le PDF.
