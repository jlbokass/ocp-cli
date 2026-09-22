from pathlib import Path

import pytest
from typer.testing import CliRunner

from ocp import ai, documentation
from ocp.cli import app
from ocp.journal import add_entry


def test_entries_preserve_history_and_do_not_invent_review(tmp_path):
    path = tmp_path / 'journal' / 'ai-journal.md'
    path.parent.mkdir()
    path.write_text('# Journal IA\n\nExisting human notes\n')
    original = path.read_text()
    first = add_entry(tmp_path, task='Audit\n## pasted heading')
    second = add_entry(tmp_path, task='Translation')
    content = path.read_text()
    assert content.startswith(original)
    assert first != second
    assert '\n## pasted heading' not in content
    assert '**Décision humaine :** À renseigner' in content
    assert '**Vérifications et résultats :** À renseigner' in content


def test_generation_logs_success_not_failure(tmp_path, monkeypatch):
    repo = tmp_path / 'repos' / 'backend'
    (repo / '.git').mkdir(parents=True)
    monkeypatch.setattr(ai.shutil, 'which', lambda _: 'codex')
    monkeypatch.setattr(ai, '_run_codex', lambda *args: '# Audit')
    ai.run_codex_audit(tmp_path, {'id':'backend', 'path':'repos/backend'})
    journal = tmp_path / 'journal' / 'ai-journal.md'
    original = journal.read_text()
    assert 'audits/backend/initial-audit.md' in original
    def fail(*args):
        raise ai.AiAuditError('failure')
    monkeypatch.setattr(ai, '_run_codex', fail)
    with pytest.raises(ai.AiAuditError):
        ai.run_codex_audit(tmp_path, {'id':'backend', 'path':'repos/backend'}, overwrite=True)
    assert journal.read_text() == original


def translator(monkeypatch):
    monkeypatch.setattr(documentation.shutil, 'which', lambda _: 'codex')
    monkeypatch.setattr(documentation, '_run_codex', lambda *args: '# Scope\n\nEnglish text')


def test_translation_preserves_source_detects_changes_and_refuses_overwrite(tmp_path, monkeypatch):
    translator(monkeypatch)
    source = tmp_path / 'scope.md'
    source.write_text('# Cadrage\n')
    target = documentation.translate(tmp_path, 'scope.md')
    assert source.read_text() == '# Cadrage\n'
    assert target.name == 'scope.en.md'
    assert documentation.translation_status(tmp_path)[0][1].startswith('in sync')
    with pytest.raises(ValueError, match='existante'):
        documentation.translate(tmp_path, 'scope.md')
    source.write_text('# Nouveau cadrage\n')
    assert documentation.translation_status(tmp_path)[0][1] == 'outdated'


def test_translation_journal_does_not_invalidate_itself(tmp_path, monkeypatch):
    translator(monkeypatch)
    add_entry(tmp_path, task='Initial task')
    documentation.translate(tmp_path, 'journal/ai-journal.md')
    assert documentation.translation_status(tmp_path)[0][1].startswith('in sync')


def test_translation_failure_keeps_existing_target(tmp_path, monkeypatch):
    translator(monkeypatch)
    source = tmp_path / 'scope.md'
    source.write_text('# Cadrage')
    target = documentation.translate(tmp_path, 'scope.md')
    original = target.read_bytes()
    def fail(*args):
        raise ai.AiAuditError('failure')
    monkeypatch.setattr(documentation, '_run_codex', fail)
    with pytest.raises(ai.AiAuditError):
        documentation.translate(tmp_path, 'scope.md', overwrite=True)
    assert target.read_bytes() == original


def test_reject_source_outside_workspace(tmp_path):
    with pytest.raises(ValueError):
        documentation.source_path(tmp_path, '../outside.md')


def test_cli_commands_from_nested_repository(tmp_path, monkeypatch):
    (tmp_path / 'project.yml').write_text('project: {}')
    nested = tmp_path / 'repos' / 'backend'
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    runner = CliRunner()
    result = runner.invoke(app, ['journal', 'add', '--task', 'Inspect', '--tool', 'ChatGPT'])
    assert result.exit_code == 0, result.output
    assert runner.invoke(app, ['journal', 'list']).exit_code == 0
    assert runner.invoke(app, ['docs', 'status']).exit_code == 0


def test_explicit_review_and_later_target_edit(tmp_path, monkeypatch):
    translator(monkeypatch)
    (tmp_path / 'scope.md').write_text('# Cadrage')
    target = documentation.translate(tmp_path, 'scope.md')
    documentation.mark_reviewed(tmp_path, 'scope.md')
    assert documentation.translation_status(tmp_path)[0][1] == 'in sync — reviewed'
    assert 'Translation draft' not in target.read_text()
    target.write_text(target.read_text() + '\nEdited')
    assert 'edited' in documentation.translation_status(tmp_path)[0][1]
    (tmp_path / 'scope.md').write_text('# Changed')
    with pytest.raises(ValueError, match='Source modifiée'):
        documentation.mark_reviewed(tmp_path, 'scope.md')
