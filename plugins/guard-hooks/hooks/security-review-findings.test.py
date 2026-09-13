#!/usr/bin/env python3
"""Prove security-review-findings.sh surfaces automatic review findings after a commit and stays silent otherwise.

The fixtures are transcript files laid out the way Claude Code writes them:
one JSONL per session under <config>/projects/<slug>/, where the slug is the
repository's full path with `/`, `.` and `_` dashed. CLAUDE_CONFIG_DIR points
the hook at a temporary tree so no real transcript is read.
"""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import _optout

HOOK = str(Path(__file__).resolve().with_name("security-review-findings.sh"))
DISABLE_VAR = "CC_GUARD_DISABLE_SECURITY_FINDINGS"
AUTO_PROMPT = "Review this change for security vulnerabilities."

fails = 0


def check(label, condition, detail=""):
    global fails
    fails += not condition
    print(f"{'ok  ' if condition else 'FAIL'} {label}{'  ' + detail if detail and not condition else ''}")


def slug(path):
    return str(path).translate(str.maketrans("/._", "---"))


def dumps(obj):
    """Claude Code writes transcripts compact, with no space after `:` or `,`."""
    return json.dumps(obj, separators=(",", ":"))


def transcript(config_dir, repo, entries, age_seconds=0):
    """Write one session file for `repo` and stamp its mtime."""
    d = Path(config_dir) / "projects" / slug(repo)
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"session-{len(list(d.iterdir()))}.jsonl"
    f.write_text("".join(dumps(e) + "\n" for e in entries))
    if age_seconds:
        t = time.time() - age_seconds
        os.utime(f, (t, t))
    return f


def user(text):
    return {"type": "user", "timestamp": "2026-09-12T01:00:00.000Z", "message": {"role": "user", "content": text}}


def verdict(findings):
    return {
        "type": "assistant",
        "timestamp": "2026-09-12T01:00:30.000Z",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "toolu_1", "name": "StructuredOutput", "input": {"findings": findings}}],
        },
    }


FINDING = {"filePath": "src/auth.ts", "category": "trust-boundary", "explanation": "Token is read from an unvalidated header."}


def repo(tmp, name):
    """An initialised git repository whose path is what the hook resolves."""
    r = Path(tmp) / name
    r.mkdir(parents=True)
    subprocess.run(["git", "-C", str(r), "init", "-q"], check=True)
    return r.resolve()


def run(config_dir, cwd, command="git commit -m x", env_extra=None):
    """Return (exit_code, additionalContext or None, stderr)."""
    payload = json.dumps({"tool_name": "Bash", "cwd": str(cwd), "tool_input": {"command": command}})
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(config_dir))
    env.pop(DISABLE_VAR, None)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(["/bin/bash", HOOK], input=payload, capture_output=True, text=True, env=env)
    out = proc.stdout.strip()
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else None
    return proc.returncode, ctx, proc.stderr


def run_print(config_dir, cwd):
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(config_dir))
    env.pop(DISABLE_VAR, None)
    proc = subprocess.run(["/bin/bash", HOOK, "--print", str(cwd)], capture_output=True, text=True, env=env)
    return proc.returncode, proc.stdout


# --- the finding reaches the model after a commit ------------------------------
with tempfile.TemporaryDirectory() as tmp:
    cfg = Path(tmp) / "cfg"
    r = repo(tmp, "app")
    transcript(cfg, r, [user(AUTO_PROMPT + "\n\nChanged files: src/auth.ts"), verdict([FINDING])])

    rc, ctx, err = run(cfg, r)
    check("a finding is surfaced after git commit", rc == 0 and ctx is not None and "src/auth.ts" in ctx, f"exit={rc} ctx={ctx} err={err[:120]}")
    check("the message says it does not block", ctx is not None and "nothing is blocked" in ctx)
    check("the category and explanation come through", ctx is not None and "trust-boundary" in ctx and "unvalidated header" in ctx)

    rc, ctx, _ = run(cfg, r, command="git -C /somewhere/else commit -F msg.txt")
    check("git -C <path> commit is recognised as a commit", ctx is not None, f"ctx={ctx}")

    for label, command in (
        ("git status is not a commit", "git status --porcelain"),
        ("git log is not a commit", "git log --oneline -3"),
        ("a non-git command is ignored", "ls -la"),
    ):
        rc, ctx, _ = run(cfg, r, command=command)
        check(label, rc == 0 and ctx is None, f"exit={rc} ctx={ctx}")

# --- the nested verdict shape is unwrapped, not lost -------------------------
with tempfile.TemporaryDirectory() as tmp:
    cfg = Path(tmp) / "cfg"
    r = repo(tmp, "app")
    transcript(cfg, r, [user(AUTO_PROMPT), verdict({"findings": [FINDING]})])
    rc, ctx, _ = run(cfg, r)
    check("a {findings: {findings: [...]}} verdict is unwrapped", ctx is not None and "src/auth.ts" in ctx, f"ctx={ctx}")

