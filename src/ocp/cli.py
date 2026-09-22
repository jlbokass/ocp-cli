from __future__ import annotations

from pathlib import Path
import subprocess

import typer
from rich.console import Console
from rich.table import Table

from .ai import (
    AiAuditError,
    AuditAlreadyExistsError,
    MissingProjectAuditError,
    MissingCadrageError,
    MissingWorkflowError,
    MissingBacklogError,
    LegacySprintFileError,
    MissingRepositoryAuditsError,
    MissingSourceDocumentsError,
    SourceDocumentError,
    run_codex_audit,
    run_codex_cadrage,
    run_codex_project_audit,
    run_codex_workflow,
    run_codex_backlog,
    run_codex_sprint,
    find_git_repository,
    plan_codex_commits,
    create_commit_plan,
)
from .backlog_github import (
    BacklogImportError,
    import_backlog_issues,
    parse_backlog,
)
from .project import (
    GitInitializationError,
    GithubRepositoryError,
    GitStatusError,
    InvalidProjectNameError,
    InvalidRepositoryError,
    ProjectAlreadyExistsError,
    ProjectConfigError,
    NothingToPublishError,
    PullRequestError,
    RepositoryAlreadyExistsError,
    RepositoryCloneError,
    WorkspaceNotFoundError,
    WorkspaceRemoteAlreadyExistsError,
    WorkspaceRemoteError,
    WorkspacePublishError,
    add_repository,
    create_github_repository,
    create_project,
    find_workspace,
    get_project_status,
    get_repositories,
    get_workspace_changes,
    build_publish_plan,
    get_unpushed_commit_count,
    get_workspace_branch,
    get_workspace_remote,
    publish_workspace,
    publish_workspace_plan,
    push_workspace,
    create_pull_request,
    merge_pull_request,
    resolve_pull_request_target,
    set_workspace_remote,
    workspace_has_commits,
)

app = typer.Typer(
    name="ocp",
    help="Organisation simple des projets OpenClassrooms DevOps.",
    no_args_is_help=True,
)
repo_app = typer.Typer(
    help="Gestion des repositories applicatifs du workspace.",
    no_args_is_help=True,
)
app.add_typer(repo_app, name="repo")

remote_app = typer.Typer(
    help="Gestion du remote Git du workspace.",
    no_args_is_help=True,
)
app.add_typer(remote_app, name="remote")

pr_app = typer.Typer(
    help="Gestion légère des Pull Requests GitHub du dépôt Git actif.",
    no_args_is_help=True,
)
app.add_typer(pr_app, name="pr")

backlog_app = typer.Typer(
    help="Import et synchronisation légère du backlog vers GitHub Issues.",
    no_args_is_help=True,
)
app.add_typer(backlog_app, name="backlog")

ai_app = typer.Typer(
    help="Commandes IA appliquées au projet.",
    no_args_is_help=True,
)
app.add_typer(ai_app, name="ai")

console = Console()


@app.callback()
def main() -> None:
    """Point d’entrée de la CLI ocp."""
    pass


@app.command()
def init() -> None:
    """Crée un nouveau workspace dans le répertoire courant."""
    name = typer.prompt("Nom du projet").strip()

    if not name:
        console.print("[red]Erreur :[/red] le nom du projet ne peut pas être vide.")
        raise typer.Exit(code=1)

    try:
        project_dir = create_project(name, Path.cwd().resolve())
    except (ProjectAlreadyExistsError, InvalidProjectNameError) as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except GitInitializationError as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Workspace créé :[/green] {project_dir}")
    console.print("[dim]Git initialisé sur la branche main. Le dossier repos/ est ignoré.[/dim]")

    try:
        with console.status("[bold]Création du repository GitHub privé…[/bold]"):
            github = create_github_repository(project_dir, project_dir.name)
    except GithubRepositoryError as exc:
        console.print(
            "[yellow]Workspace local prêt, mais le repository GitHub n'a pas été créé.[/yellow]"
        )
        console.print(f"[yellow]{exc}[/yellow]")
        console.print(
            "[dim]Le projet local reste utilisable. Tu pourras configurer le remote plus tard.[/dim]"
        )
        return

    console.print(f"[green]Repository GitHub créé :[/green] {github['remote']}")
    console.print("[green]Premier commit poussé sur origin/main.[/green]")


