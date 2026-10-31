# Synapse Capital — Le carnet de Mr Synapse

La home met Mr Synapse au premier plan dans un décor de jeu cosy. Les deux éditions et leurs boutons PDF/Copier restent compacts à gauche (sous le personnage sur mobile). Aucun slogan, menu latéral, tableau d’actifs, champ de saisie ni réponses proposées. Le personnage s’exprime uniquement dans sa bulle. Les animations sont brèves et respectent la préférence de réduction des mouvements.

## Sommeil et réveil

Le bouton sous la scène affiche **Bonne nuit** quand Mr Synapse est debout et **Bonjour** quand il est au lit. Le coucher enchaîne sa pose de dos (1,5 s), puis le lit dans une ambiance de nuit. Le réveil utilise sa pose de face (1,3 s), puis retrouve l’image d’origine avec la canne pointée vers le contenu. Les paroles restent dans sa bulle.

`character.js` gère les états et bloque les clics pendant les transitions. L’état stable est conservé localement dans le navigateur. Avec la préférence de réduction des mouvements, le changement de pose est immédiat. Un changement de préférence ou le passage de l’onglet en arrière-plan termine la transition en cours. Si le fichier de poses ne charge pas, le portrait d’origine reste visible.

`assets/synapse-poses.png` est une planche transparente préparée à partir des illustrations fournies (face, dos, lit), utilisée par positions CSS sans bibliothèque d’animation. Le portrait pointant d’origine reste dans `assets/professor.png`.

## Lancer et publier

```sh
python3 -m http.server 3000
```

Site statique, sans compilation. Vercel utilise le preset Other et la racine du dépôt (`vercel.json`). Le dépôt lié à Vercel reçoit les changements sur `main`. L’ancienne route facultative `/api/chat` reste disponible côté serveur, mais la home ne l’appelle plus ; ses variables `OPENAI_API_KEY` / `AI_GATEWAY_API_KEY` ne sont pas nécessaires aux interactions guidées.

## Rapports rédigés par la tâche ChatGPT

La tâche dépose uniquement `content/inbox/AAAA-MM-JJ.json` sur `main`, selon [le contrat de réception](content/README.md) et [l’exemple de format](content/report.example.json). La date du fichier est celle de publication, la journée analysée est la veille. Aucun PDF ni lancement manuel de workflow ne sont demandés à la tâche.

Le build Vercel (`sh scripts/build.sh`) installe les dépendances Python hors du répertoire public et transforme ces JSON en textes et PDF avant la mise en ligne. Le workflow `ingest-chatgpt.yml` versionne ensuite les fichiers générés. Le moteur conserve intégralement les paragraphes de l’auteur et ses références, sans les remplacer par le texte déterministe. Les cotations restent facultatives. Les fichiers invalides font échouer la nouvelle publication ; le dernier déploiement réussi reste en ligne.

La génération quotidienne précédente reste un secours : elle importe d’abord les JSON reçus et ne remplace pas les analyses ChatGPT déjà disponibles. Les deux workflows partagent le même groupe de concurrence pour éviter des écritures simultanées.

## Deux publications, deux dates de séance

L’édition publiée le jour J analyse uniquement la journée J−1, heure de Paris. L’édition de la veille (J−1) analyse J−2. Exemple : la carte du 31 octobre reprend la séance du 30 ; celle du 30 reprend la séance du 29. Les dates figurent sur chaque carte et dans chaque PDF. Un rapport plus ancien n’est jamais présenté à la place d’une de ces deux éditions.

Chaque édition contient :

- **Un texte de moins de 50 mots** : une information datée, quelques actifs autorisés et une lecture conditionnelle. Le bouton Copier copie exactement ce texte, sans les métadonnées de la carte.
- **Un PDF de deux pages** qui reprend le même texte et approfondit une seule information : titre et résumé sourcés, graphique des variations des actifs cités, explication économique, schéma de transmission, hypothèse, éléments de confirmation et de contradiction, références cliquables.
- **Les données sources** complètes dans `report.json`. Chaque carte donne accès à son fichier de sources.

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

Le schéma de rapport version 2 contient `date`, `publication_date`, `text`, `word_count`, `analysis` (thème, information retenue, actifs illustrés), `news`, `prices` et la couverture de l’univers. Les cartes exigent une date correcte et moins de 50 mots pour activer Copier ; Télécharger reste désactivé tant que le PDF n’est pas présent. Une édition manquante est annoncée comme indisponible. Aucune fausse publication de démonstration n’est exposée.

## Génération quotidienne

`.github/workflows/daily-brief.yml` démarre à **02:00 Europe/Paris** grâce à deux horaires UTC filtrés. Au passage à l’heure d’été, 02:00 n’existe pas : départ à 03:00. Au passage à l’heure d’hiver, seule la première occurrence est retenue. Une seconde tentative est planifiée à 06:17 UTC si le point manque encore. GitHub Actions peut retarder ou omettre une exécution ; l’heure de disponibilité n’est pas garantie.

