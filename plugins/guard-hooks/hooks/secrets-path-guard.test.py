#!/usr/bin/env python3
"""Prove secrets-path-guard.sh blocks live secret files across every input field."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

HOOK = str(Path(__file__).resolve().with_name("secrets-path-guard.sh"))

CASES = [
    # (expected_exit, label, tool_input)
    # --- the Keychain-derived secrets file, in each field the hook reads ---
    (2, "file_path: secrets file", {"file_path": "/Users/me/.zprofile.secrets"}),
    (2, "command: cat secrets file", {"command": "cat ~/.zprofile.secrets"}),
    (2, "path: grep over secrets file", {"path": "/Users/me/.zprofile.secrets"}),
    (2, "case-insensitive (APFS)", {"file_path": "/Users/me/.ZPROFILE.SECRETS"}),
    # --- live .env files ---
    (2, "file_path: .env", {"file_path": "/proj/.env"}),
    (2, "command: cat .env", {"command": "cat .env"}),
    (2, "command: source .env", {"command": "source .env"}),
    (2, ".env.local", {"file_path": "/proj/.env.local"}),
    (2, ".env.production", {"file_path": "/proj/.env.production"}),
    (2, ".env.production.local", {"file_path": "/proj/.env.production.local"}),
    (2, "quoted .env in a command", {"command": 'grep KEY ".env"'}),
    # --- must NOT block: template variants ---
    (0, "safe: .env.example", {"file_path": "/proj/.env.example"}),
    (0, "safe: .env.sample", {"file_path": "/proj/.env.sample"}),
    (0, "safe: .env.template", {"file_path": "/proj/.env.template"}),
    (0, "safe: .env.dist", {"file_path": "/proj/.env.dist"}),
    (0, "safe: .env.default", {"file_path": "/proj/.env.default"}),
    (0, "safe: .env.defaults", {"file_path": "/proj/.env.defaults"}),
    # --- must NOT block: .env as a property access, not a path component ---
    (0, "safe: process.env.HOME", {"command": "node -e 'console.log(process.env.HOME)'"}),
    (0, "safe: import.meta.env", {"command": "grep -rn import.meta.env src/"}),
    (0, "safe: unrelated file", {"file_path": "/proj/README.md"}),
    (0, "safe: unrelated command", {"command": "ls -la"}),
    # A template token must not exempt a separate live dotenv token.
    (2, "template + real .env in one command",
     {"command": "cat .env.example .env"}),
]

fails = 0
for expected, label, tool_input in CASES:
    payload = json.dumps({"tool_name": "Read", "tool_input": tool_input})
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
    ("no readable field", '{"tool_input": {"pattern": "TODO"}}'),
    ("malformed", "not json at all"),
    ("empty stdin", ""),
):
    proc = subprocess.run(["/bin/bash", HOOK], input=payload, capture_output=True, text=True)
    ok = proc.returncode == 0
    fails += not ok
    print(
        f"{'ok  ' if ok else 'FAIL'} exit={proc.returncode} (want 0)  fail-open: {label}"
    )



DISABLE_VAR = "CC_GUARD_DISABLE_SECRETS_PATH"
BLOCKING = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/proj/.env"}})
SAFE = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/proj/README.md"}})

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
