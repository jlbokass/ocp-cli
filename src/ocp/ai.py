from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

try:
    from pypdf import PdfReader
except ModuleNotFoundError:  # dépendance ajoutée après une installation editable existante
    PdfReader = None


class AiAuditError(Exception):
    pass


class CodexNotFoundError(AiAuditError):
    pass


class AuditAlreadyExistsError(AiAuditError):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Le rapport existe déjà : {path}")




class MissingSourceDocumentsError(AiAuditError):
    pass


class MissingProjectAuditError(AiAuditError):
    pass


class MissingCadrageError(AiAuditError):
    pass


class MissingWorkflowError(AiAuditError):
    pass


class MissingBacklogError(AiAuditError):
    pass


class LegacySprintFileError(AiAuditError):
    pass


class SourceDocumentError(AiAuditError):
    pass


class MissingRepositoryAuditsError(AiAuditError):
    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        joined = ", ".join(missing)
        super().__init__(
            "Audit projet impossible : les audits initiaux suivants sont manquants : "
            f"{joined}. Lance d'abord 'ocp ai audit <repository>'."
        )


def build_audit_prompt(repository_name: str) -> str:
    """Construit le prompt stable utilisé pour l'audit technique initial."""
    return f"""Tu réalises l'audit technique initial du repository « {repository_name} ».

OBJECTIF
Produire un rapport technique factuel, exploitable pour planifier le travail DevOps/DevSecOps. Tu dois inspecter le repository courant en profondeur, sans le modifier.

RÈGLES D'EXÉCUTION
- Travaille uniquement en lecture seule.
- Ne modifie, ne crée et ne supprime aucun fichier du repository.
- N'installe aucune dépendance.
- N'utilise pas le réseau.
- Tu peux exécuter des commandes locales d'inspection en lecture seule.
- N'exécute des tests, linters ou analyseurs existants que s'ils sont déjà disponibles et si leur exécution est manifestement sans effet de bord. Sinon, indique qu'ils n'ont pas été exécutés.
- Ne déduis pas une vulnérabilité, une version ou une configuration sans preuve.
- Pour chaque constat important, donne une preuve précise : chemin de fichier, ligne/section quand possible, ou commande observée.
- Distingue clairement : Observé / Inféré / Non vérifié.
- Si une information manque, écris « Non vérifié » au lieu de l'inventer.
- Le rapport final doit être rédigé en français.
- Retourne uniquement le Markdown du rapport, sans bloc ``` autour du document.

FORMAT ATTENDU
# Audit technique — {repository_name}

## 1. Résumé exécutif
Résumé court de l'état technique du repository et des principaux points d'attention.

## 2. Identification technique
Langages, frameworks, runtimes, versions déclarées, gestionnaires de paquets, principaux fichiers de configuration.

## 3. Architecture et structure du repository
Organisation des dossiers, points d'entrée, composants, architecture détectée et responsabilités principales.

## 4. Build, installation et exécution
Prérequis, scripts, commandes disponibles, processus de build/démarrage et éléments non vérifiables.

## 5. Dépendances
Manifestes, lock files, cohérence des versions, dépendances importantes, obsolescence uniquement si démontrable localement.

## 6. Tests
Frameworks, types de tests, commandes, organisation, couverture si elle est réellement disponible, lacunes observées.

## 7. Qualité de code et analyse statique
Lint, formatage, typage, analyse statique, conventions, duplication ou dette technique objectivement visible.

## 8. Sécurité / DevSecOps
Secrets potentiels, fichiers sensibles, mauvaises pratiques, permissions/configurations dangereuses, scanners déjà présents. Ne revendique aucune CVE sans preuve locale.

## 9. Docker et conteneurisation
Dockerfile(s), .dockerignore, Compose, images de base, versions, utilisateur, multi-stage, healthcheck, secrets, volumes, réseau et bonnes pratiques observées.

## 10. CI/CD
GitHub Actions, GitLab CI ou autre. Décrire les pipelines, étapes, tests, build, sécurité, artefacts, déploiement et lacunes observées.

## 11. Git et hygiène du repository
.gitignore, branches/HEAD visibles localement, historique utile, fichiers indésirables versionnés, conventions observables.

## 12. Configuration et environnements
Variables d'environnement, fichiers .env, configuration dev/test/prod, gestion des secrets et reproductibilité.

## 13. Observabilité et exploitation
Logs, health checks, métriques, traces, gestion des erreurs, readiness/liveness si applicable.

## 14. Performance, fiabilité et maintenabilité
Risques techniques visibles concernant performance, résilience, concurrence, stockage, dette ou maintenabilité.

## 15. Constats techniques prioritaires
Pour chaque constat significatif, utilise cette structure :

### [ID] Titre du constat
- **Sévérité :** Critique | Haute | Moyenne | Faible | Information
- **Statut :** Observé | Inféré | Non vérifié
- **Preuve :** `chemin:ligne` ou résultat d'inspection
- **Constat :** ...
- **Impact :** ...
- **Action proposée :** ...

Ne crée pas de constat artificiel pour remplir la section.

## 16. Points à investiguer
Liste des questions techniques encore ouvertes et pourquoi elles nécessitent une vérification supplémentaire.

## 17. Plan d'action proposé
Plan court et ordonné. Sépare :
1. actions immédiates,
2. actions avant CI/CD,
3. améliorations ultérieures.

CONTRAINTE DE QUALITÉ
Le rapport doit être spécifique à CE repository. Évite les conseils DevOps génériques qui ne sont pas reliés à une preuve ou à une lacune réellement constatée.
"""


