#!/usr/bin/env python3
"""Prove security-review-findings.sh surfaces automatic review findings after a commit and stays silent otherwise.

The fixtures are transcript files laid out the way Claude Code writes them:
one JSONL per session under <config>/projects/<slug>/, where the slug is the
session's full cwd with every non-alphanumeric character dashed. CLAUDE_CONFIG_DIR points
the hook at a temporary tree so no real transcript is read.
"""

import json
import os
import re
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
    """The rule context-handoff/bin/session-to-md uses: every non-alphanumeric character becomes a dash.

    That is a JavaScript regex without the `u` flag, so a character outside the
    BMP is two UTF-16 code units and two dashes; Python's re works per code
    point and would give one.
    """
    return "".join(c if re.fullmatch(r"[A-Za-z0-9]", c) else "--" if ord(c) > 0xFFFF else "-" for c in str(path))


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


FINDING = {
    "filePath": "src/auth.ts",
    "category": "trust-boundary",
    "severity": "high",
    "confidence": "medium",
    "explanation": "Token is read from an unvalidated header.",
}


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
    check("severity and confidence come through", ctx is not None and "high/medium" in ctx, f"ctx={ctx}")

    # Global options between `git` and `commit` are consumed, so the subcommand
    # is identified by position rather than by the word appearing anywhere.
    for label, command in (
        ("git -C <this repo> commit is recognised as a commit", f"git -C {r} commit -F msg.txt"),
        ("git -c key=value commit is recognised", "git -c commit.gpgSign=false commit -m x"),
        ("git -ckey=value (attached) commit is recognised", "git -ccommit.gpgSign=false commit -m x"),
        ("git --no-pager commit is recognised", "git --no-pager commit -m x"),
        ("git --git-dir=<x> commit is recognised", f"git --git-dir={r}/.git commit -m x"),
        ("a commit after && is recognised", "git add a.txt && git commit -m x"),
        ("a commit after ; is recognised", "git add a.txt; git commit -m x"),
        ("a commit inside a subshell is recognised", "(git commit -m x)"),
        ("an environment-assignment prefix is skipped", "GIT_EDITOR=true git commit -m x"),
        ("two assignment prefixes are skipped", "A=1 B='x y' git commit -m x"),
        ("command git commit is recognised", "command git commit -m x"),
        ("an absolute git path is recognised", "/usr/bin/git commit -m x"),
        ("--exec-path=<dir> sets the path and the commit runs", "git --exec-path=/opt/git/libexec commit -m x"),
        # Control operators are cut after tokenising, so one inside a quoted
        # value before `commit` does not end the segment early.
        ("a quoted ; in a -C value does not cut the command", 'git -C "/tmp/a;b" commit -m x'),
        ("a quoted && in a -C value does not cut the command", "git -C '/tmp/a && b' commit -m x"),
        ("a quoted | in a -c value does not cut the command", 'git -c core.pager="less | cat" commit -m x'),
        ("a glued ;git commit is still cut at the operator", "echo x;git commit -m x"),
        ("a glued &&git commit is still cut at the operator", "git add a&&git commit -m x"),
        # A line continuation between git's options and the subcommand is one
        # logical line.
        ("a backslash-newline between -C and commit is joined", "git -C /tmp/repo \\\ncommit -m x"),
        # The first line of a heredoc-fed message ends inside a quote; the
        # tokens before it must still be read (xargs -n1, not a batched printf).
        ("a message fed through a heredoc in command substitution is recognised", 'git commit -m "$(cat <<\'EOF\'\ntitle\n\nbody; with && operators | inside\nEOF\n)"'),
        ("a multi-line quoted message is recognised", 'git commit -m "line one\nline two"'),
    ):
        rc, ctx, _ = run(cfg, r, command=command)
        check(label, ctx is not None, f"ctx={ctx}")

    for label, command in (
        ("git status is not a commit", "git status --porcelain"),
        ("git log is not a commit", "git log --oneline -3"),
        ("git log --grep commit is not a commit (the word is an argument)", "git log --grep commit"),
        ("git show HEAD -- commit.txt is not a commit", "git show HEAD -- commit.txt"),
        ("a non-git command is ignored", "ls -la"),
        ("gitk commit is not git commit", "gitk commit"),
        ("git commitx is not git commit", "git commitx"),
        ("an assignment alone is not a commit", "COMMIT=1"),
        ("git --version commit prints the version, not a commit", "git --version commit"),
        ("git --help commit prints help, not a commit", "git --help commit"),
        ("git -h commit prints usage, not a commit", "git -h commit"),
        ("git --html-path commit prints a path, not a commit", "git --html-path commit"),
        ("a bare --exec-path prints the path, not a commit", "git --exec-path commit"),
        ("a prefix in front of a non-git command is ignored", "GIT_DIR=x ls commit"),
    ):
        rc, ctx, _ = run(cfg, r, command=command)
        check(label, rc == 0 and ctx is None, f"exit={rc} ctx={ctx}")

