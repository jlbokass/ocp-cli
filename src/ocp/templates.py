from __future__ import annotations

README_TEMPLATE = """# {project_name}

Workspace de travail OpenClassrooms.

## Navigation

- [Sources officielles](docs/source/)
- [Note de cadrage](docs/cadrage.md)
- [Workflow de développement](docs/development-workflow.md)
- [Architecture](docs/architecture.md)
- [Notes](docs/notes.md)
- [Backlog](management/backlog.md)
- [Sprints](management/sprints/)
- [Rétrospective](management/retrospective.md)
- [Point mentor](mentoring/current.md)
- [Recommandations mentor](mentoring/recommendations.md)
- [Journal IA](journal/ai-journal.md)
- [Préparation évaluation](evaluation/preparation.md)

## Repositories

<!-- ocp:repositories:start -->
_Aucun repository enregistré._
<!-- ocp:repositories:end -->
"""

PROJECT_YAML_TEMPLATE = """project:
  id: {project_id}
  name: {project_name}

methodology: scrum

repositories: []
"""

GITIGNORE_TEMPLATE = """# Repositories applicatifs indépendants
/repos/

# IDE / éditeurs
.idea/
.vscode/

# Environnement local / secrets
.env
.env.local
.env.*.local
!.env.example

# Python
__pycache__/
*.py[cod]
.venv/

# macOS
.DS_Store
"""

MARKDOWN_FILES = {
    "docs/source/.gitkeep": "",
    "docs/cadrage.md": "# Note de cadrage\n",
    "docs/development-workflow.md": "# Workflow de développement\n",
    "docs/architecture.md": "# Architecture\n",
    "docs/notes.md": "# Notes\n",
    "management/backlog.md": "# Backlog\n",
    "management/sprints/.gitkeep": "",
    "management/retrospective.md": "# Rétrospective\n",
    "mentoring/current.md": "# Point mentor\n",
    "mentoring/recommendations.md": "# Recommandations mentor\n\n> Ajouter ici les recommandations du mentor en conservant leur origine et leur statut.\n\n## Modèle\n\n### REC-MENTOR-001 — Titre\n- **Date :**\n- **Statut :** proposée\n- **Recommandation :**\n- **Contexte :**\n- **Décision :** à analyser\n",
    "journal/ai-journal.md": "# Journal IA\n",
    "evaluation/preparation.md": "# Préparation de l’évaluation\n",
    "audits/.gitkeep": "",
}
