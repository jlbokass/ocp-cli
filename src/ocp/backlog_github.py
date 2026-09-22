from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path


class BacklogImportError(Exception):
    pass


_ITEM_HEADING = re.compile(
    r"^####\s+((?:SPIKE|TECH|US)-\d+)\s+[—-]\s+(.+?)\s*$",
    re.MULTILINE,
)
_EPIC_HEADING = re.compile(r"^###\s+(EPIC-\d+)\s+[—-]\s+(.+?)\s*$", re.MULTILINE)
_META_LINE = re.compile(r"^- \*\*(.+?)\s*:\*\*\s*(.*?)\s*$", re.MULTILINE)
_ITEM_ID = re.compile(r"\b(?:SPIKE|TECH|US)-\d+\b")


def parse_backlog(backlog_path: Path) -> list[dict]:
    """Parse les items détaillés d'un backlog Markdown OCP."""
    if not backlog_path.is_file():
        raise BacklogImportError(f"Backlog introuvable : {backlog_path}")

    text = backlog_path.read_text(encoding="utf-8")
    matches = list(_ITEM_HEADING.finditer(text))
    if not matches:
        raise BacklogImportError(
            "Aucun item détaillé SPIKE/TECH/US trouvé dans management/backlog.md."
        )

    epics = list(_EPIC_HEADING.finditer(text))
    items: list[dict] = []
    for index, match in enumerate(matches):
        item_id = match.group(1).strip()
        title = match.group(2).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section = text[start:end].strip()

        epic_id = None
        epic_title = None
        for epic in epics:
            if epic.start() > match.start():
                break
            epic_id = epic.group(1).strip()
            epic_title = epic.group(2).strip()

        metadata = {
            key.strip().lower(): value.strip()
            for key, value in _META_LINE.findall(section)
        }

        items.append(
            {
                "id": item_id,
                "title": title,
                "type": metadata.get("type", item_id.split("-", 1)[0]),
                "priority": metadata.get("priorité", ""),
                "mvp": metadata.get("mvp", ""),
                "repositories": metadata.get("repository(s)", ""),
                "initial_status": metadata.get("statut initial", ""),
                "sources": metadata.get("sources", ""),
                "depends_on": metadata.get("dépend de", ""),
                "unblocks": metadata.get("débloque", ""),
                "epic_id": epic_id,
                "epic_title": epic_title,
                "section": section,
            }
        )

    return items


