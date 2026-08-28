#!/usr/bin/env python3
"""Prove find-trunk-repos emits exact results and handles API failures explicitly."""

import os
import subprocess
import tempfile
from pathlib import Path

SCRIPT = Path(
    os.environ.get(
        "FIND_TRUNK_REPOS_UNDER_TEST",
        Path(__file__).resolve().with_name("find-trunk-repos"),
    )
)

SCENARIOS = (
    (
        "content success emits exact TSV",
        0,
        "success",
        "owner/repo\tmain\thttps://github.com/owner/repo/blob/main/.trunk/trunk.yaml\n",
        "",
    ),
    ("authentication failure", 17, None, "", ""),
    ("repository-list failure", 23, None, "", ""),
    ("content 404 is absent", 0, 404, "", ""),
    ("content 403 names the repository", 29, 403, "", "owner/repo"),
    (
        "content failure that mentions HTTP 404 names the repository",
        31,
        "misleading-404",
        "",
        "owner/repo",
    ),
)


def fake_gh_body():
    return """#!/bin/bash
if [ "$1 $2" = "api user" ]; then
  if [ "${TEST_SCENARIO}" = "authentication failure" ]; then exit 17; fi
  printf 'owner\\n'
  exit 0
fi
if [ "$1 $2" = "repo list" ]; then
  if [ "${TEST_SCENARIO}" = "repository-list failure" ]; then exit 23; fi
  printf 'owner/repo\\tmain\\n'
  exit 0
fi
if [ "$1" = "api" ]; then
  if [ "${TEST_CONTENT_STATUS}" = "404" ]; then
    printf 'gh: Not Found (HTTP 404)\\n' >&2
    exit 1
  fi
  if [ "${TEST_CONTENT_STATUS}" = "403" ]; then
    printf 'gh: Forbidden (HTTP 403)\\n' >&2
    exit 29
  fi
  if [ "${TEST_CONTENT_STATUS}" = "misleading-404" ]; then
    printf 'gh: request failed after an unrelated HTTP 404 cache record\\n' >&2
    exit 31
  fi
  printf 'https://github.com/owner/repo/blob/main/.trunk/trunk.yaml\\n'
  exit 0
fi
exit 1
"""

failures = 0
for label, expected, content_status, expected_stdout, required_stderr in SCENARIOS:
    with tempfile.TemporaryDirectory() as temp_dir:
        fake_gh = Path(temp_dir, "gh")
        fake_gh.write_text(fake_gh_body())
        fake_gh.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = f"{temp_dir}:{env['PATH']}"
        env["TEST_SCENARIO"] = label
        if content_status is not None:
            env["TEST_CONTENT_STATUS"] = str(content_status)
        result = subprocess.run(
            ["/bin/bash", str(SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )
        passed = (
            result.returncode == expected
            and result.stdout == expected_stdout
            and required_stderr in result.stderr
        )
        failures += not passed
        print(
            f"{'ok  ' if passed else 'FAIL'} {label}: "
            f"exit={result.returncode} want={expected}"
        )

print("\nALL PASS" if not failures else f"\n{failures} FAILURES")
raise SystemExit(1 if failures else 0)
