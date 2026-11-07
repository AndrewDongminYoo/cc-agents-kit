#!/usr/bin/env python3
"""Prove post-compact-retrieval.sh names the transcript after a compaction and stays silent otherwise."""

import json
import subprocess
import sys
from pathlib import Path

# The opt-out contract helper lives beside the guard-hooks suites; import it by
# path rather than carrying a copy (CONTRIBUTING §Adding a hook, step 5).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "guard-hooks" / "hooks"))
import _optout  # noqa: E402

HOOK = str(Path(__file__).resolve().with_name("post-compact-retrieval.sh"))
DISABLE_VAR = "CC_GUARD_DISABLE_POST_COMPACT_RETRIEVAL"
TRANSCRIPT = "/tmp/claude-test/transcript.jsonl"


def run(payload):
    proc = subprocess.run(
        ["/bin/bash", HOOK], input=payload, capture_output=True, text=True
    )
    return proc.returncode, proc.stdout, proc.stderr


def event(**extra):
    body = {
        "hook_event_name": "SessionStart",
        "session_id": "s-test",
        "source": "compact",
    }
    body.update(extra)
    return json.dumps(body)


fails = 0


def check(label, condition, detail=""):
    global fails
    fails += not condition
    print(f"{'ok  ' if condition else 'FAIL'}  {label}")
    if not condition and detail:
        print(f"       {detail}")


# --- the case the hook exists for ---
code, out, err = run(event(transcript_path=TRANSCRIPT))
check("compact with transcript_path: exit 0", code == 0, f"exit={code} err={err!r}")
check("compact with transcript_path: names the file", TRANSCRIPT in out, out)
check("compact with transcript_path: says to grep it", "grep" in out, out)
check(
    "compact with transcript_path: one line",
    out.count("\n") == 1 and out.endswith("\n"),
    repr(out),
)
check(
    "compact with transcript_path: under 300 characters",
    len(out) < 300,
    f"len={len(out)}",
)
check("compact with transcript_path: stderr empty", err == "", err)

# --- silent without a transcript path, or on bad input ---
for label, payload in (
    ("no transcript_path", event()),
    ("empty transcript_path", event(transcript_path="")),
    ("newline in transcript_path", event(transcript_path="/tmp/a\nb.jsonl")),
    ("empty stdin", ""),
    ("malformed JSON", "not json"),
):
    code, out, err = run(payload)
    check(
        f"{label}: exit 0 and silent",
        code == 0 and out == "" and err == "",
        f"exit={code} out={out!r} err={err!r}",
    )

# --- opt-out prints nothing and still drains a large payload ---
code, out, err = _optout.run_piped(
    HOOK, DISABLE_VAR, event(transcript_path=TRANSCRIPT), True
)[1:4]
check(
    "opt-out: exit 0 and silent",
    code == 0 and out == "" and err == "",
    f"exit={code} out={out!r}",
)
fails += _optout.drain(HOOK, DISABLE_VAR)

print(f"\n{'ALL PASSED' if not fails else f'{fails} FAILED'}")
sys.exit(1 if fails else 0)
