---
name: ci-babysit
description: Use after pushing a branch or opening a PR when CI needs monitoring or authorized make-green work. Keeps watch-only requests read-only, requires explicit current-request or approved-plan authority before reruns or local repairs, and stops honestly when a human or logic change is needed. Works in any ecosystem.
metadata:
  category: commits-ci-release
---

# CI Babysit

Watch CI after a push until every job reaches a terminal state.
Keep watch-only work read-only.
Repair mechanical failures only when the current request or an approved plan gives explicit authority for local repair.

## When to use

- Right after `git push`, `/ship`, or `/commit-push-pr` on a branch whose CI result gates the next step, such as merge, release, or a review request.
- When the user asks to watch or monitor CI.
- When the user explicitly asks to make CI green or approves a plan that includes local repair.

Do NOT use for: local test runs (just run them), or repos without CI configured.

## Authority modes

### Watch-only

A request to watch, monitor, or report CI is watch-only unless the same request or an approved plan explicitly authorizes changes.
A watch-only request must not rerun jobs, install dependencies, format files, regenerate files, commit, or push.
Read check state and logs, then report terminal failures without changing local or remote state.

### Make-green

A make-green request must explicitly authorize state-changing reruns or local repair in the current request or an approved plan.
Authority to rerun does not authorize local repair.
Authority to repair does not authorize a commit or push.
Require separate explicit authority for each commit and each push.

## Workflow

### 1. Identify what to watch

```bash
branch_name=$(git branch --show-current)
head_sha=$(git rev-parse HEAD)
if ! pr_json=$(gh pr list --head "$branch_name" --state open --limit 2 --json number); then
  echo "Active pull-request lookup failed." >&2
  exit 1
fi
if ! jq -e 'type == "array" and all(.[]; type == "object" and (.number | type == "number"))' <<<"$pr_json" >/dev/null; then
  echo "Active pull-request lookup returned malformed JSON." >&2
  exit 1
fi
if [ "$(jq 'length' <<<"$pr_json")" -gt 1 ]; then
  echo "Active pull-request lookup returned more than one pull request." >&2
  exit 1
fi
pr_number=$(jq -r '.[0].number // empty' <<<"$pr_json")
if [ -n "$pr_number" ]; then
  gh pr checks "$pr_number"
else
  gh run list --branch "$branch_name" --commit "$head_sha" --limit 100
fi
```

Resolve the active pull request number before any CI poll.
Use that number for every pull-request check query.
Fall back to branch runs only when no active pull request exists.
Verify rather than assume — a passing local suite does not imply green CI.

**`no checks reported` right after a push means "none exist yet", not "CI is not configured" or "a maintainer must approve the run".**
Workflow runs are created minutes after the push: measured ~6 minutes on getagentseal/codeburn (push 01:09Z, first check run started 01:15:52Z, all six green by 01:18:40Z).
A single early call is not a reading of CI state — that one observation was reported as "awaiting first-time-contributor approval" on a repo with 68 contributors, and the checks had simply not been created.
So never conclude anything from one call.
Poll a bounded number of empty results, then report that CI did not create checks.
Read `gh api repos/<owner>/<repo>/commits/<head-sha>/check-runs` when the PR view has not caught up.
Origin: codeburn PR #1003, 2026-08-18.

### 2. On failure, diagnose from logs before touching anything

```bash
gh run view <run-id> --log-failed
```

Classify the failure before acting.
Log inspection is read-only and is allowed in both authority modes.

| Class         | Examples                                                                          | Action                                                 |
| ------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------ |
| Mechanical    | lockfile drift (immutable install), formatting, lint, generated files out of date | Repair in step 3 only with explicit local-repair authority. |
| Environmental | runner outage, flaky network, cache corruption                                    | Rerun once only with explicit rerun authority, then escalate. |
| Logic         | failing assertions, type errors, broken behavior                                  | Stop and report — do not auto-patch test expectations  |

A rerun changes remote state.
Run `gh run rerun <run-id> --failed` only when the current request or an approved plan explicitly authorizes a rerun.

### 3. Repair mechanical failures only with authority

Do not start a local repair unless the current request or an approved plan explicitly authorizes make-green repair work.

Detect the ecosystem from the repo, then run the CI-equivalent command locally:

- `yarn install --immutable` fails → run `yarn install` and inspect the lockfile update.
- Formatting/lint job fails → run the project's own format/lint fix command from CI config or package scripts.
- Generated files stale → regenerate via the project's codegen command; never hand-edit generated output.

One repair must stay in one focused change set.
Do not commit a repair unless the user gave explicit commit authority in the current request or approved plan.
Do not push a repair unless the user gave explicit push authority in the current request or approved plan.
If either authority is absent, report the changed files and ask for that specific authority.
After an authorized commit and push, return to step 1.

### 4. Attempt budget — stop honestly

