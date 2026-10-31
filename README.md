# Synapse Capital — Assistant qualitatif Nextwise

Page d’accueil et guide interactif en français, déployables sur Vercel sans build. La rubrique « Le marché d’hier » affiche le dernier brouillon quotidien, son texte copiable, sa fiche PDF d’une page et les données sourcées. Aucun message n’est publié automatiquement sur Nextwise.

## Démarrage

```sh
python3 -m http.server 3000
```

Le guide initial utilise des questions prédéfinies. Le point quotidien est composé à partir de données réelles selon une trame déterministe, sans modèle IA ni clé OpenAI.

## Activer la génération quotidienne

1. Le workflow `.github/workflows/daily-brief.yml` doit être présent sur la branche par défaut. Activer GitHub Actions et autoriser le workflow à écrire dans le dépôt. Une protection de branche peut empêcher le commit des rapports : adapter les permissions du bot ou le circuit de validation dans ce cas.
2. Le Sheet configuré dans `automation/config.json` doit être lisible sans authentification par le runner. Le lien « partager » ne prouve pas cet accès. Si nécessaire, publier uniquement l’onglet des actifs autorisés en CSV et définir son URL HTTPS dans le secret GitHub Actions `SHEET_CSV_URL`. Ne pas publier des positions ou des données confidentielles. Un Sheet privé nécessite une authentification Google supplémentaire, non implémentée ici.
3. Dans `automation/config.json`, vérifier `sheet_gid` (par défaut `0`) et `ticker_column`. L’auto-détection accepte notamment `Ticker Yahoo`, `Yahoo symbol` ou `Ticker`. Les cellules doivent contenir les symboles Yahoo Finance exacts : `AIR.PA`, `AAPL`, `BTC-USD`… Les ISIN et noms d’entreprises seuls ne suffisent pas. Tous les actifs de cet onglet sont traités, avec une limite explicite de 100 ; les autres onglets ne sont pas lus.
4. Exécuter manuellement « Point qualitatif quotidien » dans l’onglet Actions pour valider les données et générer le premier rapport. Aucune connexion réelle au Sheet ou aux fournisseurs n’a encore été validée depuis l’environnement cloud (restriction réseau).
5. Les rapports sont enregistrés dans `reports/` puis poussés par le workflow sur la branche par défaut. Vercel doit suivre cette branche, accepter ces commits et disposer du preset Other, racine du dépôt, sans build (`vercel.json`). Vérifier le déploiement Vercel après le premier commit automatique. Les rapports deviennent publics avec le site : ne pas y ajouter de positions confidentielles.

La planification vise **02:00 Europe/Paris**, avec deux déclenchements UTC et filtrage été/hiver. Au passage à l’heure d’été, 02:00 n’existe pas : génération à 03:00. Au passage à l’heure d’hiver, seule la première occurrence est retenue. GitHub Actions peut retarder ou omettre des exécutions ; il ne garantit pas une livraison à la minute. Une exécution manuelle permet de reprendre le rapport de la veille. L’idempotence par date et la concurrence empêchent les doublons. Un dépôt public inactif peut voir ses workflows planifiés désactivés après 60 jours.

## Périmètre éditorial et qualité des données

- Le Sheet décrit **les actifs autorisés**, pas un portefeuille. Aucune position, performance du club ou opération réalisée n’est inventée.
- Seuls les titres RSS datés de la journée civile précédente en Europe/Paris sont retenus. Flux suivis : BCE, Federal Reserve et BBC Business (filtrage macro par mots-clés pour ce dernier). Couverture limitée et non exhaustive, sans lecture intégrale des articles. Les flux RSS ne constituent pas une archive et peuvent omettre des publications.
- Les variations comparent les clôtures brutes du jour de séance précédent à celles de la journée analysée. Les dates de séance sont celles de la place de cotation. Aucun ancien cours n’est réétiqueté « hier » le week-end ou un jour férié. Dividendes, splits et décalages horaires peuvent affecter l’interprétation ; les cours ne sont pas ajustés. Le lien macro/cours est présenté comme une piste à vérifier, jamais une cause prouvée.
- Le texte cite au plus trois titres macro et quatre mouvements ; le PDF affiche au plus huit mouvements. Le JSON contient toutes les données retenues et les liens sources. Absence de nouvelles ou de séance signalée explicitement.
- Une erreur d’accès, un symbole inconnu ou un flux malformé fait échouer l’exécution ; aucun nouveau rapport n’est publié. Yahoo Finance est un endpoint public sans garantie de service : remplacer le fournisseur si nécessaire pour un usage durable. Le site date le dernier rapport et signale s’il ne couvre pas la veille.
- Relire le brouillon et la fiche avant publication ; les points de la compétition dépendent de ses règles et ne sont pas garantis.

## Vérification locale

```sh
python3 -m pip install -r automation/requirements.txt
python3 -m unittest discover -s tests -v
node --check script.js
python3 automation/daily.py  # nécessite l’accès aux sources réelles
```

Les tests utilisent des données fictives pour vérifier dates, changements d’heure, parsing des actifs, absence de cours périmés et rendu PDF. Ils ne remplacent pas la validation réelle des fournisseurs.
