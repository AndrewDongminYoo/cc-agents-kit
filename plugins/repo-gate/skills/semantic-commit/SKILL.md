---
name: semantic-commit
description: Use when staged/unstaged changes mix multiple unrelated concerns and need splitting into clean conventional commits, or when asked for "semantic commits", "logical commits", or "커밋 분리". Works in any language or ecosystem.
allowed-tools: Bash, Read, Glob
metadata:
  category: commits-ci-release
---

# Semantic Commit

Split work-in-progress changes into clean, reviewable conventional commits, verifying before each commit.

## Applicability

Use when:

- Multiple unrelated changes are unstaged/staged together
- User asks for "semantic commits", "logical commits", or "커밋 분리"
- After a multi-item implementation session before pushing

Skip when:

- There is only one logical change (just commit it directly)
- User explicitly asks for a single combined commit

## Steps

### 1. Understand the Full Diff

Run in parallel:

```bash
git status
git diff HEAD
git diff --cached
```

Read each changed file if the diff alone is insufficient to determine intent.
Treat the existing index as owned work.
Do not reset, unstage, or replace it without explicit approval.

### 2. Group by Concern

Assign each changed file to a group:

| Type              | When                                        |
| ----------------- | ------------------------------------------- |
| `feat(scope)`     | New user-facing behavior                    |
| `fix(scope)`      | Bug correction                              |
| `perf(scope)`     | Performance improvement, no behavior change |
| `refactor(scope)` | Code restructure, no behavior change        |
| `test(scope)`     | Test additions or changes only              |
| `build(scope)`    | Build system, deps, bundler, packaging      |
| `ci(scope)`       | CI/CD config and pipelines                  |
| `chore(scope)`    | Tooling, version bump, misc maintenance     |
| `docs(scope)`     | Documentation only                          |
| `style(scope)`    | Formatting, import order, no logic change   |

Rules:

- One file → one group by default.
  If a file genuinely spans two concerns, split it at hunk level (see Hunk-Level Splitting) and list it in both groups, marking which part goes where.
- Test files travel with their production file when both change together.
- Never mix `feat` and `fix` in the same commit.
- Pick `scope` from the affected module/package/feature area (see Scopes below).

### 3. Present the Plan

Show the proposed commit sequence **before executing**:

```markdown
Proposed commits:

1. feat(auth): add refresh-token rotation
   Files: src/api/..., src/auth/session.ts (hunk 1 only — the rotation path)
2. test(auth): cover refresh-token rotation edge cases
   Files: tests/auth/...
3. build(deps): bump jsonwebtoken to 9.0.2
   Files: package.json, package-lock.json
4. fix(auth): reject a refresh token past its expiry
   Files: src/auth/session.ts (hunks 2-3 only — the expiry check)
```

A file split across groups appears under each one, naming the hunks that belong there.

Wait for user confirmation ("go" / "네" / "좋습니다") before committing.

### 4. Commit Each Group

For each group in order:

1. Inspect the full index with `git diff --cached --name-only` and `git diff --cached`.
   If it contains a file or hunk outside this group, stop and ask for direction.
2. Stage only the files in this group: `git add <files>`.
   For a file split across groups, stage only its hunks (see Hunk-Level Splitting).
3. Verify the complete candidate index before every commit:

   ```bash
   git diff --cached --name-only
   git diff --cached --check
   git diff --cached
   ```

   Confirm that the full index contains only the planned group and intended hunks.
4. Run the project's verification commands against the isolated candidate (see Verification below).
5. Fix any issues before committing.
   Re-run the full-index verification after each fix.
6. Commit with the message on the subject line:

   ```bash
   git commit -m "type(scope): description"
   ```

   For a body, use a heredoc:

   ```bash
   git commit -m "$(cat <<'EOF'
   type(scope): description

   Optional body explaining the why.
   EOF
   )"
   ```

No `Co-authored-by: Claude` or similar AI trailer.

### 5. Report

After all commits, output:

```log
Committed:
  abc1234  feat(auth): add refresh-token rotation
  def5678  test(auth): cover refresh-token rotation edge cases
  ghi9012  build(deps): bump jsonwebtoken to 9.0.2
```

## Hunk-Level Splitting

`git add -p` is fully driveable over a pipe — it reads answers from stdin, so no TTY is needed:

