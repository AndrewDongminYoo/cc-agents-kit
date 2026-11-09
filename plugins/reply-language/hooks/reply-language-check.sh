#!/usr/bin/env bash
# Stop: when the text shown to the user in this response is mostly not in the
# configured reply language, block the stop once and ask for the same content
# in that language, with no new tool work.
#
# The catch for what reply-language-reminder.sh does not prevent. It cannot
# hide the draft the user already saw; it only gets the restatement written
# without the user having to ask (anthropics/claude-code#99704, #96326).
#
# Measured on the main model's text blocks since the last input that started a
# turn (a user message, a task notification, a subagent's report, a queued
# message), after removing code, inline code, URLs, link targets, paths, tags
# and quoted lines. It blocks when at least 40 letters remain and under 30% of
# them, in the whole response or in its last block, are in the target script.
# It stays silent when stop_hook_active is set (one rewrite per stop), when the
# user's last message was in another language, for headless (sdk) runs, and
# whenever it cannot judge. Fail open: any error prints nothing and exits 0.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: set CC_GUARD_DISABLE_REPLY_LANGUAGE_CHECK=1 to disable this hook.
# Checked after stdin is drained so a disabled hook never leaves the harness
# writing to a closed pipe.
[[ -n "${CC_GUARD_DISABLE_REPLY_LANGUAGE_CHECK:-}" ]] && exit 0

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd) || exit 0
PY=/usr/bin/python3
[[ -x "$PY" ]] || PY=$(command -v python3 2>/dev/null || true)
[[ -n "$PY" ]] || exit 0

printf '%s' "$HOOK_INPUT" | "$PY" -I -S "$HERE/_reply_language.py" check 2>/dev/null || true
exit 0
