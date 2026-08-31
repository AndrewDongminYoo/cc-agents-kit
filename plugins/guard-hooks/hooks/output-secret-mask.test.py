#!/usr/bin/env python3
"""Prove output-secret-mask.sh rewrites credential-shaped values out of Bash output.

The masking cases need gitleaks; without it the suite asserts the silent no-op
instead, so it stays meaningful in CI either way (same shape as
shellcheck-on-edit.test.py).
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import _optout

HOOK = str(Path(__file__).resolve().with_name("output-secret-mask.sh"))
DISABLE = "CC_GUARD_DISABLE_OUTPUT_SECRET_MASK"
HAVE_GITLEAKS = shutil.which("gitleaks") is not None

# Fixtures with real entropy — gitleaks skips low-entropy lookalikes such as
# "ghp_" + 36 identical characters, so a repeated-letter token would test nothing.
PAT = "ghp_tDnSScc9gxIVr3CA8QTAc5BCy2Q1zZvUXUnB"
AWS = "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYzQ9RkN3Lp1"


def run(payload, env_extra=None):
    """Return (exit_code, parsed stdout or None, stderr)."""
    env = dict(os.environ)
    env.pop(DISABLE, None)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        ["/bin/bash", HOOK], input=payload, capture_output=True, text=True, env=env
    )
    out = proc.stdout.strip()
    return proc.returncode, (json.loads(out) if out else None), proc.stderr


def bash_payload(stdout, stderr=""):
    return json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "cat config.txt"},
            "tool_response": {
                "stdout": stdout,
                "stderr": stderr,
                "interrupted": False,
                "isImage": False,
            },
        }
    )


fails = 0


def check(label, condition, detail=""):
    global fails
    fails += not condition
    print(f"{'ok  ' if condition else 'FAIL'}  {label}")
    if not condition and detail:
        print(f"       {detail}")


if HAVE_GITLEAKS:
    # --- the case the hook exists for: a token in stdout is replaced ---
    code, out, err = run(bash_payload(f"build ok\nGITHUB_TOKEN={PAT}\nplain line\n"))
    check("exit stays 0 (rewrites, never blocks)", code == 0, f"exit={code} stderr={err[:120]}")
    check("emits updatedToolOutput", out is not None and "updatedToolOutput" in out["hookSpecificOutput"], f"out={out}")
    updated = out["hookSpecificOutput"]["updatedToolOutput"] if out else {}
    check("token gone from stdout", PAT not in updated.get("stdout", PAT))
    check("[REDACTED] marks the spot", "GITHUB_TOKEN=[REDACTED]" in updated.get("stdout", ""))
    check("untouched lines survive", "build ok\n" in updated.get("stdout", "") and "plain line\n" in updated.get("stdout", ""))
    check("other tool_response fields preserved", updated.get("interrupted") is False and updated.get("isImage") is False)
    check(
        "additionalContext names the count",
        "masked 1 credential-shaped value" in out["hookSpecificOutput"].get("additionalContext", "") if out else False,
    )

    # --- stderr is scanned and rewritten too ---
    _, out, _ = run(bash_payload("fine\n", f"warn: token {PAT} expired\n"))
    updated = out["hookSpecificOutput"]["updatedToolOutput"] if out else {}
    check("stderr masked", PAT not in updated.get("stderr", PAT) and "[REDACTED]" in updated.get("stderr", ""))
    check("stdout left as-is when clean", updated.get("stdout") == "fine\n")

    # --- two different secrets, each replaced everywhere it appears ---
    _, out, _ = run(bash_payload(f"{AWS}\n{PAT}\nagain {PAT}\n"))
    s = out["hookSpecificOutput"]["updatedToolOutput"]["stdout"] if out else ""
    check("every occurrence of every secret masked", PAT not in s and AWS.split("=")[1] not in s and s.count("[REDACTED]") == 3, f"stdout={s!r}")
    check("count reflects distinct secrets", "masked 2 credential-shaped" in out["hookSpecificOutput"]["additionalContext"] if out else False)

    # --- clean output: no rewrite, no noise ---
    code, out, err = run(bash_payload("ordinary log line\n" * 1500))
    check("clean output → silent exit 0", code == 0 and out is None and not err, f"exit={code} out={out}")

    # --- shapes that look like secrets but are not ---
    sha_lines = "\n".join(f"{i:040x} feat: change {i}" for i in range(20))
    code, out, _ = run(bash_payload(sha_lines + "\nPATH=/opt/homebrew/bin:/usr/bin\n"))
    check("git SHAs and PATH are not masked", code == 0 and out is None, f"out={out}")

    # --- over the size cap: pass through untouched ---
    code, out, _ = run(bash_payload("x" * 2_200_000 + f"\n{PAT}\n"))
    check("output over 2 MB passes through", code == 0 and out is None)
else:
    code, out, err = run(bash_payload(f"GITHUB_TOKEN={PAT}\n"))
    check("gitleaks absent → silent no-op", code == 0 and out is None and not err, f"exit={code} out={out}")

# --- gitleaks missing at runtime must never surface as a hook error ---
with tempfile.TemporaryDirectory() as bindir:
    for tool in ("jq", "bash", "cat", "printf", "mktemp", "rm"):
        src = shutil.which(tool)
        if src:
            os.symlink(src, os.path.join(bindir, tool))
    code, out, err = run(bash_payload(f"GITHUB_TOKEN={PAT}\n"), {"PATH": bindir})
    check("no gitleaks on PATH → silent exit 0", code == 0 and out is None and not err, f"exit={code} err={err[:120]}")

# --- fail-open contract: never rewrite or error on input the hook cannot use ---
for label, payload in (
    ("empty object", "{}"),
    ("malformed", "not json at all"),
    ("tool_response is a string", json.dumps({"tool_response": f"x {PAT}"})),
    ("stdout is not a string", json.dumps({"tool_response": {"stdout": 123}})),
    ("no tool_response", json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})),
):
    code, out, err = run(payload)
    check(f"fail-open: {label}", code == 0 and out is None and not err, f"exit={code} out={out} err={err[:100]}")

# --- opt-out, and the drain-before-check contract ---
code, out, _ = run(bash_payload(f"GITHUB_TOKEN={PAT}\n"), {DISABLE: "1"})
check("opt-out on: secret passes through", code == 0 and out is None)
fails += _optout.drain(HOOK, DISABLE)

print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failure(s)")
raise SystemExit(1 if fails else 0)