def _engaged_item_ids(sprint_content: str) -> set[str]:
    """Extrait uniquement les items réellement engagés dans un sprint.

    Les dépendances et les sections « Hors sprint » ne doivent jamais produire
    de label sprint. Les sprints OCP utilisent un tableau sous « Items engagés » ;
    on lit donc uniquement la colonne ID de ce tableau.
    """
    section = re.search(
        r"^##\s+\d+\.\s+Items engagés\s*$"
        r"(.*?)(?=^##\s+\d+\.|\Z)",
        sprint_content,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not section:
        return set()

    return {
        match.group(1)
        for match in re.finditer(
            r"^\|\s*\d+\s*\|\s*((?:SPIKE|TECH|US)-\d+)\s*\|",
            section.group(1),
            flags=re.MULTILINE,
        )
    }


def sprint_labels(workspace: Path) -> dict[str, str]:
    """Retourne le dernier sprint où chaque item a réellement été engagé."""
    sprints_dir = workspace / "management" / "sprints"
    mapping: dict[str, tuple[int, str]] = {}
    if not sprints_dir.is_dir():
        return {}

    for path in sorted(sprints_dir.glob("sprint-*.md")):
        match = re.fullmatch(r"sprint-(\d+)\.md", path.name)
        if not match:
            continue
        number = int(match.group(1))
        label = f"sprint:{number:03d}"
        content = path.read_text(encoding="utf-8")
        for item_id in _engaged_item_ids(content):
            current = mapping.get(item_id)
            if current is None or number >= current[0]:
                mapping[item_id] = (number, label)

    return {item_id: value[1] for item_id, value in mapping.items()}


def labels_for_item(item: dict, sprint: str | None = None) -> list[str]:
    labels: list[str] = []
    item_type = str(item.get("type") or "").strip().lower()
    if item_type:
        labels.append(f"type:{item_type}")

    priority = str(item.get("priority") or "").strip().lower()
    if priority:
        labels.append(f"priority:{priority}")

    if str(item.get("mvp") or "").strip().lower() in {"oui", "yes", "true"}:
        labels.append("mvp")

    repositories = str(item.get("repositories") or "")
    for area in ("workspace", "backend", "frontend"):
        if re.search(rf"\b{re.escape(area)}\b", repositories, flags=re.IGNORECASE):
            labels.append(f"area:{area}")

    if sprint:
        labels.append(sprint)

    return labels


def build_issue_body(item: dict) -> str:
    epic = ""
    if item.get("epic_id"):
        epic = f"{item['epic_id']} — {item.get('epic_title') or ''}".rstrip(" —")

    lines = [
        "> Importé depuis `management/backlog.md` par OCP.",
        "",
        "## Métadonnées",
        "",
        f"- **Epic :** {epic or '—'}",
        f"- **Type :** {item.get('type') or '—'}",
        f"- **Priorité :** {item.get('priority') or '—'}",
        f"- **MVP :** {item.get('mvp') or '—'}",
        f"- **Repository(s) :** {item.get('repositories') or '—'}",
        f"- **Statut initial du backlog :** {item.get('initial_status') or '—'}",
        f"- **Sources :** {item.get('sources') or '—'}",
        f"- **Dépend de :** {item.get('depends_on') or 'Aucune'}",
        f"- **Débloque :** {item.get('unblocks') or '—'}",
        "",
        "## Spécification importée",
        "",
        str(item.get("section") or "").strip(),
        "",
    ]
    return "\n".join(lines)


_LABELS = {
    "type:spike": ("8250DF", "Investigation bornée avant décision"),
    "type:tech": ("0969DA", "Travail technique ou documentaire"),
    "type:us": ("1A7F37", "User Story / comportement utilisateur"),
    "priority:p0": ("B60205", "Priorité P0"),
    "priority:p1": ("D93F0B", "Priorité P1"),
    "priority:p2": ("FBCA04", "Priorité P2"),
    "priority:p3": ("6E7781", "Priorité P3"),
    "mvp": ("0E8A16", "Fait partie du MVP pédagogique"),
    "area:workspace": ("6E7781", "Workspace / documentation / coordination"),
    "area:backend": ("0052CC", "Backend"),
    "area:frontend": ("1D76DB", "Frontend"),
}


def _require_gh(workspace: Path) -> None:
    if shutil.which("gh") is None:
        raise BacklogImportError("GitHub CLI (gh) est introuvable dans le PATH.")
    completed = subprocess.run(
        ["gh", "auth", "status"],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "Authentification requise").strip()
        raise BacklogImportError(f"GitHub CLI n'est pas authentifié : {message}")


def _gh_json(arguments: list[str], workspace: Path) -> object:
    try:
        completed = subprocess.run(
            ["gh", *arguments],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "Erreur GitHub CLI").strip()
        raise BacklogImportError(message) from exc
    try:
        return json.loads(completed.stdout or "null")
    except json.JSONDecodeError as exc:
        raise BacklogImportError("Réponse JSON GitHub CLI invalide.") from exc


def _run_gh(arguments: list[str], workspace: Path) -> str:
    try:
        completed = subprocess.run(
            ["gh", *arguments],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "Erreur GitHub CLI").strip()
        raise BacklogImportError(message) from exc
    return completed.stdout.strip()


def get_github_repository(workspace: Path) -> str:
    data = _gh_json(["repo", "view", "--json", "nameWithOwner"], workspace)
    if not isinstance(data, dict) or not data.get("nameWithOwner"):
        raise BacklogImportError("Impossible de déterminer le repository GitHub du workspace.")
    return str(data["nameWithOwner"])


def _ensure_labels(workspace: Path, repository: str, required: set[str]) -> list[str]:
    data = _gh_json(
        ["label", "list", "--repo", repository, "--limit", "200", "--json", "name"],
        workspace,
    )
    existing = {
        str(row.get("name"))
        for row in data
        if isinstance(row, dict) and row.get("name")
    } if isinstance(data, list) else set()

    created: list[str] = []
    for label in sorted(required):
        if label in existing:
            continue
        color, description = _LABELS.get(label, ("BFD4F2", "Label géré par OCP"))
        _run_gh(
            [
                "label", "create", label,
                "--repo", repository,
                "--color", color,
                "--description", description,
            ],
            workspace,
        )
        created.append(label)
    return created


def _existing_issues(workspace: Path, repository: str) -> dict[str, dict]:
    data = _gh_json(
        [
            "issue", "list",
            "--repo", repository,
            "--state", "all",
            "--limit", "200",
            "--json", "number,title,url,labels",
        ],
        workspace,
    )
    result: dict[str, dict] = {}
    if not isinstance(data, list):
        return result
    for row in data:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "")
        match = re.match(r"^((?:SPIKE|TECH|US)-\d+)\s+[—-]", title)
        if match:
            result[match.group(1)] = row
    return result


