# Synapse Capital — Mr Camembert

La page d’accueil regroupe toutes les activités : menu d’actions à gauche, éditions du jour et de la veille, analyse PDF, réponses guidées à Mr Camembert et recherche dans l’univers Nextwise. Aucune fenêtre modale ni fonction « Écouter ». Le menu devient une liste compacte sur mobile.

## Lancer le site

```sh
python3 -m http.server 3000
```

Site statique, sans build. La conversation utilise une clé IA côté serveur ; le serveur Python ne lance pas l’API. `vercel.json` configure Vercel (preset Other, racine du dépôt). La préférence système de réduction des animations est respectée. Aucun contrôle manuel d’animation ni champ de conversation sur l’accueil. Les réponses proposées fonctionnent localement à partir du rapport disponible ; aucun appel IA n’est nécessaire pour ces interactions.

## Deux éditions sur l’accueil

L’édition d’aujourd’hui analyse la journée civile d’hier ; celle de la veille analyse la journée d’avant-hier, en heure de Paris. La page charge directement `reports/AAAA-MM-JJ/report.json` pour ces deux journées, sans substituer un ancien rapport. Les éditions absentes ou incorrectement datées sont signalées.

Le générateur produit `summary` (également dans `text` et `publication.txt`) : **moins de 50 mots**, à partir d’au plus trois actifs Nextwise dont les variations disponibles sont les plus marquées. Les variations comparent deux clôtures de séances consécutives ; cet échantillon ne représente pas tout le marché. Sans séance exploitable, la synthèse le dit explicitement.

`analysis` approfondit le titre de l’actualité la plus récente de la journée : source et date, mécanismes conditionnels, points à vérifier, limites, puis trois actifs à observer. Il ne prétend pas résumer l’article intégral ni prouver un lien avec les variations. `fiche.pdf` approfondit la synthèse sur deux pages : graphique des variations des mêmes actifs et méthode de lecture, puis mécanismes conditionnels, schéma de transmission et liens des sources. Sans actualité sourcée, le PDF indique cette limite et ne fabrique aucune explication d’actualité. Les deux éditions ont chacune un bouton de téléchargement et un bouton Copier ; ils restent désactivés quand les fichiers correspondants manquent. Le bouton de copie porte sur la synthèse courte.

Pour rattraper une édition manquante (réseau fournisseurs requis, collecte complète potentiellement longue) :

```sh
python3 automation/daily.py --date 2026-10-29
```

`--date` désigne la journée analysée, obligatoirement terminée. Une génération historique ne recule pas `reports/latest.json`. Les rapports existants ne sont pas écrasés automatiquement. Les anciens rapports sans synthèse courte doivent être régénérés séparément pour ce nouvel affichage.

## API de conversation (conservée pour intégration)

La route serveur Vercel `/api/chat` utilise `gpt-4.1-mini`. Ajouter **OPENAI_API_KEY** dans les variables du projet Vercel, puis redéployer. Une clé **AI_GATEWAY_API_KEY** est aussi acceptée via Vercel AI Gateway (prioritaire si les deux sont définies). Aucune clé n’est incluse dans le navigateur, le dépôt ou les logs. `.env.example` ne contient que les noms.

L’agent reçoit une recherche limitée à 25 actifs pertinents dans l’univers et le dernier rapport disponible. Il doit signaler l’absence ou l’ancienneté du rapport, distinguer faits et interprétations et ne pas inventer de positions. L’historique des 5 derniers échanges est gardé uniquement dans la page ; les messages sont transmis au fournisseur IA. Aucun historique serveur n’est enregistré par l’application. Une limite de 20 requêtes par 10 minutes et par adresse IP est appliquée en mémoire par instance ; elle ne constitue pas un quota distribué ou un plafond de dépenses. Les réponses sont affichées comme du texte, sans HTML exécutable.

Si aucune clé n’est configurée, le site affiche un message d’activation explicite, sans simuler de réponse IA. La conversation n’est pas encore validée avec un fournisseur réel. Le serveur statique Python ne lance pas l’API : la conversation réelle nécessite Vercel (ou `vercel dev` avec les variables locales).

```sh
npm test
```

## Univers CSV intégré

Le fichier fourni **Synapse Capital Market Analysis - Main.csv** a été importé : **3 382 actifs**, **7 places**, dont **22 marqués Interested**. À la demande du club, la collecte quotidienne examine **les 3 382 actifs**, pas seulement ces priorités.

- `data/universe.csv` : source normalisée, versionnée, lue directement par le générateur. Aucun appel Google Sheets et aucun secret Google ne sont nécessaires.
- `data/universe.json` : copie pour la recherche sur le site, avec empreinte SHA-256 du fichier source pour la traçabilité.
- Les noms des membres et les pourcentages du CSV ne sont pas publiés et ne sont pas interprétés comme des positions détenues. Les métadonnées descriptives ne sont jamais utilisées comme des instructions.
- Les tickers sont associés à leur place : Paris `.PA`, Amsterdam `.AS`, Milan `.MI`, Oslo `.OL`, Brussels `.BR`, Lisbonne `.LS`, Dublin `.IR`. Ce sont des correspondances conventionnelles, pas une validation de disponibilité Yahoo. Corriger les exceptions via `symbol_overrides` dans `automation/config.json` (clé `Place:Ticker`, valeur symbole Yahoo). Aucun ticker d’une autre place n’est substitué automatiquement.
- Pour importer une nouvelle version du CSV d’origine :