@app.command()
def status() -> None:
    """Affiche l'état Git du workspace et de tous les repositories enregistrés."""
    try:
        workspace = find_workspace(Path.cwd())
        data = get_project_status(workspace)
    except (WorkspaceNotFoundError, ProjectConfigError, GitStatusError) as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[bold]Projet :[/bold] {data['project']['name']}")
    console.print(f"[bold]Workspace :[/bold] {workspace}")
    console.print()

    ws = data["workspace"]
    console.print("[bold]Git workspace[/bold]")
    console.print(f"  Branche : {ws['branch']}")
    console.print(f"  État    : {_format_changes(ws['changes'])}")
    console.print(f"  Remote  : {ws['remote'] or '[dim]non configuré[/dim]'}")
    console.print()

    repositories = data["repositories"]
    if not repositories:
        console.print("[bold]Repositories[/bold]\n  [dim]Aucun repository enregistré.[/dim]")
        return

    table = Table(title="Repositories", show_lines=False)
    table.add_column("Repository", style="bold")
    table.add_column("Branche")
    table.add_column("État")
    table.add_column("Remote")

    for repository in repositories:
        if not repository["exists"]:
            branch = "—"
            state = "[red]dossier introuvable[/red]"
            remote = repository.get("configured_url") or "—"
        elif not repository["is_git_repository"]:
            branch = "—"
            state = "[red]pas un dépôt Git[/red]"
            remote = repository.get("configured_url") or "—"
        else:
            branch = repository["branch"]
            state = _format_changes(repository["changes"])
            remote = repository["remote"] or repository.get("configured_url") or "—"

        table.add_row(repository["name"], branch, state, remote)

    console.print(table)


def _format_changes(changes: dict | None) -> str:
    if not changes:
        return "—"
    if changes["clean"]:
        return "[green]clean[/green]"

    parts = []
    if changes["tracked"]:
        parts.append(f"{changes['tracked']} suivi(s)")
    if changes["untracked"]:
        parts.append(f"{changes['untracked']} non suivi(s)")
    details = ", ".join(parts)
    return f"[yellow]{changes['total']} changement(s)[/yellow] ({details})"


@app.command()
def publish() -> None:
    """Pousse uniquement les commits déjà créés du workspace vers origin."""
    try:
        workspace = find_workspace(Path.cwd())
        result = push_workspace(workspace)
    except (
        WorkspaceNotFoundError,
        WorkspaceRemoteError,
        WorkspacePublishError,
        NothingToPublishError,
    ) as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if result["pushed"]:
        console.print(
            f"[green]Branche publiée :[/green] origin/{result['branch']} "
            f"[dim]({result['unpushed_before_push']} commit(s) poussé(s))[/dim]"
        )
    else:
        console.print(
            f"[green]Rien à pousser :[/green] origin/{result['branch']} est déjà synchronisé."
        )


@pr_app.command("create")
def pr_create() -> None:
    """Push le dépôt Git actif, crée sa PR GitHub et l'ouvre dans le navigateur."""
    try:
        cwd = Path.cwd()
        workspace = find_workspace(cwd)
        result = create_pull_request(workspace, start=cwd, open_web=True)
    except (WorkspaceNotFoundError, PullRequestError, ProjectConfigError) as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    action = "PR créée" if result["created"] else "PR existante"
    console.print(f"[green]{action} :[/green] {result['url'] or '(URL non retournée)'}")
    console.print(
        f"[dim]Cible : {result['target']} · {result['repository']} · branche {result['branch']}[/dim]"
    )


@pr_app.command("merge")
def pr_merge() -> None:
    """Merge la PR du dépôt Git actif en rebase puis synchronise main."""
    try:
        cwd = Path.cwd()
        workspace = find_workspace(cwd)
        target = resolve_pull_request_target(workspace, cwd)
        repository_path = target["path"]
        branch_name = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repository_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (WorkspaceNotFoundError, PullRequestError, ProjectConfigError, subprocess.CalledProcessError) as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if not typer.confirm(
        f"Merger la PR de '{target['id']}:{branch_name}' en rebase puis revenir sur main ?",
        default=True,
    ):
        console.print("[yellow]Merge annulé.[/yellow]")
        raise typer.Exit()

    try:
        result = merge_pull_request(workspace, start=cwd)
    except PullRequestError as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        f"[green]PR mergée :[/green] {result['target']}:{result['merged_branch']} → main"
    )
    console.print("[green]main synchronisée avec origin.[/green]")


