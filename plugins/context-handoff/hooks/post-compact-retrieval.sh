#!/usr/bin/env bash
# SessionStart hook (matcher: compact): after a compaction, add one line of
# context naming the transcript on disk, so history the summary dropped is
# retrieved with grep instead of re-derived or guessed.
#
# Plain stdout from a SessionStart hook that exits 0 is added to the context
# (hooks reference). This is the fallback that "You don't need long context"
# (arXiv 2611.05306, section 3.1) gives for what any lossy compaction loses:
# keep every message on disk and expose it to selective reading. The design is
# docs/specs/2026-11-07-compaction-brief.md.
#
# Fail open: no transcript path, empty or malformed input exits 0 with no
# output. A line that names no file would only cost context.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: set CC_GUARD_DISABLE_POST_COMPACT_RETRIEVAL=1 to disable this hook.
# Checked after stdin is drained so a disabled hook never leaves the harness
# writing to a closed pipe.
[[ -n "${CC_GUARD_DISABLE_POST_COMPACT_RETRIEVAL:-}" ]] && exit 0

TRANSCRIPT=$(printf '%s' "$HOOK_INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)
[[ -n "$TRANSCRIPT" ]] || exit 0
case "$TRANSCRIPT" in
  *$'\n'* | *$'\r'*) exit 0 ;; # keep the context line to one line
esac

printf '%s\n' "The context was just compacted. The full pre-compaction transcript is at $TRANSCRIPT; before re-deriving or asking for anything the summary does not mention, grep that file for it."
exit 0
