#!/usr/bin/env bash
# UserPromptSubmit and PostToolUse (every tool): add context that keeps
# user-facing text in the configured reply language.
#
# Opus 5.5 drifts into English right after English input that is addressed to
# it (a subagent report, a brief it just wrote, tool output), and a correction
# holds for about one turn (anthropics/claude-code#99704). On a user message
# (which includes a background subagent reporting back) and after Agent or
# SendMessage, the hook adds a sentence that allows English only for what
# someone other than the user reads. After every other tool result it adds one
# short line, right before the next text the model writes.
#
# The target language comes from Claude Code's `language` setting, or from
# CC_REPLY_LANGUAGE. No language, or one without its own script: no output.
# Never blocks. Fail open: any error prints nothing and exits 0.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: set CC_GUARD_DISABLE_REPLY_LANGUAGE_REMINDER=1 to disable this hook.
# Checked after stdin is drained so a disabled hook never leaves the harness
# writing to a closed pipe.
[[ -n "${CC_GUARD_DISABLE_REPLY_LANGUAGE_REMINDER:-}" ]] && exit 0

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd) || exit 0
PY=/usr/bin/python3
[[ -x "$PY" ]] || PY=$(command -v python3 2>/dev/null || true)
[[ -n "$PY" ]] || exit 0

printf '%s' "$HOOK_INPUT" | "$PY" -I -S "$HERE/_reply_language.py" remind 2>/dev/null || true
exit 0
