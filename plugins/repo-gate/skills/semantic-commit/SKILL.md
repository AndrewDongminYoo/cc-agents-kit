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

Save the change you are about to split as one patch, so Step 4 can tell your hunks from anyone else's:

```bash
git diff HEAD --binary --no-textconv > <scratch>/planned.patch
git diff --cached --binary --no-textconv > <scratch>/staged.patch          # HEAD to the index as found
git diff --binary --no-textconv > <scratch>/unstaged.patch                 # the index as found to the working tree
git status --porcelain --untracked-files=all                               # lists every untracked file, also inside new directories
git diff --no-index --binary --no-textconv /dev/null <untracked-file> >> <scratch>/planned.patch   # once per untracked file; exits 1 by design
```

`git diff HEAD` compares `HEAD` with the working tree, so a line that was staged and later changed back in the working tree is in the index but not in `planned.patch`, and committing the index first leaves a later group to stage the reversal.
`staged.patch` and `unstaged.patch` record both steps from `HEAD` through the index to the working tree, so every line a group can stage appears in one of the three patches, and all three count as planned in Step 4.
`git diff HEAD` also leaves untracked files out, and plain `git status --porcelain` shows a new directory as one `?? dir/` line; the `--no-index` form records each untracked file with its content and mode.
Every patch in this skill is built with `--binary --no-textconv`: without `--binary` a changed binary file reads only `Binary files differ`, and a repository's `textconv` driver replaces the real bytes with converted text that `git apply` rejects.

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
   Compare it with `planned.patch`, `staged.patch`, and `unstaged.patch` from Step 1 by content, not by hunk shape: every added or removed line, mode change, and path in `git diff --cached --binary --no-textconv` must come from one of them, or from a fix you made yourself during verification (Step 4.5).
   The comparison runs both ways: every change the plan assigns to this group must also still be there, because a parallel edit can revert one of your hunks while another planned hunk keeps the file dirty.
   Hunk boundaries, context lines, and line numbers will differ, because a split hunk and each earlier commit of this run change the base the diff is taken against.
   Anything else, such as new content, an executable bit, or a new or deleted file, was written by a parallel writer: the user in another editor, another agent session, or a tool.
   The index is the only way such an edit reaches a commit, so this one comparison covers it however it got there; stop and ask, and do not stage, stash, or restore it.
   Then record the reviewed tree: `reviewed=$(git write-tree)`.
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

7. Compare what was committed with what you reviewed, and read the full diff rather than its `--stat`: `git diff "$reviewed" HEAD`.
   A pre-commit hook that formats and re-stages this group's own files produces formatting-only lines there, which is expected.
   Any other path, or any content that is not formatting, such as a hunk you withheld for a later group that a hook's `git add` pulled into the same file, means a hook or a parallel writer changed the index during the commit; stop and report it, and do not amend.
   This detection is best-effort.
   It covers what reaches the index, and in the candidate a formatter, a self-staging script, or a new non-ignored file.
   It does not detect a hook that rewrites files without staging them (for example `gofmt -w .` with no `git add`): the hook runs in the main checkout, so it can change withheld hunks and later-group files there while this diff stays empty.

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
  Isolate the commit candidate in a detached worktree, never by stashing the shared working tree:

  ```bash
  git worktree add --detach <scratch>/candidate HEAD
  git diff --cached --binary --no-textconv > <scratch>/candidate.patch
  git -C <scratch>/candidate apply --index <scratch>/candidate.patch
  ```

  Run verification inside `<scratch>/candidate`, installing dependencies there first when the checks need them, and prefer each tool's check-only mode.
  Before committing, confirm that the candidate still is what you staged:
  - `git -C <scratch>/candidate diff --quiet` exits `0` (no unstaged rewrite),
  - `git -C <scratch>/candidate write-tree` equals `$reviewed` from Step 4.3 (no rewrite the verifier staged itself), and
  - `git -C <scratch>/candidate ls-files --others --exclude-standard` lists nothing (no new non-ignored file that the commit would lack).
    Ignored outputs are out of scope: the candidate holds only `HEAD` plus the staged diff, so anything a verifier writes to an ignored path is derived from the candidate, and the repository has declared that path as never committed.
  Also confirm that `git write-tree` in the main checkout still equals `$reviewed`; if it does not, a parallel writer changed the main index during verification, so stop and ask as Step 4.3 requires, whatever the candidate shows.
  Otherwise, any candidate mismatch means a verifier changed the candidate only, so the main index no longer matches what passed: carry the change into the main checkout, stage it, and verify again.
  Then commit from the main checkout as usual.
  Run `git worktree remove --force <scratch>/candidate` whenever a verification attempt ends, whether it passed, failed, or found a mismatch, and build a fresh candidate for the next attempt: a second `git worktree add` on the existing path fails with `already exists`, and `--force` is required because `apply --index` always leaves the candidate with staged changes.
  The worktree holds `HEAD` plus the staged diff and nothing else, so an untracked file that belongs to a later group stays out of test discovery and out of the compiler.
  Before building the patch, confirm that the index contains only the planned group.
  A stash resets the files in the shared tree, which other writers are still using.
  If the user saves a file there while it is reset, the save lands on the reverted copy, `git stash apply` refuses to overwrite it, and another session can drop the stash before you apply it (observed 2026-10-12).
  When a check truly cannot run outside this checkout and a stash is unavoidable, push it with a unique message (`git stash push -m semantic-commit-<timestamp> ...`) and find its commit by that message in `git stash list --format='%H %gs'`, not by position.
  Another session can push a stash between your push and your lookup, and then `stash@{0}` names its entry instead of yours; the message still names yours.
  Recover through that SHA.
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
