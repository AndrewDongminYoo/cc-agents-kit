---
name: setup-trunk
description: Use when integrating trunk.io into a repository for the first time, or when configuring trunk linters, git hooks, and pre-commit/push validation in an existing codebase with legacy lint violations.
metadata:
  category: commits-ci-release
---

# Setup Trunk

## Overview

Trunk.io is a meta-linter and git hook manager.
Its core principle is "hold-the-line": existing violations are acknowledged and ignored initially, but new violations on changed files are blocked.
This lets teams adopt linting incrementally without a big-bang cleanup.
This skill covers first-time integration and configuration. Running trunk day to day is a different job — `trunk check` / `trunk fmt` at milestones, cache corruption, aligning trunk-pinned linter versions with the workspace, vulnerability triage — and is out of scope here.

## Initialization Flow

### 1. Inspect the repository before selecting linters

Do not start from a memorized linter bundle.
First inspect the repository's manifests and lockfiles, existing CI workflows, declared package scripts, language and generated-file layout, and any existing linter configuration.
Use that evidence to identify tools the project already runs, file types that actually exist, and checks CI already owns.

```bash
git ls-files | grep -E '(^|/)(package.json|pubspec.yaml|pyproject.toml|Cargo.toml|go.mod|Podfile)$'
git ls-files '.github/**'
git ls-files | grep -Ei '(^|/)([^/]*(eslint|prettier|ruff|markdownlint|shellcheck)[^/]*)$'
```

Read the files found, including scripts in manifests and the commands used by CI, before proposing `lint.enabled`.
Enable a linter only when a repository artifact or an explicit user requirement supports it; do not infer that mobile, web, infrastructure, and documentation checks all belong in the same repository.

### 2. Run trunk init

```bash
trunk init
```

The wizard prompts for:

1. Account connection (optional for local-only use)
2. Linter auto-detection based on files in the repo
3. Git hooks setup (built-in actions)
4. Initial full-repo scan to snapshot existing violations

**For open-source repos where you contribute a PR to someone else's codebase and don't want to commit trunk config:**

```bash
trunk init  # then: trunk config hide
```

`trunk config hide` adds `.trunk/` to `.gitignore`, keeping the config local.
Alternatively, `trunk init --single-player-mode` does both in one step (verified in `trunk init --help`: "initialize trunk with a gitignored config, run 'trunk config share' to undo").

### 3. Review built-in actions

After `trunk init`, review which built-in actions are active and compare them with existing CI and repository hooks:

```bash
trunk actions list
```

Available actions commonly include:

| Action                    | Purpose                                 |
| ------------------------- | --------------------------------------- |
| `trunk-announce`          | Notifies about trunk updates            |
| `trunk-check-pre-push`    | Runs `trunk check` before `git push`    |
| `trunk-fmt-pre-commit`    | Auto-formats staged files before commit |
| `trunk-upgrade-available` | Notifies when upgrades are available    |

Enable only actions that do not duplicate or conflict with the repository's existing hooks:

```bash
trunk actions enable trunk-fmt-pre-commit
trunk actions enable trunk-check-pre-push
```

**Disable `trunk-fmt-pre-commit` only** when contributing to an external repo that owns its own formatting rules (e.g., submitting a PR to an open-source project).
Re-enable when back on your own repo.

### 4. Full-repo scan and baseline

```bash
trunk check --all
```

This identifies **all** existing violations.
Existing violations in the repo are expected to be fixed — "already enabled but ignored" lint rules are in scope.

Do not auto-fix the whole repository as part of setup without explicit approval.
That is a broad rewrite, so list the affected paths first and ask for approval for those explicit paths or a narrow linter filter.
After approval, run a scoped fix such as:

```bash
trunk check --fix path/to/file
trunk check --fix --filter=eslint src/
```

To focus on one linter at a time when overwhelmed:

```bash
trunk check --all --filter=eslint
trunk check --all --filter=shellcheck --sample=5
```

## Evidence-based Linter Selection

### No universal baseline

No linter is mandatory for every repository.
Choose from the following candidates only when the inspection step finds matching files, dependencies, configuration, or CI behavior:

| Evidence | Candidate linters |
| --- | --- |
| GitHub Actions workflows | `actionlint` |
| Shell scripts | `shellcheck`, optionally `shfmt` when the repository already formats shell |
| JavaScript or TypeScript manifest and existing config | project-pinned `eslint@SYSTEM`, `prettier` |
| Python manifest and existing config | `ruff`, `mypy`, or `black` as declared by the project |
| Markdown or YAML with an established style config | `markdownlint`, `yamllint` |
| Dependency lockfiles supported by the scanner | `osv-scanner` after verifying the lockfile targets it can interpret |
| Terraform, Kubernetes, or other IaC files | `checkov` |
| A repository requirement for committed-secret scanning | `trufflehog` |

The stack examples below are reference fragments, not bundles to copy wholesale.
Remove every entry unsupported by the inspected repository and preserve tools already pinned by the project.

### React Native