def build_project_audit_prompt(repositories: list[dict]) -> str:
    """Construit le prompt de synthèse technique multi-repositories."""
    audit_lines = []
    for repository in repositories:
        repository_id = str(repository.get("id") or "").strip()
        repository_name = str(repository.get("name") or repository_id).strip()
        audit_lines.append(
            f"- {repository_name} ({repository_id}) : audits/{repository_id}/initial-audit.md"
        )

    audits = "\n".join(audit_lines)
    return f"""Tu réalises la synthèse technique globale d'un projet OpenClassrooms composé de plusieurs repositories.

OBJECTIF
Produire un audit PROJET transversal à partir des audits techniques initiaux déjà réalisés pour chaque repository. Ce document servira ensuite au cadrage et à la construction du backlog Scrum. Il ne doit pas encore être un backlog.

SOURCES PRINCIPALES À LIRE
- project.yml
- README.md
- docs/*.md lorsqu'ils contiennent déjà des informations utiles
- les audits techniques suivants :
{audits}

RÈGLES D'ANALYSE
- Travaille uniquement en lecture seule.
- N'utilise pas le réseau et n'installe rien.
- Utilise les audits de repository comme sources principales et ne refais pas un audit exhaustif de chaque repository.
- Tu peux inspecter ponctuellement les fichiers dans repos/ uniquement pour confirmer une interaction entre repositories, un contrat, une configuration partagée ou une contradiction importante.
- N'invente aucune exigence OpenClassrooms absente des fichiers du workspace.
- Distingue clairement Observé / Inféré / Non vérifié.
- Lorsqu'un constat provient d'un audit de repository, cite le fichier d'audit et, si disponible, la preuve technique originale qu'il contient.
- Repère les contradictions entre audits, les dépendances entre repositories et les risques transversaux.
- Ne génère ni user stories, ni tickets, ni sprint, ni estimation. Le backlog sera produit dans une étape séparée.
- Le rapport final doit être en français.
- Retourne uniquement le Markdown du rapport, sans bloc ``` autour du document.

FORMAT ATTENDU
# Audit technique global du projet

## 1. Résumé exécutif
Vue d'ensemble du système, niveau de maturité technique et principaux enjeux transversaux.

## 2. Périmètre analysé
Repositories pris en compte, audits disponibles, documents du workspace utilisés et limites de l'analyse.

## 3. Rôle de chaque repository
Pour chacun : responsabilité, technologies principales et place dans le système.

## 4. Architecture globale observée
Décrire le système dans son ensemble : flux, dépendances, APIs, données, services externes et points d'intégration démontrables.

## 5. Interactions entre repositories
Contrats, dépendances, ordre de démarrage/build, échanges de données, couplages et éléments encore non vérifiés.

## 6. Cohérence des environnements et du build
Versions, runtimes, package managers, variables d'environnement, reproductibilité et incompatibilités éventuelles entre repositories.

## 7. Stratégie de tests à l'échelle du projet
Tests déjà présents, trous de couverture transversaux, tests d'intégration/end-to-end nécessaires et dépendances entre suites de tests.

## 8. Qualité et maintenabilité transversales
Standards communs ou divergents, analyse statique, formatage, dette technique et points de maintenance touchant plusieurs repositories.

## 9. Sécurité / DevSecOps globale
Secrets, dépendances, surfaces d'exposition, configurations, contrôles de sécurité existants et lacunes transversales. N'affirme aucune CVE sans preuve locale.

## 10. Docker et orchestration
État de la conteneurisation par repository, besoin ou rôle d'un Compose au niveau projet, réseaux, volumes, healthchecks et ordre de démarrage. Ne recommande Docker que lorsqu'il répond à un besoin démontré.

## 11. CI/CD à l'échelle du projet
Pipelines existants, divergences GitHub/GitLab, dépendances entre pipelines, artefacts, déploiement et contrôles manquants.

## 12. Observabilité et exploitation
Logs, health checks, métriques, erreurs, dépendances opérationnelles et capacité à diagnostiquer le système complet.

## 13. Constats transversaux prioritaires
Pour chaque constat :

### [PROJ-ID] Titre
- **Sévérité :** Critique | Haute | Moyenne | Faible | Information
- **Statut :** Observé | Inféré | Non vérifié
- **Repositories concernés :** ...
- **Preuves :** chemins vers audits/fichiers pertinents
- **Constat :** ...
- **Impact projet :** ...
- **Action proposée :** ...

Ne répète pas mécaniquement tous les constats individuels : retiens ceux qui ont un impact projet ou qui conditionnent la suite.

## 14. Dépendances entre actions
Identifier ce qui doit être fait avant quoi et expliquer les dépendances techniques.

## 15. Points à clarifier avant cadrage/backlog
Questions auxquelles les audits seuls ne permettent pas de répondre : consignes du projet, choix fonctionnels, contraintes d'évaluation, informations du mentor, etc.

## 16. Séquence de travail recommandée avant backlog
Proposer un ordre court de préparation technique : vérifications à faire, décisions à prendre et informations à obtenir. Ne transforme pas cette section en liste de tickets Scrum.

CONTRAINTE DE QUALITÉ
La valeur de ce rapport est la synthèse TRANSVERSALE. Évite de recopier les audits repo par repo et concentre-toi sur les relations, contradictions, dépendances et priorités communes.
"""


def _codex_command(codex: str, prompt: str) -> list[str]:
    return [
        codex,
        "--sandbox",
        "read-only",
        "--ask-for-approval",
        "never",
        "exec",
        "--ephemeral",
        prompt,
    ]


def _run_codex(command: list[str], cwd: Path) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise AiAuditError(f"Impossible de lancer Codex CLI : {exc}") from exc

    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "Erreur Codex inconnue.").strip()
        raise AiAuditError(f"Audit Codex impossible : {details}")

    report = completed.stdout.strip()
    if not report:
        raise AiAuditError("Codex n'a retourné aucun rapport.")
    return report


def run_codex_audit(
    workspace: Path,
    repository: dict,
    *,
    overwrite: bool = False,
) -> Path:
    """Lance Codex en lecture seule puis écrit son message final dans le workspace."""
    codex = shutil.which("codex")
    if not codex:
        raise CodexNotFoundError(
            "Codex CLI est introuvable dans le PATH. Installe-le et connecte-toi avant de relancer l'audit."
        )

    repository_id = str(repository.get("id") or "").strip()
    repository_name = str(repository.get("name") or repository_id).strip()
    relative_path = str(repository.get("path") or "").strip()

    if not repository_id or not relative_path:
        raise AiAuditError("Configuration du repository incomplète dans project.yml.")

    repository_path = (workspace / relative_path).resolve()
    if not repository_path.is_dir():
        raise AiAuditError(f"Repository introuvable : {repository_path}")
    if not (repository_path / ".git").exists():
        raise AiAuditError(f"Le dossier n'est pas un repository Git : {repository_path}")

    output_dir = workspace / "audits" / repository_id
    output_path = output_dir / "initial-audit.md"
    if output_path.exists() and not overwrite:
        raise AuditAlreadyExistsError(output_path)

    prompt = build_audit_prompt(repository_name)
    report = _run_codex(_codex_command(codex, prompt), repository_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.rstrip() + "\n", encoding="utf-8")
    from .journal import record_generation
    record_generation(workspace, output_path)
    return output_path


def run_codex_project_audit(
    workspace: Path,
    repositories: list[dict],
    *,
    overwrite: bool = False,
) -> Path:
    """Synthétise les audits repo en un audit technique global du projet."""
    codex = shutil.which("codex")
    if not codex:
        raise CodexNotFoundError(
            "Codex CLI est introuvable dans le PATH. Installe-le et connecte-toi avant de relancer l'audit."
        )

    if not repositories:
        raise AiAuditError("Aucun repository n'est enregistré dans project.yml.")

    missing: list[str] = []
    for repository in repositories:
        repository_id = str(repository.get("id") or "").strip()
        if not repository_id:
            raise AiAuditError("Configuration d'un repository incomplète dans project.yml.")
        audit_path = workspace / "audits" / repository_id / "initial-audit.md"
        if not audit_path.is_file() or not audit_path.read_text(encoding="utf-8").strip():
            missing.append(repository_id)

    if missing:
        raise MissingRepositoryAuditsError(missing)

    output_path = workspace / "audits" / "project-audit.md"
    if output_path.exists() and not overwrite:
        raise AuditAlreadyExistsError(output_path)

    prompt = build_project_audit_prompt(repositories)
    report = _run_codex(_codex_command(codex, prompt), workspace)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.rstrip() + "\n", encoding="utf-8")
    from .journal import record_generation
    record_generation(workspace, output_path)
    return output_path

def extract_pdf_sources(source_dir: Path) -> list[dict[str, str]]:
    """Extrait le texte des PDF officiels en conservant la provenance par page."""
    if PdfReader is None:
        raise SourceDocumentError(
            "La dépendance PDF 'pypdf' n'est pas installée dans l'environnement OCP. "
            "Depuis le dossier ocp-cli, exécute : pipx reinstall ocp-cli"
        )

    if not source_dir.is_dir():
        raise MissingSourceDocumentsError(
            "Le dossier docs/source est introuvable. Dépose d'abord les PDF officiels du projet."
        )

    pdf_files = sorted(
        path for path in source_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    )
    if not pdf_files:
        raise MissingSourceDocumentsError(
            "Aucun PDF trouvé dans docs/source. Dépose d'abord les documents officiels du projet."
        )

    documents: list[dict[str, str]] = []
    for pdf_path in pdf_files:
        try:
            reader = PdfReader(str(pdf_path))
        except Exception as exc:
            raise SourceDocumentError(
                f"Impossible de lire le PDF {pdf_path.name} : {exc}"
            ) from exc

        pages: list[str] = []
        for number, page in enumerate(reader.pages, start=1):
            try:
                text = (page.extract_text() or "").strip()
            except Exception as exc:
                raise SourceDocumentError(
                    f"Impossible d'extraire le texte de {pdf_path.name}, page {number} : {exc}"
                ) from exc
            if text:
                pages.append(
                    f"--- SOURCE: {pdf_path.name} | PAGE: {number} ---\n{text}"
                )

        if not pages:
            raise SourceDocumentError(
                f"Le PDF {pdf_path.name} ne contient aucun texte exploitable. "
                "Vérifie qu'il s'agit d'un PDF texte et non d'un scan image."
            )

        documents.append({
            "name": pdf_path.name,
            "content": "\n\n".join(pages),
        })

    return documents