# --- the SESSION selects the findings, never the commit's -C / cd / --git-dir --
# Claude Code stores the automatic reviews beside the session that made the
# edit, keyed by that session's cwd. A commit aimed elsewhere still belongs to
# this session's work, so its findings are the ones to surface.
with tempfile.TemporaryDirectory() as tmp:
    cfg = Path(tmp) / "cfg"
    session = repo(tmp, "session")
    other = repo(tmp, "other")
    transcript(cfg, session, [user(AUTO_PROMPT), verdict([FINDING])])
    transcript(cfg, other, [user(AUTO_PROMPT), verdict([dict(FINDING, filePath="other/only.ts")])])

    for label, command in (
        ("git -C <other repo> commit surfaces THIS session's findings", f"git -C {other} commit -m x"),
        ("a quoted -C path is consumed, not followed", f'git -C "{other}" commit -m x'),
        ("the attached -C<path> form is consumed, not followed", f"git -C{other} commit -m x"),
        ("cd <other> && git commit surfaces THIS session's findings", f"cd {other} && git commit -m x"),
        ("--git-dir/--work-tree are consumed, not followed", f"git --git-dir={other}/.git --work-tree={other} commit -m x"),
        ("a -C path that does not exist still counts as a commit", "git -C /no/such/dir commit -m x"),
        ("a -C path carrying an expansion still counts as a commit", "git -C $R commit -m x"),
    ):
        rc, ctx, _ = run(cfg, session, command=command)
        check(label, ctx is not None and "src/auth.ts" in ctx and "other/only.ts" not in ctx, f"ctx={ctx}")

# --- a session opened in a subdirectory is keyed by that subdirectory -----------
with tempfile.TemporaryDirectory() as tmp:
    cfg = Path(tmp) / "cfg"
    r = repo(tmp, "app")
    sub = r / "packages" / "web"
    sub.mkdir(parents=True)
    transcript(cfg, sub, [user(AUTO_PROMPT), verdict([FINDING])])
    rc, ctx, _ = run(cfg, sub)
    check("a session in /repo/subdir looks under -repo-subdir, not -repo", ctx is not None, f"ctx={ctx}")
    rc, ctx, _ = run(cfg, r)
    check("the repository root does not see the subdirectory session's findings", ctx is None, f"ctx={ctx}")

# --- a repository path with spaces maps to its slug -----------------------------
with tempfile.TemporaryDirectory() as tmp:
    cfg = Path(tmp) / "cfg"
    r = repo(tmp, "my repo (v2)")
    transcript(cfg, r, [user(AUTO_PROMPT), verdict([FINDING])])
    rc, ctx, _ = run(cfg, r)
    check("a path with spaces and parentheses maps to its slug", ctx is not None, f"ctx={ctx}")

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

# --- a command larger than the pipe buffer still counts ------------------------
# The pre-filter used to pipe the command into `grep -q`, which exits at the
# first match; on a multi-line command past the 64 KiB pipe buffer the printf
# behind it took SIGPIPE and pipefail turned a TRUE match into a silent exit.
with tempfile.TemporaryDirectory() as tmp:
    cfg = Path(tmp) / "cfg"
    r = repo(tmp, "app")
    transcript(cfg, r, [user(AUTO_PROMPT), verdict([FINDING])])
    big = "git commit -m x\n" + "echo padding line\n" * 12000  # ~200 KB
    rc, ctx, err = run(cfg, r, command=big)
    check("a 200 KB multi-line command with the commit on line 1 still reports", rc == 0 and ctx is not None and "src/auth.ts" in ctx, f"exit={rc} ctx={str(ctx)[:80]} err={err[:120]}")
    # Segments without `git` are skipped before tokenising: at ~8 ms per xargs
    # call, 12000 segments would otherwise hold the hook for a minute and a
    # half, past Claude Code's hook timeout.
    started = time.time()
    rc, ctx, err = run(cfg, r, command="echo padding line\n" * 12000 + "git commit -m x")
    elapsed = time.time() - started
    check("the same with the commit on the last line", rc == 0 and ctx is not None, f"exit={rc} err={err[:120]}")
    check("12000 git-less lines are skipped in well under the hook timeout", elapsed < 5, f"{elapsed:.1f}s")