# --- only automatic sessions count -------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    cfg = Path(tmp) / "cfg"
    r = repo(tmp, "app")
    # A user session that merely quotes the prompt later on, then emits the same
    # StructuredOutput shape, is not an automatic review.
    transcript(cfg, r, [user("please look at this"), user(AUTO_PROMPT), verdict([FINDING])])
    rc, ctx, _ = run(cfg, r)
    check("a session whose FIRST user turn is not the auto prompt is ignored", rc == 0 and ctx is None, f"ctx={ctx}")

    transcript(cfg, r, [user(AUTO_PROMPT), verdict([])])
    rc, ctx, _ = run(cfg, r)
    check("an automatic review with an empty verdict stays silent", rc == 0 and ctx is None, f"ctx={ctx}")

# --- the window is two days ---------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    cfg = Path(tmp) / "cfg"
    r = repo(tmp, "app")
    transcript(cfg, r, [user(AUTO_PROMPT), verdict([FINDING])], age_seconds=3 * 86400)
    rc, ctx, _ = run(cfg, r)
    check("a finding older than two days is not surfaced", rc == 0 and ctx is None, f"ctx={ctx}")

# --- the slug is the full path, dashed -----------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    cfg = Path(tmp) / "cfg"
    r = repo(tmp, ".dot_repo")
    transcript(cfg, r, [user(AUTO_PROMPT), verdict([FINDING])])
    rc, ctx, _ = run(cfg, r)
    check("a dotted, underscored repository path maps to its slug", ctx is not None, f"ctx={ctx}")
    # The same file placed under a basename-shaped slug must NOT be found — this
    # pins that the hook does not fall back to substring matching on the name.
    other = Path(tmp) / "cfg2"
    (other / "projects" / "-dot-repo").mkdir(parents=True)
    (other / "projects" / "-dot-repo" / "s.jsonl").write_text(dumps(user(AUTO_PROMPT)) + "\n" + dumps(verdict([FINDING])) + "\n")
    rc, ctx, _ = run(other, r)
    check("a basename-only slug is not matched", ctx is None, f"ctx={ctx}")

# --- fail-open: every missing precondition is silence, never an error ------
with tempfile.TemporaryDirectory() as tmp:
    cfg = Path(tmp) / "cfg"
    r = repo(tmp, "app")
    rc, ctx, err = run(cfg, r)
    check("no projects directory at all is silence", rc == 0 and ctx is None and not err, f"exit={rc} err={err[:120]}")
    rc, ctx, err = run(cfg, Path(tmp) / "not-a-repo")
    check("a cwd outside any repository is silence", rc == 0 and ctx is None and not err, f"exit={rc} err={err[:120]}")
    rc, ctx, err = run(cfg, Path(tmp) / "does-not-exist")
    check("a cwd that does not exist is silence", rc == 0 and ctx is None and not err, f"exit={rc} err={err[:120]}")

# --- --print runs the same lookup without hook JSON ----------------------------
with tempfile.TemporaryDirectory() as tmp:
    cfg = Path(tmp) / "cfg"
    r = repo(tmp, "app")
    transcript(cfg, r, [user(AUTO_PROMPT), verdict([FINDING])])
    rc, out = run_print(cfg, r)
    check("--print prints the finding as plain text", rc == 0 and "src/auth.ts" in out and not out.startswith("{"), f"exit={rc} out={out[:120]}")
    rc, out = run_print(cfg, Path(tmp) / "not-a-repo")
    check("--print outside a repository prints nothing", rc == 0 and not out, f"exit={rc} out={out[:120]}")

# --- opt-out contract -------------------------------------------------------
# This hook warns rather than blocks, so the shared blocking cases do not apply;
# see _optout for why the drain case exists.
with tempfile.TemporaryDirectory() as tmp:
    cfg = Path(tmp) / "cfg"
    r = repo(tmp, "app")
    transcript(cfg, r, [user(AUTO_PROMPT), verdict([FINDING])])
    payload = json.dumps({"tool_name": "Bash", "cwd": str(r), "tool_input": {"command": "git commit -m x"}})
    os.environ["CLAUDE_CONFIG_DIR"] = str(cfg)
    try:
        _, hook_rc, out, err = _optout.run_piped(HOOK, DISABLE_VAR, payload, True)
        check("opt-out on: warning input stays silent", hook_rc == 0 and not out and not err, f"exit={hook_rc} stdout={out[:120]}")
        _, _, out, _ = _optout.run_piped(HOOK, DISABLE_VAR, payload, False)
        check("opt-out off: warning still fires", bool(out), f"stdout={out[:120]}")
    finally:
        del os.environ["CLAUDE_CONFIG_DIR"]

fails += _optout.drain(HOOK, DISABLE_VAR)

print("\nALL PASS" if not fails else f"\n{fails} FAILURES")
raise SystemExit(1 if fails else 0)