@backlog_app.command("import")
def backlog_import() -> None:
    """Importe management/backlog.md en GitHub Issues et labels.

    L'ajout au GitHub Project doit être assuré par le workflow Auto-add du Project.
    """
    try:
        workspace = find_workspace(Path.cwd())
        items = parse_backlog(workspace / "management" / "backlog.md")
    except (WorkspaceNotFoundError, BacklogImportError) as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[bold]Items détectés :[/bold] {len(items)}")
    console.print(
        "[dim]OCP créera uniquement des labels et des GitHub Issues. "
        "Il n'effectuera aucune mutation GitHub Project.[/dim]"
    )
    console.print(
        "[yellow]Vérifie que le workflow GitHub Project 'Auto-add to project' "
        "est activé avant de continuer.[/yellow]"
    )
    if not typer.confirm("Importer le backlog dans GitHub Issues ?", default=True):
        console.print("[yellow]Import annulé.[/yellow]")
        raise typer.Exit()

    try:
        with console.status("[bold]Création / vérification des Issues GitHub…[/bold]"):
            result = import_backlog_issues(workspace)
    except BacklogImportError as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Repository :[/green] {result['repository']}")
    console.print(f"[green]Issues créées :[/green] {len(result['created'])}")
    console.print(f"[green]Issues déjà présentes :[/green] {len(result['reused'])}")
    console.print(f"[green]Labels créés :[/green] {len(result['created_labels'])}")
    console.print(
        "[dim]Les nouvelles Issues doivent apparaître automatiquement dans le Project via le workflow Auto-add.[/dim]"
    )


@remote_app.command("set")
def remote_set() -> None:
    """Configure le remote origin du workspace sans commit ni push."""
    try:
        workspace = find_workspace(Path.cwd())
        current = get_workspace_remote(workspace)
    except (WorkspaceNotFoundError, WorkspaceRemoteError) as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if current:
        console.print(f"[dim]Remote origin actuel : {current}[/dim]")

    url = typer.prompt("URL Git du workspace").strip()
    replace = False

    if current and current != url:
        replace = typer.confirm("Remplacer le remote origin actuel ?", default=False)
        if not replace:
            console.print("[yellow]Aucune modification effectuée.[/yellow]")
            raise typer.Exit()

    try:
        remote = set_workspace_remote(workspace, url, replace=replace)
    except WorkspaceRemoteAlreadyExistsError as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except WorkspaceRemoteError as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Remote origin configuré :[/green] {remote}")
    console.print("[dim]Aucun commit ni push n'a été effectué.[/dim]")


@repo_app.command("add")
def repo_add() -> None:
    """Clone un repository dans repos/ et l'enregistre dans project.yml."""
    name = typer.prompt("Nom du repository").strip()
    url = typer.prompt("URL Git").strip()

    try:
        workspace = find_workspace(Path.cwd())
        repository = add_repository(workspace, name, url)
    except (
        WorkspaceNotFoundError,
        InvalidRepositoryError,
        RepositoryAlreadyExistsError,
        RepositoryCloneError,
        ProjectConfigError,
    ) as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Repository ajouté :[/green] {repository['name']}")
    console.print(f"[dim]Local : {repository['path']}[/dim]")
    console.print("[dim]project.yml et README.md ont été mis à jour.[/dim]")


