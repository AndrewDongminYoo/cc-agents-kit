#!/usr/bin/env python3
"""Prove compaction-brief.sh prints the brief on every compaction and nothing when disabled."""

import json
import subprocess
import sys
from pathlib import Path

# The opt-out contract helper lives beside the guard-hooks suites; import it by
# path rather than carrying a copy (CONTRIBUTING §Adding a hook, step 5).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "guard-hooks" / "hooks"))
import _optout  # noqa: E402

HOOK = str(Path(__file__).resolve().with_name("compaction-brief.sh"))
DISABLE_VAR = "CC_GUARD_DISABLE_COMPACTION_BRIEF"

HEADINGS = (
    "- Task:",
    "- Done when:",
    "- User constraints:",
    "- Persistent state:",
    "- Objective:",
    "- Established facts:",
    "- Applied changes:",
    "- Verification:",
    "- Dead ends:",
    "- Remaining plan:",
    "- Retrieval:",
    "- External status:",
)
CLOSING = "Re-read any status above from its named source before acting on it; treat a status with no named source as unverified."
TRANSCRIPT = "/tmp/claude-test/transcript.jsonl"


def run(payload):
    """Return (exit_code, stdout, stderr) for a raw stdin payload."""
    proc = subprocess.run(
        ["/bin/bash", HOOK], input=payload, capture_output=True, text=True
    )
    return proc.returncode, proc.stdout, proc.stderr


def event(trigger, **extra):
    body = {
        "hook_event_name": "PreCompact",
        "session_id": "s-test",
        "trigger": trigger,
        "custom_instructions": None,
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


def brief_ok(out):
    return all(h in out for h in HEADINGS) and CLOSING in out


# --- the case the hook exists for: an auto-compact gets the brief ---
code, out, err = run(event("auto", transcript_path=TRANSCRIPT))
check("auto: exit 0", code == 0, f"exit={code} err={err!r}")
check("auto: all twelve headings and the closing line", brief_ok(out), out)
check("auto: transcript path named", TRANSCRIPT in out, out)
check(
    "auto: no decision, no systemMessage",
    "decision" not in out and "systemMessage" not in out,
)
check("auto: stderr empty", err == "", err)
check("auto: under 4000 characters", len(out) < 4000, f"len={len(out)}")

# --- manual /compact with custom instructions still gets the brief ---
code, out, _ = run(
    event(
        "manual", custom_instructions="focus on the tests", transcript_path=TRANSCRIPT
    )
)
check("manual with custom_instructions: exit 0", code == 0, f"exit={code}")
check("manual with custom_instructions: brief printed", brief_ok(out), out)
check("manual: custom text not echoed", "focus on the tests" not in out)

# --- no transcript path: brief still valid, generic persistent-state line ---
code, out, _ = run(event("auto"))
check("no transcript_path: exit 0", code == 0, f"exit={code}")
check("no transcript_path: brief printed", brief_ok(out), out)
check(
    "no transcript_path: says the transcript stays on disk", "stays on disk" in out, out
)
check("no transcript_path: no empty 'at:' line", "on disk at: " not in out, out)

# --- a transcript path carrying a line break is dropped, not printed ---
code, out, _ = run(event("auto", transcript_path="/tmp/a\nb.jsonl"))
check("newline in transcript_path: exit 0", code == 0, f"exit={code}")
check(
    "newline in transcript_path: path dropped",
    "/tmp/a" not in out and brief_ok(out),
    out,
)

# --- fail open: empty and malformed input still print the brief ---
for label, payload in (
    ("empty stdin", ""),
    ("malformed JSON", "not json"),
    ("key-less object", "{}"),
):
    code, out, err = run(payload)
    check(f"{label}: exit 0", code == 0, f"exit={code} err={err!r}")
    check(f"{label}: brief printed", brief_ok(out), out)

# --- opt-out prints nothing and still drains a large payload ---
code, out, err = _optout.run_piped(
    HOOK, DISABLE_VAR, event("auto", transcript_path=TRANSCRIPT), True
)[1:4]
check(
    "opt-out: exit 0 and silent",
    code == 0 and out == "" and err == "",
    f"exit={code} out={out!r}",
)
fails += _optout.drain(HOOK, DISABLE_VAR)

print(f"\n{'ALL PASSED' if not fails else f'{fails} FAILED'}")
sys.exit(1 if fails else 0)
