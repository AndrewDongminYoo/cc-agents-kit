#!/bin/bash
# Regenerates docs/compaction-brief.gif: the sections context-handoff's
# PreCompact hook asks a compaction summary for, and the line its SessionStart
# hook adds once the compaction is done.
# Usage and the CI check: docs/demo.lib.sh.
set -euo pipefail
# shellcheck source=docs/demo.lib.sh
source "$(dirname "$0")/demo.lib.sh"

transcript=/Users/you/.claude/projects/my-app/5f1c.jsonl

play() {
  say "$C" "# Auto-compact fires. Claude Code asks the PreCompact hook how to write the summary;"
  say "$C" "# the full brief is longer, so only its section headings are shown here."
  pause 1.2

  type_out "compaction-brief.sh | grep -oE '^(FIXED|RECAP)|^- [^:]+'"
  run_hook context-handoff/hooks/compaction-brief.sh \
    "{\"hook_event_name\":\"PreCompact\",\"trigger\":\"auto\",\"transcript_path\":\"$transcript\"}" \
    '^(FIXED|RECAP)|^- [^:]+'
  say "$C" "# FIXED is copied word for word into every later summary; RECAP is rewritten each time."
  pause 3.4

  say "$C" "# After the compaction, the SessionStart hook adds one line to the new context:"
  pause 1.0
  type_out "post-compact-retrieval.sh"
  run_hook context-handoff/hooks/post-compact-retrieval.sh \
    "{\"hook_event_name\":\"SessionStart\",\"source\":\"compact\",\"transcript_path\":\"$transcript\"}"
  pause 1.2
  say "$P" "# /plugin install context-handoff@cc-agents-kit"
  pause 3.2
}

demo_main compaction-brief "$@"
