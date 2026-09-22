from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

import yaml

from .templates import (
    GITIGNORE_TEMPLATE,
    MARKDOWN_FILES,
    README_TEMPLATE,
)


class ProjectAlreadyExistsError(Exception):
    pass


class InvalidProjectNameError(Exception):
    pass


class GitInitializationError(Exception):
    pass


class WorkspaceNotFoundError(Exception):
    pass


class InvalidRepositoryError(Exception):
    pass


class RepositoryAlreadyExistsError(Exception):
    pass


class RepositoryCloneError(Exception):
    pass


class ProjectConfigError(Exception):
    pass


class GitStatusError(Exception):
    pass


class WorkspaceRemoteError(Exception):
    pass


class WorkspaceRemoteAlreadyExistsError(WorkspaceRemoteError):
    def __init__(self, remote: str) -> None:
        self.remote = remote
        super().__init__(f"Le remote origin est déjà configuré : {remote}")


class WorkspacePublishError(Exception):
    pass


class NothingToPublishError(WorkspacePublishError):
    pass


class GithubRepositoryError(Exception):
    pass


class PullRequestError(Exception):
    pass


def slugify_project_name(project_name: str) -> str:
    """Convertit un nom en nom de dossier kebab-case ASCII."""
    normalized = unicodedata.normalize("NFKD", project_name.strip())
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_name)
    return slug.strip("-").lower()


def create_project(project_name: str, destination: Path) -> Path:
    project_name = project_name.strip()
    project_slug = slugify_project_name(project_name)

    if not project_slug:
        raise InvalidProjectNameError(
            "Le nom du projet doit contenir au moins une lettre ou un chiffre."
        )

    project_dir = destination / project_slug

    if project_dir.exists():
        raise ProjectAlreadyExistsError(f"Le dossier existe déjà : {project_dir}")

    project_dir.mkdir(parents=True)
    (project_dir / "repos").mkdir()

    (project_dir / "README.md").write_text(
        README_TEMPLATE.format(project_name=project_name), encoding="utf-8"
    )

    project_config = {
        "project": {
            "id": project_slug,
            "name": project_name,
        },
        "methodology": "scrum",
        "repositories": [],
    }
    _write_config(project_dir, project_config)

    (project_dir / ".gitignore").write_text(GITIGNORE_TEMPLATE, encoding="utf-8")

    for relative_path, content in MARKDOWN_FILES.items():
        path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    _git_init(project_dir)
    return project_dir



def create_initial_commit(
    workspace: Path, message: str = "chore: initialize project workspace"
) -> str:
    """Crée le premier commit du workspace, sans remote ni push."""
    if workspace_has_commits(workspace):
        return _run_git(["rev-parse", "--short", "HEAD"], workspace)

    try:
        _run_git(["add", "-A"], workspace)
        _run_git(["commit", "-m", message], workspace)
        return _run_git(["rev-parse", "--short", "HEAD"], workspace)
    except FileNotFoundError as exc:
        raise GithubRepositoryError(
            "Impossible de lancer Git. Vérifie que Git est installé."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message_git = (exc.stderr or exc.stdout or "Erreur Git inconnue.").strip()
        raise GithubRepositoryError(
            f"Impossible de créer le premier commit : {message_git}"
        ) from exc


def create_github_repository(
    workspace: Path, repository_name: str | None = None
) -> dict[str, str]:
    """Crée un repository GitHub privé depuis le workspace et pousse le commit local."""
    repository_name = (repository_name or workspace.name).strip()
    if not repository_name:
        raise GithubRepositoryError("Le nom du repository GitHub est vide.")

    if get_workspace_remote(workspace):
        raise GithubRepositoryError(
            "Le workspace possède déjà un remote origin. Aucun repository GitHub n'a été créé."
        )

    if shutil.which("gh") is None:
        raise GithubRepositoryError(
            "GitHub CLI (gh) n'est pas installé ou n'est pas présent dans le PATH."
        )

    auth = subprocess.run(
        ["gh", "auth", "status"],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    )
    if auth.returncode != 0:
        message = (auth.stderr or auth.stdout or "Authentification GitHub requise.").strip()
        raise GithubRepositoryError(
            f"GitHub CLI n'est pas authentifié : {message}"
        )

    create_initial_commit(workspace)

    try:
        completed = subprocess.run(
            [
                "gh",
                "repo",
                "create",
                repository_name,
                "--private",
                "--source=.",
                "--remote=origin",
                "--push",
            ],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "Erreur GitHub CLI inconnue.").strip()
        raise GithubRepositoryError(
            f"Impossible de créer le repository GitHub : {message}"
        ) from exc

    remote = get_workspace_remote(workspace)
    if not remote:
        raise GithubRepositoryError(
            "Le repository GitHub semble créé, mais aucun remote origin n'a été configuré."
        )

    return {
        "name": repository_name,
        "remote": remote,
        "output": completed.stdout.strip(),
    }

def find_workspace(start: Path) -> Path:
    """Cherche le workspace OCP dans le dossier courant ou ses parents."""
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / "project.yml").is_file() and (candidate / "repos").is_dir():
            return candidate
    raise WorkspaceNotFoundError(
        "Aucun workspace OCP trouvé. Place-toi dans un projet créé avec 'ocp init'."
    )