def import_backlog_issues(
    workspace: Path,
    *,
    pause_seconds: float = 0.35,
) -> dict:
    """Crée/complète les Issues GitHub à partir de management/backlog.md.

    Cette fonction ne touche volontairement pas à l'API GitHub Projects : le workflow
    Auto-add du Project doit prendre en charge l'ajout des nouvelles Issues.
    """
    _require_gh(workspace)
    backlog_path = workspace / "management" / "backlog.md"
    items = parse_backlog(backlog_path)
    repository = get_github_repository(workspace)
    sprints = sprint_labels(workspace)

    required_labels: set[str] = set()
    item_labels: dict[str, list[str]] = {}
    for item in items:
        labels = labels_for_item(item, sprints.get(item["id"]))
        item_labels[item["id"]] = labels
        required_labels.update(labels)

    created_labels = _ensure_labels(workspace, repository, required_labels)
    existing = _existing_issues(workspace, repository)

    created: list[dict] = []
    reused: list[dict] = []
    for item in items:
        item_id = item["id"]
        title = f"{item_id} — {item['title']}"
        labels = item_labels[item_id]
        known = existing.get(item_id)

        if known:
            current_labels = {
                str(entry.get("name"))
                for entry in (known.get("labels") or [])
                if isinstance(entry, dict) and entry.get("name")
            }
            missing = [label for label in labels if label not in current_labels]
            if missing:
                args = ["issue", "edit", str(known["number"]), "--repo", repository]
                for label in missing:
                    args.extend(["--add-label", label])
                _run_gh(args, workspace)
            reused.append(
                {
                    "id": item_id,
                    "number": known.get("number"),
                    "url": known.get("url"),
                }
            )
            continue

        body_path = workspace / ".ocp-issue-body.tmp.md"
        body_path.write_text(build_issue_body(item), encoding="utf-8")
        try:
            args = [
                "issue", "create",
                "--repo", repository,
                "--title", title,
                "--body-file", str(body_path),
            ]
            for label in labels:
                args.extend(["--label", label])
            url = _run_gh(args, workspace)
        finally:
            body_path.unlink(missing_ok=True)

        number_match = re.search(r"/(\d+)$", url)
        created.append(
            {
                "id": item_id,
                "number": int(number_match.group(1)) if number_match else None,
                "url": url,
            }
        )
        if pause_seconds > 0:
            time.sleep(pause_seconds)

    return {
        "repository": repository,
        "items": len(items),
        "created_labels": created_labels,
        "created": created,
        "reused": reused,
    }
