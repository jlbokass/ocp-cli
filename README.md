# ocp-cli

CLI personnel pour organiser les projets OpenClassrooms DevOps sans multiplier les outils.

OCP centralise la documentation, les audits, le backlog et les sprints dans un workspace Git. Les repositories applicatifs restent indépendants dans `repos/`.

## Prérequis

- Python 3.12 ou supérieur.
- Git avec une identité de commit configurée (`user.name` et `user.email`).
- GitHub CLI (`gh`), authentifié pour créer les repositories, importer les Issues et gérer les Pull Requests.
- Codex CLI installé et authentifié pour les commandes `ocp ai …`.
- `pipx` pour l'installation isolée ci-dessous.

## Installation

Depuis un compte ayant accès au repository :

```bash
git clone https://github.com/jlbokass/ocp-cli.git
cd ocp-cli
pipx install .
ocp --help
```

Pour mettre à jour une installation existante depuis ce clone :

```bash
git pull --ff-only
pipx install --force .
```

## Démarrage rapide

Vérifie l'authentification GitHub avant de créer un workspace :

```bash
gh auth status
# Si nécessaire : gh auth login
```

Depuis le dossier où tu souhaites ranger tes projets :

```bash
ocp init
# Saisir « Mon projet » à l'invite crée le dossier mon-projet/.
cd mon-projet
ocp repo add
ocp status
```

`ocp repo add` demande le nom et l'URL du repository à cloner. Répète la commande pour chaque repository applicatif. `ocp init` tente de créer un repository GitHub privé et de pousser le premier commit ; si cette étape échoue, le workspace local reste disponible.

Dépose ensuite les PDF officiels dans `docs/source/`, puis génère et relis les documents dans cet ordre :

```bash
ocp ai audit          # À répéter pour chaque repository enregistré
ocp ai project-audit
ocp ai cadrage
ocp ai workflow
ocp ai backlog
ocp ai sprint
```

L'aide de chaque commande est accessible avec `--help`, par exemple `ocp ai audit --help`.

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

Depuis le clone du repository :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e . pytest
python -m pytest
```

Organisation du code :

```text
src/ocp/
├── cli.py             # Commandes et interactions terminal
├── project.py         # Workspaces, repositories et opérations Git/GitHub
├── ai.py              # Prompts, génération documentaire et plans de commits
├── backlog_github.py  # Lecture du backlog et import des Issues
└── templates.py       # Fichiers initiaux des workspaces
tests/                 # Tests pytest
```

Le `.gitignore` de la CLI exclut les environnements virtuels, caches Python, artefacts de build et fichiers `.env` locaux. Les fichiers `.env.example` restent versionnables.
