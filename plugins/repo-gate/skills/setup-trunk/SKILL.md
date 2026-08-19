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

### 1. Run trunk init

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

### 2. Verify built-in actions are enabled

After `trunk init`, confirm all four built-in actions are active:

```bash
trunk actions list
```

Expected enabled actions:

| Action                    | Purpose                                 |
| ------------------------- | --------------------------------------- |
| `trunk-announce`          | Notifies about trunk updates            |
| `trunk-check-pre-push`    | Runs `trunk check` before `git push`    |
| `trunk-fmt-pre-commit`    | Auto-formats staged files before commit |
| `trunk-upgrade-available` | Notifies when upgrades are available    |

Enable any missing action:

```bash
trunk actions enable trunk-fmt-pre-commit
trunk actions enable trunk-check-pre-push
```

**Disable `trunk-fmt-pre-commit` only** when contributing to an external repo that owns its own formatting rules (e.g., submitting a PR to an open-source project).
Re-enable when back on your own repo.

### 3. Full-repo scan and baseline

```bash
trunk check --all
```

This identifies **all** existing violations.
Existing violations in the repo are expected to be fixed — "already enabled but ignored" lint rules are in scope.

To auto-fix everything fixable:

```bash
trunk check --all --fix
```

To focus on one linter at a time when overwhelmed:

```bash
trunk check --all --filter=eslint
trunk check --all --filter=shellcheck --sample=5
```

## Stack-specific Linter Selection

### Universal baseline (all stacks)

These linters appear in virtually every repo and should always be enabled:

| Linter           | Purpose                                   |
| ---------------- | ----------------------------------------- |
| `git-diff-check` | Detects whitespace/merge conflict markers |
| `trufflehog`     | Secrets detection in committed content    |
| `osv-scanner`    | Dependency vulnerability scanning         |
| `checkov`        | Infrastructure-as-code security           |
| `markdownlint`   | Markdown style enforcement                |
| `prettier`       | Multi-language code formatter             |
| `yamllint`       | YAML syntax and style                     |

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
    - linters: [osv-scanner]
      paths: ["**/Podfile.lock"]
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
    - linters: [osv-scanner]
      paths: ["**/Podfile.lock"]
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
| `shellcheck`     | `android/gradlew`, `example/android/gradlew`       | Always add to ignore paths                                                                       |
| `osv-scanner`    | `**/Podfile.lock`                                  | Always ignore for iOS dependency locks                                                           |
| `markdownlint`   | `.github/**/*.md` (PR templates, issue templates)  | Ignore — not user-authored prose                                                                 |
| `dart`           | Flutter projects using a pinned SDK                | Disable; use `custom action` instead                                                             |
| `dotenv-linter`  | `ios/.xcode.env`, `ios/.xcode.env.local`           | Ignore — Xcode requires `export VAR=VALUE`; dotenv-linter strips `export`, breaking Xcode builds |
| `cspell`         | `android/gradlew` (auto-generated identifiers)     | Add to ignore alongside shellcheck                                                               |
| Any linter       | `*.lock` files                                     | Add to `lint.ignore`                                                                             |
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

```yaml
lint:
  ignore:
    - linters: [ALL]
      paths:
        - "**/*.lock" # lock files (all linters)
        - "src/generated/**" # generated code
        - "!src/generated/**/*.ts" # re-enable for TS inside generated/
    - linters: [shellcheck, cspell]
      paths:
        - "android/gradlew"
        - "example/android/gradlew"
    - linters: [osv-scanner]
      paths:
        - "**/Podfile.lock"
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
trunk fmt
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

1. Assess impact scope — is the vulnerable code path reachable?
2. If not reachable: add to `lint.ignore` with an explanation comment, or suppress inline on the lock file.
3. If reachable: upgrade the dependency or pin to a safe version.
4. If no upstream fix: file an issue with the upstream project.

## Common Mistakes

| Mistake                                                       | Fix                                                                  |
| ------------------------------------------------------------- | -------------------------------------------------------------------- |
| Running `trunk check --all` every commit                      | Use `trunk check` (no `--all`) for daily work                        |
| Disabling `trunk-fmt-pre-commit` for convenience              | Only disable for external repo contributions                         |
| Leaving `svgo` enabled in a mobile repo                       | Disable — SVG optimization rarely applies and can corrupt assets     |
| Not ignoring `android/gradlew` for shellcheck                 | Add to `lint.ignore` immediately on any React Native / Flutter repo  |
| Not ignoring `**/Podfile.lock` for osv-scanner                | iOS lock files trigger false CVEs from pod metadata, not actual deps |
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
trunk check --all --fix             # Auto-fix all fixable issues
trunk check --filter=<linter>       # Scope to one linter
trunk fmt                           # Format changed files
trunk check --sample=5              # Test linter config on 5 sample files
```
