# OCP — Ordre d’exécution et journal IA

[English](command-workflow.en.md)

Version : premier lot journal IA et traductions, branche `feat/ai-journal-bilingual-docs`.
Les commandes nouvelles ne sont disponibles sur ton poste qu’après installation de cette branche ou de sa version fusionnée. Elles ne sont pas déjà installées par le simple fait d’ouvrir la PR.

## 1. Installer la version à essayer

Dans ton clone d’OCP, après avoir conservé tes éventuels changements locaux :

```bash
git fetch origin
git switch --track origin/feat/ai-journal-bilingual-docs
pipx install --force .
ocp --help
ocp journal --help
ocp docs --help
```

Si la branche locale existe déjà, utiliser `git switch feat/ai-journal-bilingual-docs`, puis `git pull --ff-only` et réinstaller. Après fusion, revenir sur `main`, faire `git pull --ff-only`, puis `pipx install --force .`.
Prérequis : Python >= 3.12, Git, pipx, GitHub CLI authentifié et Codex CLI authentifié pour les commandes IA. Aucune traduction via une API payante supplémentaire n’est configurée par OCP.

## 2. Ne pas confondre les trois emplacements

- Le dépôt `ocp-cli` contient l’outil et ce guide.
- Le workspace du projet contient `project.yml`, `docs/`, `management/`, `journal/`, etc.
- `repos/backend` et `repos/frontend` sont des dépôts Git indépendants à l’intérieur du workspace.

Lancer les commandes projet depuis le workspace. Les nouvelles commandes `journal` et `docs` trouvent aussi ce workspace depuis ses sous-dossiers. Un chemin donné à `docs translate/review` est relatif à la racine du workspace.

## 3. Créer un workspace et préparer ses sources

```bash
ocp init
# Saisir oc-p3 à l’invite.
cd oc-p3
ocp status
```

`init` crée les fichiers initiaux, initialise Git et tente de créer/pousser un dépôt GitHub privé. Il peut donc effectuer une écriture distante. Ne pas le relancer pour réinitialiser un projet existant.
Déposer les PDF officiels dans `docs/source/`. Le générateur de cadrage extrait les PDF : un DOCX ou un ODT doit être exporté en PDF pour ce circuit, sans perdre son original.
Consigner les arbitrages dans `docs/notes.md`, reporter les choix acceptés dans `docs/cadrage.md` et les consignes mentor dans `mentoring/recommendations.md`.

### Cas d’un nouveau projet sans code : oc-p3

Le pipeline actuel d’OCP a été conçu autour d’audits de dépôts existants. `ocp ai cadrage` exige un audit projet, lui-même dépendant des audits de repositories. Ne pas créer de faux audits ni choisir une stack uniquement pour débloquer cette commande.

Pour P3, commencer par les sources, les décisions, la scorecard et le cadrage rédigé/relu manuellement. Après choix de stack et initialisation des vrais dépôts, les enregistrer avec `ocp repo add`, puis utiliser le pipeline ci-dessous. L’audit d’un squelette doit indiquer qu’aucune fonctionnalité métier n’est encore implémentée.
Les commandes de génération peuvent proposer de remplacer des documents : relire le diff et conserver les arbitrages validés. `docs/notes.md` n’est pas automatiquement une entrée de tous les prompts ; reporter les décisions dans les documents réellement consommés.

## 4. Ordre du pipeline avec des dépôts existants

Chaque commande s’exécute séparément, avec relecture avant la suivante.

| Ordre | Commande | Résultat et action humaine |
|---|---|---|
| 1 | `ocp repo add` | Enregistrer/cloner chaque dépôt réel ; à faire une seule fois par dépôt |
| 2 | `ocp ai audit` | Choisir un dépôt ; répéter pour chacun ; relire les audits |
| 3 | `ocp ai project-audit` | Synthèse des audits ; vérifier les constats |
| 4 | `ocp ai cadrage` | Cadrage à partir des sources PDF et de l’audit ; préserver les décisions acceptées |
| 5 | `ocp ai workflow` | Conventions et organisation ; relire |
| 6 | `ocp ai backlog` | Backlog détaillé et identifiants stables ; relire avant import |
| 7 | `ocp ai sprint` | Nouveau sprint numéroté ; valider les engagements |
| 8 | `ocp backlog import` | Créer/réutiliser les Issues et appliquer les labels, dont ceux du sprint |

On peut importer le backlog avant de préparer le sprint, puis réimporter après pour ses labels. La commande ne pilote pas les champs du GitHub Project et ne constitue pas une synchronisation bidirectionnelle de tous les contenus/statuts.
Configurer un Project avec Backlog, Ready, In Progress, Review, Done. Ajouter les Issues via le workflow Auto-add du Project si disponible, sinon manuellement. Préserver les identifiants US/TECH/SPIKE entre Markdown et Issues. Mettre à jour le bilan de sprint avant de planifier le suivant.

## 5. Ce que fait le journal IA

### Ajout manuel

