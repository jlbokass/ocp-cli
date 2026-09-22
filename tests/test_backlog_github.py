from pathlib import Path

from ocp.backlog_github import (
    build_issue_body,
    labels_for_item,
    parse_backlog,
    sprint_labels,
)


def test_parse_backlog_extracts_detailed_items(tmp_path: Path) -> None:
    backlog = tmp_path / "backlog.md"
    backlog.write_text(
        """# Product Backlog

### EPIC-01 — Préparer

#### TECH-001 — Préparer l'environnement

- **Type :** TECH
- **Priorité :** P0
- **MVP :** Oui
- **Repository(s) :** workspace, backend
- **Statut initial :** Ready
- **Sources :** EX-01
- **Dépend de :** SPIKE-001

**Critères d’acceptation :**

- [ ] Docker fonctionne.

#### US-001 — Se connecter

- **Type :** US
- **Priorité :** P1
- **MVP :** Oui
- **Repository(s) :** backend, frontend
- **Statut initial :** Blocked
- **Sources :** EX-05
- **Dépend de :** TECH-001
""",
        encoding="utf-8",
    )

    items = parse_backlog(backlog)

    assert [item["id"] for item in items] == ["TECH-001", "US-001"]
    assert items[0]["priority"] == "P0"
    assert items[0]["epic_id"] == "EPIC-01"
    assert "Docker fonctionne" in items[0]["section"]


def test_labels_include_type_priority_mvp_area_and_latest_sprint(tmp_path: Path) -> None:
    item = {
        "type": "TECH",
        "priority": "P0",
        "mvp": "Oui",
        "repositories": "workspace, backend",
    }
    labels = labels_for_item(item, "sprint:002")
    assert labels == [
        "type:tech",
        "priority:p0",
        "mvp",
        "area:workspace",
        "area:backend",
        "sprint:002",
    ]


def test_sprint_labels_keep_only_engaged_items_and_latest_sprint(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sprints = workspace / "management" / "sprints"
    sprints.mkdir(parents=True)

    (sprints / "sprint-001.md").write_text(
        """# Sprint 001

## 3. Items engagés

| Ordre | ID | Titre | Dépend de |
|---|---|---|---|
| 1 | SPIKE-001 | Observer | Aucune |
| 2 | SPIKE-002 | Docker | SPIKE-001 |

## 5. Hors sprint

| Item(s) | Raison |
|---|---|
| TECH-001, US-001 | Plus tard |
""",
        encoding="utf-8",
    )
    (sprints / "sprint-002.md").write_text(
        """# Sprint 002

## 3. Items engagés

| Ordre | ID | Titre | Dépend de |
|---|---|---|---|
| 1 | TECH-001 | Configurer | SPIKE-002 |
| 2 | TECH-002 | Docker dev | TECH-001 |

## 5. Hors sprint

SPIKE-003, US-001 et TECH-003 sont hors sprint.
""",
        encoding="utf-8",
    )

    mapping = sprint_labels(workspace)

    assert mapping == {
        "SPIKE-001": "sprint:001",
        "SPIKE-002": "sprint:001",
        "TECH-001": "sprint:002",
        "TECH-002": "sprint:002",
    }


def test_issue_body_preserves_metadata_and_specification() -> None:
    item = {
        "id": "TECH-001",
        "title": "Configurer",
        "type": "TECH",
        "priority": "P0",
        "mvp": "Oui",
        "repositories": "backend",
        "initial_status": "Ready",
        "sources": "EX-01",
        "depends_on": "SPIKE-001",
        "unblocks": "TECH-002",
        "epic_id": "EPIC-01",
        "epic_title": "Préparer",
        "section": "**Critères d’acceptation :**\n\n- [ ] OK",
    }
    body = build_issue_body(item)
    assert "EPIC-01 — Préparer" in body
    assert "SPIKE-001" in body
    assert "Critères d’acceptation" in body