@ai_app.command("audit")
def ai_audit(
    repository_id: str | None = typer.Argument(
        None,
        help="Identifiant du repository. Si absent, ocp propose la liste du projet.",
    ),
) -> None:
    """Génère un audit technique Markdown d'un repository avec Codex CLI."""
    try:
        workspace = find_workspace(Path.cwd())
        repositories = get_repositories(workspace)
    except (WorkspaceNotFoundError, ProjectConfigError) as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if not repositories:
        console.print("[red]Erreur :[/red] aucun repository enregistré dans project.yml.")
        raise typer.Exit(code=1)

    selected = None
    if repository_id:
        wanted = repository_id.strip().lower()
        for repository in repositories:
            if str(repository.get("id", "")).lower() == wanted:
                selected = repository
                break
        if selected is None:
            console.print(f"[red]Erreur :[/red] repository inconnu : {repository_id}")
            raise typer.Exit(code=1)
    elif len(repositories) == 1:
        selected = repositories[0]
    else:
        console.print("[bold]Repository à auditer :[/bold]")
        for index, repository in enumerate(repositories, start=1):
            name = repository.get("name") or repository.get("id") or f"Repository {index}"
            repo_id = repository.get("id") or "—"
            console.print(f"  {index}. {name} [dim]({repo_id})[/dim]")

        choice = typer.prompt("Choix", type=int)
        if choice < 1 or choice > len(repositories):
            console.print("[red]Erreur :[/red] choix invalide.")
            raise typer.Exit(code=1)
        selected = repositories[choice - 1]

    output_path = workspace / "audits" / str(selected.get("id")) / "initial-audit.md"
    overwrite = False
    if output_path.exists():
        overwrite = typer.confirm(
            f"{output_path.relative_to(workspace)} existe déjà. Le remplacer ?",
            default=False,
        )
        if not overwrite:
            console.print("[yellow]Audit annulé.[/yellow]")
            raise typer.Exit()

    repo_name = selected.get("name") or selected.get("id")
    console.print(f"[bold]Repository :[/bold] {repo_name}")
    console.print("[dim]Codex sera exécuté en lecture seule, sans approbation interactive.[/dim]")

    try:
        with console.status("[bold]Audit technique en cours avec Codex…[/bold]"):
            report_path = run_codex_audit(workspace, selected, overwrite=overwrite)
    except (AiAuditError, AuditAlreadyExistsError) as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Audit généré :[/green] {report_path.relative_to(workspace)}")
    console.print("[dim]Le repository applicatif n'a pas été modifié.[/dim]")


@ai_app.command("project-audit")
def ai_project_audit() -> None:
    """Synthétise les audits des repositories en un audit technique global du projet."""
    try:
        workspace = find_workspace(Path.cwd())
        repositories = get_repositories(workspace)
    except (WorkspaceNotFoundError, ProjectConfigError) as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if not repositories:
        console.print("[red]Erreur :[/red] aucun repository enregistré dans project.yml.")
        raise typer.Exit(code=1)

    output_path = workspace / "audits" / "project-audit.md"
    overwrite = False
    if output_path.exists():
        overwrite = typer.confirm(
            f"{output_path.relative_to(workspace)} existe déjà. Le remplacer ?",
            default=False,
        )
        if not overwrite:
            console.print("[yellow]Audit projet annulé.[/yellow]")
            raise typer.Exit()

    console.print(f"[bold]Projet :[/bold] {workspace.name}")
    console.print(f"[bold]Repositories :[/bold] {len(repositories)}")
    console.print(
        "[dim]Codex synthétisera les audits existants en lecture seule. "
        "Il ne générera pas encore le backlog.[/dim]"
    )

    try:
        with console.status("[bold]Synthèse technique du projet en cours avec Codex…[/bold]"):
            report_path = run_codex_project_audit(
                workspace, repositories, overwrite=overwrite
            )
    except MissingRepositoryAuditsError as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except (AiAuditError, AuditAlreadyExistsError) as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        f"[green]Audit projet généré :[/green] {report_path.relative_to(workspace)}"
    )
    console.print(
        "[dim]Ce rapport sert de passerelle entre les audits techniques et le futur cadrage/backlog.[/dim]"
    )


@ai_app.command("cadrage")
def ai_cadrage() -> None:
    """Génère docs/cadrage.md à partir des PDF officiels et de l'audit projet."""
    try:
        workspace = find_workspace(Path.cwd())
    except WorkspaceNotFoundError as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    output_path = workspace / "docs" / "cadrage.md"
    overwrite = False
    if output_path.exists():
        current = output_path.read_text(encoding="utf-8").strip()
        if current not in {"", "# Note de cadrage"}:
            overwrite = typer.confirm(
                f"{output_path.relative_to(workspace)} contient déjà un cadrage. Le remplacer ?",
                default=False,
            )
            if not overwrite:
                console.print("[yellow]Cadrage annulé.[/yellow]")
                raise typer.Exit()

    source_dir = workspace / "docs" / "source"
    pdf_count = len(list(source_dir.glob("*.pdf"))) if source_dir.is_dir() else 0
    console.print(f"[bold]Projet :[/bold] {workspace.name}")
    console.print(f"[bold]Sources PDF :[/bold] {pdf_count}")
    console.print(
        "[dim]Les documents officiels ont priorité sur l'audit technique. "
        "Aucun backlog ni sprint ne sera généré à cette étape.[/dim]"
    )

    try:
        with console.status("[bold]Extraction des sources et génération du cadrage avec Codex…[/bold]"):
            cadrage_path = run_codex_cadrage(workspace, overwrite=overwrite)
    except (
        AiAuditError,
        AuditAlreadyExistsError,
        MissingProjectAuditError,
        MissingSourceDocumentsError,
        SourceDocumentError,
    ) as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Cadrage généré :[/green] {cadrage_path.relative_to(workspace)}")
    console.print(
        "[dim]Relis et valide ce document avant de générer le backlog Scrum.[/dim]"
    )