```yaml
lint:
  enabled:
    - actionlint # GitHub Actions workflow validation
    - checkov
    - dotenv-linter # .env file hygiene
    - eslint # JS/TS bridge code
    - git-diff-check
    - grype # container/binary vulnerability scan
    - ktlint # Android/Kotlin
    - markdownlint
    - osv-scanner
    - prettier
    - shellcheck # shell scripts
    - shfmt # shell formatter
    - swiftformat # iOS/Swift (or swiftlint)
    - trufflehog
    - yamllint
  ignore:
    - linters: [shellcheck]
      paths: ["android/gradlew", "example/android/gradlew"]
    - linters: [markdownlint]
      paths: [".github/**/*.md"]
    - linters: [dotenv-linter]
      paths:
        - "ios/.xcode.env" # uses 'export VAR=VALUE' — dotenv-linter rewrites to 'VAR=VALUE', breaking Xcode
        - "ios/.xcode.env.local"
```

### Flutter

```yaml
lint:
  disabled:
    - dart # trunk's built-in dart linter conflicts with project SDK; use custom action instead
  enabled:
    - actionlint
    - checkov
    - git-diff-check
    - ktlint # Android/Kotlin
    - markdownlint
    - osv-scanner
    - oxipng # PNG optimizer (review output before trusting)
    - prettier
    - shellcheck
    - shfmt
    - swiftformat # iOS/Swift
    - trufflehog
    - yamllint
  ignore:
    - linters: [shellcheck]
      paths: ["android/gradlew"]
    - linters: [markdownlint]
      paths: [".github/**/*.md"]
# Custom dart tooling via actions (replaces trunk's dart linter):
actions:
  definitions:
    - id: dart-actions
      description: Run 'dart run import_sorter:main' on pre-commit
      display_name: Dart Import Sorter Pre-Commit Hook
      run: |
        #!/usr/bin/env bash
        set -euo pipefail
        if dart run import_sorter:main -e | grep -qE 'Sorted [1-9]'; then
          exit 1
        else
          exit 0
        fi
      packages_file: pubspec.yaml
      triggers:
        - git_hooks: [pre-commit]
  enabled:
    - dart-actions
    - trunk-announce
    - trunk-check-pre-push
    - trunk-fmt-pre-commit
    - trunk-upgrade-available
```

### Python

```yaml
lint:
  disabled:
    - bandit # high false-positive rate; use ruff's S rules instead
    - isort # replaced by ruff's I rules
  enabled:
    - actionlint
    - black # formatter
    - checkov
    - git-diff-check
    - markdownlint
    - mypy # type checking
    - osv-scanner
    - prettier
    - ruff # fast linter (replaces flake8/isort/bandit)
    - trufflehog
    - yamllint
```

### Next.js / TypeScript

```yaml
lint:
  enabled:
    - actionlint
    - checkov
    - dotenv-linter
    - eslint # use @SYSTEM if repo pins its own eslint version
    - git-diff-check
    - markdownlint
    - osv-scanner
    - oxipng # PNG assets
    - prettier
    - svgo # SVG assets — keep enabled for web, disable for mobile
    - trufflehog
    - yamllint
```

## Handling False Positives and Destructive Linters

### Known problematic combinations

| Linter           | Problematic target                                 | Action                                                                                           |
| ---------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `oxipng`, `svgo` | SVG/PNG assets managed externally or with metadata | Disable unless you've reviewed output                                                            |
| `svgo`           | Mobile (React Native/Flutter) repos with SVGs      | Disable — rarely useful, high risk                                                               |
| `shellcheck`     | `android/gradlew`, `example/android/gradlew`       | Ignore only after confirming the generated wrapper is intentionally outside shell lint scope     |
| `osv-scanner`    | Resolved dependency lockfiles                      | Scan supported targets directly; ignore only a proven unsupported or mis-mapped target            |
| `markdownlint`   | `.github/**/*.md` (PR templates, issue templates)  | Ignore — not user-authored prose                                                                 |
| `dart`           | Flutter projects using a pinned SDK                | Disable; use `custom action` instead                                                             |
| `dotenv-linter`  | `ios/.xcode.env`, `ios/.xcode.env.local`           | Ignore — Xcode requires `export VAR=VALUE`; dotenv-linter strips `export`, breaking Xcode builds |
| `cspell`         | `android/gradlew` (auto-generated identifiers)     | Add to ignore alongside shellcheck                                                               |
| Any linter       | Config files in non-root dirs (`.github/`, etc.)   | Check if linter respects non-root path                                                           |

**Warning:** `oxipng`, `svgo`, and `dotenv-linter` modify files in place.
`oxipng`/`svgo` can corrupt binary assets; `dotenv-linter` silently rewrites `.env` syntax that platform tooling depends on (e.g., Xcode requires `export KEY=VALUE` but dotenv-linter normalizes it to `KEY=VALUE`).
Always verify output on first run.

### Linters that use the repo's own tooling (version mismatch false positives)

Some linters invoke the repo's own binary (eslint via `node_modules`, dart via the project's SDK).
If trunk's managed version differs from the project's, it may apply different rules or miss plugins.