```bash
git diff -- <file>                      # count and read the hunks first
printf 'y\nn\n' | git add -p -- <file>  # one y/n answer per hunk, in diff order
git diff --cached -- <file>             # confirm exactly the intended hunks are staged
```

Rules:

- Read the full diff and count the hunks **before** answering — provide exactly one answer per hunk.
  On EOF `git add -p` quits without staging further hunks, so an answer-count mismatch under-stages silently; the `git diff --cached` confirmation is mandatory, not optional.
- If two concerns are interleaved inside a single hunk, do not use `s` (its split points are line-count driven and rarely land on the concern boundary).
  Fall back to patch editing: `git diff -- <file> > /tmp/part.patch`, delete the unwanted hunks/lines from the patch, then `git apply --cached --recount /tmp/part.patch`.
  `--recount` is not optional once lines are deleted from inside a hunk: the `@@` counts go stale and `git apply` rejects the whole file with `corrupt patch` rather than applying what is left. It is harmless when whole hunks were dropped instead.
- After partial staging, the working tree and the index differ, so checks run on the working tree would test code that is not being committed.
  Isolate the commit candidate: `git stash push --keep-index --include-untracked`, run verification, commit, then `git stash apply` → confirm the remaining hunks are back → `git stash drop` (prefer apply-then-drop over `pop`).
  `--include-untracked` is load-bearing: `--keep-index` alone leaves untracked files in the tree, so a new file belonging to a later group stays visible to test discovery and to the compiler, and verification is not running against the commit candidate after all.
  Before stashing, confirm that the index contains only the planned group.
  Do not stash another person's staged files to make the candidate appear isolated.
- Do not blindly re-`git add` a partially staged file after a formatter runs — that would pull the withheld hunks back in.
  Use the formatter's `--check` mode as the gate for such files, or re-split from scratch.

## Verification

Detect the verify commands from the project — **do not assume any single stack.**
Prefer the project's own declared scripts (npm `package.json` scripts, `Makefile`/`justfile` targets, `CONTRIBUTING.md`, CI config) over the defaults below.

| Manifest / signal                     | Format / fix                | Lint / typecheck                         | Test                         |
| ------------------------------------- | --------------------------- | ---------------------------------------- | ---------------------------- |
| `package.json`                        | `npm run format` / prettier | `npm run lint` / eslint / `tsc --noEmit` | `npm test`                   |
| `pubspec.yaml`                        | `dart format .`             | `flutter analyze` or `dart analyze`      | `flutter test` / `dart test` |
| `Cargo.toml`                          | `cargo fmt`                 | `cargo clippy -- -D warnings`            | `cargo test`                 |
| `pyproject.toml` / `requirements.txt` | `ruff format` / black       | `ruff check` / mypy                      | `pytest`                     |
| `go.mod`                              | `gofmt -w` / `go fmt`       | `go vet` / golangci-lint                 | `go test ./...`              |
| `*.csproj` / `*.sln`                  | `dotnet format`             | `dotnet build -warnaserror`              | `dotnet test`                |
| shell scripts                         | `shfmt -w`                  | `shellcheck`                             | bats / project test script   |

For **JS/TS**, detect the package manager from the lockfile — `pnpm-lock.yaml` → `pnpm`, `yarn.lock` → `yarn`, `bun.lockb` → `bun`, else `npm` — and substitute it for `npm` above (e.g. `pnpm test`).
In a workspace/monorepo, scope to the changed package (`pnpm --filter <pkg> test`).

Format commands rewrite files — after formatting a staged group, re-run `git add` on the affected files (or use the formatter's `--check` mode purely as the gate).
Scale verification to the commit: a `docs`-only or `style`-only commit needs format/lint, not the full test suite.
Run the full test suite at least after the final commit.
If the project has **no** test or lint setup, say so rather than inventing commands.

## Scopes

Use a short scope naming the affected area.
Derive scopes from the repository's own structure — top-level packages, feature folders, or modules.
Common cross-cutting scopes: `deps`, `ci`, `release`, `config`, `docs`.
If a change is genuinely repo-wide, omit the scope (`chore: ...`).

## Exit Criteria

- All changes are committed (no unstaged/staged leftovers)
- Lint/typecheck passes after every commit
- Tests pass after the final commit
- No commit mixes unrelated concerns
