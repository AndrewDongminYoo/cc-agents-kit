#!/usr/bin/env python3
"""Prove lockfile-drift-check.sh warns only when a sibling lockfile is stale."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

HOOK = str(Path(__file__).resolve().with_name("lockfile-drift-check.sh"))

OLD, NEW = 1_700_000_000, 1_700_000_100


def run(file_path):
    """Return (exit_code, additionalContext or None)."""
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": file_path}})
    proc = subprocess.run(["bash", HOOK], input=payload, capture_output=True, text=True)
    out = proc.stdout.strip()
    if not out:
        return proc.returncode, None
    return proc.returncode, json.loads(out)["hookSpecificOutput"]["additionalContext"]


def fixture(tmp, manifest, locks, manifest_time=NEW, lock_time=OLD):
    """Write a manifest and its lockfiles, then stamp their mtimes."""
    d = Path(tmp)
    m = d / manifest
    m.write_text("{}\n")
    for lock in locks:
        p = d / lock
        p.write_text("lock\n")
        os.utime(p, (lock_time, lock_time))
    os.utime(m, (manifest_time, manifest_time))
    return str(m)


fails = 0


def check(label, condition, detail=""):
    global fails
    fails += not condition
    print(f"{'ok  ' if condition else 'FAIL'}  {label}")
    if not condition and detail:
        print(f"       {detail}")


with tempfile.TemporaryDirectory() as tmp:
    # --- stale lockfile: the case the hook exists for ---
    code, ctx = run(fixture(tmp, "package.json", ["yarn.lock"]))
    check("stale yarn.lock warns", ctx is not None and "yarn.lock" in ctx, f"ctx={ctx}")
    check("exit stays 0 (advisory, never blocks)", code == 0, f"exit={code}")

with tempfile.TemporaryDirectory() as tmp:
    # --- every supported ecosystem is detected by its own manifest ---
    for manifest, lock in (
        ("pubspec.yaml", "pubspec.lock"),
        ("Cargo.toml", "Cargo.lock"),
        ("pyproject.toml", "uv.lock"),
        ("Gemfile", "Gemfile.lock"),
        ("Podfile", "Podfile.lock"),
        ("composer.json", "composer.lock"),
    ):
        sub = Path(tmp) / manifest.replace(".", "_")
        sub.mkdir()
        _, ctx = run(fixture(sub, manifest, [lock]))
        check(f"{manifest} → {lock}", ctx is not None and lock in ctx, f"ctx={ctx}")

with tempfile.TemporaryDirectory() as tmp:
    # --- several stale lockfiles are all named ---
    _, ctx = run(fixture(tmp, "package.json", ["yarn.lock", "pnpm-lock.yaml"]))
    check(
        "all stale lockfiles listed",
        ctx is not None and "yarn.lock" in ctx and "pnpm-lock.yaml" in ctx,
        f"ctx={ctx}",
    )

with tempfile.TemporaryDirectory() as tmp:
    # --- fresh lockfile: silence, or the warning is noise on every edit ---
    _, ctx = run(fixture(tmp, "package.json", ["yarn.lock"], manifest_time=OLD, lock_time=NEW))
    check("fresh lockfile stays silent", ctx is None, f"ctx={ctx}")

with tempfile.TemporaryDirectory() as tmp:
    # --- not a dependency manifest ---
    d = Path(tmp)
    (d / "README.md").write_text("hi\n")
    (d / "yarn.lock").write_text("lock\n")
    os.utime(d / "yarn.lock", (OLD, OLD))
    os.utime(d / "README.md", (NEW, NEW))
    _, ctx = run(str(d / "README.md"))
    check("non-manifest edit stays silent", ctx is None, f"ctx={ctx}")

with tempfile.TemporaryDirectory() as tmp:
    # --- manifest with no lockfile beside it ---
    _, ctx = run(fixture(tmp, "package.json", []))
    check("manifest without a lockfile stays silent", ctx is None, f"ctx={ctx}")

with tempfile.TemporaryDirectory() as tmp:
    # --- a lockfile of a different ecosystem must not be picked up ---
    _, ctx = run(fixture(tmp, "package.json", ["Cargo.lock"]))
    check("foreign lockfile ignored", ctx is None, f"ctx={ctx}")

# --- fail-open contract ---
for label, payload in (
    ("empty object", "{}"),
    ("nonexistent path", '{"tool_input": {"file_path": "/nope/package.json"}}'),
    ("malformed", "not json at all"),
    ("empty stdin", ""),
):
    proc = subprocess.run(["bash", HOOK], input=payload, capture_output=True, text=True)
    check(
        f"fail-open: {label}",
        proc.returncode == 0 and not proc.stdout.strip(),
        f"exit={proc.returncode} stdout={proc.stdout.strip()[:120]}",
    )


# --- opt-out contract -------------------------------------------------------
# The opt-out is checked AFTER stdin is drained, on purpose. A hook that exits
# before reading leaves the harness writing to a closed pipe, so a *disabled*
# hook makes the tool call report an error. The large-payload case below pins
# that placement: it fails (writer killed by SIGPIPE, 141) if the check moves
# above the read.
DISABLE_VAR = "CC_GUARD_DISABLE_LOCKFILE_DRIFT"
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
            ["bash", "-c", WRAP, "_", tmp, HOOK], capture_output=True, text=True, env=env
        )
    finally:
        os.unlink(tmp)
    lines = proc.stdout.splitlines()
    writer, hook = (int(x) for x in lines[-1].split()[1:3])
    return writer, hook, "\n".join(lines[:-1]), proc.stderr


with tempfile.TemporaryDirectory() as tmp:
    warning_payload = json.dumps(
        {"tool_name": "Write", "tool_input": {"file_path": fixture(tmp, "package.json", ["yarn.lock"])}}
    )
    _, hook_rc, out, err = run_piped(warning_payload, True)
    check(
        "opt-out on: warning input stays silent",
        hook_rc == 0 and not out and not err,
        f"exit={hook_rc} stdout={out[:120]}",
    )
    _, _, out, _ = run_piped(warning_payload, False)
    check("opt-out off: warning still fires", bool(out), f"stdout={out[:120]}")

writer_rc, hook_rc, _, _ = run_piped(HUGE, True)
check(
    "disabled hook still drains a 200KB payload",
    writer_rc == 0 and hook_rc == 0,
    f"writer={writer_rc} hook={hook_rc}",
)

print("\nALL PASS" if not fails else f"\n{fails} FAILURES")
raise SystemExit(1 if fails else 0)