**Affected linters:** `eslint`, `dart`

**Symptom:** `trunk check` reports violations that don't appear when running the tool directly.

**Fix:**

```yaml
lint:
  enabled:
    - eslint@SYSTEM # use node_modules/.bin/eslint
    - dart@SYSTEM # use project's dart SDK on PATH
```

`SYSTEM` tells trunk to skip its sandboxed version and invoke the repo's binary.
Do **not** use `SYSTEM` if the tool isn't installed in the project.

### Configuring ignores in `.trunk/trunk.yaml`

Keep format and style ignores linter-specific.
Never place resolved dependency lockfiles under `[ALL]`: vulnerability scanners need to inspect supported resolved locks directly.
Ignore a scanner target only after direct evidence shows that exact target is unsupported or mis-mapped, and record the rationale beside the scanner-specific ignore.

```yaml
lint:
  ignore:
    - linters: [ALL]
      paths:
        - "src/generated/**" # generated code
        - "!src/generated/**/*.ts" # re-enable for TS inside generated/
    - linters: [shellcheck, cspell]
      paths:
        - "android/gradlew"
        - "example/android/gradlew"
    - linters: [markdownlint]
      paths:
        - ".github/**/*.md"
    - linters: [svgo, oxipng]
      paths:
        - "**" # disable entirely for mobile repos
```

### Linter config files in subdirectories

If a linter's config file lives in `.github/` or another non-root directory (e.g., `.cspell.json` in `.github/`), trunk may not detect it and will report false positives.
Options:

- Move the config to the repo root, OR
- Add a root-level config that references the subdirectory file, OR
- Suppress the linter for affected paths in `lint.ignore`

## Pre-commit / Pre-push Validation Workflow

Trunk checks **only changed files** by default (no `--all`).
This is intentional — run without `--all` before committing:

```bash
trunk check
trunk fmt path/to/changed-file
```

If a violation is **intentional** (accepted technical debt, unavoidable pattern), suppress it inline:

<!-- trunk-ignore-all(trunk/ignore-unknown-linter) -->

```bash
# Single line
some_code  # trunk-ignore(linter-name/rule-id): reason

# Block
# trunk-ignore-begin(linter-name)
legacy_code_block()
# trunk-ignore-end(linter-name)

# Entire file
# trunk-ignore-all(linter-name)
```

**Only commit when `trunk check` exits clean** (or all remaining issues have explicit `trunk-ignore` annotations).

### Vulnerability findings

When `trunk check` reports a dependency vulnerability (e.g., from `osv-scanner`):

1. Scan the actual resolved lockfile directly with the scanner and confirm the advisory maps to the resolved dependency path and target.
2. Assess impact scope — is the vulnerable code path reachable?
3. If reachable, upgrade the dependency or pin to a safe version. If no upstream fix exists, file an issue with the upstream project.
4. If not reachable, document the reachability decision without hiding the resolved lockfile from unrelated scanners.
5. Ignore a scanner target only after direct evidence shows that exact target is unsupported or mis-mapped. Keep the ignore scanner-specific and record the evidence and rationale.

## Common Mistakes

| Mistake                                                       | Fix                                                                  |
| ------------------------------------------------------------- | -------------------------------------------------------------------- |
| Running `trunk check --all` every commit                      | Use `trunk check` (no `--all`) for daily work                        |
| Disabling `trunk-fmt-pre-commit` for convenience              | Only disable for external repo contributions                         |
| Leaving `svgo` enabled in a mobile repo                       | Disable — SVG optimization rarely applies and can corrupt assets     |
| Blanket-ignoring resolved lockfiles under `[ALL]`             | Keep style ignores linter-specific and scan supported locks directly |
| Using trunk's `dart` linter in Flutter projects               | Disable `dart`; use a custom `dart-actions` definition instead       |
| eslint/dart reporting different results than running directly | Pin to `@SYSTEM` in `trunk.yaml` to use the repo's own binary        |
| Forgetting `!path` negative globs                             | Use `!pattern` to re-enable a subset inside an ignored directory     |

## Quick Reference

Before inventing a config, look at one you already wrote. `find-trunk-repos` is on PATH whenever this plugin is enabled and lists your own public repositories whose default branch already carries `.trunk/trunk.yaml`, so an existing setup can be read rather than reconstructed. It needs the GitHub CLI authenticated (`gh auth login`), and prints `<owner/repo>  <default-branch>  <file-url>`.

```bash
find-trunk-repos                    # your repos that already have a trunk config

trunk init                          # Initialize trunk in repo
trunk config hide                   # Keep .trunk/ local (not committed)
trunk config share                  # Commit .trunk/ config to repo
trunk actions list                  # View enabled/disabled actions
trunk actions enable <action>       # Enable a built-in action
trunk check                         # Check changed files only
trunk check --all                   # Check entire repo (use at init)
trunk check --fix path/to/file      # Fix an approved explicit path
trunk check --filter=<linter>       # Scope to one linter
trunk fmt path/to/file              # Format an explicit path
trunk check --sample=5              # Test linter config on 5 sample files
```