Maximum **3 repair attempts** per babysit session.
This budget applies only to authorized repair work.
If CI is still red after 3 attempts, or the failure is a logic failure at any point: stop, summarize what failed, what was tried, and the exact failing log excerpt.
Never declare success while any job is red, and never weaken tests, skip jobs, or edit CI config to force green without explicit user approval.

## Watch cadence — event watch, not foreground polling

CI jobs take minutes — arm a `Monitor` tool watch right after the push so each check result arrives as a notification (one line per completed check, exits when the run finishes):

```bash
empty_polls=0
max_empty_polls=6
previous_checks=""
checks_error=$(mktemp)
trap 'rm -f "$checks_error"' EXIT
while true; do
  checks=""
  checks_status=0
  checks_source="gh pr checks"
  if [ -n "$pr_number" ]; then
    checks=$(gh pr checks "$pr_number" --json name,bucket 2>"$checks_error") || checks_status=$?
  else
    checks_source="gh run list"
    runs=$(gh run list --branch "$branch_name" --commit "$head_sha" --limit 100 --json name,status,conclusion 2>"$checks_error") || checks_status=$?
    if [ "$checks_status" -ne 0 ]; then
      echo "gh run list failed with exit $checks_status." >&2
      cat "$checks_error" >&2
      exit 1
    fi
    if ! jq -e 'type == "array" and all(.[]; type == "object" and (.name | type == "string") and (.status | type == "string") and (.conclusion | type == "string"))' <<<"$runs" >/dev/null; then
      echo "gh run list returned malformed JSON." >&2
      exit 1
    fi
    checks=$(jq -c '[.[] | {
      name: .name,
      bucket: (
        if .status == "completed" and .conclusion == "success" then "pass"
        elif .status == "completed" and .conclusion == "skipped" then "skipping"
        elif .status == "completed" and .conclusion == "cancelled" then "cancel"
        elif .status == "completed" then "fail"
        elif .status == "queued" or .status == "in_progress" or .status == "requested" or .status == "waiting" or .status == "pending" then "pending"
        else "fail"
        end
      )
    }]' <<<"$runs")
  fi
  if ! jq -e 'type == "array" and all(.[]; type == "object" and (.name | type == "string") and (.bucket | type == "string"))' <<<"$checks" >/dev/null; then
    echo "$checks_source returned malformed JSON with exit $checks_status." >&2
    cat "$checks_error" >&2
    exit 1
  fi
  unknown_buckets=$(jq -r '.[] | select(.bucket != "pass" and .bucket != "fail" and .bucket != "pending" and .bucket != "skipping" and .bucket != "cancel") | "\(.name): \(.bucket)"' <<<"$checks")
  if [ -n "$unknown_buckets" ]; then
    printf '%s returned unknown buckets:\n%s\n' "$checks_source" "$unknown_buckets" >&2
    exit 1
  fi
  terminal_failures=$(jq -r '.[] | select(.bucket == "fail" or .bucket == "cancel") | "\(.name): \(.bucket)"' <<<"$checks")
  if [ -n "$terminal_failures" ]; then
    printf 'CI reached a terminal failure:\n%s\n' "$terminal_failures" >&2
    exit 1
  fi
  case "$checks_status" in
    0) ;;
    8)
      if ! jq -e 'length > 0 and any(.[]; .bucket == "pending")' <<<"$checks" >/dev/null; then
        echo "gh pr checks exited 8 without valid pending check data." >&2
        exit 1
      fi
      ;;
    *)
      echo "$checks_source failed with exit $checks_status." >&2
      cat "$checks_error" >&2
      exit 1
      ;;
  esac
  if jq -e 'length == 0' <<<"$checks" >/dev/null; then
    empty_polls=$((empty_polls + 1))
    if [ "$empty_polls" -ge "$max_empty_polls" ]; then
      echo "CI did not report checks after $max_empty_polls empty polls." >&2
      exit 1
    fi
    sleep 30
    continue
  fi
  current_checks=$(jq -r '.[] | select(.bucket!="pending") | "\(.name): \(.bucket)"' <<<"$checks" | sort)
  comm -13 <(printf '%s\n' "$previous_checks") <(printf '%s\n' "$current_checks")
  previous_checks="$current_checks"
  if jq -e 'length > 0 and all(.[]; .bucket == "pass" or .bucket == "skipping")' <<<"$checks" >/dev/null; then
    exit 0
  fi
  sleep 30
done
```

Each `fail` or `cancel` bucket is a terminal failure.
Only a non-empty set of `pass` and `skipping` buckets exits successfully.
Malformed JSON and unknown buckets are explicit errors.
After terminal failures are handled, a command failure with an exit other than 0 or 8 is also an explicit error.
An exit of 8 is pending only when the command returned valid non-empty JSON that contains a `pending` bucket.
For branch pushes without a PR, the loop limits `gh run list` to the current head SHA and applies the same empty-poll cap and terminal criteria.
Fallback only if the Monitor tool is unavailable: `gh run watch` (blocking) or re-check every 3–4 minutes — never hot-loop.