def build_cadrage_prompt(
    project_yaml: str,
    project_audit: str,
    source_documents: list[dict[str, str]],
) -> str:
    """Construit le prompt de cadrage à partir des sources officielles et de l'audit projet."""
    sources = "\n\n".join(
        f"===== DOCUMENT OFFICIEL: {doc['name']} =====\n{doc['content']}"
        for doc in source_documents
    )

    return f"""Tu rédiges la note de cadrage d'un projet OpenClassrooms à partir de sources locales fournies explicitement.

OBJECTIF
Produire un document de cadrage factuel qui transforme les consignes officielles en périmètre de travail clair, tout en utilisant l'audit technique uniquement pour décrire l'état initial du code. Ce document servira ensuite à construire le backlog Scrum. Il ne doit pas encore contenir de tickets ni de sprint.

HIÉRARCHIE DES SOURCES
1. Les documents officiels de docs/source/ font autorité pour les exigences, objectifs, étapes, résultats attendus et contraintes pédagogiques.
2. audits/project-audit.md décrit l'état technique observé ; il ne crée aucune exigence fonctionnelle.
3. project.yml fournit l'identité et l'organisation du workspace.

RÈGLES IMPÉRATIVES
- N'utilise aucune connaissance externe pour compléter les consignes.
- Ne corrige pas silencieusement une consigne qui paraît inhabituelle ou contradictoire. Signale-la dans « Points à clarifier ».
- Ne transforme jamais une recommandation technique de l'audit en exigence OpenClassrooms.
- Distingue clairement : « Exigence officielle », « État initial observé », « Inférence » et « À clarifier ».
- Pour chaque exigence officielle importante, indique sa source sous la forme `(Source : nom-du-fichier.pdf, p. N)`.
- N'utilise aucun chemin absolu local dans le document final.
- Ne génère ni user stories, ni tickets, ni estimation, ni sprint.
- Ne propose pas encore de solution d'implémentation détaillée.
- Préserve les versions, technologies, seuils de couverture, outils et résultats attendus tels qu'ils apparaissent dans les sources.
- Si deux sources officielles se contredisent, expose les deux formulations et marque le point « À clarifier ».
- Le document final doit être en français.
- Retourne uniquement le Markdown du document, sans bloc ``` autour.

FORMAT ATTENDU
# Note de cadrage

## 1. Identification du projet
Nom, contexte OpenClassrooms, méthodologie du workspace et repositories concernés lorsque l'information est disponible.

## 2. Contexte et finalité
Pourquoi le projet existe, compétences visées et nature de l'application existante.

## 3. Objectifs officiels
Objectifs explicitement demandés dans les documents sources.

## 4. Périmètre fonctionnel
Fonctionnalités et parcours à réaliser, regroupés dans l'ordre imposé ou explicitement guidé par les consignes.

## 5. Hors périmètre et limites explicites
Ce que les sources disent ne pas demander, ce qui est optionnel, ou ce qui n'est pas spécifié. Ne déduis pas de hors-périmètre absent des sources.

## 6. Résultats attendus et critères de réussite
Rassembler les « résultats attendus », comportements vérifiables, seuils et preuves explicitement demandés.

## 7. Contraintes techniques imposées
Technologies, versions, outils, environnements ou conventions explicitement prescrits.

## 8. Exigences de tests et qualité
Types de tests, frameworks, couverture, rapports attendus, règles ou séquence de test prévues par les sources.

## 9. Sécurité et contrôle d'accès exigés
Uniquement les exigences explicitement présentes dans les sources officielles.

## 10. État initial technique observé
Synthèse courte de audits/project-audit.md : architecture actuelle, écarts entre l'existant et les consignes, risques ou inconnues. Chaque élément doit être clairement présenté comme état observé et non comme exigence.

## 11. Dépendances et ordre logique de réalisation
Dépendances réellement imposées par les prérequis et les étapes officielles.

## 12. Livrables, preuves et démonstrations attendues
Documents, rapports, exécutions, démonstrations ou éléments mesurables explicitement identifiables dans les sources.

## 13. Risques et points de vigilance
Risques issus soit des consignes officielles, soit de l'audit technique. Identifie clairement leur origine.

## 14. Points à clarifier
Ambiguïtés, contradictions, informations manquantes ou décisions qui nécessitent le mentor plutôt qu'une supposition.

## 15. Traçabilité des exigences
Tableau synthétique : ID | Exigence | Source officielle | Page | Statut (clair / à clarifier).

CONFIGURATION DU PROJET
```yaml
{project_yaml.strip()}
```

AUDIT TECHNIQUE GLOBAL — ÉTAT INITIAL
```markdown
{project_audit.strip()}
```

DOCUMENTS OFFICIELS EXTRAITS
{sources}

CONTRAINTE DE QUALITÉ
Le cadrage doit pouvoir être relu par un mentor et permettre ensuite de produire un backlog sans retourner aux sources pour comprendre les obligations principales. Il doit cependant rester fidèle aux documents et signaler toute information absente plutôt que l'inventer.
"""


def run_codex_cadrage(
    workspace: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Génère docs/cadrage.md à partir des PDF officiels et de l'audit projet."""
    codex = shutil.which("codex")
    if not codex:
        raise CodexNotFoundError(
            "Codex CLI est introuvable dans le PATH. Installe-le et connecte-toi avant de relancer le cadrage."
        )

    project_yml_path = workspace / "project.yml"
    if not project_yml_path.is_file():
        raise AiAuditError("project.yml est introuvable dans le workspace.")

    project_audit_path = workspace / "audits" / "project-audit.md"
    if not project_audit_path.is_file() or not project_audit_path.read_text(encoding="utf-8").strip():
        raise MissingProjectAuditError(
            "L'audit projet est manquant. Lance d'abord 'ocp ai project-audit'."
        )

    source_documents = extract_pdf_sources(workspace / "docs" / "source")

    output_path = workspace / "docs" / "cadrage.md"
    if output_path.exists() and not overwrite:
        current = output_path.read_text(encoding="utf-8").strip()
        # Le squelette créé par ocp init peut être remplacé sans confirmation supplémentaire.
        if current not in {"", "# Note de cadrage"}:
            raise AuditAlreadyExistsError(output_path)

    project_yaml = project_yml_path.read_text(encoding="utf-8")
    project_audit = project_audit_path.read_text(encoding="utf-8")
    prompt = build_cadrage_prompt(project_yaml, project_audit, source_documents)
    report = _run_codex(_codex_command(codex, prompt), workspace)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.rstrip() + "\n", encoding="utf-8")
    from .journal import record_generation
    record_generation(workspace, output_path)
    return output_path