# --- a huge report is capped and still delivered, never a hook error ---------
with tempfile.TemporaryDirectory() as tmp:
    cfg = Path(tmp) / "cfg"
    r = repo(tmp, "app")
    many = [dict(FINDING, filePath=f"src/f{i}.ts", explanation="x" * 300) for i in range(600)]
    transcript(cfg, r, [user(AUTO_PROMPT), verdict(many)])
    rc, ctx, err = run(cfg, r)
    check("600 findings do not error the hook", rc == 0 and not err, f"exit={rc} err={err[:120]}")
    check("600 findings are still delivered", ctx is not None and "src/f0.ts" in ctx, f"ctx={str(ctx)[:120]}")
    check("the report is capped with a pointer to --print", ctx is not None and "more line(s) not shown" in ctx and "--print" in ctx)
    check("the cap keeps the report under ARG_MAX territory", ctx is not None and len(ctx) < 100_000, f"len={len(ctx) if ctx else 0}")
    # --print is the full list the cap points at, so it is never cut.
    rc, out = run_print(cfg, r)
    check("--print delivers all 600 findings uncut", rc == 0 and "src/f599.ts" in out and "more line(s) not shown" not in out, f"exit={rc} len={len(out)}")

# --- the slug is per character, whatever the locale ------------------------------
# Claude Code dashes per character (JS replace); `tr -c` dashes per BYTE under
# a C locale, which would turn one Korean character into three dashes.
with tempfile.TemporaryDirectory() as tmp:
    cfg = Path(tmp) / "cfg"
    r = repo(tmp, "\ud504\ub85c\uc81d\ud2b8")  # 프로젝트
    transcript(cfg, r, [user(AUTO_PROMPT), verdict([FINDING])])
    check("the fixture slug has one dash per Korean character", slug(r).endswith("-" * 4), slug(r))
    rc, ctx, err = run(cfg, r, env_extra={"LC_ALL": "C", "LANG": "C"})
    check("a Korean cwd is found under LC_ALL=C", rc == 0 and ctx is not None, f"exit={rc} ctx={ctx} err={err[:120]}")
    rc, ctx, err = run(cfg, r, env_extra={"LC_ALL": "en_US.UTF-8"})
    check("a Korean cwd is found under a UTF-8 locale", rc == 0 and ctx is not None, f"exit={rc} ctx={ctx} err={err[:120]}")
    # An emoji is one code point but two UTF-16 code units, so Claude Code's
    # JavaScript rule writes two dashes for it.
    e = repo(tmp, "app-\U0001F600")
    transcript(cfg, e, [user(AUTO_PROMPT), verdict([FINDING])])
    check("the fixture slug has two dashes for an emoji", slug(e).endswith("app---"), slug(e))
    rc, ctx, err = run(cfg, e)
    check("an emoji in the cwd is found under the two-dash slug", rc == 0 and ctx is not None, f"exit={rc} ctx={ctx} err={err[:120]}")

# --- fail-open: every missing precondition is silence, never an error ------
with tempfile.TemporaryDirectory() as tmp:
    cfg = Path(tmp) / "cfg"
    r = repo(tmp, "app")
    rc, ctx, err = run(cfg, r)
    check("no projects directory at all is silence", rc == 0 and ctx is None and not err, f"exit={rc} err={err[:120]}")
    rc, ctx, err = run(cfg, Path(tmp) / "not-a-repo")
    check("a cwd with no session directory is silence (nothing asks whether it is a repository)", rc == 0 and ctx is None and not err, f"exit={rc} err={err[:120]}")
    rc, ctx, err = run(cfg, Path(tmp) / "does-not-exist")
    check("a cwd that does not exist has no session directory either: silence", rc == 0 and ctx is None and not err, f"exit={rc} err={err[:120]}")

# --- --print runs the same lookup without hook JSON ----------------------------
with tempfile.TemporaryDirectory() as tmp:
    cfg = Path(tmp) / "cfg"
    r = repo(tmp, "app")
    transcript(cfg, r, [user(AUTO_PROMPT), verdict([FINDING])])
    rc, out = run_print(cfg, r)
    check("--print prints the finding as plain text", rc == 0 and "src/auth.ts" in out and not out.startswith("{"), f"exit={rc} out={out[:120]}")
    rc, out = run_print(cfg, Path(tmp) / "not-a-repo")
    check("--print for a cwd with no session directory prints nothing", rc == 0 and not out, f"exit={rc} out={out[:120]}")
    # Claude Code keys projects/ by process.cwd(), the physical path, so a
    # symlinked or trailing-slash argument must land on the same slug.
    link = Path(tmp) / "app-link"
    link.symlink_to(r)
    rc, out = run_print(cfg, link)
    check("--print through a symlink resolves to the physical path's slug", rc == 0 and "src/auth.ts" in out, f"exit={rc} out={out[:120]}")
    rc, out = run_print(cfg, str(r) + "/")
    check("--print with a trailing slash finds the same slug", rc == 0 and "src/auth.ts" in out, f"exit={rc} out={out[:120]}")
    rc, out = run_print(cfg, Path(tmp) / "does-not-exist")
    check("--print for a path that does not exist prints nothing", rc == 0 and not out, f"exit={rc} out={out[:120]}")

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