```bash
ocp journal add --task "Revue du contrat API" --tool "ChatGPT" \
  --request "Vérifier les droits du propriétaire" \
  --contribution "Proposition de contrôles d’accès" \
  --decision "À renseigner" \
  --verification "À renseigner" \
  --references "US-001 ; PR à renseigner"
```

Ajoute une entrée à `journal/ai-journal.md`, avec identifiant unique et date UTC, sans effacer les précédentes. Aucun appel IA n’est fait par `journal add`. Sans `--task`, la tâche est demandée dans le terminal ; les autres options gardent leurs valeurs par défaut. Indiquer l’outil réel, plutôt que conserver Codex CLI par défaut pour un échange ChatGPT.
Après relecture, compléter les champs de l’entrée dans le Markdown : accepté/modifié/rejeté, corrections et preuves de tests réellement exécutés. Le journal n’est pas un registre immuable ni une preuve cryptographique ; Git fournit l’historique des modifications.

### Consultation

```bash
ocp journal list
```

Affiche tout le journal dans le terminal. Ne génère pas de synthèse, ne modifie rien, ne relit pas le code et n’exécute aucun test.

### Enregistrement automatique

`audit`, `project-audit`, `cadrage`, `workflow`, `backlog`, `sprint` ajoutent une entrée après écriture réussie du document. L’entrée contient l’outil, une description générique de la génération et le chemin du résultat. Elle ne capture pas le prompt complet, ne mesure pas le temps gagné et n’atteste aucune revue humaine.

Les champs Décision humaine et Vérifications restent **À renseigner**. Compléter cette entrée après relecture, sans ajouter une deuxième entrée pour le même événement. Un échec de génération ne crée pas une entrée de succès ; un échec d’écriture du journal émet un avertissement sans supprimer le document généré.
Les échanges ChatGPT, le travail dans l’IDE, les tests et `ocp ai commit` ne sont pas capturés automatiquement par cette version : utiliser l’ajout manuel quand ils sont pertinents.

## 6. Traduire et enregistrer une relecture

```bash
ocp docs translate docs/cadrage.md
# Ouvrir et relire docs/cadrage.en.md ; corriger si nécessaire.
ocp docs review docs/cadrage.md
ocp docs status
```

- `translate` appelle Codex et écrit un brouillon anglais voisin. Le français n’est pas modifié. Un registre SHA-256 suit les deux fichiers.
- `review` te demande si **tu as relu et validé** la traduction. Répondre oui enregistre cette déclaration humaine pour l’état actuel. La commande ne fait appel à aucune IA, ne vérifie pas la qualité linguistique et ne valide ni le code ni les décisions métier.
- `status` compare les empreintes. Une traduction peut être synchronisée mais encore à relire. Une modification du français la rend obsolète ; une modification de l’anglais après revue impose une nouvelle revue.

Le chemin passé à `review` est celui du français, pas `cadrage.en.md`. Une source modifiée empêche de valider une traduction périmée.

```bash
ocp docs translate docs/cadrage.md --overwrite
# Relire les changements : l’ancienne traduction est remplacée.
ocp docs review docs/cadrage.md
```

Conserver/commiter d’abord les corrections anglaises importantes avant une retraduction. Les identifiants, commandes et liens doivent rester cohérents ; leur préservation est demandée à l’IA, pas garantie par un validateur structurel dans ce premier lot.
`journal/translations.json` est versionné. Il ne contient que les traductions enregistrées, pas un inventaire exhaustif des Markdown. Traduire le journal en dernier : toute nouvelle entrée invalide sa traduction. Sa propre traduction est suivie dans le registre mais n’ajoute pas une entrée qui invaliderait immédiatement sa source.

## 7. Routine d’une tâche de développement

1. Choisir l’Issue dans GitHub Project et la passer à In Progress.
2. Créer une branche dans chaque dépôt concerné.
3. Développer ; consigner les décisions et les contributions IA ; lancer les tests pertinents.
4. Mettre à jour la documentation française et ses traductions ; relire.
5. Dans le dépôt applicatif concerné, exécuter `ocp ai commit`, puis `ocp pr create`.
6. Dans le workspace, commiter aussi journal, décisions et documentation avec `ocp ai commit workspace`, puis créer sa PR depuis le workspace.
7. Examiner les PR et la CI ; passer les Issues à Review. La revue d’une traduction ne remplace pas la revue d’une PR.
8. Après validation, utiliser `ocp pr merge` depuis le bon dépôt. Cette commande effectue réellement le merge.
9. Mettre le Project et le bilan de sprint à jour ; vérifier `ocp status`.

`ocp publish` pousse des commits existants ; il n’est pas nécessaire avant `ocp pr create`, qui pousse déjà si besoin. Ne pas lancer automatiquement toutes les étapes de publication/merge.

## 8. État de livraison

Le journal, la traduction et la revue sont dans la branche de travail. La publication sélective MkDocs/GitHub Pages n’est pas encore implémentée et aucune commande `ocp docs publish` n’existe. La documentation française reste la référence opérationnelle ; ne pas donner le backlog anglais au parseur d’import français.
