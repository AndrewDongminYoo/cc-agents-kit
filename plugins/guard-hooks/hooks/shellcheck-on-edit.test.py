#!/usr/bin/env python3
"""Prove shellcheck-on-edit.sh surfaces findings for shell scripts and stays quiet otherwise."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

HOOK = str(Path(__file__).resolve().with_name("shellcheck-on-edit.sh"))

DIRTY = "#!/usr/bin/env bash\nUNQUOTED=/tmp/a b\necho $UNQUOTED\n"
CLEAN = '#!/usr/bin/env bash\nset -euo pipefail\necho "hello"\n'


def run(file_path):
    """Return (exit_code, additionalContext or None)."""
    payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": file_path}})
    proc = subprocess.run(["bash", HOOK], input=payload, capture_output=True, text=True)
    out = proc.stdout.strip()
    if not out:
        return proc.returncode, None
    return proc.returncode, json.loads(out)["hookSpecificOutput"]["additionalContext"]


def write(tmp, name, body):
    p = Path(tmp) / name
    p.write_text(body)
    return str(p)


fails = 0


def check(label, condition, detail=""):
    global fails
    fails += not condition
    print(f"{'ok  ' if condition else 'FAIL'}  {label}")
    if not condition and detail:
        print(f"       {detail}")


# The hook exits 0 when no shellcheck binary is reachable, which would make
# every assertion below vacuously "quiet". Detect that and say so instead.
have_shellcheck = bool(
    shutil.which("shellcheck")
    or Path.home().joinpath(".claude/.trunk/tools/shellcheck").is_file()
    or Path("/opt/homebrew/bin/shellcheck").is_file()
)

with tempfile.TemporaryDirectory() as tmp:
    if not have_shellcheck:
        print("SKIP  no shellcheck binary reachable — findings cannot be exercised")
        code, ctx = run(write(tmp, "dirty.sh", DIRTY))
        check("degrades quietly without shellcheck", code == 0 and ctx is None,
              f"exit={code} ctx={ctx}")
    else:
        # --- a script with a finding: the case the hook exists for ---
        code, ctx = run(write(tmp, "dirty.sh", DIRTY))
        check("finding is surfaced", ctx is not None and "shellcheck" in ctx.lower(),
              f"ctx={ctx}")
        check("the finding text is included", ctx is not None and "SC2086" in ctx,
              f"ctx={ctx}")
        check("exit stays 0 (advisory, never blocks)", code == 0, f"exit={code}")

        # --- a clean script must not produce noise on every edit ---
        _, ctx = run(write(tmp, "clean.sh", CLEAN))
        check("clean script stays silent", ctx is None, f"ctx={ctx}")

        # --- .bash is also a shell script ---
        _, ctx = run(write(tmp, "dirty.bash", DIRTY))
        check(".bash extension is checked", ctx is not None, f"ctx={ctx}")

    # --- non-shell files are out of scope, even if they would not parse ---
    _, ctx = run(write(tmp, "notes.md", DIRTY))
    check("non-shell file ignored", ctx is None, f"ctx={ctx}")
    _, ctx = run(write(tmp, "script.py", DIRTY))
    check(".py ignored", ctx is None, f"ctx={ctx}")

# --- fail-open contract ---
for label, payload in (
    ("empty object", "{}"),
    ("nonexistent path", '{"tool_input": {"file_path": "/nope/x.sh"}}'),
    ("malformed", "not json at all"),
    ("empty stdin", ""),
):
    proc = subprocess.run(["bash", HOOK], input=payload, capture_output=True, text=True)
    check(
        f"fail-open: {label}",
        proc.returncode == 0 and not proc.stdout.strip(),
        f"exit={proc.returncode} stdout={proc.stdout.strip()[:120]}",
    )

print("\nALL PASS" if not fails else f"\n{fails} FAILURES")
raise SystemExit(1 if fails else 0)
