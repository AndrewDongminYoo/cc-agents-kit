#!/usr/bin/env python3
"""Prove zsh-quoting-guard.sh blocks the observed mistakes and passes everything else."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

HOOK = str(Path(__file__).resolve().with_name("zsh-quoting-guard.sh"))

CASES = [
    # (expected_exit, label, command)
    (
        2,
        "operator's real slip: backtick in -m",
        'git commit -m "fix: cancel `players` subscription"',
    ),
    (
        2,
        "backtick in gh pr body",
        'gh pr create --title "x" --body "uses `AudioPool` now"',
    ),
    (2, "unquoted --include glob", 'grep -rn "AudioPool" lib/ --include=*.dart'),
    (2, "unquoted find -name glob", "find . -name *.md"),
    (0, "safe: -F file carrier", "git commit -F /tmp/msg.txt"),
    (
        0,
        "safe: quoted heredoc delimiter",
        "git commit -F - <<'MSG'\nfix: `players`\nMSG",
    ),
    (
        0,
        "safe: prose about globs inside a quoted heredoc",
        "git commit -F - <<'MSG'\ndocs: --include=*.dart and -name *.md abort under nomatch\nMSG",
    ),
    (
        2,
        "unquoted heredoc still interpolates",
        "git commit -F - <<MSG\nfix: `players`\nMSG",
    ),
    # The glob arg regex anchors on a leading space; prove that holds when the
    # command is chained rather than first.
    (2, "glob arg after a newline", "cd /tmp\nfind . -name *.md"),
    (2, "glob arg after a semicolon", "cd /tmp; find . -name *.md"),
    (0, "safe: single-quoted message", "git commit -m 'fix: `players` subscription'"),
    (0, "safe: escaped backtick", 'git commit -m "fix: \\`players\\` subscription"'),
    (0, "safe: quoted glob", "grep -rn x lib/ --include='*.dart'"),
    (0, "safe: $() substitution", 'git commit -m "release $(cat VERSION)"'),
    (0, "unrelated command", "ls -la /tmp"),
]

fails = 0
for expected, label, command in CASES:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    proc = subprocess.run(["/bin/bash", HOOK], input=payload, capture_output=True, text=True)
    ok = proc.returncode == expected
    fails += not ok
    print(
        f"{'ok  ' if ok else 'FAIL'} exit={proc.returncode} (want {expected})  {label}"
    )
    if not ok and proc.stderr:
        print(f"       stderr: {proc.stderr.strip()[:160]}")

# fail-open contract
for label, payload in (
    ("empty object", "{}"),
    ("malformed", "not json at all"),
    ("empty stdin", ""),
):
    proc = subprocess.run(["/bin/bash", HOOK], input=payload, capture_output=True, text=True)
    ok = proc.returncode == 0
    fails += not ok
    print(
        f"{'ok  ' if ok else 'FAIL'} exit={proc.returncode} (want 0)  fail-open: {label}"
    )



DISABLE_VAR = "CC_GUARD_DISABLE_ZSH_QUOTING"
BLOCKING = json.dumps({"tool_name": "Bash", "tool_input": {"command": "find . -name *.md"}})
SAFE = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls -la /tmp"}})

# --- opt-out contract -------------------------------------------------------
# The opt-out is checked AFTER stdin is drained, on purpose. A hook that exits
# before reading leaves the harness writing to a closed pipe, so a *disabled*
# hook makes the tool call report an error. The large-payload case below pins
# that placement: it fails (writer killed by SIGPIPE, 141) if the check moves
# above the read.
WRAP = 'cat "$1" | bash "$2"; echo "STATUS ${PIPESTATUS[0]} ${PIPESTATUS[1]}"'
HUGE = json.dumps(
    {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x.sh", "content": "x" * 200_000}}
)


def run_piped(payload, disabled):
    """Feed the hook over a real pipe. Returns (writer_status, hook_status, stdout, stderr)."""
    env = dict(os.environ)
    env.pop(DISABLE_VAR, None)
    if disabled:
        env[DISABLE_VAR] = "1"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        fh.write(payload)
        tmp = fh.name
    try:
        proc = subprocess.run(
            ["/bin/bash", "-c", WRAP, "_", tmp, HOOK], capture_output=True, text=True, env=env
        )
    finally:
        os.unlink(tmp)
    lines = proc.stdout.splitlines()
    writer, hook = (int(x) for x in lines[-1].split()[1:3])
    return writer, hook, "\n".join(lines[:-1]), proc.stderr


for label, disabled, payload, want_exit, want_quiet in (
    ("opt-out on: blocking input passes", True, BLOCKING, 0, True),
    ("opt-out off: blocking input still blocks", False, BLOCKING, 2, False),
    ("opt-out on: unrelated input passes", True, SAFE, 0, True),
):
    _, hook_rc, out, err = run_piped(payload, disabled)
    quiet = not out and not err
    ok = hook_rc == want_exit and (quiet if want_quiet else True)
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} exit={hook_rc} (want {want_exit})  {label}")

writer_rc, hook_rc, _, _ = run_piped(HUGE, True)
ok = writer_rc == 0 and hook_rc == 0
fails += not ok
print(
    f"{'ok  ' if ok else 'FAIL'} writer={writer_rc} (want 0)  "
    "disabled hook still drains a 200KB payload"
)

print("\nALL PASS" if not fails else f"\n{fails} FAILURES")
raise SystemExit(1 if fails else 0)