def build_workflow_prompt(
    project_yaml: str,
    cadrage: str,
    project_audit: str,
    mentor_recommendations: str,
) -> str:
    """Construit le prompt des règles de travail du projet avant génération du backlog."""
    return f"""Tu définis le workflow de développement d'un projet OpenClassrooms avant la création du backlog Scrum.

OBJECTIF
Produire un document de travail court, concret et applicable au quotidien. Il doit fixer les règles de développement communes aux repositories, définir un MVP pédagogique, intégrer explicitement les recommandations du mentor et établir les conventions Git, qualité, tests et environnement qui guideront ensuite le backlog et les sprints.

HIÉRARCHIE DES SOURCES
1. docs/cadrage.md définit les exigences officielles, le périmètre et les contraintes du projet.
2. mentoring/recommendations.md contient les recommandations du mentor. Elles doivent rester identifiées comme recommandations, pas comme exigences OpenClassrooms.
3. audits/project-audit.md décrit l'état technique observé, les risques et les outils déjà présents ou absents.
4. project.yml décrit l'organisation du workspace et les repositories.
5. Tu peux inspecter en lecture seule les repositories sous repos/ pour vérifier les outils, conventions et fichiers de configuration réellement présents.

RÈGLES IMPÉRATIVES
- Travaille uniquement en lecture seule ; ne modifie aucun repository.
- N'utilise pas le réseau et n'installe rien.
- Ne transforme jamais une recommandation du mentor en exigence officielle.
- Ne transforme jamais une recommandation d'audit en exigence OpenClassrooms.
- Privilégie l'efficacité d'un développeur travaillant seul avec mentorat : évite les processus lourds sans bénéfice démontré.
- Ne génère pas encore le backlog, les tickets, les estimations ni les sprints.
- Le MVP doit être le plus petit jalon cohérent, démontrable et testable qui permet d'avancer vers le projet complet. Il ne remplace aucune exigence officielle restant à réaliser ensuite.
- Pour les conventions de code, commence par ce qui existe réellement dans les repositories. S'il manque un standard, propose un standard adapté aux technologies détectées, en l'identifiant clairement comme décision de projet.
- Pour Java, il n'existe pas un unique équivalent universel des PSR PHP : distingue conventions de code, formatage et analyse statique et ne propose un outil supplémentaire que s'il apporte une valeur démontrable.
- Pour Angular/TypeScript, distingue Angular Style Guide, règles TypeScript, lint et formatage ; n'impose pas ESLint/Prettier s'ils sont inutiles ou en conflit avec l'existant.
- Utilise Conventional Commits comme convention de commit par défaut, sauf incompatibilité démontrée avec l'existant.
- Propose des branches courtes et simples. Lorsque le backlog existera, prévoir l'usage de l'identifiant du ticket dans le nom de branche.
- Les secrets réels ne doivent jamais être versionnés. Distingue les fichiers d'exemple versionnables (`.env.example`, par exemple) des fichiers locaux (`.env.local` ou équivalent) selon les technologies et recommandations du mentor.
- Pour Docker et le hot reload, ne décris comme règle retenue que ce qui est compatible avec le projet ou explicitement recommandé/accepté ; sinon marque le point comme proposition à valider.
- Distingue toujours « versions/runtimes de référence » et « installation native sur le poste ». Si une stratégie Docker-first est explicitement retenue, ne demande pas l'installation hôte de Java, Maven, Node, npm ou Angular CLI sauf nécessité démontrée. Le poste peut n'exiger que Docker/Compose et les outils de développement nécessaires.
- Si cette stratégie diffère de la formulation littérale d'un prérequis OpenClassrooms, conserve la divergence visible comme décision de projet à confirmer avec le mentor au lieu de la présenter comme exigence officielle.
- Le document final doit être en français.
- Retourne uniquement le Markdown du document, sans bloc ``` autour.

FORMAT ATTENDU
# Workflow de développement

## 1. Objectif et principes
Décrire brièvement le but du workflow : efficacité, reproductibilité, traçabilité et qualité sans sur-processus.

## 2. Repositories et responsabilités
Rappeler les repositories, leur rôle et les règles qui sont communes ou spécifiques à chacun.

## 3. MVP pédagogique
Définir le plus petit jalon cohérent et démontrable. Pour chaque élément : objectif, preuve de réussite et dépendances. Ajouter une section « Après le MVP » pour rappeler les exigences obligatoires restantes sans produire de backlog.

## 4. Recommandations du mentor
Tableau : ID | Recommandation | Statut (retenue / à valider / différée) | Traduction concrète dans le workflow | Justification.
Préserver les identifiants REC-MENTOR-* lorsqu'ils existent.

## 5. Workflow Git
Définir une stratégie légère adaptée à un projet individuel : branche stable, branches courtes, moment du merge et usage éventuel des PR.

## 6. Convention de nommage des branches
Proposer une convention précise, par exemple `feature/<ticket>-<slug>`, `fix/<ticket>-<slug>`, `test/<ticket>-<slug>`, `chore/<ticket>-<slug>`. Adapter si le projet justifie autre chose.

## 7. Convention de commits
Conventional Commits, scopes utiles par repository, exemples réalistes et règles de granularité. Un commit doit représenter une intention cohérente.

## 8. Standards de code par repository
Pour chaque repository : conventions déjà présentes, standards retenus, formatage, lint/analyse statique, règles de nommage et points à ne pas sur-outiller.

## 9. Environnement de développement
Versions de référence, installation, variables d'environnement, fichiers locaux, Docker/Compose, volumes/hot reload lorsque pertinent, et commandes de démarrage démontrées ou à valider.

## 10. Workflow de tests
Quand écrire/lancer les tests, niveaux de tests exigés, commandes disponibles ou à confirmer, couverture attendue et relation avec la Definition of Done.

## 11. Qualité et sécurité avant commit/merge
Contrôles minimaux : formatage/lint, tests, analyse statique ou sécurité seulement lorsqu'ils existent ou sont retenus. Inclure la vérification des secrets.

## 12. Definition of Ready
Critères minimaux avant de commencer une tâche : objectif compris, source/EX connue, dépendances identifiées, critères d'acceptation connus, environnement prêt.

## 13. Definition of Done
Critères minimaux pour considérer un travail terminé : code, tests, qualité, documentation utile, sécurité, démonstration possible et commit/merge propre.

## 14. Cycle de travail d'une tâche
Séquence simple et répétable depuis la sélection d'un item jusqu'à sa publication : branche → développement → tests → contrôle → commit → merge/push → journal/mentor si pertinent.

## 15. Décisions et points à valider
Lister uniquement les choix non résolus qui doivent être confirmés avant d'être rendus obligatoires.

CONFIGURATION DU PROJET
```yaml
{project_yaml.strip()}
```

CADRAGE VALIDÉ
```markdown
{cadrage.strip()}
```

AUDIT TECHNIQUE GLOBAL
```markdown
{project_audit.strip()}
```

RECOMMANDATIONS DU MENTOR
```markdown
{mentor_recommendations.strip() or '# Recommandations mentor\n\nAucune recommandation consignée.'}
```

CONTRAINTE DE QUALITÉ
Ce document doit pouvoir être appliqué immédiatement par un développeur seul. Chaque règle doit avoir une raison liée au projet, au cadrage, à l'audit ou au mentor. Évite les cérémonies et outils ajoutés uniquement « parce que c'est une bonne pratique ».
"""


def run_codex_workflow(
    workspace: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Génère docs/development-workflow.md à partir du cadrage, de l'audit et des recommandations mentor."""
    codex = shutil.which("codex")
    if not codex:
        raise CodexNotFoundError(
            "Codex CLI est introuvable dans le PATH. Installe-le et connecte-toi avant de relancer le workflow."
        )

    project_yml_path = workspace / "project.yml"
    if not project_yml_path.is_file():
        raise AiAuditError("project.yml est introuvable dans le workspace.")

    cadrage_path = workspace / "docs" / "cadrage.md"
    if not cadrage_path.is_file():
        raise MissingCadrageError(
            "La note de cadrage est manquante. Lance d'abord 'ocp ai cadrage'."
        )
    cadrage = cadrage_path.read_text(encoding="utf-8").strip()
    if cadrage in {"", "# Note de cadrage"}:
        raise MissingCadrageError(
            "La note de cadrage est vide. Lance d'abord 'ocp ai cadrage' et valide son contenu."
        )

    project_audit_path = workspace / "audits" / "project-audit.md"
    if not project_audit_path.is_file():
        raise MissingProjectAuditError(
            "L'audit projet est manquant. Lance d'abord 'ocp ai project-audit'."
        )
    project_audit = project_audit_path.read_text(encoding="utf-8").strip()
    if not project_audit:
        raise MissingProjectAuditError(
            "L'audit projet est vide. Relance 'ocp ai project-audit'."
        )

    recommendations_path = workspace / "mentoring" / "recommendations.md"
    if recommendations_path.is_file():
        mentor_recommendations = recommendations_path.read_text(encoding="utf-8").strip()
    else:
        mentor_recommendations = "# Recommandations mentor\n\nAucune recommandation consignée."

    output_path = workspace / "docs" / "development-workflow.md"
    if output_path.exists() and not overwrite:
        current = output_path.read_text(encoding="utf-8").strip()
        if current not in {"", "# Workflow de développement"}:
            raise AuditAlreadyExistsError(output_path)

    project_yaml = project_yml_path.read_text(encoding="utf-8")
    prompt = build_workflow_prompt(
        project_yaml,
        cadrage,
        project_audit,
        mentor_recommendations,
    )
    report = _run_codex(_codex_command(codex, prompt), workspace)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.rstrip() + "\n", encoding="utf-8")
    from .journal import record_generation
    record_generation(workspace, output_path)
    return output_path


