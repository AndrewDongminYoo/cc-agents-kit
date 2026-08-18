#!/usr/bin/env python3
"""Prove zsh-quoting-guard.sh blocks the observed mistakes and passes everything else."""

import json
import subprocess
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
    proc = subprocess.run(["bash", HOOK], input=payload, capture_output=True, text=True)
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
    proc = subprocess.run(["bash", HOOK], input=payload, capture_output=True, text=True)
    ok = proc.returncode == 0
    fails += not ok
    print(
        f"{'ok  ' if ok else 'FAIL'} exit={proc.returncode} (want 0)  fail-open: {label}"
    )

print("\nALL PASS" if not fails else f"\n{fails} FAILURES")
raise SystemExit(1 if fails else 0)
