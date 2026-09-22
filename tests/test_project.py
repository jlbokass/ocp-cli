from pathlib import Path
import subprocess

import yaml

from ocp.project import (
    add_repository,
    create_github_repository,
    create_initial_commit,
    create_project,
    create_pull_request,
    find_workspace,
    get_project_status,
    get_workspace_remote,
    publish_workspace,
    resolve_pull_request_target,
    set_workspace_remote,
    slugify_project_name,
)


def test_slugify_project_name() -> None:
    assert slugify_project_name("P2 Mon Projet") == "p2-mon-projet"
    assert slugify_project_name("Testez et améliorez une application") == (
        "testez-et-ameliorez-une-application"
    )
    assert slugify_project_name("  Projet___DevOps  ") == "projet-devops"


def test_create_project(tmp_path: Path) -> None:
    project_dir = create_project("P2 Mon Projet", tmp_path)

    assert project_dir.name == "p2-mon-projet"
    assert project_dir.exists()
    assert (project_dir / ".git").exists()
    assert (project_dir / "project.yml").exists()
    assert (project_dir / "README.md").exists()
    assert (project_dir / "repos").is_dir()
    assert (project_dir / "docs/source").is_dir()
    assert (project_dir / "docs/source/.gitkeep").exists()
    assert (project_dir / "mentoring/current.md").exists()
    assert (project_dir / "journal/ai-journal.md").exists()
    assert "/repos/" in (project_dir / ".gitignore").read_text(encoding="utf-8")

    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert branch == "main"

    config = yaml.safe_load((project_dir / "project.yml").read_text(encoding="utf-8"))
    assert config["project"]["id"] == "p2-mon-projet"
    assert config["project"]["name"] == "P2 Mon Projet"


def test_find_workspace_from_child_directory(tmp_path: Path) -> None:
    project_dir = create_project("P2", tmp_path)
    child = project_dir / "docs" / "subdir"
    child.mkdir()

    assert find_workspace(child) == project_dir


def test_add_repository_clones_and_updates_project(tmp_path: Path) -> None:
    source = _create_git_repository(tmp_path / "source-repo")

    project_dir = create_project("P2", tmp_path / "workspace-parent")
    repo = add_repository(project_dir, "Backend API", str(source))

    assert repo["id"] == "backend-api"
    assert (project_dir / "repos/backend-api/.git").exists()

    config = yaml.safe_load((project_dir / "project.yml").read_text(encoding="utf-8"))
    assert config["repositories"] == [
        {
            "id": "backend-api",
            "name": "Backend API",
            "path": "repos/backend-api",
            "url": str(source),
        }
    ]

    readme = (project_dir / "README.md").read_text(encoding="utf-8")
    assert f"[Backend API]({source})" in readme
    assert "`repos/backend-api`" in readme


def test_get_project_status_reports_workspace_and_repositories(tmp_path: Path) -> None:
    source = _create_git_repository(tmp_path / "source-repo")
    project_dir = create_project("P2", tmp_path / "workspace-parent")
    add_repository(project_dir, "Backend", str(source))

    status = get_project_status(project_dir)

    assert status["project"]["name"] == "P2"
    assert status["workspace"]["branch"]
    assert status["workspace"]["changes"]["clean"] is False
    assert len(status["repositories"]) == 1

    backend = status["repositories"][0]
    assert backend["name"] == "Backend"
    assert backend["exists"] is True
    assert backend["is_git_repository"] is True
    assert backend["branch"]
    assert backend["changes"]["clean"] is True
    assert backend["remote"] == str(source)


def test_get_project_status_reports_dirty_repository(tmp_path: Path) -> None:
    source = _create_git_repository(tmp_path / "source-repo")
    project_dir = create_project("P2", tmp_path / "workspace-parent")
    add_repository(project_dir, "Backend", str(source))

    backend_path = project_dir / "repos/backend"
    (backend_path / "README.md").write_text("modification\n", encoding="utf-8")
    (backend_path / "new.txt").write_text("nouveau\n", encoding="utf-8")

    status = get_project_status(project_dir)
    changes = status["repositories"][0]["changes"]

    assert changes["clean"] is False
    assert changes["total"] == 2
    assert changes["tracked"] == 1
    assert changes["untracked"] == 1