@ai_app.command("workflow")
def ai_workflow() -> None:
    """Génère le workflow de développement, le MVP et les conventions avant le backlog."""
    try:
        workspace = find_workspace(Path.cwd())
    except WorkspaceNotFoundError as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    output_path = workspace / "docs" / "development-workflow.md"
    overwrite = False
    if output_path.exists():
        current = output_path.read_text(encoding="utf-8").strip()
        if current not in {"", "# Workflow de développement"}:
            overwrite = typer.confirm(
                f"{output_path.relative_to(workspace)} contient déjà un workflow. Le remplacer ?",
                default=False,
            )
            if not overwrite:
                console.print("[yellow]Workflow annulé.[/yellow]")
                raise typer.Exit()

    recommendations_path = workspace / "mentoring" / "recommendations.md"
    if recommendations_path.is_file():
        recommendations = recommendations_path.read_text(encoding="utf-8").strip()
        recommendation_prefix = "- **Recommandation :**"
        has_recommendations = any(
            line.strip().startswith(recommendation_prefix)
            and line.strip() != recommendation_prefix
            for line in recommendations.splitlines()
        )
    else:
        has_recommendations = False

    console.print(f"[bold]Projet :[/bold] {workspace.name}")
    console.print(
        f"[bold]Recommandations mentor :[/bold] "
        f"{'présentes' if has_recommendations else '[yellow]aucune consignée[/yellow]'}"
    )
    if not has_recommendations:
        console.print(
            "[yellow]Le workflow peut être généré, mais les recommandations du mentor ne pourront pas être intégrées tant qu'elles ne sont pas ajoutées dans mentoring/recommendations.md.[/yellow]"
        )
    console.print(
        "[dim]Codex définira un MVP pédagogique et des règles de travail adaptées au projet. "
        "Aucun backlog ni sprint ne sera généré à cette étape.[/dim]"
    )

    try:
        with console.status("[bold]Génération du workflow de développement avec Codex…[/bold]"):
            workflow_path = run_codex_workflow(workspace, overwrite=overwrite)
    except (
        AiAuditError,
        AuditAlreadyExistsError,
        MissingProjectAuditError,
        MissingCadrageError,
    ) as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        f"[green]Workflow généré :[/green] {workflow_path.relative_to(workspace)}"
    )
    console.print(
        "[dim]Relis et valide le MVP, les conventions Git et les standards avant de générer le backlog.[/dim]"
    )


@ai_app.command("backlog")
def ai_backlog() -> None:
    """Génère le Product Backlog traçable à partir du cadrage et du workflow validés."""
    try:
        workspace = find_workspace(Path.cwd())
    except WorkspaceNotFoundError as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    output_path = workspace / "management" / "backlog.md"
    overwrite = False
    if output_path.exists():
        current = output_path.read_text(encoding="utf-8").strip()
        if current not in {"", "# Backlog", "# Product Backlog"}:
            overwrite = typer.confirm(
                f"{output_path.relative_to(workspace)} contient déjà un backlog. Le remplacer ?",
                default=False,
            )
            if not overwrite:
                console.print("[yellow]Génération du backlog annulée.[/yellow]")
                raise typer.Exit()

    console.print(f"[bold]Projet :[/bold] {workspace.name}")
    console.print(
        "[dim]Codex construira le backlog à partir du cadrage, du workflow, de l'audit global "
        "et des recommandations mentor. Le MVP sera conservé, avec des items US / TECH / SPIKE. "
        "Aucun sprint ni estimation ne sera créé.[/dim]"
    )

    try:
        with console.status("[bold]Génération du Product Backlog avec Codex…[/bold]"):
            backlog_path = run_codex_backlog(workspace, overwrite=overwrite)
    except (
        AiAuditError,
        AuditAlreadyExistsError,
        MissingProjectAuditError,
        MissingCadrageError,
        MissingWorkflowError,
    ) as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        f"[green]Backlog généré :[/green] {backlog_path.relative_to(workspace)}"
    )
    console.print(
        "[dim]Relis l'ordre, le périmètre MVP, les items bloqués et la traçabilité avant de préparer le Sprint 1.[/dim]"
    )


