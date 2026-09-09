---
name: markdownlint-triage
description: Use when summarizing Markdownlint logs, selecting useful Markdown rules, or fixing an existing Markdownlint backlog with file-scoped parallel work.
metadata:
  category: code-quality
---

# Markdownlint Triage

Turn Markdownlint diagnostics into a rule summary and a bounded cleanup.
First-time trunk integration, including the Prettier-compatible Markdownlint baseline it seeds, belongs to `setup-trunk`.
Trunk cache, download, or runtime failures are a different job and out of scope here.
Requests to summarize or recommend settings are read-only.
Change rules or documents only within the requested scope.

## Inspect the Active Configuration

Verify the absolute repository root and account before inspecting its Git state.
Read repository instructions, the selected runner configuration, and representative reported lines.
Identify generated files and archives that require exact source preservation.
Identify mirrored copies of the same document, such as per-profile duplicates: assign both copies to one worker and compare the pairs after repair.
Do not transfer settings or results from another repository merely because its rule counts look similar.

`markdownlint-summary` is on PATH whenever this plugin is enabled.
It selects `markdownlint` on PATH, then `trunk`.
It downloads nothing: a checkout's own `.npmrc` can point an auto-installed package at a registry the checkout controls, so the helper never runs `npx`.
It requires Bash, awk, and standard shell utilities.
A selected runner failure does not trigger another runner.
Each runner uses its own configuration, ignore rules, and installed version.
Running Trunk executes the checkout's own `.trunk/trunk.yaml` definitions, and `--fix` writes wherever the linter resolves a path, symlinks included.
On a checkout you do not trust, use log mode and no `--fix`.
Run mode prints only the summary and discards the runner's output.
To keep the raw diagnostics, redirect the linter's own output to a log file and use log mode.
For an existing Trunk backlog, capture Trunk output explicitly and use log mode so the runner does not change during comparison.
When the repository has no Markdownlint configuration and no Trunk setup, seed the baseline the same way `setup-trunk` does before selecting exceptions.

## Capture and Summarize

Run commands from the target repository.
Use a fresh log path for each comparison and retain the diagnostic log until validation is complete.
Do not overwrite an existing log without authorization.
Use `--all` only for an authorized repository-wide scan.

```bash
trunk check --no-fix --filter=markdownlint --all --color=false > markdownlint.log 2>&1
echo "Linter exit: $?"
markdownlint-summary --log markdownlint.log
```

Both `>` and `2>&1` are required.
Without `>`, the log filename becomes a Trunk path argument and Trunk rejects it as incompatible with `--all`.
Use `>>` to append only when accumulated runs are intentional: the summary counts repeated diagnostics again.
To show output while saving it, preserve pipeline failures:

```bash
set -o pipefail
trunk check --no-fix --filter=markdownlint --all --color=false 2>&1 | tee markdownlint.log
```

Without Trunk, install the CLI outside the checkout first, then capture its output the same way:

```bash
npm install -g markdownlint-cli@0.49.1
markdownlint -- docs/ README.md > markdownlint.log 2>&1
echo "Linter exit: $?"
markdownlint-summary --log markdownlint.log
```

Do not run `npx` inside a checkout you do not control: it prefers the checkout's own `node_modules`, so a tracked package at the pinned version runs as you.

For a new check with automatic runner selection, pass explicit target paths when the approved scope is narrow:

```bash
markdownlint-summary docs/ README.md
markdownlint-summary --fix docs/ README.md
markdownlint-summary --log markdownlint.log
```

Omitting paths scans Markdown under the current directory.
`--fix` changes the target files and requires an authorized fix scope.
The output contains count, description, and normalized rule ID, separated by tabs and sorted by descending count.
Run mode preserves the linter exit code.
Log mode reports parsing completion, not linter success.
An empty summary does not prove a clean run: check the original exit code and log for failures or an unsupported output format.
Keep the original diagnostics for file and line assignments; aggregate counts cannot identify repair targets.

## Select Rules by Document Purpose

Inspect examples before changing a rule.
Keep structural and content checks that detect actual defects.
A large count alone does not justify disabling a rule.
Compare before and after results with the same runner, version, configuration path, and file scope.
Report findings removed by configuration separately from defects repaired in documents.

The baseline that `setup-trunk` seeds already disables the formatting rules Prettier owns.
The table below covers only the content rules that baseline leaves on.
For flexible notes or prompts, consider this selective policy only when the document requirements support it:

