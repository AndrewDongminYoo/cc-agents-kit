#!/usr/bin/env python3
"""Prove session-to-md renders safe sessions and rejects unsafe output requests."""

import os
import subprocess
import tempfile
from pathlib import Path

SCRIPT = Path(
    os.environ.get(
        "SESSION_TO_MD_UNDER_TEST",
        Path(__file__).resolve().with_name("session-to-md"),
    )
)


def run(arguments, temp_dir):
    transcript = Path(temp_dir, "session.jsonl")
    transcript.write_text(
        '{"type":"user","timestamp":"2026-08-27T00:00:00.000Z","message":{"content":"hello"}}\n'
    )
    return subprocess.run(
        ["node", str(SCRIPT), str(transcript), *arguments],
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_CONFIG_DIR": temp_dir, "HOME": temp_dir},
    )


def fails(label, arguments, required_text=None):
    with tempfile.TemporaryDirectory() as temp_dir:
        result = run(arguments, temp_dir)
        output = result.stdout + result.stderr
        passed = result.returncode != 0 and (
            required_text is None or required_text in output
        )
        print(f"{'ok  ' if passed else 'FAIL'} {label}: exit={result.returncode}")
        return not passed


failures = 0
for label, arguments, required_text in (
    ("rejects a suffixed --last value", ["--last", "1x"], "--last"),
    ("rejects a zero --last value", ["--last", "0"], "--last"),
    ("rejects an unsupported --tools value", ["--tools", "summary"], "--tools"),
    ("rejects multiple session identifiers", ["other-session"], "session identifier"),
):
    failures += fails(label, arguments, required_text)

with tempfile.TemporaryDirectory() as temp_dir:
    output = Path(temp_dir, "rendered-session.md")
    result = run(["--out", str(output)], temp_dir)
    rendered = output.read_text() if output.is_file() else ""
    passed = (
        result.returncode == 0
        and result.stdout == f"{output}\n"
        and "# hello" in rendered
        and "## 👤 User" in rendered
        and "hello" in rendered
    )
    print(f"{'ok  ' if passed else 'FAIL'} renders a session to the exact output path: exit={result.returncode}")
    failures += not passed

with tempfile.TemporaryDirectory() as temp_dir:
    output = Path(temp_dir, "existing.md")
    original = b"do not replace\x00this"
    output.write_bytes(original)
    result = run(["--out", str(output)], temp_dir)
    passed = result.returncode != 0 and output.read_bytes() == original
    print(
        f"{'ok  ' if passed else 'FAIL'} preserves an existing output file: "
        f"exit={result.returncode}"
    )
    failures += not passed

with tempfile.TemporaryDirectory() as temp_dir:
    output = Path(temp_dir, "missing", "output.md")
    result = run(["--out", str(output)], temp_dir)
    lines = [line for line in (result.stdout + result.stderr).splitlines() if line]
    passed = result.returncode != 0 and len(lines) == 1 and "Error" not in lines[0]
    print(
        f"{'ok  ' if passed else 'FAIL'} reports a write failure without a stack trace: "
        f"exit={result.returncode}"
    )
    failures += not passed

print("\nALL PASS" if not failures else f"\n{failures} FAILURES")
raise SystemExit(1 if failures else 0)