def _create_git_repository(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "OCP Tests"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    (path / "README.md").write_text("initial\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    return path


def test_set_workspace_remote_adds_origin(tmp_path: Path) -> None:
    project_dir = create_project("P2", tmp_path)
    url = "git@github.com:john/p2-workspace.git"

    assert get_workspace_remote(project_dir) is None
    assert set_workspace_remote(project_dir, url) == url
    assert get_workspace_remote(project_dir) == url


def test_set_workspace_remote_can_replace_origin(tmp_path: Path) -> None:
    project_dir = create_project("P2", tmp_path)
    first = "git@github.com:john/p2-old.git"
    second = "git@gitlab.com:john/p2-new.git"

    set_workspace_remote(project_dir, first)
    set_workspace_remote(project_dir, second, replace=True)

    assert get_workspace_remote(project_dir) == second


def _configure_workspace_identity(path: Path) -> None:
    subprocess.run(
        ["git", "config", "user.email", "tests@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "OCP Tests"],
        cwd=path,
        check=True,
        capture_output=True,
    )


def _create_bare_remote(path: Path) -> Path:
    subprocess.run(
        ["git", "init", "--bare", str(path)],
        check=True,
        capture_output=True,
    )
    return path


def test_publish_workspace_creates_first_commit_and_pushes(tmp_path: Path) -> None:
    project_dir = create_project("P2", tmp_path / "workspace-parent")
    _configure_workspace_identity(project_dir)
    remote = _create_bare_remote(tmp_path / "remote.git")
    set_workspace_remote(project_dir, str(remote))

    result = publish_workspace(project_dir, "chore: initialize project workspace")

    assert result["committed"] is True
    assert result["commit"]
    assert result["remote"] == str(remote)

    remote_head = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", f"refs/heads/{result['branch']}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    local_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert remote_head == local_head


def test_publish_workspace_commits_subsequent_changes(tmp_path: Path) -> None:
    project_dir = create_project("P2", tmp_path / "workspace-parent")
    _configure_workspace_identity(project_dir)
    remote = _create_bare_remote(tmp_path / "remote.git")
    set_workspace_remote(project_dir, str(remote))
    first = publish_workspace(project_dir, "chore: initialize project workspace")

    notes = project_dir / "docs/notes.md"
    notes.write_text("Nouvelle note\n", encoding="utf-8")
    second = publish_workspace(project_dir, "docs: update project workspace")

    assert first["commit"] != second["commit"]
    assert second["committed"] is True
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert status == ""


def test_get_repositories(tmp_path: Path) -> None:
    from ocp.project import get_repositories

    source = _create_git_repository(tmp_path / "source-repo")
    project_dir = create_project("P2", tmp_path / "workspace-parent")
    add_repository(project_dir, "Backend", str(source))

    repositories = get_repositories(project_dir)
    assert len(repositories) == 1
    assert repositories[0]["id"] == "backend"


def test_create_initial_commit(tmp_path: Path) -> None:
    project_dir = create_project("P2", tmp_path)
    _configure_workspace_identity(project_dir)

    commit = create_initial_commit(project_dir)

    assert commit
    assert subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() == ""


def test_create_github_repository_uses_gh_and_configures_origin(
    tmp_path: Path, monkeypatch
) -> None:
    import os

    project_dir = create_project("P2 Mon Projet", tmp_path / "projects")
    _configure_workspace_identity(project_dir)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    args_file = tmp_path / "gh-args.txt"
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"auth\" ] && [ \"$2\" = \"status\" ]; then\n"
        "  exit 0\n"
        "fi\n"
        "printf '%s\n' \"$@\" > \"$FAKE_GH_ARGS\"\n"
        "if [ \"$1\" = \"repo\" ] && [ \"$2\" = \"create\" ]; then\n"
        "  git remote add origin \"git@github.com:test/$3.git\"\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)

    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_GH_ARGS", str(args_file))

    result = create_github_repository(project_dir, "p2-mon-projet")

    assert result["remote"] == "git@github.com:test/p2-mon-projet.git"
    assert get_workspace_remote(project_dir) == result["remote"]
    assert subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=project_dir,
        check=False,
        capture_output=True,
        text=True,
    ).returncode == 0

    args = args_file.read_text(encoding="utf-8").splitlines()
    assert args[:3] == ["repo", "create", "p2-mon-projet"]
    assert "--private" in args
    assert "--source=." in args
    assert "--remote=origin" in args
    assert "--push" in args


def test_build_publish_plan_groups_workspace_changes(tmp_path: Path) -> None:
    from ocp.project import build_publish_plan

    project_dir = create_project("P2", tmp_path / "workspace-parent")
    _configure_workspace_identity(project_dir)
    create_initial_commit(project_dir)

    (project_dir / "audits" / "project-audit.md").write_text("audit\n", encoding="utf-8")
    (project_dir / "docs" / "notes.md").write_text("notes modifiées\n", encoding="utf-8")
    (project_dir / "README.md").write_text("readme modifié\n", encoding="utf-8")

    plan = build_publish_plan(project_dir)

    assert [group["key"] for group in plan] == ["audits", "docs", "workspace"]
    assert plan[0]["message"] == "docs(audit): update technical audits"
    assert "audits/project-audit.md" in plan[0]["paths"]
    assert plan[1]["message"] == "docs: update project documentation"
    assert "docs/notes.md" in plan[1]["paths"]
    assert "README.md" in plan[2]["paths"]


def test_publish_workspace_plan_creates_multiple_commits_and_pushes(tmp_path: Path) -> None:
    from ocp.project import build_publish_plan, publish_workspace_plan

    project_dir = create_project("P2", tmp_path / "workspace-parent")
    _configure_workspace_identity(project_dir)
    remote = _create_bare_remote(tmp_path / "remote.git")
    set_workspace_remote(project_dir, str(remote))
    publish_workspace(project_dir, "chore: initialize project workspace")

    (project_dir / "audits" / "project-audit.md").write_text("audit\n", encoding="utf-8")
    (project_dir / "docs" / "notes.md").write_text("notes\n", encoding="utf-8")

    plan = build_publish_plan(project_dir)
    result = publish_workspace_plan(project_dir, plan)

    assert result["pushed"] is True
    assert len(result["commits"]) == 2
    assert [item["message"] for item in result["commits"]] == [
        "docs(audit): update technical audits",
        "docs: update project documentation",
    ]

    log = subprocess.run(
        ["git", "log", "-2", "--pretty=%s"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert log == [
        "docs: update project documentation",
        "docs(audit): update technical audits",
    ]


def test_publish_workspace_plan_clean_and_synced_does_not_push(tmp_path: Path) -> None:
    from ocp.project import build_publish_plan, get_unpushed_commit_count, publish_workspace_plan

    project_dir = create_project("P2", tmp_path / "workspace-parent")
    _configure_workspace_identity(project_dir)
    remote = _create_bare_remote(tmp_path / "remote.git")
    set_workspace_remote(project_dir, str(remote))
    publish_workspace(project_dir, "chore: initialize project workspace")

    assert build_publish_plan(project_dir) == []
    assert get_unpushed_commit_count(project_dir) == 0

    result = publish_workspace_plan(project_dir, [])
    assert result["pushed"] is False
    assert result["commits"] == []


def test_create_project_includes_workflow_and_mentor_recommendations(tmp_path: Path) -> None:
    project_dir = create_project("P2", tmp_path)

    workflow = project_dir / "docs" / "development-workflow.md"
    recommendations = project_dir / "mentoring" / "recommendations.md"

    assert workflow.is_file()
    assert workflow.read_text(encoding="utf-8").strip() == "# Workflow de développement"
    assert recommendations.is_file()
    assert "REC-MENTOR-001" in recommendations.read_text(encoding="utf-8")


def test_create_project_ignores_ide_files(tmp_path: Path) -> None:
    from ocp.project import create_project

    project = create_project("Demo", tmp_path)
    gitignore = (project / ".gitignore").read_text(encoding="utf-8")

    assert ".idea/" in gitignore
    assert ".vscode/" in gitignore
    assert ".DS_Store" in gitignore


def test_create_project_uses_numbered_sprints_directory_and_env_ignores(tmp_path: Path) -> None:
    project = create_project("Demo", tmp_path)
    assert (project / "management" / "sprints" / ".gitkeep").is_file()
    assert not (project / "management" / "sprint.md").exists()
    gitignore = (project / ".gitignore").read_text(encoding="utf-8")
    assert ".env.local" in gitignore
    assert "!.env.example" in gitignore


def test_push_workspace_only_pushes_existing_commits(tmp_path: Path) -> None:
    from ocp.project import push_workspace

    project_dir = create_project("P2", tmp_path / "workspace-parent")
    _configure_workspace_identity(project_dir)
    remote = _create_bare_remote(tmp_path / "remote.git")
    set_workspace_remote(project_dir, str(remote))
    create_initial_commit(project_dir)

    result = push_workspace(project_dir)
    assert result["pushed"] is True
    assert result["branch"] == "main"

    second = push_workspace(project_dir)
    assert second["pushed"] is False


def test_push_workspace_refuses_uncommitted_changes(tmp_path: Path) -> None:
    from ocp.project import WorkspacePublishError, push_workspace

    project_dir = create_project("P2", tmp_path / "workspace-parent")
    _configure_workspace_identity(project_dir)
    remote = _create_bare_remote(tmp_path / "remote.git")
    set_workspace_remote(project_dir, str(remote))
    create_initial_commit(project_dir)
    (project_dir / "docs" / "notes.md").write_text("dirty\n", encoding="utf-8")

    try:
        push_workspace(project_dir)
    except WorkspacePublishError as exc:
        assert "ocp ai commit workspace" in str(exc)
    else:
        raise AssertionError("push_workspace aurait dû refuser les changements non committés")


def test_resolve_pull_request_target_uses_nested_registered_repository(tmp_path: Path) -> None:
    source = _create_git_repository(tmp_path / "source-repo")
    project_dir = create_project("P2", tmp_path / "workspace-parent")
    add_repository(project_dir, "Backend", str(source))

    backend = project_dir / "repos/backend"
    nested = backend / "src"
    nested.mkdir()

    target = resolve_pull_request_target(project_dir, nested)

    assert target["id"] == "backend"
    assert target["path"] == backend.resolve()


def test_create_pull_request_targets_fork_origin_from_nested_repo(
    tmp_path: Path, monkeypatch
) -> None:
    import os
    import ocp.project as project_module

    source = _create_git_repository(tmp_path / "source-repo")
    project_dir = create_project("P2", tmp_path / "workspace-parent")
    add_repository(project_dir, "Backend", str(source))
    backend = project_dir / "repos/backend"
    _configure_workspace_identity(backend)

    subprocess.run(
        ["git", "switch", "-c", "feature/test-pr"],
        cwd=backend,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "set-url", "origin", "git@github.com:test/backend-fork.git"],
        cwd=backend,
        check=True,
        capture_output=True,
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    args_file = tmp_path / "gh-args.txt"
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_GH_ARGS\"\n"
        "if [ \"$1\" = \"auth\" ] && [ \"$2\" = \"status\" ]; then exit 0; fi\n"
        "if [ \"$1\" = \"pr\" ] && [ \"$2\" = \"view\" ]; then exit 1; fi\n"
        "if [ \"$1\" = \"pr\" ] && [ \"$2\" = \"create\" ]; then\n"
        "  echo 'https://github.com/test/backend-fork/pull/1'\n"
        "  exit 0\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)

    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_GH_ARGS", str(args_file))
    monkeypatch.setattr(
        project_module,
        "_push_git_target",
        lambda target: {"branch": "feature/test-pr", "pushed": True},
    )

    result = create_pull_request(project_dir, start=backend, open_web=False)

    assert result["target"] == "backend"
    assert result["repository"] == "test/backend-fork"
    assert result["created"] is True

    calls = args_file.read_text(encoding="utf-8").splitlines()
    create_call = next(line for line in calls if line.startswith("pr create "))
    assert "-R test/backend-fork" in create_call
    assert "--base main" in create_call
    assert "--head feature/test-pr" in create_call
