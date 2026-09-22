from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from ocp.ai import build_audit_prompt, run_codex_audit
from ocp.project import add_repository, create_project


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


def test_build_audit_prompt_is_technical_and_read_only() -> None:
    prompt = build_audit_prompt("Backend")
    assert "audit technique" in prompt.lower()
    assert "lecture seule" in prompt.lower()
    assert "Docker" in prompt
    assert "CI/CD" in prompt
    assert "Preuve" in prompt
    assert "Non vérifié" in prompt


def test_run_codex_audit_writes_report_outside_repository(tmp_path: Path, monkeypatch) -> None:
    source = _create_git_repository(tmp_path / "source-repo")
    workspace = create_project("P2", tmp_path / "workspace-parent")
    repository = add_repository(workspace, "Backend", str(source))

    monkeypatch.setattr("ocp.ai.shutil.which", lambda name: "/usr/local/bin/codex")

    observed = {}

    def fake_run(command, cwd, check, capture_output, text):
        observed["command"] = command
        observed["cwd"] = cwd
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="# Audit technique — Backend\n\nRapport de test.\n",
            stderr="",
        )

    monkeypatch.setattr("ocp.ai.subprocess.run", fake_run)

    output = run_codex_audit(workspace, repository)

    assert output == workspace / "audits/backend/initial-audit.md"
    assert output.exists()
    assert "Rapport de test" in output.read_text(encoding="utf-8")
    assert observed["cwd"] == workspace / "repos/backend"
    command = observed["command"]
    assert "--sandbox" in command
    assert "read-only" in command
    assert "--ask-for-approval" in command
    assert "never" in command
    assert "exec" in command
    assert "--ephemeral" in command
    assert command.index("--sandbox") < command.index("exec")
    assert command.index("--ask-for-approval") < command.index("exec")
    assert command.index("--ephemeral") > command.index("exec")
    assert not (workspace / "repos/backend/initial-audit.md").exists()


def test_build_project_audit_prompt_is_transversal_and_not_backlog() -> None:
    from ocp.ai import build_project_audit_prompt

    prompt = build_project_audit_prompt(
        [
            {"id": "backend", "name": "Backend"},
            {"id": "frontend", "name": "Frontend"},
        ]
    )
    assert "synthèse technique globale" in prompt.lower()
    assert "audits/backend/initial-audit.md" in prompt
    assert "audits/frontend/initial-audit.md" in prompt
    assert "Interactions entre repositories" in prompt
    assert "Ne génère ni user stories" in prompt
    assert "TRANSVERSALE" in prompt


def test_run_codex_project_audit_requires_all_repository_audits(tmp_path: Path, monkeypatch) -> None:
    from ocp.ai import MissingRepositoryAuditsError, run_codex_project_audit

    workspace = create_project("P2", tmp_path / "workspace-parent")
    repositories = [
        {"id": "backend", "name": "Backend", "path": "repos/backend"},
        {"id": "frontend", "name": "Frontend", "path": "repos/frontend"},
    ]
    (workspace / "audits/backend").mkdir(parents=True)
    (workspace / "audits/backend/initial-audit.md").write_text(
        "# Audit backend\n", encoding="utf-8"
    )
    monkeypatch.setattr("ocp.ai.shutil.which", lambda name: "/usr/local/bin/codex")

    try:
        run_codex_project_audit(workspace, repositories)
    except MissingRepositoryAuditsError as exc:
        assert exc.missing == ["frontend"]
    else:
        raise AssertionError("MissingRepositoryAuditsError attendu")