@ai_app.command("sprint")
def ai_sprint() -> None:
    """Crée le prochain sprint numéroté sans écraser les précédents."""
    try:
        workspace = find_workspace(Path.cwd())
    except WorkspaceNotFoundError as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[bold]Projet :[/bold] {workspace.name}")
    console.print(
        "[dim]Codex créera un nouveau fichier management/sprints/sprint-XXX.md. "
        "Les sprints précédents restent immuables et servent d'historique afin d'éviter de "
        "replanifier du travail déjà terminé.[/dim]"
    )

    try:
        with console.status("[bold]Préparation du prochain sprint avec Codex…[/bold]"):
            sprint_path = run_codex_sprint(workspace)
    except (
        AiAuditError,
        AuditAlreadyExistsError,
        MissingBacklogError,
        MissingWorkflowError,
        LegacySprintFileError,
    ) as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        f"[green]Sprint généré :[/green] {sprint_path.relative_to(workspace)}"
    )
    console.print(
        "[dim]Valide l'objectif et les items engagés avant de commencer le travail. "
        "Le backlog et les sprints précédents n'ont pas été modifiés.[/dim]"
    )


@ai_app.command("commit")
def ai_commit(
    target: str | None = typer.Argument(
        None,
        help="Dépôt à committer : workspace ou identifiant d'un repository. Par défaut : dépôt Git courant.",
    ),
) -> None:
    """Analyse les changements avec Codex et crée des Conventional Commits cohérents."""
    try:
        if target:
            workspace = find_workspace(Path.cwd())
            wanted = target.strip().lower()
            if wanted in {"workspace", "project"}:
                repository = workspace
                label = "workspace"
            else:
                repositories = get_repositories(workspace)
                selected = next(
                    (
                        repo
                        for repo in repositories
                        if str(repo.get("id") or "").lower() == wanted
                    ),
                    None,
                )
                if selected is None:
                    raise AiAuditError(f"Repository inconnu : {target}")
                repository = (workspace / str(selected.get("path"))).resolve()
                label = str(selected.get("name") or selected.get("id"))
        else:
            repository = find_git_repository(Path.cwd())
            label = repository.name
    except (WorkspaceNotFoundError, ProjectConfigError, AiAuditError) as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[bold]Dépôt :[/bold] {label}")
    console.print(f"[dim]{repository}[/dim]")
    console.print(
        "[dim]Codex analyse le diff en lecture seule. Aucun fichier ne sera découpé entre plusieurs commits.[/dim]"
    )

    try:
        with console.status("[bold]Analyse des changements avec Codex…[/bold]"):
            plan = plan_codex_commits(repository)
    except AiAuditError as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if plan.get("summary"):
        console.print(f"\n[bold]Résumé :[/bold] {plan['summary']}")

    warnings = plan.get("warnings", [])
    if warnings:
        console.print("\n[bold yellow]Points d'attention :[/bold yellow]")
        for warning in warnings:
            console.print(f"  [yellow]• {warning}[/yellow]")

    console.print("\n[bold]Commits proposés :[/bold]")
    for index, item in enumerate(plan["commits"], start=1):
        console.print(f"\n  [cyan]{index}. {item['message']}[/cyan]")
        if item.get("reason"):
            console.print(f"     [dim]{item['reason']}[/dim]")
        for path in item["paths"]:
            console.print(f"     {path}")

    if not typer.confirm(
        f"Créer ces {len(plan['commits'])} commit(s) ?",
        default=True,
    ):
        console.print("[yellow]Aucun commit créé.[/yellow]")
        raise typer.Exit()

    try:
        results = create_commit_plan(repository, plan)
    except AiAuditError as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print()
    for result in results:
        console.print(
            f"[green]Commit créé :[/green] {result['commit']} [dim]{result['message']}[/dim]"
        )
    console.print("[dim]Aucun push n'a été effectué.[/dim]")


if __name__ == "__main__":
    app()
