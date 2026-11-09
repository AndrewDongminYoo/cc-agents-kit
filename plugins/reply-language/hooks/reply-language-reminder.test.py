#!/usr/bin/env python3
"""Prove reply-language-reminder.sh adds the reader-defined language sentence and nothing else."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# The opt-out contract helper lives beside the guard-hooks suites; import it by
# path rather than carrying a copy (CONTRIBUTING §Adding a hook, step 5).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "guard-hooks" / "hooks"))
import _optout  # noqa: E402

HOOK = str(Path(__file__).resolve().with_name("reply-language-reminder.sh"))
DISABLE_VAR = "CC_GUARD_DISABLE_REPLY_LANGUAGE_REMINDER"
CONFIG = tempfile.mkdtemp(prefix="reply-language-config-")


def run(payload, language=None, config=CONFIG, project=None):
    # No real settings may leak in: an empty config dir and HOME, no inherited
    # project dir, and the language only from the case itself.
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("CC_") and k != "CLAUDE_PROJECT_DIR"
    }
    env.update(CLAUDE_CONFIG_DIR=config, HOME=config)
    if project is not None:
        env["CLAUDE_PROJECT_DIR"] = project
    if language is not None:
        env["CC_REPLY_LANGUAGE"] = language
    proc = subprocess.run(
        ["/bin/bash", HOOK], input=payload, capture_output=True, text=True, env=env
    )
    return proc.returncode, proc.stdout, proc.stderr


def event(name, **extra):
    body = {"hook_event_name": name, "session_id": "s-test", "cwd": CONFIG}
    body.update(extra)
    return json.dumps(body)


fails = 0


def check(label, condition, detail=""):
    global fails
    fails += not condition
    print(f"{'ok  ' if condition else 'FAIL'}  {label}")
    if not condition and detail:
        print(f"       {detail}")


def context(out):
    try:
        return json.loads(out)["hookSpecificOutput"]
    except (ValueError, KeyError, TypeError):
        return {}


# --- the cases the hook exists for ---
for name in ("UserPromptSubmit", "PostToolUse"):
    code, out, err = run(event(name, tool_name="Agent"), "Korean")
    ctx = context(out)
    check(f"{name}: exit 0", code == 0, f"exit={code} err={err!r}")
    check(f"{name}: names its event", ctx.get("hookEventName") == name, out)
    check(
        f"{name}: Korean sentence defined by who reads it",
        "사용자가 읽는 텍스트" in ctx.get("additionalContext", "")
        and "사용자가 아닌 독자" in ctx.get("additionalContext", ""),
        out,
    )

code, out, _ = run(event("PostToolUse", tool_name="SendMessage"), "Korean")
check("PostToolUse SendMessage: full sentence", "사용자가 아닌 독자" in out, out)

for tool in ("Bash", "Read", None):
    code, out, err = run(event("PostToolUse", tool_name=tool), "Korean")
    ctx = context(out).get("additionalContext", "")
    check(
        f"PostToolUse {tool}: the short line only",
        code == 0 and ctx == "사용자에게 보이는 다음 텍스트는 한국어로 씁니다.",
        f"exit={code} out={out!r} err={err!r}",
    )

code, out, _ = run(event("PostToolUse", tool_name="Bash"), "Russian")
check(
    "PostToolUse Bash, Russian: English short line names the language",
    context(out).get("additionalContext")
    == "The next text the user sees is written in Russian.",
    out,
)

code, out, _ = run(event("UserPromptSubmit"), "ja-JP")
check("region code ja-JP: Japanese sentence", "ユーザーが読むテキスト" in out, out)

code, out, _ = run(event("UserPromptSubmit"), "Russian")
check(
    "Russian, no template: English sentence names the language",
    "written in Russian" in context(out).get("additionalContext", ""),
    out,
)

# --- the language comes from the settings chain when no override is set ---
with tempfile.TemporaryDirectory() as config, tempfile.TemporaryDirectory() as project:
    Path(config, "settings.json").write_text(json.dumps({"language": "한국어"}))
    code, out, _ = run(event("UserPromptSubmit", cwd=project), config=config)
    check("user settings 한국어: Korean sentence", "사용자가 읽는 텍스트" in out, out)
    Path(project, ".claude").mkdir()
    Path(project, ".claude", "settings.local.json").write_text(
        json.dumps({"language": "Japanese"})
    )
    code, out, _ = run(event("UserPromptSubmit", cwd=project), config=config)
    check("project local settings override user settings", "ユーザー" in out, out)
    subdir = Path(project, "src")
    subdir.mkdir()
    code, out, _ = run(
        event("UserPromptSubmit", cwd=str(subdir)), config=config, project=project
    )
    check(
        "after a cd into a subdirectory, CLAUDE_PROJECT_DIR still finds the project settings",
        "ユーザー" in out,
        out,
    )

# --- silent cases ---
for label, payload, language in (
    ("no language configured", event("UserPromptSubmit"), None),
    ("Latin-script language is unsupported", event("UserPromptSubmit"), "French"),
    ("Stop is not a reminder event", event("Stop"), "Korean"),
    ("empty input", "", "Korean"),
    ("malformed input", "{not json", "Korean"),
    ("JSON that is not an object", "[1, 2]", "Korean"),
):
    code, out, err = run(payload, language)
    check(
        f"{label}: exit 0 and silent",
        code == 0 and out == "" and err == "",
        f"exit={code} out={out!r} err={err!r}",
    )

# --- opt-out prints nothing and still drains a large payload ---
code, out, err = _optout.run_piped(HOOK, DISABLE_VAR, event("UserPromptSubmit"), True)[
    1:4
]
check(
    "opt-out: exit 0 and silent",
    code == 0 and out == "" and err == "",
    f"exit={code} out={out!r}",
)
fails += _optout.drain(HOOK, DISABLE_VAR)

print(f"\n{'ALL PASSED' if not fails else f'{fails} FAILED'}")
sys.exit(1 if fails else 0)