def test_run_codex_project_audit_writes_global_report(tmp_path: Path, monkeypatch) -> None:
    from ocp.ai import run_codex_project_audit

    workspace = create_project("P2", tmp_path / "workspace-parent")
    repositories = [
        {"id": "backend", "name": "Backend", "path": "repos/backend"},
        {"id": "frontend", "name": "Frontend", "path": "repos/frontend"},
    ]
    for repository in repositories:
        audit_dir = workspace / "audits" / repository["id"]
        audit_dir.mkdir(parents=True)
        (audit_dir / "initial-audit.md").write_text(
            f"# Audit {repository['name']}\n\nConstat test.\n", encoding="utf-8"
        )

    monkeypatch.setattr("ocp.ai.shutil.which", lambda name: "/usr/local/bin/codex")
    observed = {}

    def fake_run(command, cwd, check, capture_output, text):
        observed["command"] = command
        observed["cwd"] = cwd
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="# Audit technique global du projet\n\nSynthèse de test.\n",
            stderr="",
        )

    monkeypatch.setattr("ocp.ai.subprocess.run", fake_run)

    output = run_codex_project_audit(workspace, repositories)

    assert output == workspace / "audits/project-audit.md"
    assert output.exists()
    assert "Synthèse de test" in output.read_text(encoding="utf-8")
    assert observed["cwd"] == workspace
    command = observed["command"]
    assert command.index("--sandbox") < command.index("exec")
    assert command.index("--ask-for-approval") < command.index("exec")
    assert command.index("--ephemeral") > command.index("exec")


def test_extract_pdf_sources_keeps_filename_and_pages(tmp_path: Path, monkeypatch) -> None:
    from ocp import ai

    source_dir = tmp_path / "docs" / "source"
    source_dir.mkdir(parents=True)
    (source_dir / "brief.pdf").write_bytes(b"%PDF-fake")

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, path: str) -> None:
            assert path.endswith("brief.pdf")
            self.pages = [FakePage("Page one"), FakePage("Page two")]

    monkeypatch.setattr(ai, "PdfReader", FakeReader)

    documents = ai.extract_pdf_sources(source_dir)

    assert len(documents) == 1
    assert documents[0]["name"] == "brief.pdf"
    assert "SOURCE: brief.pdf | PAGE: 1" in documents[0]["content"]
    assert "Page one" in documents[0]["content"]
    assert "SOURCE: brief.pdf | PAGE: 2" in documents[0]["content"]


def test_extract_pdf_sources_requires_pdf(tmp_path: Path) -> None:
    from ocp.ai import MissingSourceDocumentsError, extract_pdf_sources

    source_dir = tmp_path / "docs" / "source"
    source_dir.mkdir(parents=True)

    with pytest.raises(MissingSourceDocumentsError):
        extract_pdf_sources(source_dir)


def test_build_cadrage_prompt_prioritizes_official_sources() -> None:
    from ocp.ai import build_cadrage_prompt

    prompt = build_cadrage_prompt(
        "project:\n  name: Demo\n",
        "# Audit\nÉtat technique\n",
        [{"name": "brief.pdf", "content": "--- SOURCE: brief.pdf | PAGE: 1 ---\nExigence A"}],
    )

    assert "Les documents officiels de docs/source/ font autorité" in prompt
    assert "ne crée aucune exigence fonctionnelle" in prompt
    assert "brief.pdf" in prompt
    assert "Exigence A" in prompt
    assert "Ne génère ni user stories" in prompt


def test_run_codex_cadrage_writes_document(tmp_path: Path, monkeypatch) -> None:
    from ocp import ai

    workspace = tmp_path / "workspace"
    (workspace / "audits").mkdir(parents=True)
    (workspace / "docs" / "source").mkdir(parents=True)
    (workspace / "docs" / "cadrage.md").write_text("# Note de cadrage\n", encoding="utf-8")
    (workspace / "project.yml").write_text("project:\n  name: Demo\n", encoding="utf-8")
    (workspace / "audits" / "project-audit.md").write_text("# Audit projet\n", encoding="utf-8")
    (workspace / "docs" / "source" / "brief.pdf").write_bytes(b"%PDF-fake")

    fake_codex = tmp_path / "codex"
    fake_codex.write_text("#!/bin/sh\nprintf '# Note de cadrage\\n\\nContenu généré\\n'\n", encoding="utf-8")
    fake_codex.chmod(0o755)

    monkeypatch.setattr(ai.shutil, "which", lambda name: str(fake_codex) if name == "codex" else None)
    monkeypatch.setattr(
        ai,
        "extract_pdf_sources",
        lambda source_dir: [{"name": "brief.pdf", "content": "--- SOURCE: brief.pdf | PAGE: 1 ---\nExigence A"}],
    )

    output = ai.run_codex_cadrage(workspace)

    assert output == workspace / "docs" / "cadrage.md"
    assert "Contenu généré" in output.read_text(encoding="utf-8")


