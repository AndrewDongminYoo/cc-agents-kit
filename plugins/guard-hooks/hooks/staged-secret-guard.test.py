#!/usr/bin/env python3
"""Prove staged-secret-guard.sh blocks credentials in the staged diff, and only then."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

HOOK = str(Path(__file__).resolve().with_name("staged-secret-guard.sh"))

# Fake values assembled at runtime so this file carries no scannable literal.
NPM = "//registry.npmjs.org/:_authToken=" + "0" * 36
GITHUB = "ghp_" + "A" * 36
OPENAI = "sk-" + "B" * 32
AWS = "AKIA" + "C" * 16
PRIVATE_KEY = "-----BEGIN RSA PRIVATE KEY-----"


def repo(files, stage=True):
    """Create a git repo with files staged, and return its path."""
    d = tempfile.mkdtemp()
    run = lambda *a: subprocess.run(["git", "-C", d, *a], capture_output=True, text=True)
    run("init", "-q")
    run("config", "user.email", "t@example.invalid")
    run("config", "user.name", "t")
    for name, body in files.items():
        Path(d, name).write_text(body)
    if stage:
        run("add", "-A")
    return d


def check_hook(command, cwd):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    proc = subprocess.run(
        ["/bin/bash", HOOK], input=payload, capture_output=True, text=True, cwd=cwd
    )
    return proc.returncode, proc.stderr


fails = 0


def check(label, condition, detail=""):
    global fails
    fails += not condition
    print(f"{'ok  ' if condition else 'FAIL'}  {label}")
    if not condition and detail:
        print(f"       {detail}")


# --- each credential shape blocks -------------------------------------------
for label, body in (
    ("npm auth token", f".npmrc content\n{NPM}\n"),
    ("GitHub token", f"const t = '{GITHUB}'\n"),
    ("OpenAI-style key", f"KEY={OPENAI}\n"),
    ("AWS access key id", f"aws_access_key_id = {AWS}\n"),
    ("private key block", f"{PRIVATE_KEY}\nMIIEow...\n"),
):
    d = repo({"config.txt": body})
    rc, err = check_hook("git commit -m 'add config'", d)
    check(f"blocks {label}", rc == 2, f"exit={rc} stderr={err.strip()[:120]}")
    check(f"names {label} in the message", label in err, f"stderr={err.strip()[:160]}")

# --- the value itself is never echoed in full -------------------------------
d = repo({"config.txt": f"{GITHUB}\n"})
_, err = check_hook("git commit -m x", d)
check("does not echo the whole value", GITHUB not in err, f"stderr={err.strip()[:160]}")

# --- must NOT block ---------------------------------------------------------
d = repo({"README.md": "# hello\nNo secrets here.\n"})
rc, _ = check_hook("git commit -m docs", d)
check("clean diff passes", rc == 0, f"exit={rc}")

# A secret being REMOVED must not block its own removal.
d = repo({"config.txt": f"{GITHUB}\n"})
subprocess.run(["git", "-C", d, "commit", "-qm", "seed"], capture_output=True)
Path(d, "config.txt").write_text("cleaned\n")
subprocess.run(["git", "-C", d, "add", "-A"], capture_output=True)
rc, _ = check_hook("git commit -m 'remove the token'", d)
check("removing a secret is allowed", rc == 0, f"exit={rc}")

d = repo({"README.md": "# hello\n"}, stage=False)
rc, _ = check_hook("git commit -m nothing", d)
check("nothing staged passes", rc == 0, f"exit={rc}")

d = repo({"config.txt": f"{GITHUB}\n"})
for label, command in (
    ("non-commit git command", "git status --short"),
    ("prose mentioning git commit", "echo 'run git commit next'"),
    ("unrelated command", "ls -la"),
):
    rc, _ = check_hook(command, d)
    check(f"ignores {label}", rc == 0, f"exit={rc}")

# --- honours git -C so the right repo is scanned ----------------------------
dirty = repo({"config.txt": f"{GITHUB}\n"})
clean = repo({"README.md": "# hello\n"})
rc, _ = check_hook(f"git -C {dirty} commit -m x", clean)
check("git -C scans the named repo", rc == 2, f"exit={rc}")

# --- fail-open contract -----------------------------------------------------
for label, payload in (
    ("empty object", "{}"),
    ("no command key", '{"tool_input": {"file_path": "/tmp/x"}}'),
    ("malformed", "not json at all"),
    ("empty stdin", ""),
):
    proc = subprocess.run(["/bin/bash", HOOK], input=payload, capture_output=True, text=True)
    check(f"fail-open: {label}", proc.returncode == 0, f"exit={proc.returncode}")

# --- not a git repository at all --------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    rc, _ = check_hook("git commit -m x", tmp)
    check("outside a repository passes", rc == 0, f"exit={rc}")

DISABLE_VAR = "CC_GUARD_DISABLE_STAGED_SECRET"
WRAP = 'cd "$3" && cat "$1" | bash "$2"; echo "STATUS ${PIPESTATUS[0]} ${PIPESTATUS[1]}"'
HUGE = json.dumps(
    {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x.sh", "content": "x" * 200_000}}
)
BLOCKING = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}})
SAFE = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls -la /tmp"}})
dirty = repo({"config.txt": f"{GITHUB}\n"})


def run_piped(payload, disabled, cwd):
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
            ["/bin/bash", "-c", WRAP, "_", tmp, HOOK, cwd], capture_output=True, text=True, env=env
        )
    finally:
        os.unlink(tmp)
    lines = proc.stdout.splitlines()
    writer, hook = (int(x) for x in lines[-1].split()[1:3])
    return writer, hook, "\n".join(lines[:-1]), proc.stderr


# --- opt-out contract -------------------------------------------------------
# The opt-out is checked AFTER stdin is drained, on purpose. A hook that exits
# before reading leaves the harness writing to a closed pipe, so a *disabled*
# hook makes the tool call report an error. The large-payload case below pins
# that placement: it fails (writer killed by SIGPIPE, 141) if the check moves
# above the read.
for label, disabled, payload, want_exit in (
    ("opt-out on: staged secret passes", True, BLOCKING, 0),
    ("opt-out off: staged secret still blocks", False, BLOCKING, 2),
    ("opt-out on: unrelated input passes", True, SAFE, 0),
):
    _, hook_rc, _, _ = run_piped(payload, disabled, dirty)
    check(f"{label} (exit={hook_rc})", hook_rc == want_exit, f"want {want_exit}")

writer_rc, hook_rc, _, _ = run_piped(HUGE, True, dirty)
check(
    "disabled hook still drains a 200KB payload",
    writer_rc == 0 and hook_rc == 0,
    f"writer={writer_rc} hook={hook_rc}",
)

print("\nALL PASS" if not fails else f"\n{fails} FAILURES")
raise SystemExit(1 if fails else 0)
