"""Append-only AI activity journal; human review is never inferred."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import warnings


def add_entry(workspace: Path, *, task: str, tool: str = "Codex CLI",
              request: str = "À renseigner", contribution: str = "À renseigner",
              decision: str = "À renseigner", verification: str = "À renseigner",
              references: str = "À renseigner") -> str:
    if not task.strip() or not tool.strip():
        raise ValueError("La tâche et l’outil sont obligatoires.")
    entry_id = "AI-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
    path = workspace / "journal" / "ai-journal.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = {"Date (UTC)": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "Tâche": task, "Outil": tool, "Demande": request,
              "Contribution": contribution, "Décision humaine": decision,
              "Vérifications et résultats": verification, "Références": references}
    # Indent continuations so pasted text cannot create journal headings.
    body = "\n\n## " + entry_id + "\n" + "\n".join(
        f"- **{key} :** " + value.strip().replace("\n", "\n  ")
        for key, value in fields.items()) + "\n"
    with path.open("a", encoding="utf-8") as stream:
        if path.stat().st_size == 0:
            stream.write("# Journal IA\n")
        stream.write(body)
    return entry_id


def record_generation(workspace: Path, output: Path) -> None:
    """A journal failure must not hide a successfully generated document."""
    try:
        relative = output.relative_to(workspace).as_posix()
        add_entry(workspace, task=f"Génération de {relative}",
                  request="Génération documentaire via une commande ocp ai.",
                  contribution=f"Document écrit : {relative}", references=relative)
    except (OSError, ValueError) as exc:
        warnings.warn(f"Document généré, mais journal IA non enregistré : {exc}", stacklevel=2)