def test_run_codex_cadrage_requires_project_audit(tmp_path: Path, monkeypatch) -> None:
    from ocp import ai

    workspace = tmp_path / "workspace"
    (workspace / "docs" / "source").mkdir(parents=True)
    (workspace / "project.yml").write_text("project:\n  name: Demo\n", encoding="utf-8")

    monkeypatch.setattr(ai.shutil, "which", lambda name: "/usr/bin/codex")

    with pytest.raises(ai.MissingProjectAuditError):
        ai.run_codex_cadrage(workspace)


def test_extract_pdf_sources_reports_missing_pypdf_cleanly(tmp_path: Path, monkeypatch) -> None:
    from ocp import ai

    source_dir = tmp_path / "docs" / "source"
    source_dir.mkdir(parents=True)
    (source_dir / "brief.pdf").write_bytes(b"%PDF-fake")

    monkeypatch.setattr(ai, "PdfReader", None)

    with pytest.raises(ai.SourceDocumentError) as exc:
        ai.extract_pdf_sources(source_dir)

    assert "pipx reinstall ocp-cli" in str(exc.value)


def test_build_workflow_prompt_includes_mvp_mentor_and_working_agreements() -> None:
    from ocp.ai import build_workflow_prompt

    prompt = build_workflow_prompt(
        "project:\n  name: Demo\n",
        "# Note de cadrage\nEX-05 authentification\n",
        "# Audit technique global du projet\nJava + Angular\n",
        "# Recommandations mentor\n\n### REC-MENTOR-001 — Hot reload\n- **Recommandation :** Ajouter des volumes Docker.\n",
    )

    assert "MVP pédagogique" in prompt
    assert "REC-MENTOR-001" in prompt
    assert "Conventional Commits" in prompt
    assert "Convention de nommage des branches" in prompt
    assert "Standards de code par repository" in prompt
    assert "Definition of Ready" in prompt
    assert "Definition of Done" in prompt
    assert "Ne génère pas encore le backlog" in prompt