def build_backlog_prompt(
    project_yaml: str,
    cadrage: str,
    workflow: str,
    project_audit: str,
    mentor_recommendations: str,
) -> str:
    """Construit le prompt de backlog Scrum traçable, avec MVP, TECH et SPIKE."""
    return f"""Tu construis le Product Backlog initial d'un projet OpenClassrooms géré en Scrum.

OBJECTIF
Transformer le cadrage validé et le workflow de développement en backlog actionnable, ordonné et traçable. Le backlog doit permettre de commencer à travailler immédiatement, sans inventer de périmètre et sans transformer toutes les observations techniques en obligations.

HIÉRARCHIE DES SOURCES
1. docs/cadrage.md définit les exigences officielles, le périmètre, les contraintes et les identifiants EX-*.
2. docs/development-workflow.md définit le MVP pédagogique, les règles de travail, la Definition of Ready, la Definition of Done et les décisions de projet déjà retenues.
3. mentoring/recommendations.md contient les recommandations du mentor. Elles restent des recommandations tant qu'une décision ne les a pas retenues.
4. audits/project-audit.md décrit l'état technique observé et les constats PROJ-* ; il sert à créer des tâches techniques ou des investigations lorsqu'elles sont justifiées.
5. project.yml identifie le projet et les repositories.

RÈGLES DE MODÉLISATION
- Ne change pas le MVP défini dans le workflow : matérialise-le dans le backlog et identifie clairement sa frontière.
- Respecte l'ordre fonctionnel officiel et les dépendances techniques documentées.
- Utilise exactement trois types d'items :
  - US : valeur ou comportement observable par un utilisateur/acteur du système ;
  - TECH : travail technique nécessaire pour satisfaire une exigence, une décision de projet ou une recommandation retenue ;
  - SPIKE : investigation bornée destinée à lever une inconnue avant implémentation.
- N'écris pas de fausses user stories « En tant que développeur... » pour du travail technique : utilise TECH.
- Une recommandation mentor non encore validée ne devient pas automatiquement une tâche d'implémentation : crée un SPIKE si une validation/investigation est réellement nécessaire, ou indique-la dans les points à arbitrer.
- Un constat PROJ-* ne devient un item que s'il est nécessaire au périmètre, au MVP, à la qualité attendue ou à une décision explicite.
- Chaque item doit citer sa ou ses sources : EX-*, PROJ-*, REC-MENTOR-* ou « Décision workflow ».
- Chaque item doit indiquer le ou les repositories concernés : workspace, backend, frontend, ou plusieurs.
- Les critères d'acceptation doivent être observables et vérifiables. Ne pas introduire de critères absents des sources sauf lorsqu'ils découlent explicitement de la Definition of Done ; dans ce cas, le signaler comme « Décision workflow ».
- Marque chaque item « MVP : Oui » ou « MVP : Non ».
- Marque les dépendances par identifiants d'items lorsque possible.
- Attribue une priorité P0, P1, P2 ou P3 : P0 bloque le démarrage/MVP, P1 appartient au chemin principal ou à une exigence obligatoire proche, P2 est obligatoire mais ultérieur, P3 est amélioration/différable.
- Ajoute un statut initial parmi : Ready | Blocked | To clarify. Utilise la Definition of Ready du workflow ; ne marque pas Ready un item dont les règles métier ou critères nécessaires sont inconnus.
- Ne génère aucun sprint, aucune date, aucune vélocité, aucun story point et aucune estimation de durée. Le Sprint 1 sera construit séparément après validation humaine du backlog.
- Les remises à niveau ou validations de compétences présentées comme optionnelles ne doivent JAMAIS devenir un préalable bloquant par défaut. Elles restent hors chemin critique ou deviennent une question mentor. Ne crée une dépendance bloquante que si une lacune concrète, déjà observée et explicitement documentée, empêche réellement d'exécuter le travail technique.
- Distingue une version/runtime exigé (Java, Maven, Node, Angular, etc.) de son mode d'installation sur l'hôte. Une exigence de version ne signifie pas automatiquement « installer localement sur macOS/Linux » : un environnement conteneurisé peut être une décision de projet si le workflow ou le mentor la retient.
- Ne crée pas de tâche générique de type « faire la CI/CD », « dockeriser », « ajouter Sonar » ou « améliorer la sécurité » sans source ou besoin démontré.
- Le document final doit être en français.
- Retourne uniquement le Markdown, sans bloc ``` autour du document.

IDENTIFIANTS
- Epics : EPIC-01, EPIC-02, ...
- User stories : US-001, US-002, ...
- Tâches techniques : TECH-001, TECH-002, ...
- Spikes : SPIKE-001, SPIKE-002, ...
Les identifiants doivent être uniques et stables dans le document.

FORMAT ATTENDU
# Product Backlog

## 1. Règles du backlog
Rappeler brièvement : source de vérité, types d'items, priorité, statut, sens de MVP et absence volontaire d'estimation/sprint.

## 2. MVP pédagogique
Décrire la frontière du MVP telle qu'elle existe déjà dans le workflow. Fournir un tableau : Item | Objectif | Repository(s) | Source(s) | Dépend de.

## 3. Vue d'ensemble ordonnée
Tableau compact de TOUS les items : Ordre | ID | Type | Epic | Titre | Priorité | MVP | Repository(s) | Statut | Dépend de | Sources.
L'ordre doit refléter les dépendances et l'ordre officiel, pas seulement les priorités.

## 4. Backlog détaillé par Epic
Pour chaque epic :

### EPIC-XX — Titre
But de l'epic en une ou deux phrases.

Puis pour chaque item :

#### US-XXX | TECH-XXX | SPIKE-XXX — Titre
- **Type :** US | TECH | SPIKE
- **Priorité :** P0 | P1 | P2 | P3
- **MVP :** Oui | Non
- **Repository(s) :** ...
- **Statut initial :** Ready | Blocked | To clarify
- **Sources :** EX-.., PROJ-.., REC-MENTOR-.., Décision workflow
- **Dépend de :** ID(s) ou Aucune
- **Débloque :** ID(s) si pertinent

Pour une US, ajoute :
**Valeur / comportement attendu :** description concise centrée utilisateur.

Pour une TECH, ajoute :
**Résultat technique attendu :** résultat concret et vérifiable.

Pour un SPIKE, ajoute :
**Question à résoudre :** question bornée.
**Sortie attendue :** décision, preuve ou mini-document attendu ; pas de mise en production implicite.

Pour tous les items :
**Critères d'acceptation :**
- [ ] ...
- [ ] ...

**Preuve attendue :** commande, test, capture, réponse HTTP, rapport ou autre preuve explicitement pertinente.

## 5. Points bloquants / à arbitrer
Lister uniquement les inconnues qui empêchent des items d'être Ready. Référencer les SPIKEs correspondants lorsque créés.

## 6. Couverture des exigences
Tableau : Exigence EX-* | Item(s) du backlog | Couverture (MVP / Après MVP) | Remarque.
Toutes les exigences claires du cadrage doivent être reliées à au moins un item. Les exigences « à clarifier » doivent pointer vers un SPIKE/point d'arbitrage ou expliquer pourquoi elles ne bloquent pas encore.

## 7. Recommandations mentor
Tableau : REC-MENTOR-* | Décision actuelle | Item(s) associé(s) | Commentaire.
Ne transforme pas « à valider » en « retenue » sans preuve.

## 8. Constats techniques pris en compte
Tableau : PROJ-* | Item(s) associé(s) ou « différé » | Justification.
Le but est de montrer pourquoi un risque technique entre ou non dans le backlog.

## 9. Contrôle de cohérence avant Sprint 1
Vérifier explicitement :
- le MVP du workflow est entièrement représenté ;
- aucune exigence claire n'est orpheline ;
- aucun item Blocked/To clarify n'est présenté comme démarrable ;
- les dépendances ne sont pas circulaires ;
- aucun sprint ni estimation n'a été créé.

CONFIGURATION DU PROJET
```yaml
{project_yaml.strip()}
```

CADRAGE VALIDÉ
```markdown
{cadrage.strip()}
```

WORKFLOW DE DÉVELOPPEMENT VALIDÉ
```markdown
{workflow.strip()}
```

AUDIT TECHNIQUE GLOBAL
```markdown
{project_audit.strip()}
```

RECOMMANDATIONS DU MENTOR
```markdown
{mentor_recommendations.strip() or '# Recommandations mentor\n\nAucune recommandation consignée.'}
```

CONTRAINTE DE QUALITÉ
Le backlog doit être suffisamment précis pour sélectionner ensuite un Sprint 1 sans retourner aux documents sources pour comprendre l'intention des items. Il doit rester sobre : préfère moins d'items cohérents à une décomposition artificiellement fine. Ne duplique pas une même exigence dans plusieurs items sans raison fonctionnelle ou technique explicite.
"""