| Rules | Decision criteria |
| --- | --- |
| MD026, MD036, MD041 | Consider exceptions when punctuation, emphasized labels, or documents without an opening H1 are intentional. |
| MD033, MD034 | Consider exceptions when the renderer accepts intentional HTML or bare URLs. Retain stricter rules when publishing requirements need them. |
| MD024 | Consider `siblings_only: true` when repeated headings under different parent sections are valid. Duplicates under the same parent still fire and need a heading change. |
| MD001, MD025 | Retain hierarchy checks when the documents require ordered heading levels and one document title. |
| MD037, MD038, MD040, MD056 | Retain checks for malformed emphasis, code-span spacing, missing fence languages, and table column mismatches. Review the source before changing it. |

Do not replace the whole configuration with this table or disable unrelated rules that already provide useful coverage.
Apply approved exceptions to the configuration actually loaded by the runner.
For example, an approved MD024 adjustment is:

```yaml
MD024:
  siblings_only: true
```

## Repair the Remaining Findings

Use the raw diagnostics to build an exact file list after the approved rule changes.
Fix generated output at its source or generator.
For ordinary documents, preserve meaning, frontmatter, links, examples, and data.

- MD001, MD024, MD025: inspect heading context before changing hierarchy or names. Check affected anchors and internal links.
- MD037, MD038: distinguish accidental spaces from intentional literal content before changing delimiters or whitespace.
- MD040: use the actual language when known, `log` for output, and `plaintext` when the content is plain text or cannot be classified. Respect matching backtick or tilde fence lengths.
- MD056: compare header, separator, and body cells. Account for escaped pipes. Do not delete or invent cell values to satisfy the count: a missing cell becomes an empty cell, and an extra cell goes back to the owner as a content question.

Classify fence languages before workers start, not in a later audit; reclassifying afterwards costs a second pass over every fence.

| Block content | Language |
| --- | --- |
| Slash-command lists, CLI output, shell transcripts, status dumps | `log` |
| Shell commands meant to be run | `bash` |
| Tool-call syntax, or config and data in a real syntax | that language: `python`, `dotenv`, `yaml`, `json` |
| Paths, ASCII structure, pseudocode, prose samples | `plaintext` |

Keep mechanical autofixes limited to approved files or filters and review their diff.
Do not run a repository-wide formatter as a side effect of fixing Markdownlint findings.

### Choose Execution by File Count

Count unique files that still require repairs after rule selection and scope exclusions.
Use the complete diagnostic file list, not the number of violations or all Markdown files in the repository.
Do not choose an execution mode from truncated output.
Report the target file count and selected mode before editing.

- Zero files: report the check result without starting repair work.
- One to five files: repair inline in the root session.
- Six or more files: assign non-overlapping file batches to two subagents when delegation is available.

If delegation is unavailable, process the batches inline and disclose the fallback.
Do not split workers by rule alone: one file can contain several rules.
Assign each file to exactly one worker, with all its relevant findings.
The root owns shared configuration, the file assignment map, and final verification.

Give each worker:

- The verified absolute repository, account, exact owned paths, and relevant repository instructions.
- The raw findings for those files, active configuration, and required content-preservation constraints.
- The fence language table above.
- One outcome: repair the assigned findings without changes to shared configuration or other files.
- The explicit-path validation command and expected result.
- The required response: changed paths, repairs, check command and exit code, remaining findings, and questions that need a content decision.

Workers must not delegate, stage, commit, or modify shared logs.
Start with two independent batches and avoid overlapping formatter runs.
Return ambiguous content repairs to the root instead of guessing.
Approval for cleanup does not authorize push or publication.

## Verify and Report

Rerun the same linter against repaired files and summarize a fresh log.
On a checkout you trust, then run the repository's whole gate on the changed files, not only Markdownlint: a fence language that Prettier has a parser for, such as `json`, `yaml`, or `markdown`, makes it format the block body, and a repaired table can trip MD060 alignment.
The whole gate executes the checkout's own `.trunk/trunk.yaml` definitions, so on a checkout you do not trust stay on log mode as above and leave the gate run to its owner.
For an approved full-backlog cleanup, finish with the same full-scope check used for the baseline.
Inspect the diff for content loss and unrelated formatting.
Use the project's renderer or link checker when repairs change rendering or anchors.
Lint success alone does not prove content fidelity.

When changing rule configuration, use a temporary fixture to prove an enabled rule still detects a known violation.
Remove the fixture and rerun the check.
Report remaining findings and nonzero exit codes without describing a partial cleanup as complete.
Include counts before and after, rule exceptions with their rationale, repaired paths, and checks actually run.
Do not reuse historical counts or verification results as current evidence.

The helper's regression suite is `bin/markdownlint-summary.test.py`, beside the script in this plugin.
