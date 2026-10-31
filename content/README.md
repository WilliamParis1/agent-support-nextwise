# Publier une analyse sur Mr Synapse

Le seul fichier que la tâche ChatGPT doit écrire est `content/inbox/AAAA-MM-JJ.json`, sur la branche **main** de `WilliamParis1/agent-support-nextwise`. Le nom utilise la date de **publication** en heure de Paris. `date` désigne la journée analysée, la veille de `publication_date`.

Exemple : `content/inbox/2026-10-31.json` contient `publication_date: "2026-10-31"` et `date: "2026-10-30"`.

Le commit déclenche automatiquement :

1. Le déploiement Vercel : `scripts/build.sh` vérifie le JSON et produit le texte, les données et le PDF dans `reports/DATE_ANALYSEE/` avant la mise en ligne.
2. Le workflow **Publier un rapport ChatGPT** : il réalise les mêmes contrôles et versionne les fichiers générés dans GitHub.

**Aucun déclenchement manuel de workflow, PDF téléversé, clé API ou modification de l’interface n’est nécessaire.** Les rapports du jour et de la veille sont lus automatiquement par la homepage. Les analyses ChatGPT remplacent l’éventuel rapport automatique de la même journée ; une génération automatique ultérieure ne les écrase pas.

## Contrat JSON

Consulter `content/report.example.json` pour la structure. Ce fichier est un exemple de format, pas une actualité et pas un fichier à publier tel quel. Seuls les fichiers `.json` de `content/inbox/` sont importés.

| Champ | Contenu |
| --- | --- |
| `publication_date` | Date de l’édition, `AAAA-MM-JJ`, pas dans le futur. |
| `date` | Journée civile analysée, exactement la veille, en heure de Paris. |
| `title` | Titre concret de l’analyse, 150 caractères maximum. |
| `text` | Synthèse française autonome, de 1 à **49 mots**, sans Markdown. |
| `assets` | **2 à 4** valeurs uniques du champ `yahoo_symbol` dans `data/universe.csv`. Exemple : `CAP.PA`, `SCR.PA`. |
| `sources` | **1 à 8** références d’actualité publiées pendant `date`. Chaque référence contient `id` (`s1`, `s2`…), `title`, `publisher`, `url` HTTPS et `published_at` au format ISO 8601 avec fuseau. |
| `sections` | **4 à 6** sections, **250 à 700 mots au total** : faits, interprétation, confirmation, contradiction, échéances. Chacune contient `title`, `text` et `source_ids`, une liste d’identifiants définis dans `sources`. Les paragraphes et les nuances sont conservés dans le PDF. |
| `diagram` | Exactement **4** libellés courts pour le schéma de transmission proposé. Maximum 60 caractères chacun. |
| `quotes` | Liste facultative, vide si les cours ne sont pas vérifiés. |

Une cotation facultative contient : `symbol`, `date`, `close`, `previous_date`, `previous_close`, `currency` (ex. `EUR`), `source_url` HTTPS. Sa date doit être celle de la journée analysée, et `previous_date` celle d’une séance précédente. La variation est recalculée à partir des deux clôtures : ne pas envoyer de variation inventée. Les actifs sans cotation vérifiée sont analysables sur la base de leurs annonces, sans chiffre de cours ajouté. Le PDF utilise alors un schéma plutôt qu’un graphique de prix.

Les champs numériques JSON doivent être finis (pas de NaN/Infinity). Les sources et citations doivent être cohérentes. Les contrôles automatiques vérifient la structure, les dates, l’appartenance à l’univers et les calculs ; **la recherche et la vérification des faits restent la responsabilité de l’auteur du rapport**.

Les fichiers sont publics avec le dépôt et le site. Ne jamais inclure de clé, identifiant privé ou donnée confidentielle.

## Modifier une édition

Mettre à jour le même fichier JSON, puis commiter sur `main`. Le PDF et les fichiers du site seront régénérés. Un fichier inchangé ne provoque pas de réécriture des rapports. Les éditions historiques restent disponibles et un rattrapage ne recule jamais `reports/latest.json`.

Si un fichier est invalide, le workflow et le déploiement échouent avec une erreur précise ; le dernier déploiement Vercel réussi reste disponible. Corriger le JSON et le commiter de nouveau. Ne pas déclarer le PDF publié sur la seule base du commit d’entrée.

## Vérifier

Après publication, contrôler les fichiers `reports/DATE_ANALYSEE/report.json`, `publication.txt` et `fiche.pdf`, et le succès du déploiement Vercel. L’empreinte `input_sha256` du rapport identifie la version du JSON importée. `origin: "chatgpt"` distingue cette analyse du texte déterministe de secours.

En local : `python -m automation.ingest`. La commande ne fait aucun appel réseau et n’a pas besoin de clé IA. Le build Vercel installe uniquement les dépendances Python déclarées, puis exécute cette même commande.
