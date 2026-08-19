#!/usr/bin/env python3
"""Prove find-trunk-repos propagates GitHub authentication and listing failures."""

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
        "authentication failure",
        17,
        """#!/bin/bash
if [ "$1 $2" = "api user" ]; then exit 17; fi
exit 0
""",
    ),
    (
        "repository-list failure",
        23,
        """#!/bin/bash
if [ "$1 $2" = "api user" ]; then printf 'owner\\n'; exit 0; fi
if [ "$1 $2" = "repo list" ]; then exit 23; fi
exit 0
""",
    ),
)

failures = 0
for label, expected, fake_gh_body in SCENARIOS:
    with tempfile.TemporaryDirectory() as temp_dir:
        fake_gh = Path(temp_dir, "gh")
        fake_gh.write_text(fake_gh_body)
        fake_gh.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = f"{temp_dir}:{env['PATH']}"
        result = subprocess.run(
            ["/bin/bash", str(SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )
        passed = result.returncode == expected
        failures += not passed
        print(
            f"{'ok  ' if passed else 'FAIL'} {label}: "
            f"exit={result.returncode} want={expected}"
        )

print("\nALL PASS" if not failures else f"\n{failures} FAILURES")
raise SystemExit(1 if failures else 0)