Le générateur prépare les deux éditions si elles manquent. Les historiques sont téléchargés **une seule fois par actif**, même pour deux dates. Les rapports valides existants sont conservés, les anciennes versions de format sont régénérées, et un rattrapage ne remplace jamais le manifeste du dernier rapport par un plus ancien.

```sh
python3 -m pip install -r automation/requirements.txt
python3 -m automation.daily --quick        # éditions rapides du jour et de la veille
python3 -m automation.daily --days 1       # seulement l’édition du jour
python3 -m automation.daily --scheduled   # respecte le créneau de Paris
```

Activer GitHub Actions avec permission d’écriture sur la branche par défaut. Les changements de données ou du générateur sur `main` déclenchent aussi le workflow. Une nouvelle exécution remplace une génération en cours obsolète. Le mode rapide accepte au moins 75 % de cotations reconnues et publie la couverture exacte ; aucun cours manquant n’est inventé. GitHub Actions sur ce dépôt public et les endpoints publics évitent une clé ou un abonnement IA, sans garantie de disponibilité des fournisseurs. Une exécution manuelle est possible dans Actions. Les protections de branche peuvent empêcher le push du bot. Vercel doit suivre la branche et accepter ces commits ; vérifier le déploiement après la première génération. Les fichiers publiés sont publics avec le site.

## Univers et collecte

Le CSV fourni a été importé dans `data/universe.csv` et `data/universe.json` : **3 382 actifs**, **7 places européennes**, dont 22 marqués Interested. Le workflow quotidien utilise désormais `--quick` : huit actifs liquides du CSV (ASML, Thales, Leonardo, Air Liquide, BNP Paribas, L’Oréal, TotalEnergies, Sanofi), pour produire rapidement un texte et un PDF sans clé payante. Une collecte manuelle sans `--quick` conserve le périmètre complet. Quelques exemples seulement sont retenus pour le texte et le graphique, selon le thème et les variations observées. Le CSV reste la référence du générateur, sans tableau d’actifs sur la home.

Aucun appel Google Sheets n’est nécessaire. Les noms de membres et pourcentages d’origine sont exclus de l’import public ; ils ne sont pas des preuves de positions détenues. Pour actualiser le CSV :

```sh
python3 -m automation.import_universe '/chemin/vers/le-fichier.csv'
```

Commiter les deux fichiers générés ensemble. Les tickers locaux sont associés à leur place (.PA, .AS, .MI, .OL, .BR, .LS, .IR). Corriger les exceptions dans `symbol_overrides` de `automation/config.json` (clé `Place:Ticker`). Ces correspondances conventionnelles ne garantissent pas la disponibilité de chaque symbole.

Quatre workers et deux requêtes par seconde : environ 30 minutes au minimum pour l’univers complet, dans une limite de job de 60 minutes. Au moins 90 % des symboles doivent être reconnus ; les absents sont comptabilisés. Un refus d’accès ou une limitation du fournisseur interrompt la génération. Yahoo Finance est un endpoint public sans garantie de service ; un fournisseur contractuel peut être nécessaire à cette échelle.

Sources macro : RSS BCE, Federal Reserve et BBC Business (filtre macro pour BBC). Seuls les titres et résumés publiés pendant la journée analysée, heure de Paris, sont retenus. Les flux ne sont ni exhaustifs ni des archives : le rattrapage dépend des éléments encore présents. Un flux inaccessible est signalé dans `feed_errors` ; les autres sources restent utilisables. Tous les flux indisponibles font échouer la génération ; les jours sans séance peuvent produire une édition explicitement sans nouveau cours si le fournisseur confirme une dernière séance datée. Sans aucune preuve exploitable, aucune édition n’est fabriquée. Les variations sont calculées entre clôtures brutes datées de la place, non ajustées des dividendes ou splits. Aucune ancienne séance n’est réétiquetée comme récente.

## Vérification et limites actuelles

```sh
python3 -m unittest discover -s tests -v
node tests/chat.test.cjs
node --check script.js
```

Les tests vérifient le CSV réel, les deux dates de publication (y compris les changements d’heure), la contrainte de mots, la mutualisation des requêtes, la conservation des archives et le PDF de deux pages avec liens et graphiques. Les contrôles navigateur couvrent les deux cartes, copie, téléchargement, navigation sur la home, filtres, réponses guidées et mobile.

**L’accès réel aux flux reste bloqué dans l’environnement cloud (HTTP 403).** Les cartes restent indisponibles tant que la collecte n’a pas réussi ; les données de test servent uniquement aux vérifications locales. Domaines nécessaires : `www.ecb.europa.eu`, `www.federalreserve.gov`, `feeds.bbci.co.uk`, `query1.finance.yahoo.com`. Le runner GitHub a son propre réseau : son exécution reste à vérifier. Le site n’effectue aucune publication automatique sur le compte Nextwise ; un membre relit puis publie le texte et le PDF.

Première validation réelle : les éditions du 30 et du 31 octobre 2026 ont été produites par GitHub Actions, chacune avec 36 mots, huit cotations reconnues sur huit et un PDF sourcé de deux pages. Les boutons Copier et les deux téléchargements ont été vérifiés avec ces fichiers réels.
