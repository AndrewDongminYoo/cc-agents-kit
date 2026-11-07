#!/usr/bin/env bash
# PreCompact hook (matcher: manual|auto): print the compaction brief.
#
# Claude Code uses a PreCompact hook's stdout as the instructions for the
# compaction summary when the hook exits 0 and does not block (hooks reference,
# "Exit code and JSON output"; stdout is capped at 10,000 characters per hook).
# This hook never blocks, never prints a decision, and never prints a
# systemMessage (PreCompact discards it). It only shapes what the summary keeps.
#
# The section list is the one the paper "You don't need long context"
# (arXiv 2611.05306, Appendix G) ran at every compaction threshold: a brief for
# the work still to be done, not a narrative of the work so far. The design is
# docs/specs/2026-11-07-compaction-brief.md. The handoff skill's template uses
# the same sections, so a compaction is the thin version of a handoff.
#
# Fail open: empty, malformed or key-less input still prints the brief, because
# printing nothing silently falls back to the default summary, which is the
# condition this hook exists to replace. A brief with no transcript path is
# still a valid brief.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: set CC_GUARD_DISABLE_COMPACTION_BRIEF=1 to disable this hook. Checked
# after stdin is drained so a disabled hook never leaves the harness writing to
# a closed pipe.
[[ -n "${CC_GUARD_DISABLE_COMPACTION_BRIEF:-}" ]] && exit 0

TRANSCRIPT=$(printf '%s' "$HOOK_INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)
case "$TRANSCRIPT" in
  *$'\n'* | *$'\r'*) TRANSCRIPT="" ;; # a path with a line break would break the brief's layout
esac

if [[ -n "$TRANSCRIPT" ]]; then
  TRANSCRIPT_LINE="  The full transcript of this conversation is on disk at: $TRANSCRIPT"
else
  TRANSCRIPT_LINE="  The full transcript of this conversation stays on disk (the session's transcript file)."
fi

cat <<EOF
Write the summary as a handoff brief for the work still to be done, not as a narrative of the work so far.
Keep only what the next stretch of work needs to act on; drop repetition, drop the order events happened in unless it matters, and never weight a fact by how often it appeared.
Do not invent observations. Mark anything unverified as unverified.
Use exactly these sections, in this order, with these headings.

FIXED (append-only: copy every entry from an earlier brief in the conversation word for word, then add what the user said since, in order; never paraphrase or drop an entry, and where a later request or correction replaces an earlier one, keep both and say which is current)
- Task: every request the user made, in their words and in order.
- Done when: the acceptance criteria, in the user's words where they gave them.
- User constraints: constraints and preferences the user stated, and any from CLAUDE.md or AGENTS.md that were quoted; write None if there are none.

RECAP (replaces any earlier recap; every section is written fresh from the current state)
- Persistent state: branch, worktree, uncommitted files, running services or background tasks, and the transcript path, as they are now.
$TRANSCRIPT_LINE
- Objective: one line, the required result of the current stretch.
- Established facts: exact paths, symbols, commands, observed values and the important errors or output, with observations separated from unverified ideas.
- Applied changes: each changed or created file, what changed, and whether it was verified.
- Verification: the exact checks run, their outcomes, failures, obstacles and workarounds.
- Dead ends: approaches that failed and must not be repeated, each with the evidence that it failed.
- Remaining plan: the outstanding subgoals in execution order, the immediate next command or edit, and the condition for completion.
- Retrieval: narrow commands to re-fetch anything this summary had to truncate or drop, such as a grep or sed -n over the transcript path above, or a file with a line range.
- External status: each tracker issue, review, console or inbox mentioned, with the URL, ID or path to re-read it from.

End with this line, unchanged: Re-read any status above from its named source before acting on it; treat a status with no named source as unverified.
EOF
exit 0
