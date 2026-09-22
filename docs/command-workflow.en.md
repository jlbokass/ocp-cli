# OCP — Command order and AI journal

[Français](command-workflow.md)

Version: first AI journal and translation increment, branch `feat/ai-journal-bilingual-docs`.
New commands become available on your computer only after installing this branch or its merged release. Opening the PR does not install them.

## 1. Install the version to try

In your OCP clone, after preserving any local changes:

```bash
git fetch origin
git switch --track origin/feat/ai-journal-bilingual-docs
pipx install --force .
ocp --help
ocp journal --help
ocp docs --help
```

If the local branch already exists, use `git switch feat/ai-journal-bilingual-docs`, then `git pull --ff-only` and reinstall. After merging, switch back to `main`, run `git pull --ff-only`, then `pipx install --force .`.
Requirements: Python >= 3.12, Git, pipx, authenticated GitHub CLI, and authenticated Codex CLI for AI commands. OCP does not configure an additional paid translation API.

## 2. Distinguish the three locations

- The `ocp-cli` repository contains the tool and this guide.
- A project workspace contains `project.yml`, `docs/`, `management/`, `journal/`, etc.
- `repos/backend` and `repos/frontend` are independent Git repositories inside the workspace.

Run project commands from the workspace. The new `journal` and `docs` commands also locate it from subdirectories. Paths supplied to `docs translate/review` are relative to the workspace root.

## 3. Create a workspace and prepare its sources

```bash
ocp init
# Enter oc-p3 at the prompt.
cd oc-p3
ocp status
```

`init` creates initial files, initializes Git, and attempts to create/push a private GitHub repository. It can therefore write remotely. Do not rerun it to reset an existing project.
Place official PDFs in `docs/source/`. The scope generator extracts PDFs: export DOCX/ODT sources to PDF for this pipeline while retaining the originals.
Record decisions in `docs/notes.md`, reflect accepted choices in `docs/cadrage.md`, and record mentor guidance in `mentoring/recommendations.md`.

### A new project without code: oc-p3

The current pipeline was designed around existing repositories. `ocp ai cadrage` requires a project audit, which requires repository audits. Do not fabricate audits or choose a stack just to unlock this command.

For P3, begin with sources, decisions, the scorecard, and a manually written/reviewed scope. Once the stack is chosen and real repositories are initialized, register them with `ocp repo add`, then use the pipeline below. An audit of scaffolding must explicitly state that business features are not implemented yet.
Generators may offer to replace documents: review the diff and preserve accepted decisions. `docs/notes.md` is not automatically an input to every prompt; reflect decisions in the documents actually consumed.

## 4. Pipeline order for existing repositories

Run each command separately, reviewing its result before continuing.

| Order | Command | Result and human action |
|---|---|---|
| 1 | `ocp repo add` | Register/clone each real repository once |
| 2 | `ocp ai audit` | Select a repository; repeat for each; review the audits |
| 3 | `ocp ai project-audit` | Consolidate audits; verify findings |
| 4 | `ocp ai cadrage` | Derive scope from PDFs and audit; preserve accepted decisions |
| 5 | `ocp ai workflow` | Review conventions and organization |
| 6 | `ocp ai backlog` | Review detailed backlog and stable identifiers before import |
| 7 | `ocp ai sprint` | Create a numbered sprint; validate commitments |
| 8 | `ocp backlog import` | Create/reuse Issues and apply labels, including sprint labels |

The backlog may be imported before sprint planning, then reimported for sprint labels. Import does not manage GitHub Project fields and is not full bidirectional content/status synchronization.
Configure a Project with Backlog, Ready, In Progress, Review, Done. Add Issues through the Project Auto-add workflow if available, otherwise manually. Preserve US/TECH/SPIKE identifiers across Markdown and Issues. Update the sprint outcome before planning the next sprint.

## 5. What the AI journal does

### Manual entry

```bash
ocp journal add --task "API contract review" --tool "ChatGPT" \
  --request "Check ownership permissions" \
  --contribution "Proposed access controls" \
  --decision "Pending human review" \
  --verification "Not yet performed" \
  --references "US-001; PR pending"
```

Appends an entry to `journal/ai-journal.md`, with a unique ID and UTC timestamp, without overwriting previous entries. `journal add` makes no AI call. Without `--task`, the terminal prompts for the task; other options keep their defaults. Specify the actual tool rather than leaving Codex CLI as the default for a ChatGPT conversation.
After review, edit that Markdown entry: accepted/modified/rejected, corrections, and evidence of tests actually run. The journal is neither immutable nor cryptographic evidence; Git provides change history.

### Reading

```bash
ocp journal list
```

Prints the entire journal. It does not summarize, modify files, review code, or run tests.

### Automatic recording

`audit`, `project-audit`, `cadrage`, `workflow`, `backlog`, and `sprint` append an entry after successfully writing their document. Entries include the tool, a generic generation description, and the output path. They do not capture the full prompt, measure saved time, or certify human review.

Human decision and verification fields remain **À renseigner** (to be completed). Complete the generated entry after review instead of duplicating it. Failed generation does not create a success entry; journal write failure emits a warning without deleting the generated document.
ChatGPT conversations, IDE work, tests, and `ocp ai commit` are not automatically captured in this version: add relevant entries manually.

## 6. Translate and record a review

```bash
ocp docs translate docs/cadrage.md
# Open and review docs/cadrage.en.md; correct it as needed.
ocp docs review docs/cadrage.md
ocp docs status
```

- `translate` calls Codex and writes a neighbouring English draft. The French source is unchanged. A SHA-256 registry tracks both files.
- `review` asks whether **you have reviewed and approved** the translation. Answering yes records your declaration for its current state. It makes no AI call, checks no linguistic quality, and approves neither code nor business decisions.
- `status` compares hashes. A translation can be in sync but still need review. French changes make it outdated; English edits after review require another review.

Pass the French path to `review`, not `cadrage.en.md`. A changed source prevents approval of an outdated translation.

```bash
ocp docs translate docs/cadrage.md --overwrite
# Review the diff: the previous English translation is replaced.
ocp docs review docs/cadrage.md
```

Preserve/commit important English edits before retranslating. Identifiers, commands, and links must remain consistent; the AI is instructed to preserve them, but this first increment has no structural validator guaranteeing that outcome.
Version `journal/translations.json`. It tracks registered translations only, not every Markdown file. Translate the journal last: any new entry makes its translation outdated. Translating the journal updates the registry but does not append an entry that would immediately invalidate its own source.

## 7. Daily development routine

1. Select the Issue in GitHub Project and move it to In Progress.
2. Create a branch in each affected repository.
3. Develop, record decisions and AI contributions, and run relevant tests.
4. Update French documentation and translations; review them.
5. In the affected application repository, run `ocp ai commit`, then `ocp pr create`.
6. In the workspace, commit the journal, decisions, and documentation using `ocp ai commit workspace`, then create its PR from the workspace.
7. Review PRs and CI; move Issues to Review. Translation approval does not replace PR review.
8. Once approved, run `ocp pr merge` from the correct repository. This command performs an actual merge.
9. Update the Project and sprint outcome; check `ocp status`.

`ocp publish` pushes existing commits; it is unnecessary before `ocp pr create`, which already pushes when needed. Do not blindly execute every publishing/merging step in sequence.

## 8. Delivery status

Journal, translation, and review are available on the working branch. Selective MkDocs/GitHub Pages publication is not implemented yet, and there is no `ocp docs publish` command. French remains the operational source; do not feed the English backlog to the French import parser.
