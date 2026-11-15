#!/usr/bin/env bash
# PreToolUse (AskUserQuestion): refuse the call when the question and options
# the user would see are mostly not in the configured reply language, and ask
# for the same question rewritten in that language.
#
# The question lives in the tool input, so neither reply-language-reminder.sh
# (it runs after a tool returns) nor reply-language-check.sh (it reads text
# blocks) sees it. Unlike the Stop check, this runs before the user sees
# anything, so the English draft never reaches the dialog.
#
# Judged on each question, header, option label and option description, with
# the same stripping and thresholds as the Stop check: at least 40 letters and
# under 30% of them in the target script. A preview (a mockup or code) is not
# judged. It stays silent when the user's last message was in another
# language, for headless (sdk) runs, and whenever it cannot judge.
# Fail open: any error prints nothing and exits 0.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: set CC_GUARD_DISABLE_REPLY_LANGUAGE_ASK=1 to disable this hook.
# Checked after stdin is drained so a disabled hook never leaves the harness
# writing to a closed pipe.
[[ -n "${CC_GUARD_DISABLE_REPLY_LANGUAGE_ASK:-}" ]] && exit 0

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd) || exit 0
PY=/usr/bin/python3
[[ -x "$PY" ]] || PY=$(command -v python3 2>/dev/null || true)
[[ -n "$PY" ]] || exit 0

REASON=$(printf '%s' "$HOOK_INPUT" | "$PY" -I -S "$HERE/_reply_language.py" ask 2>/dev/null || true)
[[ -n "$REASON" ]] || exit 0
printf '%s\n' "$REASON" >&2
exit 2