def test_run_codex_workflow_writes_document(tmp_path: Path, monkeypatch) -> None:
    from ocp import ai

    workspace = tmp_path / "workspace"
    (workspace / "audits").mkdir(parents=True)
    (workspace / "docs").mkdir(parents=True)
    (workspace / "mentoring").mkdir(parents=True)
    (workspace / "project.yml").write_text("project:\n  name: Demo\n", encoding="utf-8")
    (workspace / "docs" / "cadrage.md").write_text(
        "# Note de cadrage\n\nCadrage validé\n", encoding="utf-8"
    )
    (workspace / "audits" / "project-audit.md").write_text(
        "# Audit projet\n\nAudit valide\n", encoding="utf-8"
    )
    (workspace / "mentoring" / "recommendations.md").write_text(
        "# Recommandations mentor\n\n### REC-MENTOR-001 — Hot reload\n"
        "- **Recommandation :** Ajouter des volumes Docker.\n",
        encoding="utf-8",
    )
    (workspace / "docs" / "development-workflow.md").write_text(
        "# Workflow de développement\n", encoding="utf-8"
    )

    fake_codex = tmp_path / "codex"
    fake_codex.write_text(
        "#!/bin/sh\nprintf '# Workflow de développement\\n\\nMVP et conventions générés\\n'\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    monkeypatch.setattr(ai.shutil, "which", lambda name: str(fake_codex) if name == "codex" else None)

    output = ai.run_codex_workflow(workspace)

    assert output == workspace / "docs" / "development-workflow.md"
    content = output.read_text(encoding="utf-8")
    assert "MVP et conventions générés" in content


def test_run_codex_workflow_requires_nonempty_cadrage(tmp_path: Path, monkeypatch) -> None:
    from ocp import ai

    workspace = tmp_path / "workspace"
    (workspace / "audits").mkdir(parents=True)
    (workspace / "docs").mkdir(parents=True)
    (workspace / "project.yml").write_text("project:\n  name: Demo\n", encoding="utf-8")
    (workspace / "docs" / "cadrage.md").write_text("# Note de cadrage\n", encoding="utf-8")
    (workspace / "audits" / "project-audit.md").write_text("# Audit projet\n", encoding="utf-8")

    monkeypatch.setattr(ai.shutil, "which", lambda name: "/usr/bin/codex")

    with pytest.raises(ai.MissingCadrageError):
        ai.run_codex_workflow(workspace)



def test_build_backlog_prompt_preserves_mvp_and_types() -> None:
    from ocp.ai import build_backlog_prompt

    prompt = build_backlog_prompt(
        "project:\n  name: Demo\n",
        "# Note de cadrage\nEX-05 login JWT\nEX-09 CRUD étudiants\n",
        "# Workflow de développement\n## MVP pédagogique\nLogin Angular + JWT\n",
        "# Audit technique global du projet\n### [PROJ-04] Auth incomplète\n",
        "# Recommandations mentor\n### REC-MENTOR-001 — Hot reload\n- **Statut :** proposée\n",
    )

    assert "Ne change pas le MVP défini dans le workflow" in prompt
    assert "US :" in prompt
    assert "TECH :" in prompt
    assert "SPIKE :" in prompt
    assert "REC-MENTOR-001" in prompt
    assert "PROJ-*" in prompt
    assert "Aucun sprint ni estimation" in prompt or "aucun sprint" in prompt.lower()
    assert "Couverture des exigences" in prompt


def test_run_codex_backlog_writes_document(tmp_path: Path, monkeypatch) -> None:
    from ocp import ai

    workspace = tmp_path / "workspace"
    (workspace / "audits").mkdir(parents=True)
    (workspace / "docs").mkdir(parents=True)
    (workspace / "management").mkdir(parents=True)
    (workspace / "mentoring").mkdir(parents=True)
    (workspace / "project.yml").write_text("project:\n  name: Demo\n", encoding="utf-8")
    (workspace / "docs" / "cadrage.md").write_text(
        "# Note de cadrage\n\nEX-05 login JWT\n", encoding="utf-8"
    )
    (workspace / "docs" / "development-workflow.md").write_text(
        "# Workflow de développement\n\n## MVP pédagogique\nLogin + JWT\n",
        encoding="utf-8",
    )
    (workspace / "audits" / "project-audit.md").write_text(
        "# Audit technique global du projet\n\nPROJ-04 auth incomplète\n",
        encoding="utf-8",
    )
    (workspace / "mentoring" / "recommendations.md").write_text(
        "# Recommandations mentor\n\n### REC-MENTOR-001 — Hot reload\n"
        "- **Recommandation :** Ajouter des volumes Docker.\n",
        encoding="utf-8",
    )
    (workspace / "management" / "backlog.md").write_text("# Backlog\n", encoding="utf-8")

    fake_codex = tmp_path / "codex"
    fake_codex.write_text(
        "#!/bin/sh\nprintf '# Product Backlog\\n\\n## 2. MVP pédagogique\\n\\nUS-001\\n'\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    monkeypatch.setattr(ai.shutil, "which", lambda name: str(fake_codex) if name == "codex" else None)

    output = ai.run_codex_backlog(workspace)

    assert output == workspace / "management" / "backlog.md"
    content = output.read_text(encoding="utf-8")
    assert "# Product Backlog" in content
    assert "US-001" in content


def test_run_codex_backlog_requires_workflow(tmp_path: Path, monkeypatch) -> None:
    from ocp import ai

    workspace = tmp_path / "workspace"
    (workspace / "audits").mkdir(parents=True)
    (workspace / "docs").mkdir(parents=True)
    (workspace / "management").mkdir(parents=True)
    (workspace / "project.yml").write_text("project:\n  name: Demo\n", encoding="utf-8")
    (workspace / "docs" / "cadrage.md").write_text(
        "# Note de cadrage\n\nCadrage validé\n", encoding="utf-8"
    )
    (workspace / "audits" / "project-audit.md").write_text(
        "# Audit projet\n\nAudit valide\n", encoding="utf-8"
    )
    monkeypatch.setattr(ai.shutil, "which", lambda name: "/usr/bin/codex")

    with pytest.raises(ai.MissingWorkflowError):
        ai.run_codex_backlog(workspace)


def test_run_codex_backlog_refuses_nonempty_backlog_without_overwrite(tmp_path: Path, monkeypatch) -> None:
    from ocp import ai

    workspace = tmp_path / "workspace"
    (workspace / "audits").mkdir(parents=True)
    (workspace / "docs").mkdir(parents=True)
    (workspace / "management").mkdir(parents=True)
    (workspace / "project.yml").write_text("project:\n  name: Demo\n", encoding="utf-8")
    (workspace / "docs" / "cadrage.md").write_text(
        "# Note de cadrage\n\nValidé\n", encoding="utf-8"
    )
    (workspace / "docs" / "development-workflow.md").write_text(
        "# Workflow de développement\n\nValidé\n", encoding="utf-8"
    )
    (workspace / "audits" / "project-audit.md").write_text(
        "# Audit projet\n\nValidé\n", encoding="utf-8"
    )
    (workspace / "management" / "backlog.md").write_text(
        "# Product Backlog\n\nContenu existant\n", encoding="utf-8"
    )
    monkeypatch.setattr(ai.shutil, "which", lambda name: "/usr/bin/codex")

    with pytest.raises(ai.AuditAlreadyExistsError):
        ai.run_codex_backlog(workspace)


def test_build_sprint_prompt_prefers_small_coherent_scope() -> None:
    from ocp.ai import build_sprint_prompt

    prompt = build_sprint_prompt(
        "project:\n  name: Demo\n",
        "# Product Backlog\nSPIKE-001 Ready\nTECH-001 Blocked\n",
        "# Workflow de développement\n## Definition of Done\nTests ciblés\n",
        "",
        "# Point mentor\n",
        "# Recommandations mentor\n",
        sprint_number=2,
        sprint_history="# Sprint 001\n\nSPIKE-001 — Done\n",
    )

    assert "plus petit ensemble cohérent" in prompt
    assert "raisonne en chaîne de déblocage" in prompt
    assert "uniquement de SPIKEs/documents" in prompt
    assert "Docker-first" in prompt
    assert "2 à 4 items" in prompt
    assert "Ajustements du backlog à valider" in prompt
    assert "Aucun story point" in prompt
    assert "résultat TECHNIQUE concret" in prompt
    assert "Sprint 002" in prompt
    assert "sprint-002.md" in prompt
    assert "Ne reprogramme pas un item clairement terminé" in prompt


def test_run_codex_sprint_creates_numbered_file_and_keeps_history(tmp_path: Path, monkeypatch) -> None:
    from ocp import ai

    workspace = tmp_path / "workspace"
    (workspace / "docs").mkdir(parents=True)
    (workspace / "management" / "sprints").mkdir(parents=True)
    (workspace / "mentoring").mkdir(parents=True)
    (workspace / "project.yml").write_text("project:\n  name: Demo\n", encoding="utf-8")
    (workspace / "docs" / "development-workflow.md").write_text(
        "# Workflow de développement\n\nWorkflow validé\n", encoding="utf-8"
    )
    (workspace / "management" / "backlog.md").write_text(
        "# Product Backlog\n\nSPIKE-001 Ready\nTECH-001 Ready\n", encoding="utf-8"
    )
    (workspace / "management" / "sprints" / "sprint-001.md").write_text(
        "# Sprint 001\n\nSPIKE-001 — Done\n", encoding="utf-8"
    )
    (workspace / "management" / "retrospective.md").write_text("# Rétrospective\n", encoding="utf-8")
    (workspace / "mentoring" / "current.md").write_text("# Point mentor\n", encoding="utf-8")
    (workspace / "mentoring" / "recommendations.md").write_text(
        "# Recommandations mentor\n", encoding="utf-8"
    )

    fake_codex = tmp_path / "codex"
    fake_codex.write_text(
        "#!/bin/sh\nprintf '# Sprint 002\\n\\n## 1. Objectif du sprint\\n\\nValider authentification\\n'\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    monkeypatch.setattr(ai.shutil, "which", lambda name: str(fake_codex) if name == "codex" else None)

    output = ai.run_codex_sprint(workspace)

    assert output == workspace / "management" / "sprints" / "sprint-002.md"
    content = output.read_text(encoding="utf-8")
    assert "# Sprint 002" in content
    assert "Valider authentification" in content
    assert (workspace / "management" / "sprints" / "sprint-001.md").read_text(encoding="utf-8").startswith("# Sprint 001")


def test_run_codex_sprint_refuses_legacy_sprint_file(tmp_path: Path, monkeypatch) -> None:
    from ocp import ai

    workspace = tmp_path / "workspace"
    (workspace / "docs").mkdir(parents=True)
    (workspace / "management").mkdir(parents=True)
    (workspace / "project.yml").write_text("project:\n  name: Demo\n", encoding="utf-8")
    (workspace / "docs" / "development-workflow.md").write_text(
        "# Workflow de développement\n\nWorkflow validé\n", encoding="utf-8"
    )
    (workspace / "management" / "backlog.md").write_text(
        "# Product Backlog\n\nSPIKE-001 Ready\n", encoding="utf-8"
    )
    (workspace / "management" / "sprint.md").write_text(
        "# Sprint actuel\n\nAncien sprint réel\n", encoding="utf-8"
    )
    monkeypatch.setattr(ai.shutil, "which", lambda name: "/usr/bin/codex")

    with pytest.raises(ai.LegacySprintFileError):
        ai.run_codex_sprint(workspace)


def test_run_codex_sprint_requires_backlog(tmp_path: Path, monkeypatch) -> None:
    from ocp import ai

    workspace = tmp_path / "workspace"
    (workspace / "docs").mkdir(parents=True)
    (workspace / "project.yml").write_text("project:\n  name: Demo\n", encoding="utf-8")
    (workspace / "docs" / "development-workflow.md").write_text(
        "# Workflow de développement\n\nWorkflow validé\n", encoding="utf-8"
    )

    monkeypatch.setattr(ai.shutil, "which", lambda name: "/usr/bin/codex")

    with pytest.raises(ai.MissingBacklogError):
        ai.run_codex_sprint(workspace)


def test_build_commit_prompt_requires_file_level_atomic_plan() -> None:
    from ocp.ai import build_commit_prompt

    prompt = build_commit_prompt(["compose.yaml", "docs/spike.md"])
    assert "EXACTEMENT UNE FOIS" in prompt
    assert "ne peut PAS être découpé" in prompt
    assert "Conventional Commits" in prompt
    assert "UNIQUEMENT un objet JSON" in prompt


def test_plan_codex_commits_validates_all_changed_files(tmp_path: Path, monkeypatch) -> None:
    from ocp import ai

    repo = _create_git_repository(tmp_path / "repo")
    (repo / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (repo / "docs.md").write_text("notes\n", encoding="utf-8")

    monkeypatch.setattr(ai.shutil, "which", lambda name: "/usr/local/bin/codex")
    monkeypatch.setattr(
        ai,
        "_run_codex",
        lambda command, cwd: '{"summary":"Docker work","warnings":[],"commits":['
        '{"message":"chore(docker): add compose prototype","paths":["compose.yaml"],"reason":"docker"},'
        '{"message":"docs(spike): document findings","paths":["docs.md"],"reason":"docs"}'
        ']}',
    )

    plan = ai.plan_codex_commits(repo)

    assert len(plan["commits"]) == 2
    assert plan["commits"][0]["paths"] == ["compose.yaml"]
    assert plan["repository"] == str(repo.resolve())


def test_plan_codex_commits_rejects_staged_changes(tmp_path: Path, monkeypatch) -> None:
    from ocp import ai

    repo = _create_git_repository(tmp_path / "repo")
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    monkeypatch.setattr(ai.shutil, "which", lambda name: "/usr/local/bin/codex")

    with pytest.raises(ai.AiAuditError, match="stagés"):
        ai.plan_codex_commits(repo)


def test_create_commit_plan_creates_multiple_commits_without_push(tmp_path: Path) -> None:
    from ocp.ai import create_commit_plan

    repo = _create_git_repository(tmp_path / "repo")
    (repo / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (repo / "docs.md").write_text("notes\n", encoding="utf-8")
    plan = {
        "commits": [
            {
                "message": "chore(docker): add compose prototype",
                "paths": ["compose.yaml"],
            },
            {
                "message": "docs(spike): document findings",
                "paths": ["docs.md"],
            },
        ]
    }

    results = create_commit_plan(repo, plan)

    assert len(results) == 2
    assert subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() == ""
    messages = subprocess.run(
        ["git", "log", "-2", "--pretty=%s"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert messages == [
        "docs(spike): document findings",
        "chore(docker): add compose prototype",
    ]