def run_codex_backlog(
    workspace: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Génère management/backlog.md à partir du cadrage, workflow, audit et mentor."""
    codex = shutil.which("codex")
    if not codex:
        raise CodexNotFoundError(
            "Codex CLI est introuvable dans le PATH. Installe-le et connecte-toi avant de relancer le backlog."
        )

    project_yml_path = workspace / "project.yml"
    if not project_yml_path.is_file():
        raise AiAuditError("project.yml est introuvable dans le workspace.")

    cadrage_path = workspace / "docs" / "cadrage.md"
    if not cadrage_path.is_file():
        raise MissingCadrageError(
            "La note de cadrage est manquante. Lance d'abord 'ocp ai cadrage'."
        )
    cadrage = cadrage_path.read_text(encoding="utf-8").strip()
    if cadrage in {"", "# Note de cadrage"}:
        raise MissingCadrageError(
            "La note de cadrage est vide. Lance d'abord 'ocp ai cadrage' et valide son contenu."
        )

    workflow_path = workspace / "docs" / "development-workflow.md"
    if not workflow_path.is_file():
        raise MissingWorkflowError(
            "Le workflow de développement est manquant. Lance d'abord 'ocp ai workflow'."
        )
    workflow = workflow_path.read_text(encoding="utf-8").strip()
    if workflow in {"", "# Workflow de développement"}:
        raise MissingWorkflowError(
            "Le workflow de développement est vide. Lance d'abord 'ocp ai workflow' et valide son contenu."
        )

    project_audit_path = workspace / "audits" / "project-audit.md"
    if not project_audit_path.is_file():
        raise MissingProjectAuditError(
            "L'audit projet est manquant. Lance d'abord 'ocp ai project-audit'."
        )
    project_audit = project_audit_path.read_text(encoding="utf-8").strip()
    if not project_audit:
        raise MissingProjectAuditError(
            "L'audit projet est vide. Relance 'ocp ai project-audit'."
        )

    recommendations_path = workspace / "mentoring" / "recommendations.md"
    if recommendations_path.is_file():
        mentor_recommendations = recommendations_path.read_text(encoding="utf-8").strip()
    else:
        mentor_recommendations = "# Recommandations mentor\n\nAucune recommandation consignée."

    output_path = workspace / "management" / "backlog.md"
    if output_path.exists() and not overwrite:
        current = output_path.read_text(encoding="utf-8").strip()
        if current not in {"", "# Backlog", "# Product Backlog"}:
            raise AuditAlreadyExistsError(output_path)

    project_yaml = project_yml_path.read_text(encoding="utf-8")
    prompt = build_backlog_prompt(
        project_yaml,
        cadrage,
        workflow,
        project_audit,
        mentor_recommendations,
    )
    report = _run_codex(_codex_command(codex, prompt), workspace)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.rstrip() + "\n", encoding="utf-8")
    from .journal import record_generation
    record_generation(workspace, output_path)
    return output_path

def build_sprint_prompt(
    project_yaml: str,
    backlog: str,
    workflow: str,
    retrospective: str,
    mentor_current: str,
    mentor_recommendations: str,
    *,
    sprint_number: int = 1,
    sprint_history: str = "",
) -> str:
    """Construit le prompt d'un nouveau sprint numéroté à partir du backlog validé."""
    sprint_label = f"Sprint {sprint_number:03d}"
    sprint_path = f"management/sprints/sprint-{sprint_number:03d}.md"
    return f"""Tu prépares {sprint_label} d'un projet OpenClassrooms géré en Scrum.

OBJECTIF
Sélectionner le plus petit ensemble cohérent d'items du Product Backlog permettant d'atteindre un objectif de sprint clair et démontrable. Le sprint doit aider à travailler immédiatement, pas maximiser le nombre de tickets.

SOURCES ET PRIORITÉ
1. management/backlog.md : identifiants, priorité, MVP, statuts et dépendances des items.
2. docs/development-workflow.md : règles Git, Definition of Ready, Definition of Done, MVP et cycle de travail.
3. management/sprints/sprint-*.md : historique des sprints déjà créés. Un item explicitement marqué Done dans un sprint précédent ne doit pas être replanifié, même si le backlog n'a pas encore été synchronisé.
4. management/retrospective.md : enseignements du sprint précédent lorsqu'il contient réellement une rétrospective.
5. mentoring/current.md et mentoring/recommendations.md : blocages/questions/recommandations utiles au sprint, sans transformer une recommandation non validée en obligation.
6. project.yml : identité du projet et repositories.

RÈGLES DE SÉLECTION
- Ne crée aucun nouvel item de backlog et ne renumérote aucun identifiant.
- Ne reprogramme pas un item clairement terminé dans l'historique des sprints. Si le backlog présente encore un statut ancien, signale l'écart dans « Ajustements du backlog à valider ».
- Cherche d'abord un résultat TECHNIQUE concret et démontrable (environnement réellement exécutable, application démarrée, parcours vérifié, fonctionnalité testée) plutôt qu'un sprint uniquement documentaire.
- Pars des items Ready, mais raisonne en chaîne de déblocage : un item Blocked peut être planifié si ses bloqueurs sélectionnés peuvent être résolus plus tôt dans CE MÊME sprint. Tous les items n'ont pas besoin d'être Ready à la première minute du sprint.
- Si un bloqueur est uniquement pédagogique, documentaire ou dépend d'un avis mentor qui n'empêche pas techniquement d'avancer, ne le laisse pas monopoliser le sprint : place la question dans « Questions / mentor » et signale dans « Ajustements du backlog à valider » que cette dépendance devrait devenir non bloquante.
- Un item To clarify n'entre pas dans le travail engagé lorsqu'une décision est réellement indispensable à son implémentation ; sélectionne alors le SPIKE qui lève l'inconnue.
- Si le backlog contient une dépendance ou un statut qui semble contredire explicitement le cadrage/workflow ou l'historique, ne le corrige pas silencieusement : signale-le dans « Ajustements du backlog à valider ».
- N'accepte pas un sprint composé uniquement de SPIKEs/documents si un travail MVP concret peut raisonnablement être débloqué et exécuté dans le même sprint.
- Préfère un sprint court. En général 2 à 4 items suffisent ; dépasse ce nombre uniquement si la chaîne bloqueur → exécution → preuve l'exige.
- Respecte l'ordre fonctionnel officiel et la frontière du MVP.
- Ne sélectionne pas du travail après-MVP tant qu'il existe du travail MVP cohérent et démarrable.
- N'ajoute ni CI/CD, Docker, sécurité, lint ou outillage sans item correspondant dans le backlog ou décision explicite du workflow/mentor.
- Distingue les versions/runtimes à utiliser du mode d'installation sur l'hôte. Si le workflow retient un environnement Docker-first, prépare et vérifie cet environnement conteneurisé au lieu d'imposer Java/Node/Maven/Angular en installation native.
- Aucun story point, aucune vélocité, aucune estimation horaire et aucune date ne sont inventés.
- Ce sprint est un nouveau document immuable : {sprint_path}. Ne demande jamais d'écraser un sprint précédent.
- Le document final est en français.
- Retourne uniquement le Markdown, sans bloc ``` autour du document.

FORMAT ATTENDU
# {sprint_label}

## 1. Objectif du sprint
Une phrase orientée résultat démontrable.

## 2. Pourquoi ce sprint maintenant
2 à 5 points maximum reliant la sélection au backlog, au MVP, aux dépendances et aux sprints précédents.

## 3. Items engagés
Tableau : Ordre | ID | Titre | Type | Repository(s) | Statut au démarrage | Dépend de | Résultat attendu.
L'ordre doit être exécutable.

## 4. Plan d'exécution
Pour chaque item engagé :
### ID — Titre
- **But :** ...
- **Avant de commencer :** préconditions concrètes.
- **Travail :** étapes courtes tirées des critères d'acceptation du backlog, sans inventer de sous-projet.
- **Vérifications / preuves :** commandes, tests ou preuves attendues déjà prévues par le backlog/workflow.
- **Terminé lorsque :** résumé observable de la DoD applicable.

## 5. Hors sprint
Lister quelques items proches volontairement non sélectionnés et la raison : dépendance, clarification, après-MVP ou capacité volontairement limitée.

## 6. Questions / mentor
Uniquement les décisions utiles pendant le sprint. Les questions non bloquantes sont explicitement marquées « non bloquante ».

## 7. Ajustements du backlog à valider
Uniquement si une incohérence de statut/dépendance/historique est détectée. Sinon écrire « Aucun ». Ne modifie pas le backlog.

## 8. Checklist de clôture
- [ ] Objectif du sprint démontré
- [ ] Items engagés terminés ou écarts explicités
- [ ] Tests/contrôles applicables exécutés
- [ ] Preuves sans secrets conservées
- [ ] Commits/branches conformes au workflow
- [ ] Documentation/journal mis à jour
- [ ] Blocages et questions préparés pour le mentor

CONFIGURATION DU PROJET
```yaml
{project_yaml.strip()}
```

PRODUCT BACKLOG VALIDÉ
```markdown
{backlog.strip()}
```

WORKFLOW DE DÉVELOPPEMENT VALIDÉ
```markdown
{workflow.strip()}
```

HISTORIQUE DES SPRINTS
```markdown
{sprint_history.strip() or '# Historique des sprints\n\nAucun sprint numéroté précédent.'}
```

RÉTROSPECTIVE DISPONIBLE
```markdown
{retrospective.strip() or '# Rétrospective\n\nAucune rétrospective substantielle disponible.'}
```

POINT MENTOR COURANT
```markdown
{mentor_current.strip() or '# Point mentor\n\nAucun point mentor substantiel disponible.'}
```

RECOMMANDATIONS DU MENTOR
```markdown
{mentor_recommendations.strip() or '# Recommandations mentor\n\nAucune recommandation consignée.'}
```

CONTRAINTE DE QUALITÉ
Le sprint doit être immédiatement utilisable. Il vaut mieux un objectif étroit terminé et démontrable qu'un sprint rempli de tâches parallèles. Ne recopie pas tout le backlog et ne rejoue pas les items déjà terminés.
"""


def _sprint_files(workspace: Path) -> list[Path]:
    sprint_dir = workspace / "management" / "sprints"
    if not sprint_dir.exists():
        return []
    candidates: list[tuple[int, Path]] = []
    for path in sprint_dir.glob("sprint-*.md"):
        match = re.fullmatch(r"sprint-(\d+)\.md", path.name)
        if match:
            candidates.append((int(match.group(1)), path))
    return [path for _, path in sorted(candidates)]


def _legacy_sprint_is_substantive(workspace: Path) -> bool:
    legacy = workspace / "management" / "sprint.md"
    if not legacy.is_file():
        return False
    content = legacy.read_text(encoding="utf-8").strip()
    return content not in {"", "# Sprint actuel"}


def get_next_sprint_number(workspace: Path) -> int:
    files = _sprint_files(workspace)
    if not files:
        if _legacy_sprint_is_substantive(workspace):
            raise LegacySprintFileError(
                "Ancien fichier management/sprint.md détecté. Avant de générer un nouveau sprint, "
                "archive-le manuellement dans management/sprints/sprint-001.md (ou le numéro correct), "
                "puis supprime management/sprint.md. OCP ne devine pas l'historique à ta place."
            )
        return 1
    last = files[-1]
    match = re.fullmatch(r"sprint-(\d+)\.md", last.name)
    assert match is not None
    return int(match.group(1)) + 1


def _read_sprint_history(workspace: Path, limit: int = 5) -> str:
    files = _sprint_files(workspace)[-limit:]
    sections: list[str] = []
    for path in files:
        content = path.read_text(encoding="utf-8").strip()
        if content:
            sections.append(f"--- {path.name} ---\n{content}")
    return "\n\n".join(sections)


def run_codex_sprint(workspace: Path) -> Path:
    """Crée le prochain management/sprints/sprint-XXX.md sans écraser l'historique."""
    codex = shutil.which("codex")
    if not codex:
        raise CodexNotFoundError(
            "Codex CLI est introuvable dans le PATH. Installe-le et connecte-toi avant de préparer le sprint."
        )

    project_yml_path = workspace / "project.yml"
    if not project_yml_path.is_file():
        raise AiAuditError("project.yml est introuvable dans le workspace.")

    backlog_path = workspace / "management" / "backlog.md"
    if not backlog_path.is_file():
        raise MissingBacklogError(
            "Le Product Backlog est manquant. Lance d'abord 'ocp ai backlog'."
        )
    backlog = backlog_path.read_text(encoding="utf-8").strip()
    if backlog in {"", "# Backlog", "# Product Backlog"}:
        raise MissingBacklogError(
            "Le Product Backlog est vide. Lance d'abord 'ocp ai backlog' et valide son contenu."
        )

    workflow_path = workspace / "docs" / "development-workflow.md"
    if not workflow_path.is_file():
        raise MissingWorkflowError(
            "Le workflow de développement est manquant. Lance d'abord 'ocp ai workflow'."
        )
    workflow = workflow_path.read_text(encoding="utf-8").strip()
    if workflow in {"", "# Workflow de développement"}:
        raise MissingWorkflowError(
            "Le workflow de développement est vide. Lance d'abord 'ocp ai workflow' et valide son contenu."
        )

    retrospective_path = workspace / "management" / "retrospective.md"
    retrospective = retrospective_path.read_text(encoding="utf-8").strip() if retrospective_path.is_file() else ""
    if retrospective == "# Rétrospective":
        retrospective = ""

    mentor_current_path = workspace / "mentoring" / "current.md"
    mentor_current = mentor_current_path.read_text(encoding="utf-8").strip() if mentor_current_path.is_file() else ""
    if mentor_current == "# Point mentor":
        mentor_current = ""

    recommendations_path = workspace / "mentoring" / "recommendations.md"
    mentor_recommendations = recommendations_path.read_text(encoding="utf-8").strip() if recommendations_path.is_file() else ""

    sprint_number = get_next_sprint_number(workspace)
    sprint_history = _read_sprint_history(workspace)
    output_path = workspace / "management" / "sprints" / f"sprint-{sprint_number:03d}.md"
    if output_path.exists():
        raise AuditAlreadyExistsError(output_path)

    project_yaml = project_yml_path.read_text(encoding="utf-8")
    prompt = build_sprint_prompt(
        project_yaml,
        backlog,
        workflow,
        retrospective,
        mentor_current,
        mentor_recommendations,
        sprint_number=sprint_number,
        sprint_history=sprint_history,
    )
    report = _run_codex(_codex_command(codex, prompt), workspace)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.rstrip() + "\n", encoding="utf-8")
    from .journal import record_generation
    record_generation(workspace, output_path)
    return output_path


