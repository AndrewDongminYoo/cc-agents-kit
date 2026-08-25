"""The opt-out contract every hook shares, exercised behind a real pipe.

Imported by the suites beside it; the leading underscore keeps it out of CI's
`*.test.py` glob so it is a helper, not a suite.

The opt-out is checked AFTER stdin is drained, on purpose. A hook that exits
before reading leaves the harness writing to a closed pipe, so a *disabled*
hook makes the tool call report an error. The 200KB case below pins that
placement: it fails (writer killed by SIGPIPE, 141) if the check moves above
the read. Python's `subprocess` swallows `BrokenPipeError`, so the writer has
to be a real shell whose `PIPESTATUS` we can read back.
"""

import json
import os
import subprocess
import tempfile

WRAP = 'cd "$3" && cat "$1" | bash "$2"; echo "STATUS ${PIPESTATUS[0]} ${PIPESTATUS[1]}"'
HUGE = json.dumps(
    {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x.sh", "content": "x" * 200_000}}
)


def run_piped(hook, disable_var, payload, disabled, cwd="."):
    """Feed the hook over a real pipe. Returns (writer_status, hook_status, stdout, stderr)."""
    env = dict(os.environ)
    env.pop(disable_var, None)
    if disabled:
        env[disable_var] = "1"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        fh.write(payload)
        tmp = fh.name
    try:
        proc = subprocess.run(
            ["/bin/bash", "-c", WRAP, "_", tmp, hook, cwd], capture_output=True, text=True, env=env
        )
    finally:
        os.unlink(tmp)
    lines = proc.stdout.splitlines()
    writer, hook_rc = (int(x) for x in lines[-1].split()[1:3])
    return writer, hook_rc, "\n".join(lines[:-1]), proc.stderr


def report(ok, detail):
    print(f"{'ok  ' if ok else 'FAIL'} {detail}")
    return not ok


def drain(hook, disable_var, cwd="."):
    """A disabled hook must still drain a 200KB payload. Returns failures."""
    writer_rc, hook_rc, _, _ = run_piped(hook, disable_var, HUGE, True, cwd)
    ok = writer_rc == 0 and hook_rc == 0
    return report(ok, f"writer={writer_rc} (want 0)  disabled hook still drains a 200KB payload")


def contract(hook, disable_var, blocking, safe, cwd="."):
    """The three blocking-guard opt-out cases plus the drain case. Returns failures."""
    failures = 0
    for label, disabled, payload, want_exit, want_quiet in (
        ("opt-out on: blocking input passes", True, blocking, 0, True),
        ("opt-out off: blocking input still blocks", False, blocking, 2, False),
        ("opt-out on: unrelated input passes", True, safe, 0, True),
    ):
        _, hook_rc, out, err = run_piped(hook, disable_var, payload, disabled, cwd)
        quiet = not out and not err
        ok = hook_rc == want_exit and (quiet if want_quiet else True)
        failures += report(ok, f"exit={hook_rc} (want {want_exit})  {label}")
    return failures + drain(hook, disable_var, cwd)
