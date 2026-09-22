# ocp-cli

CLI personnel pour organiser les projets OpenClassrooms DevOps sans multiplier les outils.

## Commandes principales

```bash
ocp init
ocp repo add
ocp status
ocp remote set
ocp ai audit
ocp ai project-audit
ocp ai cadrage
ocp ai workflow
ocp ai backlog
ocp backlog import
ocp ai sprint
ocp ai commit
ocp publish
ocp pr create
ocp pr merge
```

## `ocp init`

Crée le workspace, `docs/source/`, `management/sprints/`, initialise Git sur `main`, crée un premier commit et tente de créer automatiquement un repository GitHub privé avec `gh`.

Le `.gitignore` du workspace ignore notamment :

```text
/repos/
.idea/
.vscode/
.DS_Store
.env
.env.local
.env.*.local
```

`.env.example` reste versionnable.

## Sources et documents IA

Les PDF officiels sont déposés manuellement dans `docs/source/`.

```text
ocp ai audit <repo>   -> audits/<repo>/initial-audit.md
ocp ai project-audit  -> audits/project-audit.md
ocp ai cadrage        -> docs/cadrage.md
ocp ai workflow       -> docs/development-workflow.md
ocp ai backlog        -> management/backlog.md
```


## GitHub Issues / Project

Le pilotage opérationnel peut utiliser GitHub Issues + un GitHub Project très léger.
OCP ne modifie pas les champs du Project et évite ainsi les mutations GraphQL répétées.

Configuration manuelle recommandée du Project :

- Board groupé par `Status` ;
- statuts : Backlog, Ready, In Progress, Review, Done ;
- workflow GitHub `Auto-add to project` ciblant le repository workspace avec le filtre `is:issue`.

Une fois ce workflow activé :

```bash
ocp backlog import
```

La commande transforme les items détaillés de `management/backlog.md` en Issues GitHub, de manière idempotente. Elle crée également les labels :

```text
type:spike / type:tech / type:us
priority:p0 ... priority:p3
mvp
area:workspace / area:backend / area:frontend
sprint:001 / sprint:002 / ...
```

Les labels `sprint:*` sont déduits des fichiers `management/sprints/sprint-XXX.md`.
Les Issues déjà présentes sont réutilisées ; l'import peut donc être relancé après une interruption sans créer de doublons.

L'ajout au GitHub Project est volontairement laissé au workflow `Auto-add to project` natif de GitHub.

## Sprints numérotés et immuables

`ocp ai sprint` ne remplace plus un fichier `sprint.md`. Chaque exécution crée le prochain fichier :

```text
management/sprints/
├── sprint-001.md
├── sprint-002.md
└── sprint-003.md
```

Les sprints précédents sont fournis à Codex comme historique. Un item explicitement terminé dans un sprint précédent ne doit pas être replanifié simplement parce que son statut dans le backlog n'a pas encore été synchronisé.

### Migration depuis les versions <= 1.5

Si `management/sprint.md` contient déjà un vrai sprint et qu'aucun sprint numéroté n'existe, OCP refuse de deviner l'historique. Archive manuellement le fichier dans le bon numéro, par exemple :

```bash
mkdir -p management/sprints
mv management/sprint.md management/sprints/sprint-001.md
```

Si `management/sprint.md` a déjà été écrasé, récupère la bonne version depuis Git avant de l'archiver.

## Commits assistés par IA

```bash
ocp ai commit
ocp ai commit workspace
ocp ai commit backend
ocp ai commit frontend
```

Codex analyse le diff, propose des Conventional Commits cohérents et ne pousse rien. Un même fichier n'est pas découpé automatiquement entre plusieurs commits.

## `ocp publish`

`publish` a désormais une seule responsabilité : **pousser des commits déjà créés**.

```bash
ocp publish
```

Équivalent conceptuel :

```bash
git push
```

ou, pour une nouvelle branche :

```bash
git push -u origin <branche>
```

Si des modifications non commitées existent, la commande s'arrête et demande d'utiliser `ocp ai commit workspace`.

## Pull Requests

### Créer une PR

```bash
ocp pr create
```

La commande détecte le **dépôt Git actif** : workspace, backend ou frontend.

Elle :

1. vérifie uniquement que ce dépôt est propre ;
2. pousse sa branche courante si nécessaire ;
3. déduit explicitement `owner/repository` depuis son remote `origin` ;
4. exécute `gh pr ... -R owner/repository`, ce qui évite qu'un fork ouvre accidentellement une PR vers son dépôt parent ;
5. ouvre la PR dans le navigateur.

La commande peut donc être lancée directement depuis `repos/backend` ou `repos/frontend`.

### Merger une PR

Après relecture humaine :

```bash
ocp pr merge
```

La commande cible explicitement le repository GitHub correspondant au dépôt actif, effectue un **rebase merge**, puis réaligne `main` locale sur `origin/main`.

Après un rebase merge GitHub, les SHA peuvent changer. OCP utilise `git cherry` avant le réalignement :

- si les commits locaux sont déjà présents sous forme patch-équivalente sur `origin/main`, `main` est réalignée automatiquement ;
- si `main` contient un commit local réellement unique, OCP s'arrête au lieu de l'écraser.

Le merge n'est jamais déclenché automatiquement par `ocp pr create`.

## Workflow Git recommandé

```text
branche de travail
      ↓
travail
      ↓
ocp ai commit
      ↓
ocp pr create
      ↓
relecture GitHub
      ↓
ocp pr merge
      ↓
main synchronisée
```

`ocp publish` reste disponible lorsqu'on souhaite uniquement pousser une branche sans ouvrir de PR.

## Développement de la CLI

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest
pytest
```