_CONVENTIONAL_COMMIT_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^)]+\))?!?: .+"
)


def find_git_repository(start: Path) -> Path:
    """Retourne la racine du dépôt Git contenant start."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise AiAuditError(
            "Aucun dépôt Git trouvé depuis le répertoire courant."
        ) from exc
    return Path(completed.stdout.strip()).resolve()


def get_changed_paths(repository: Path) -> list[str]:
    """Liste les fichiers modifiés/non suivis sans modifier l'index."""
    commands = [
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    paths: set[str] = set()
    try:
        for command in commands:
            completed = subprocess.run(
                command,
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            )
            paths.update(line.strip() for line in completed.stdout.splitlines() if line.strip())
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise AiAuditError(f"Impossible d'inspecter le dépôt Git : {exc}") from exc
    return sorted(paths)


def has_staged_changes(repository: Path) -> bool:
    """Indique si l'index contient déjà des changements stagés."""
    completed = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode not in {0, 1}:
        raise AiAuditError("Impossible de vérifier l'index Git.")
    return completed.returncode == 1


def build_commit_prompt(changed_paths: list[str]) -> str:
    """Construit le prompt d'analyse des changements pour des commits cohérents."""
    files = "\n".join(f"- {path}" for path in changed_paths)
    return f"""Tu prépares un plan de commits Git pour le dépôt courant.

OBJECTIF
Inspecter les changements Git réels du dépôt (git diff, fichiers non suivis et historique récent) et proposer le plus petit ensemble de commits Conventional Commits cohérents.

FICHIERS MODIFIÉS À RÉPARTIR
{files}

RÈGLES STRICTES
- Travaille uniquement en lecture seule : ne modifie aucun fichier, l'index Git ou l'historique.
- Inspecte le diff et le contexte nécessaire avant de proposer le plan.
- Chaque fichier listé doit apparaître EXACTEMENT UNE FOIS dans le plan.
- Un même fichier ne peut PAS être découpé entre plusieurs commits dans cette version d'OCP.
- Regroupe des fichiers uniquement lorsqu'ils portent la même intention.
- Si un fichier mélange plusieurs intentions impossibles à séparer au niveau fichier, ajoute un warning expliquant qu'une séparation manuelle est préférable ; ne simule pas de git add -p.
- Utilise Conventional Commits : feat, fix, docs, style, refactor, perf, test, build, ci, chore ou revert.
- Ajoute un scope seulement s'il apporte de la clarté.
- Messages courts, précis et orientés intention. Utilise l'anglais par défaut, sauf si l'historique du dépôt montre clairement une autre convention.
- Ne propose ni push, ni merge, ni réécriture d'historique.
- Signale dans warnings tout risque visible : secret potentiel, fichier généré, changement non lié, gros fichier ou ambiguïté importante.
- Retourne UNIQUEMENT un objet JSON valide, sans bloc Markdown ni commentaire hors JSON.

SCHÉMA JSON EXACT
{{
  "summary": "résumé très court des changements",
  "warnings": ["warning éventuel"],
  "commits": [
    {{
      "message": "chore(scope): concise message",
      "paths": ["path/file"],
      "reason": "pourquoi ces fichiers forment une intention cohérente"
    }}
  ]
}}
"""


def _parse_commit_plan(raw: str, changed_paths: list[str]) -> dict:
    """Valide strictement la réponse JSON de Codex."""
    content = raw.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    try:
        plan = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AiAuditError("Codex n'a pas retourné un plan de commits JSON valide.") from exc

    if not isinstance(plan, dict) or not isinstance(plan.get("commits"), list):
        raise AiAuditError("Plan de commits invalide : clé 'commits' manquante.")
    commits = plan["commits"]
    if not commits:
        raise AiAuditError("Codex n'a proposé aucun commit.")

    expected = set(changed_paths)
    assigned: list[str] = []
    for item in commits:
        if not isinstance(item, dict):
            raise AiAuditError("Plan de commits invalide : entrée de commit incorrecte.")
        message = str(item.get("message") or "").strip()
        paths = item.get("paths")
        if not _CONVENTIONAL_COMMIT_RE.match(message):
            raise AiAuditError(f"Message Conventional Commit invalide : {message or '(vide)'}")
        if not isinstance(paths, list) or not paths:
            raise AiAuditError(f"Le commit '{message}' ne contient aucun fichier.")
        normalized = [str(path).strip() for path in paths if str(path).strip()]
        if len(normalized) != len(paths):
            raise AiAuditError(f"Chemin vide dans le commit '{message}'.")
        assigned.extend(normalized)
        item["paths"] = normalized

    assigned_set = set(assigned)
    duplicates = sorted({path for path in assigned if assigned.count(path) > 1})
    missing = sorted(expected - assigned_set)
    unknown = sorted(assigned_set - expected)
    if duplicates or missing or unknown:
        details = []
        if duplicates:
            details.append(f"dupliqués: {', '.join(duplicates)}")
        if missing:
            details.append(f"manquants: {', '.join(missing)}")
        if unknown:
            details.append(f"inconnus: {', '.join(unknown)}")
        raise AiAuditError("Plan de commits incohérent (" + "; ".join(details) + ").")

    warnings = plan.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = [str(warnings)]
    plan["warnings"] = [str(w).strip() for w in warnings if str(w).strip()]
    plan["summary"] = str(plan.get("summary") or "").strip()
    return plan


def plan_codex_commits(repository: Path) -> dict:
    """Analyse le dépôt avec Codex et retourne un plan de commits validé."""
    codex = shutil.which("codex")
    if not codex:
        raise CodexNotFoundError(
            "Codex CLI est introuvable dans le PATH. Installe-le et connecte-toi avant de relancer la commande."
        )
    repository = repository.resolve()
    if has_staged_changes(repository):
        raise AiAuditError(
            "L'index Git contient déjà des changements stagés. Committe-les ou déstage-les avant 'ocp ai commit' pour éviter de mélanger les intentions."
        )
    changed_paths = get_changed_paths(repository)
    if not changed_paths:
        raise AiAuditError("Aucun changement à committer dans ce dépôt.")

    prompt = build_commit_prompt(changed_paths)
    raw = _run_codex(_codex_command(codex, prompt), repository)
    plan = _parse_commit_plan(raw, changed_paths)
    plan["repository"] = str(repository)
    return plan


def create_commit_plan(repository: Path, plan: dict) -> list[dict[str, str]]:
    """Crée les commits du plan validé sans effectuer de push."""
    repository = repository.resolve()
    if has_staged_changes(repository):
        raise AiAuditError(
            "L'index Git a changé depuis l'analyse. Déstage les fichiers puis relance 'ocp ai commit'."
        )

    current_paths = set(get_changed_paths(repository))
    planned_paths = {path for item in plan.get("commits", []) for path in item.get("paths", [])}
    if current_paths != planned_paths:
        raise AiAuditError(
            "Les changements Git ont évolué depuis l'analyse. Relance 'ocp ai commit' pour recalculer le plan."
        )

    results: list[dict[str, str]] = []
    for item in plan["commits"]:
        message = item["message"]
        paths = item["paths"]
        try:
            subprocess.run(
                ["git", "add", "--", *paths],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            )
            staged = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=repository,
                check=False,
                capture_output=True,
                text=True,
            )
            if staged.returncode == 0:
                raise AiAuditError(f"Aucun changement stagé pour le commit '{message}'.")
            if staged.returncode != 1:
                raise AiAuditError(f"Impossible de vérifier le commit '{message}'.")
            subprocess.run(
                ["git", "commit", "-m", message],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            )
            commit = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except AiAuditError:
            raise
        except subprocess.CalledProcessError as exc:
            details = (exc.stderr or exc.stdout or "Erreur Git inconnue.").strip()
            raise AiAuditError(
                f"Impossible de créer le commit '{message}' : {details}. Les commits déjà créés sont conservés."
            ) from exc
        results.append({"commit": commit, "message": message})
    return results
