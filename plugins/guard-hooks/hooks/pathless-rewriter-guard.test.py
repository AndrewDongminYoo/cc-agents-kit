#!/usr/bin/env python3
"""Prove pathless-rewriter-guard.sh blocks path-less rewrites and nothing else."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

HOOK = str(Path(__file__).resolve().with_name("pathless-rewriter-guard.sh"))

CASES = [
    # (expected_exit, label, command)
    # --- the incident: a rewriter run bare during a verification step ---
    (2, "bare jsonsort", "jsonsort"),
    (2, "bare sortjson alias", "sortjson"),
    (2, "jsonsort with only flags", "jsonsort --silent --arrays"),
    (2, "bare trunk fmt", "trunk fmt"),
    (2, "trunk fmt --all", "trunk fmt --all"),
    (2, "bare ruff format", "ruff format"),
    # --- write-mode tools, no path ---
    (2, "prettier --write", "prettier --write"),
    (2, "prettier -w", "prettier -w"),
    (2, "eslint --fix", "eslint --fix"),
    (2, "shfmt -w", "shfmt -w"),
    # --- reached through a runner or an absolute path ---
    (2, "npx prefix", "npx prettier --write"),
    (2, "pnpm dlx prefix", "pnpm dlx prettier --write"),
    (2, "absolute binary path", "/opt/homebrew/bin/jsonsort"),
    (2, "env assignment prefix", "NODE_ENV=production jsonsort"),
    # --- chained, so the rewriter is not the first command ---
    (2, "after &&", "cd /repo && jsonsort"),
    (2, "after ;", "echo hi; trunk fmt"),
    (2, "in a subshell", "(cd /repo && jsonsort)"),
    # --- must NOT block: a path is present ---
    (0, "safe: jsonsort with a file", "jsonsort package.json"),
    (0, "safe: jsonsort with a dir", "jsonsort config/"),
    (0, "safe: flags then a path", "jsonsort --silent package.json"),
    (0, "safe: trunk fmt with a path", "trunk fmt scripts/lib.sh"),
    (0, "safe: prettier --write with a glob", "prettier --write 'src/**/*.ts'"),
    (0, "safe: eslint --fix with a path", "eslint --fix src/"),
    (0, "safe: shfmt -w with a path", "shfmt -w install.sh"),
    (0, "safe: ruff format with a path", "ruff format ."),
    # --- must NOT block: read-only invocations of write-mode tools ---
    (0, "safe: prettier --check", "prettier --check"),
    (0, "safe: bare eslint (reports only)", "eslint"),
    (0, "safe: trunk check is not a rewriter", "trunk check"),
    (0, "safe: shfmt -d (diff only)", "shfmt -d"),
    # --- must NOT block: the name appears as an argument, not a command ---
    (0, "safe: grep for the tool name", "grep -rn jsonsort docs/"),
    (0, "safe: which", "command -v jsonsort"),
    (0, "safe: unrelated command", "ls -la /tmp"),
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

# fail-open contract: never block on input the hook cannot parse
for label, payload in (
    ("empty object", "{}"),
    ("no command key", '{"tool_input": {"file_path": "/tmp/x"}}'),
    ("malformed", "not json at all"),
    ("empty stdin", ""),
):
    proc = subprocess.run(["/bin/bash", HOOK], input=payload, capture_output=True, text=True)
    ok = proc.returncode == 0
    fails += not ok
    print(
        f"{'ok  ' if ok else 'FAIL'} exit={proc.returncode} (want 0)  fail-open: {label}"
    )

DISABLE_VAR = "CC_GUARD_DISABLE_PATHLESS_REWRITER"
BLOCKING = json.dumps({"tool_name": "Bash", "tool_input": {"command": "jsonsort"}})
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