```sh
python3 -m automation.import_universe '/chemin/vers/le-fichier.csv'
```

Cette commande régénère les deux fichiers `data/universe.*`. Commiter les deux ensemble. Les filtres de recherche de la page n’affectent pas le périmètre quotidien.

## Génération à 2 h, heure de Paris

`.github/workflows/daily-brief.yml` doit être sur la branche par défaut. Activer GitHub Actions avec permission d’écriture dans le dépôt ; les protections de branche peuvent demander un circuit de validation supplémentaire.

Le workflow vise **02:00 Europe/Paris**. Deux horaires UTC sont filtrés pour tenir compte de l’heure d’été/hiver. Au passage à l’heure d’été, 02:00 n’existe pas : départ à 03:00. Au passage à l’heure d’hiver, seule la première occurrence est utilisée. GitHub peut retarder ou omettre une exécution ; la disponibilité à 02:00 précises n’est pas garantie. Le parcours complet de 3 382 actifs prend environ 30 minutes au minimum à deux requêtes par seconde, davantage selon les réponses. Le job est limité à 60 minutes. Le workflow peut être relancé manuellement pour la veille. Une modification des données ou du générateur sur `main` déclenche aussi une génération (sauf si le rapport de la veille existe déjà).

La collecte utilise quatre workers, un débit global de deux requêtes par seconde et des tentatives limitées. Tous les actifs sont examinés. Un symbole absent est comptabilisé comme indisponible, sans être remplacé par un autre actif. Au moins **90 % des symboles doivent être reconnus** pour publier un brouillon ; la couverture et les indisponibilités sont explicites dans le texte et le JSON. Un refus d’accès ou une limitation du fournisseur fait échouer la génération sans remplacer le dernier rapport. Yahoo Finance est un endpoint public sans garantie de service : à cette échelle, un fournisseur de données contractuel peut devenir nécessaire. Les correspondances réelles et l’exécution complète ne sont pas encore validées.

Après une exécution réussie :

- `reports/AAAA-MM-JJ/publication.txt` : texte du brouillon ;
- `reports/AAAA-MM-JJ/fiche.pdf` : pièce jointe A4 de deux pages avec identité du club ;
- `reports/AAAA-MM-JJ/report.json` : couverture, métadonnées, cotations et sources ;
- `reports/latest.json` : dernier rapport disponible, affiché sur le site.

Le workflow pousse les rapports sur la branche par défaut. Vercel doit suivre cette branche et accepter les commits du bot. Vérifier le déploiement après la première génération. Les rapports sont publics avec le site. Le site signale les rapports anciens ; il ne présente pas un ancien rapport comme le point de la veille. Les sorties sont idempotentes par date, la concurrence est sérialisée. Sur un dépôt public, les workflows planifiés peuvent être désactivés après 60 jours d’inactivité.

## Règles éditoriales

- Journée analysée : veille civile, **Europe/Paris uniquement**. Pas de nouvelles plus anciennes réutilisées.
- Macro : titres des RSS BCE, Federal Reserve et BBC Business (filtre de mots-clés macro pour BBC). Couverture non exhaustive, sans lecture intégrale des articles ; certains titres peuvent rester en anglais. Un flux indisponible fait échouer le rapport, une journée sans publication est signalée.
- Marchés : variations entre la clôture brute de la journée analysée et la précédente clôture de séance, dates locales des places. Aucun ancien cours n’est réétiqueté « hier » les jours sans séance. Splits et dividendes peuvent affecter ces cours non ajustés.
- Trame déterministe fondée sur les données, sans modèle IA. La synthèse cite jusqu’à trois mouvements ; le PDF approfondit une information et présente jusqu’à trois actifs. Toutes les données disponibles restent dans le JSON.
- Les liens entre nouvelles macro et prix sont des pistes de lecture, pas des causalités prouvées. Aucune position ou opération du club n’est inventée à partir de la liste autorisée. Relire et adapter avant publication ; les points dépendent des règles Nextwise.
- Aucun envoi ni publication automatique sur le compte club : un membre copie le texte et télécharge la fiche.

## Vérifications

```sh
python3 -m pip install -r automation/requirements.txt
python3 -m unittest discover -s tests -v
node --check script.js
python3 automation/daily.py  # nécessite l’accès aux flux et aux cours réels
```

Les tests valident l’univers réel de 3 382 actifs, l’import, les places, la collecte complète avec réponses simulées, le seuil de couverture, les dates, les changements d’heure et le PDF de deux pages. Ils ne valident pas l’accès réel aux fournisseurs, encore bloqué par la politique réseau du cloud au moment de l’intégration. Les domaines requis sont `www.ecb.europa.eu`, `www.federalreserve.gov`, `feeds.bbci.co.uk`, `query1.finance.yahoo.com`. Le runner GitHub utilise son propre réseau ; un premier lancement manuel dans Actions permet de diagnostiquer les accès réels.
