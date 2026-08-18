---
name: ci-babysit
description: Use after pushing a branch or opening a PR when CI must go green. Watches CI via a Monitor event watch over the gh CLI, self-heals mechanical failures (lockfile drift, formatting, lint) within a 3-attempt budget, and stops honestly when a human or logic change is needed. Works in any ecosystem.
metadata:
  category: commits-ci-release
---

# CI Babysit

Watch CI after a push until every job passes, repairing mechanical failures autonomously and escalating everything else.

## When to use

- Right after `git push`, `/ship`, or `/commit-push-pr` on a branch whose CI result gates the next step (merge, release, review request).
- When the user says "CI 볼 때까지 봐줘", "make CI green", or resumes a session where CI was left red.

Do NOT use for: local test runs (just run them), or repos without CI configured.

## Workflow

### 1. Identify what to watch

```bash
gh pr checks --watch 2>/dev/null || gh run list --branch "$(git branch --show-current)" --limit 5
```

Prefer `gh pr checks` when a PR exists; fall back to `gh run watch <run-id>` for branch pushes.
Verify rather than assume — a passing local suite does not imply green CI.

**`no checks reported` right after a push means "none exist yet", not "CI is not configured" or "a maintainer must approve the run".**
Workflow runs are created minutes after the push: measured ~6 minutes on getagentseal/codeburn (push 01:09Z, first check run started 01:15:52Z, all six green by 01:18:40Z).
A single early call is not a reading of CI state — that one observation was reported as "awaiting first-time-contributor approval" on a repo with 68 contributors, and the checks had simply not been created.
So never conclude anything from one call: keep the watch loop below running, or read `gh api repos/<owner>/<repo>/commits/<head-sha>/check-runs` which lists runs whether or not the PR view has caught up.
Origin: codeburn PR #1003, 2026-08-18.

### 2. On failure, diagnose from logs before touching anything

```bash
gh run view <run-id> --log-failed
```

Classify the failure before acting:

| Class         | Examples                                                                          | Action                                                 |
| ------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------ |
| Mechanical    | lockfile drift (immutable install), formatting, lint, generated files out of date | Self-heal (step 3)                                     |
| Environmental | runner outage, flaky network, cache corruption                                    | Re-run once via `gh run rerun --failed`, then escalate |
| Logic         | failing assertions, type errors, broken behavior                                  | Stop and report — do not auto-patch test expectations  |

### 3. Self-heal mechanical failures only

Detect the ecosystem from the repo (lockfile/manifest present), then run the CI-equivalent command locally, commit the result, and push:

- `yarn install --immutable` fails → run `yarn install`, commit the lockfile.
- Formatting/lint job fails → run the project's own format/lint fix command (from CI config or package scripts), commit.
- Generated files stale → regenerate via the project's codegen command; never hand-edit generated output.

One repair = one focused commit (conventional message), then return to step 1.

### 4. Attempt budget — stop honestly

Maximum **3 repair attempts** per babysit session.
If CI is still red after 3 attempts, or the failure is a logic failure at any point: stop, summarize what failed, what was tried, and the exact failing log excerpt.
Never declare success while any job is red, and never weaken tests, skip jobs, or edit CI config to force green without explicit user approval.

## Watch cadence — event watch, not foreground polling

CI jobs take minutes — arm a `Monitor` tool watch right after the push so each check result arrives as a notification (one line per completed check, exits when the run finishes):

```bash
prev=""
while true; do
  s=$(gh pr checks {n} --json name,bucket 2>/dev/null || echo '[]')
  cur=$(jq -r '.[] | select(.bucket!="pending") | "\(.name): \(.bucket)"' <<<"$s" | sort)
  comm -13 <(printf '%s\n' "$prev") <(printf '%s\n' "$cur")
  prev="$cur"
  jq -e 'length > 0 and all(.bucket!="pending")' <<<"$s" >/dev/null && break
  sleep 30
done
```

Each `fail` notification enters the repair loop above; the loop's exit is the all-checks-done signal.
For branch pushes without a PR, substitute `gh run list --branch <branch> --json databaseId,status,conclusion` state diffs.
Fallback only if the Monitor tool is unavailable: `gh run watch` (blocking) or re-check every 3–4 minutes — never hot-loop.