def add_repository(workspace: Path, repository_name: str, url: str) -> dict[str, str]:
    repository_name = repository_name.strip()
    url = url.strip()
    repository_id = slugify_project_name(repository_name)

    if not repository_id:
        raise InvalidRepositoryError(
            "Le nom du repository doit contenir au moins une lettre ou un chiffre."
        )
    if not url:
        raise InvalidRepositoryError("L'URL Git ne peut pas être vide.")

    config = _read_config(workspace)
    repositories = config.setdefault("repositories", [])
    if not isinstance(repositories, list):
        raise ProjectConfigError("La clé 'repositories' de project.yml doit être une liste.")

    relative_path = f"repos/{repository_id}"
    target = workspace / relative_path

    for repository in repositories:
        if not isinstance(repository, dict):
            continue
        if repository.get("id") == repository_id or repository.get("path") == relative_path:
            raise RepositoryAlreadyExistsError(
                f"Un repository '{repository_id}' est déjà enregistré."
            )
        if repository.get("url") == url:
            raise RepositoryAlreadyExistsError(
                "Cette URL Git est déjà enregistrée dans le projet."
            )

    if target.exists():
        raise RepositoryAlreadyExistsError(f"Le dossier existe déjà : {target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    _git_clone(url, target)

    repository = {
        "id": repository_id,
        "name": repository_name,
        "path": relative_path,
        "url": url,
    }
    repositories.append(repository)

    _write_config(workspace, config)
    _update_readme_repositories(workspace, repositories)

    return repository


def get_workspace_remote(workspace: Path) -> str | None:
    """Retourne l'URL du remote origin du workspace, s'il existe."""
    try:
        return _run_git_optional(["config", "--get", "remote.origin.url"], workspace)
    except FileNotFoundError as exc:
        raise WorkspaceRemoteError(
            "Impossible de lancer Git. Vérifie que Git est installé."
        ) from exc


def set_workspace_remote(workspace: Path, url: str, replace: bool = False) -> str:
    """Configure le remote origin du workspace sans effectuer de push."""
    url = url.strip()
    if not url:
        raise WorkspaceRemoteError("L'URL Git du workspace ne peut pas être vide.")

    try:
        is_repo = _run_git(["rev-parse", "--is-inside-work-tree"], workspace)
        if is_repo != "true":
            raise WorkspaceRemoteError("Le workspace n'est pas un dépôt Git.")

        current = get_workspace_remote(workspace)
        if current == url:
            return url
        if current and not replace:
            raise WorkspaceRemoteAlreadyExistsError(current)

        if current:
            _run_git(["remote", "set-url", "origin", url], workspace)
        else:
            _run_git(["remote", "add", "origin", url], workspace)
    except WorkspaceRemoteError:
        raise
    except FileNotFoundError as exc:
        raise WorkspaceRemoteError(
            "Impossible de lancer Git. Vérifie que Git est installé."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "Erreur Git inconnue.").strip()
        raise WorkspaceRemoteError(
            f"Impossible de configurer le remote du workspace : {message}"
        ) from exc

    return url


def get_workspace_changes(workspace: Path) -> list[str]:
    """Retourne les lignes porcelain des changements du workspace."""
    try:
        porcelain = _run_git(["status", "--porcelain"], workspace)
    except FileNotFoundError as exc:
        raise WorkspacePublishError(
            "Impossible de lancer Git. Vérifie que Git est installé."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "Erreur Git inconnue.").strip()
        raise WorkspacePublishError(
            f"Impossible de lire les changements du workspace : {message}"
        ) from exc

    return [line for line in porcelain.splitlines() if line.strip()]


def get_workspace_branch(workspace: Path) -> str:
    """Retourne le nom de la branche courante du workspace."""
    try:
        branch = _run_git(["symbolic-ref", "--quiet", "--short", "HEAD"], workspace)
    except FileNotFoundError as exc:
        raise WorkspacePublishError(
            "Impossible de lancer Git. Vérifie que Git est installé."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "Erreur Git inconnue.").strip()
        raise WorkspacePublishError(
            f"Impossible de déterminer la branche courante : {message}"
        ) from exc

    if not branch:
        raise WorkspacePublishError("Impossible de déterminer la branche courante.")
    return branch


def workspace_has_commits(workspace: Path) -> bool:
    """Indique si le workspace possède déjà au moins un commit."""
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0




def get_workspace_change_paths(workspace: Path) -> list[str]:
    """Retourne les chemins modifiés du workspace, sans les repositories ignorés."""
    try:
        tracked = []
        if workspace_has_commits(workspace):
            output = _run_git(["diff", "HEAD", "--name-only", "--diff-filter=ACDMRTUXB"], workspace)
            tracked = [line.strip() for line in output.splitlines() if line.strip()]

        untracked_output = _run_git(["ls-files", "--others", "--exclude-standard"], workspace)
        untracked = [line.strip() for line in untracked_output.splitlines() if line.strip()]
    except FileNotFoundError as exc:
        raise WorkspacePublishError(
            "Impossible de lancer Git. Vérifie que Git est installé."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "Erreur Git inconnue.").strip()
        raise WorkspacePublishError(
            f"Impossible de lire les fichiers modifiés du workspace : {message}"
        ) from exc

    return sorted(dict.fromkeys(tracked + untracked))


PUBLISH_GROUPS = [
    ("audits", "docs(audit): update technical audits"),
    ("docs", "docs: update project documentation"),
    ("management", "docs(scrum): update project management"),
    ("mentoring", "docs(mentor): update mentoring notes"),
    ("journal", "docs(journal): update AI journal"),
    ("evaluation", "docs(evaluation): update evaluation preparation"),
]


def build_publish_plan(workspace: Path) -> list[dict]:
    """Regroupe les changements du workspace en commits logiques et déterministes."""
    paths = get_workspace_change_paths(workspace)
    if not paths:
        return []

    if not workspace_has_commits(workspace):
        return [{
            "key": "initial",
            "message": "chore: initialize project workspace",
            "paths": paths,
        }]

    grouped: dict[str, dict] = {}
    root_paths: list[str] = []

    for path in paths:
        matched = False
        for prefix, message in PUBLISH_GROUPS:
            if path == prefix or path.startswith(prefix + "/"):
                group = grouped.setdefault(prefix, {
                    "key": prefix,
                    "message": message,
                    "paths": [],
                })
                group["paths"].append(path)
                matched = True
                break
        if not matched:
            root_paths.append(path)

    plan = [grouped[prefix] for prefix, _ in PUBLISH_GROUPS if prefix in grouped]
    if root_paths:
        plan.append({
            "key": "workspace",
            "message": "chore: update project workspace",
            "paths": root_paths,
        })
    return plan


def get_unpushed_commit_count(workspace: Path) -> int:
    """Retourne le nombre de commits locaux non présents sur l'upstream/origin courant."""
    if not workspace_has_commits(workspace):
        return 0

    branch = get_workspace_branch(workspace)
    upstream = _run_git_optional(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        workspace,
    )
    target = upstream or f"origin/{branch}"

    target_exists = subprocess.run(
        ["git", "rev-parse", "--verify", target],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    ).returncode == 0
    if not target_exists:
        try:
            count = _run_git(["rev-list", "--count", "HEAD"], workspace)
            return int(count or "0")
        except (ValueError, subprocess.CalledProcessError, FileNotFoundError) as exc:
            raise WorkspacePublishError(
                "Impossible de déterminer les commits locaux à pousser."
            ) from exc

    try:
        count = _run_git(["rev-list", "--count", f"{target}..HEAD"], workspace)
        return int(count or "0")
    except (ValueError, subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise WorkspacePublishError(
            "Impossible de déterminer les commits locaux à pousser."
        ) from exc


def publish_workspace_plan(workspace: Path, plan: list[dict] | None = None) -> dict:
    """Crée les commits logiques du workspace puis effectue un seul push."""
    remote = get_workspace_remote(workspace)
    if not remote:
        raise WorkspacePublishError(
            "Aucun remote origin configuré. Utilise d'abord 'ocp remote set'."
        )

    branch = get_workspace_branch(workspace)
    plan = build_publish_plan(workspace) if plan is None else plan
    commits: list[dict[str, str]] = []

    try:
        for group in plan:
            paths = list(group.get("paths") or [])
            message = str(group.get("message") or "").strip()
            if not paths or not message:
                continue

            _run_git(["add", "--", *paths], workspace)
            staged = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=workspace,
                check=False,
                capture_output=True,
                text=True,
            )
            if staged.returncode not in (0, 1):
                raise subprocess.CalledProcessError(
                    staged.returncode, staged.args, staged.stdout, staged.stderr
                )
            if staged.returncode == 0:
                continue

            _run_git(["commit", "-m", message], workspace)
            commits.append({
                "message": message,
                "commit": _run_git(["rev-parse", "--short", "HEAD"], workspace),
            })

        if not workspace_has_commits(workspace):
            raise NothingToPublishError("Aucun commit à publier dans le workspace.")

        unpushed = get_unpushed_commit_count(workspace)
        if unpushed == 0:
            commit_hash = _run_git(["rev-parse", "--short", "HEAD"], workspace)
            return {
                "branch": branch,
                "remote": remote,
                "commits": commits,
                "commit": commit_hash,
                "pushed": False,
                "unpushed_before_push": 0,
            }

        upstream = _run_git_optional(
            ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            workspace,
        )
        if upstream:
            _run_git(["push"], workspace)
        else:
            _run_git(["push", "-u", "origin", branch], workspace)

        commit_hash = _run_git(["rev-parse", "--short", "HEAD"], workspace)
    except NothingToPublishError:
        raise
    except FileNotFoundError as exc:
        raise WorkspacePublishError(
            "Impossible de lancer Git. Vérifie que Git est installé."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message_git = (exc.stderr or exc.stdout or "Erreur Git inconnue.").strip()
        raise WorkspacePublishError(f"Publication impossible : {message_git}") from exc

    return {
        "branch": branch,
        "remote": remote,
        "commits": commits,
        "commit": commit_hash,
        "pushed": True,
        "unpushed_before_push": unpushed,
    }

def publish_workspace(workspace: Path, message: str) -> dict:
    """Commit les changements du workspace puis les pousse vers origin."""
    message = message.strip()
    if not message:
        raise WorkspacePublishError("Le message de commit ne peut pas être vide.")

    remote = get_workspace_remote(workspace)
    if not remote:
        raise WorkspacePublishError(
            "Aucun remote origin configuré. Utilise d'abord 'ocp remote set'."
        )

    branch = get_workspace_branch(workspace)
    changes = get_workspace_changes(workspace)
    committed = False

    try:
        if changes:
            _run_git(["add", "-A"], workspace)

            staged = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=workspace,
                check=False,
                capture_output=True,
                text=True,
            )
            if staged.returncode not in (0, 1):
                raise subprocess.CalledProcessError(
                    staged.returncode, staged.args, staged.stdout, staged.stderr
                )

            if staged.returncode == 1:
                _run_git(["commit", "-m", message], workspace)
                committed = True

        if not workspace_has_commits(workspace):
            raise NothingToPublishError(
                "Aucun commit à publier dans le workspace."
            )

        upstream = _run_git_optional(
            ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            workspace,
        )
        if upstream:
            _run_git(["push"], workspace)
        else:
            _run_git(["push", "-u", "origin", branch], workspace)

        commit_hash = _run_git(["rev-parse", "--short", "HEAD"], workspace)
    except NothingToPublishError:
        raise
    except FileNotFoundError as exc:
        raise WorkspacePublishError(
            "Impossible de lancer Git. Vérifie que Git est installé."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message_git = (exc.stderr or exc.stdout or "Erreur Git inconnue.").strip()
        raise WorkspacePublishError(f"Publication impossible : {message_git}") from exc

    return {
        "branch": branch,
        "remote": remote,
        "committed": committed,
        "commit": commit_hash,
    }



def push_workspace(workspace: Path) -> dict:
    """Pousse uniquement les commits déjà créés du workspace vers origin."""
    remote = get_workspace_remote(workspace)
    if not remote:
        raise WorkspacePublishError(
            "Aucun remote origin configuré. Utilise d'abord 'ocp remote set'."
        )

    changes = get_workspace_changes(workspace)
    if changes:
        raise WorkspacePublishError(
            "Des modifications locales ne sont pas commitées. Lance d'abord 'ocp ai commit workspace'."
        )
    if not workspace_has_commits(workspace):
        raise NothingToPublishError("Aucun commit à publier dans le workspace.")

    branch = get_workspace_branch(workspace)
    unpushed = get_unpushed_commit_count(workspace)
    if unpushed == 0:
        return {
            "branch": branch,
            "remote": remote,
            "pushed": False,
            "unpushed_before_push": 0,
        }

    try:
        upstream = _run_git_optional(
            ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            workspace,
        )
        if upstream:
            _run_git(["push"], workspace)
        else:
            _run_git(["push", "-u", "origin", branch], workspace)
    except FileNotFoundError as exc:
        raise WorkspacePublishError(
            "Impossible de lancer Git. Vérifie que Git est installé."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "Erreur Git inconnue.").strip()
        raise WorkspacePublishError(f"Push impossible : {message}") from exc

    return {
        "branch": branch,
        "remote": remote,
        "pushed": True,
        "unpushed_before_push": unpushed,
    }


def _require_gh(repository: Path) -> None:
    if shutil.which("gh") is None:
        raise PullRequestError(
            "GitHub CLI (gh) n'est pas installé ou n'est pas présent dans le PATH."
        )
    auth = subprocess.run(
        ["gh", "auth", "status"],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if auth.returncode != 0:
        message = (auth.stderr or auth.stdout or "Authentification GitHub requise.").strip()
        raise PullRequestError(f"GitHub CLI n'est pas authentifié : {message}")


def _git_changes(repository: Path) -> list[str]:
    try:
        porcelain = _run_git(["status", "--porcelain"], repository)
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "Erreur Git inconnue.").strip()
        raise PullRequestError(
            f"Impossible de lire l'état Git de {repository.name} : {message}"
        ) from exc
    return [line for line in porcelain.splitlines() if line.strip()]


def _git_branch(repository: Path) -> str:
    try:
        return _run_git(["symbolic-ref", "--quiet", "--short", "HEAD"], repository)
    except subprocess.CalledProcessError as exc:
        raise PullRequestError(
            f"Impossible de déterminer la branche courante de {repository.name}."
        ) from exc


def _git_origin(repository: Path) -> str | None:
    return _run_git_optional(["config", "--get", "remote.origin.url"], repository)


def _github_repository_from_url(url: str | None) -> str | None:
    if not url:
        return None

    value = url.strip().rstrip("/")
    patterns = (
        r"^https?://github\.com/(?P<repo>[^/]+/[^/]+?)(?:\.git)?$",
        r"^git@github\.com:(?P<repo>[^/]+/[^/]+?)(?:\.git)?$",
        r"^ssh://git@github\.com/(?P<repo>[^/]+/[^/]+?)(?:\.git)?$",
    )
    for pattern in patterns:
        match = re.match(pattern, value)
        if match:
            return match.group("repo")
    return None


def resolve_pull_request_target(workspace: Path, start: Path) -> dict:
    """Résout le dépôt Git actif : workspace ou repository applicatif enregistré."""
    workspace = workspace.resolve()
    start = start.resolve()

    try:
        git_root = Path(_run_git(["rev-parse", "--show-toplevel"], start)).resolve()
    except subprocess.CalledProcessError as exc:
        raise PullRequestError(
            "Le dossier courant n'appartient pas à un dépôt Git du projet OCP."
        ) from exc

    if git_root == workspace:
        return {
            "id": "workspace",
            "name": "workspace",
            "path": workspace,
            "configured_url": get_workspace_remote(workspace),
        }

    config = _read_config(workspace)
    repositories = config.get("repositories", [])
    if not isinstance(repositories, list):
        raise ProjectConfigError("La clé 'repositories' de project.yml doit être une liste.")

    for repository in repositories:
        if not isinstance(repository, dict):
            continue
        relative_path = repository.get("path")
        if not relative_path:
            continue
        repository_path = (workspace / str(relative_path)).resolve()
        if git_root == repository_path:
            return {
                "id": str(repository.get("id") or repository_path.name),
                "name": str(repository.get("name") or repository.get("id") or repository_path.name),
                "path": repository_path,
                "configured_url": repository.get("url"),
            }

    raise PullRequestError(
        f"Le dépôt Git courant ({git_root}) n'est pas enregistré dans project.yml."
    )


def _github_repository_for_target(target: dict) -> str:
    repository = target["path"]
    origin = _git_origin(repository)

    # Le remote origin réel est prioritaire : pour un fork, c'est lui qui doit recevoir la PR.
    github_repository = _github_repository_from_url(origin)
    if github_repository:
        return github_repository

    github_repository = _github_repository_from_url(target.get("configured_url"))
    if github_repository:
        return github_repository

    raise PullRequestError(
        "Impossible de déterminer le repository GitHub cible. "
        "Configure un remote origin GitHub pour ce dépôt."
    )


def _push_git_target(target: dict) -> dict:
    repository = target["path"]
    target_id = target["id"]

    if _git_changes(repository):
        raise PullRequestError(
            "Des modifications locales ne sont pas commitées. "
            f"Lance d'abord 'ocp ai commit {target_id}'."
        )

    branch = _git_branch(repository)
    if not _git_origin(repository):
        raise PullRequestError(
            f"Le dépôt '{target_id}' n'a pas de remote origin configuré."
        )

    upstream = _run_git_optional(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        repository,
    )

    try:
        if upstream:
            completed = subprocess.run(
                ["git", "push"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            completed = subprocess.run(
                ["git", "push", "-u", "origin", branch],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            )
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "Erreur Git inconnue.").strip()
        raise PullRequestError(f"Push impossible pour '{target_id}' : {message}") from exc

    output = "\n".join(filter(None, [completed.stdout.strip(), completed.stderr.strip()]))
    pushed = "Everything up-to-date" not in output
    return {"branch": branch, "pushed": pushed}


def create_pull_request(
    workspace: Path,
    *,
    start: Path | None = None,
    open_web: bool = True,
) -> dict:
    """Push le dépôt Git actif puis crée (ou retrouve) sa Pull Request GitHub."""
    target = resolve_pull_request_target(workspace, start or workspace)
    repository = target["path"]
    target_id = target["id"]

    if _git_changes(repository):
        raise PullRequestError(
            "Des modifications locales ne sont pas commitées. "
            f"Lance d'abord 'ocp ai commit {target_id}'."
        )

    branch = _git_branch(repository)
    if branch == "main":
        raise PullRequestError(
            "La branche courante est main. Crée ou place-toi sur une branche de travail avant d'ouvrir une PR."
        )

    github_repository = _github_repository_for_target(target)
    _require_gh(repository)
    push_result = _push_git_target(target)

    existing = subprocess.run(
        [
            "gh", "pr", "view", branch,
            "-R", github_repository,
            "--json", "url",
            "--jq", ".url",
        ],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if existing.returncode == 0 and existing.stdout.strip():
        url = existing.stdout.strip()
        created = False
    else:
        try:
            created_pr = subprocess.run(
                [
                    "gh", "pr", "create",
                    "-R", github_repository,
                    "--base", "main",
                    "--head", branch,
                    "--fill",
                ],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or "Erreur GitHub CLI inconnue.").strip()
            raise PullRequestError(f"Création de la PR impossible : {message}") from exc
        url = created_pr.stdout.strip()
        created = True

    if open_web:
        try:
            subprocess.run(
                ["gh", "pr", "view", branch, "-R", github_repository, "--web"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or "Erreur GitHub CLI inconnue.").strip()
            raise PullRequestError(
                f"La PR existe mais son ouverture dans le navigateur a échoué : {message}"
            ) from exc

    return {
        "target": target_id,
        "repository": github_repository,
        "branch": branch,
        "url": url,
        "created": created,
        "pushed": bool(push_result.get("pushed")),
    }


def _synchronize_main_after_rebase(repository: Path, merged_branch: str) -> None:
    """Réaligne main sur origin/main après un rebase-merge sans écraser de commit local unique."""
    try:
        _run_git(["fetch", "origin"], repository)
        _run_git(["switch", "main"], repository)

        cherry = subprocess.run(
            ["git", "cherry", "origin/main", "main"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        unique_commits = [line for line in cherry.splitlines() if line.startswith("+")]
        if unique_commits:
            raise PullRequestError(
                "La PR est mergée, mais main locale contient des commits uniques non présents "
                "sur origin/main. Synchronisation automatique interrompue pour éviter toute perte."
            )

        # Après un rebase-merge GitHub, des commits patch-équivalents peuvent avoir de nouveaux SHA.
        # origin/main est alors la source de vérité et le reset est sûr si git cherry ne trouve aucun '+'.
        _run_git(["reset", "--hard", "origin/main"], repository)

        subprocess.run(
            ["git", "branch", "-D", merged_branch],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "push", "origin", "--delete", merged_branch],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "Erreur Git inconnue.").strip()
        raise PullRequestError(
            f"La PR est mergée mais la synchronisation locale de main a échoué : {message}"
        ) from exc


def merge_pull_request(workspace: Path, *, start: Path | None = None) -> dict:
    """Merge la PR du dépôt Git actif en rebase puis synchronise main proprement."""
    target = resolve_pull_request_target(workspace, start or workspace)
    repository = target["path"]
    target_id = target["id"]

    if _git_changes(repository):
        raise PullRequestError(
            "Des modifications locales ne sont pas commitées. "
            f"Lance d'abord 'ocp ai commit {target_id}' ou restaure-les avant le merge."
        )

    branch = _git_branch(repository)
    if branch == "main":
        raise PullRequestError(
            "La branche courante est main. Place-toi sur la branche de la PR à merger."
        )

    github_repository = _github_repository_for_target(target)
    _require_gh(repository)
    _push_git_target(target)

    try:
        subprocess.run(
            [
                "gh", "pr", "merge", branch,
                "-R", github_repository,
                "--rebase",
            ],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "Erreur GitHub CLI inconnue.").strip()
        raise PullRequestError(f"Merge de la PR impossible : {message}") from exc

    _synchronize_main_after_rebase(repository, branch)

    return {
        "target": target_id,
        "repository": github_repository,
        "merged_branch": branch,
        "current_branch": "main",
    }

def get_repositories(workspace: Path) -> list[dict]:
    """Retourne les repositories enregistrés dans project.yml."""
    config = _read_config(workspace)
    repositories = config.get("repositories", [])
    if not isinstance(repositories, list):
        raise ProjectConfigError("La clé 'repositories' de project.yml doit être une liste.")

    valid = []
    for repository in repositories:
        if isinstance(repository, dict):
            valid.append(repository)
    return valid


def get_project_status(workspace: Path) -> dict:
    """Retourne un état synthétique du workspace et de ses repositories."""
    config = _read_config(workspace)
    project = config.get("project", {})
    if not isinstance(project, dict):
        raise ProjectConfigError("La clé 'project' de project.yml doit être un objet.")

    repositories = config.get("repositories", [])
    if not isinstance(repositories, list):
        raise ProjectConfigError("La clé 'repositories' de project.yml doit être une liste.")

    result = {
        "project": {
            "id": project.get("id", workspace.name),
            "name": project.get("name", workspace.name),
        },
        "workspace": _get_git_status(workspace),
        "repositories": [],
    }

    for repository in repositories:
        if not isinstance(repository, dict):
            continue

        relative_path = repository.get("path") or ""
        path = workspace / relative_path if relative_path else workspace / "repos" / str(
            repository.get("id", "")
        )

        item = {
            "id": repository.get("id", path.name),
            "name": repository.get("name") or repository.get("id") or path.name,
            "path": relative_path,
            "configured_url": repository.get("url"),
        }

        if not path.exists():
            item.update(
                {
                    "exists": False,
                    "is_git_repository": False,
                    "branch": None,
                    "remote": None,
                    "changes": None,
                }
            )
        elif not (path / ".git").exists():
            item.update(
                {
                    "exists": True,
                    "is_git_repository": False,
                    "branch": None,
                    "remote": None,
                    "changes": None,
                }
            )
        else:
            item.update({"exists": True, "is_git_repository": True})
            item.update(_get_git_status(path))

        result["repositories"].append(item)

    return result


def _get_git_status(path: Path) -> dict:
    if not path.exists():
        raise GitStatusError(f"Le chemin n'existe pas : {path}")

    try:
        branch = _run_git(["symbolic-ref", "--quiet", "--short", "HEAD"], path)
        porcelain = _run_git(["status", "--porcelain"], path)
        remote = _run_git_optional(["config", "--get", "remote.origin.url"], path)
    except FileNotFoundError as exc:
        raise GitStatusError("Impossible de lancer Git. Vérifie que Git est installé.") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "Erreur Git inconnue.").strip()
        raise GitStatusError(f"Impossible de lire l'état Git de {path}: {message}") from exc

    lines = [line for line in porcelain.splitlines() if line.strip()]
    untracked = sum(1 for line in lines if line.startswith("??"))
    changed = len(lines) - untracked

    return {
        "branch": branch or "HEAD",
        "remote": remote,
        "changes": {
            "total": len(lines),
            "tracked": changed,
            "untracked": untracked,
            "clean": len(lines) == 0,
        },
    }


def _run_git(arguments: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _run_git_optional(arguments: list[str], cwd: Path) -> str | None:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip()
    return value or None


def _read_config(workspace: Path) -> dict:
    path = workspace / "project.yml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ProjectConfigError(f"Impossible de lire {path}.") from exc

    if not isinstance(data, dict):
        raise ProjectConfigError("project.yml doit contenir un objet YAML à la racine.")
    return data


def _write_config(workspace: Path, config: dict) -> None:
    path = workspace / "project.yml"
    try:
        path.write_text(
            yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    except OSError as exc:
        raise ProjectConfigError(f"Impossible d'écrire {path}.") from exc


def _update_readme_repositories(workspace: Path, repositories: list[dict]) -> None:
    readme_path = workspace / "README.md"
    if not readme_path.exists():
        return

    text = readme_path.read_text(encoding="utf-8")
    lines = []
    for repository in repositories:
        name = repository.get("name") or repository.get("id") or "Repository"
        url = repository.get("url", "")
        path = repository.get("path", "")
        lines.append(f"- [{name}]({url}) — `{path}`")

    body = "\n".join(lines) if lines else "_Aucun repository enregistré._"
    managed = (
        "<!-- ocp:repositories:start -->\n"
        f"{body}\n"
        "<!-- ocp:repositories:end -->"
    )

    marker_pattern = re.compile(
        r"<!-- ocp:repositories:start -->.*?<!-- ocp:repositories:end -->",
        re.DOTALL,
    )

    if marker_pattern.search(text):
        text = marker_pattern.sub(managed, text)
    else:
        section_pattern = re.compile(
            r"(^## Repositories\s*$)(.*?)(?=^##\s|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        if section_pattern.search(text):
            text = section_pattern.sub(lambda m: f"{m.group(1)}\n\n{managed}\n", text)
        else:
            text = text.rstrip() + f"\n\n## Repositories\n\n{managed}\n"

    readme_path.write_text(text, encoding="utf-8")


def _git_init(project_dir: Path) -> None:
    try:
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=project_dir,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise GitInitializationError(
            "Impossible d'initialiser Git. Vérifie que Git est installé."
        ) from exc


def _git_clone(url: str, target: Path) -> None:
    try:
        subprocess.run(
            ["git", "clone", url, str(target)],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RepositoryCloneError(
            "Impossible de lancer Git. Vérifie que Git est installé."
        ) from exc
    except subprocess.CalledProcessError as exc:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        message = (exc.stderr or exc.stdout or "Erreur Git inconnue.").strip()
        raise RepositoryCloneError(f"Échec du clone : {message}") from exc
