#!/usr/bin/env python3
"""Prove reply-language-check.sh asks for a restatement only when a turn drifted out of the reply language."""

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

HOOK = str(Path(__file__).resolve().with_name("reply-language-check.sh"))
DISABLE_VAR = "CC_GUARD_DISABLE_REPLY_LANGUAGE_CHECK"
WORK = tempfile.mkdtemp(prefix="reply-language-check-")

KO_ASK = "문서 사이트를 최신 릴리스에 맞게 갱신해 주세요."
KO_REPLY = "문서 사이트를 v0.9.0에 맞게 갱신했습니다. 버전과 훅 목록을 고쳤고, 전체 검사를 통과했습니다."
EN_REPLY = "I updated the documentation site to v0.9.0. The version and the hook list are fixed, and the full check passed."
EN_STATUS = "Now I'll read the failing CI log and check which tool did not install on the runner."


def human(text, entrypoint="cli"):
    return {
        "type": "user",
        "origin": {"kind": "human"},
        "entrypoint": entrypoint,
        "message": {"role": "user", "content": text},
    }


def queued(text):
    return {
        "type": "attachment",
        "attachment": {
            "type": "queued_command",
            "prompt": text,
            "origin": {"kind": "human"},
        },
    }


def say(text, sidechain=False, entrypoint="cli"):
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "entrypoint": entrypoint,
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


def notification(
    text="<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n</task-notification>",
):
    return {
        "type": "user",
        "origin": {"kind": "task-notification"},
        "message": {"role": "user", "content": text},
    }


def tool_round():
    return [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}
                ]
            },
        },
    ]


def transcript(entries):
    fd, path = tempfile.mkstemp(suffix=".jsonl", dir=WORK)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def run(entries=None, language="Korean", raw=None, models=None, **extra):
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("CC_") and k != "CLAUDE_PROJECT_DIR"
    }
    env.update(CLAUDE_CONFIG_DIR=WORK, HOME=WORK)
    if models is not None:
        env["CC_REPLY_LANGUAGE_MODELS"] = models
    if language is not None:
        env["CC_REPLY_LANGUAGE"] = language
    if raw is None:
        body = {
            "hook_event_name": "Stop",
            "session_id": "s-test",
            "cwd": WORK,
            "stop_hook_active": False,
        }
        if entries is not None:
            body["transcript_path"] = transcript(entries)
        body.update(extra)
        raw = json.dumps(body)
    proc = subprocess.run(
        ["/bin/bash", HOOK], input=raw, capture_output=True, text=True, env=env
    )
    return proc.returncode, proc.stdout, proc.stderr


fails = 0


def check(label, condition, detail=""):
    global fails
    fails += not condition
    print(f"{'ok  ' if condition else 'FAIL'}  {label}")
    if not condition and detail:
        print(f"       {detail}")


def blocks(label, entries, expect="한국어로 다시 써서", **kw):
    code, out, err = run(entries, **kw)
    try:
        decision = json.loads(out)
    except ValueError:
        decision = {}
    check(f"{label}: exit 0", code == 0, f"exit={code} err={err!r}")
    check(
        f"{label}: blocks once with a reason in the target language",
        decision.get("decision") == "block" and expect in decision.get("reason", ""),
        repr(out),
    )


def silent(label, entries=None, **kw):
    code, out, err = run(entries, **kw)
    check(
        f"{label}: exit 0 and silent",
        code == 0 and out == "" and err == "",
        f"exit={code} out={out!r} err={err!r}",
    )


# --- the cases the hook exists for ---
blocks("English final answer", [human(KO_ASK), *tool_round(), say(EN_REPLY)])
blocks(
    "English status lines, then an English answer",
    [human(KO_ASK), say(EN_STATUS), *tool_round(), say(EN_REPLY)],
)
blocks(
    "Korean status line, English final answer",
    [human(KO_ASK), say(KO_REPLY), *tool_round(), say(EN_REPLY)],
)
blocks(
    "slash command: the English command name is not the user's language",
    [
        human(
            "<command-message>log-it</command-message>\n<command-name>/context-handoff:log-it</command-name>"
        ),
        say(EN_REPLY),
    ],
)
blocks(
    "pasted English log: the paste is not the user's language",
    [
        human('<pasted_content id="1">' + EN_STATUS * 3 + "</pasted_content>"),
        say(EN_REPLY),
    ],
)
blocks(
    "Japanese target, English answer",
    [human("ドキュメントを更新してください。"), say(EN_REPLY)],
    expect="日本語で書き直して",
    language="Japanese",
)
blocks(
    "Russian target, no template: English reason names the language",
    [human("Пожалуйста, обновите сайт документации."), say(EN_REPLY)],
    expect="restate it in Russian",
    language="Russian",
)

# --- turns that pass ---
silent(
    "Korean answer",
    [human(KO_ASK), say(EN_STATUS), *tool_round(), say(KO_REPLY), say(KO_REPLY)],
)
silent(
    "Korean answer around an English code block",
    [human(KO_ASK), say(KO_REPLY + "\n\n```bash\n" + EN_REPLY * 4 + "\n```\n")],
)
silent(
    "Korean answer naming English paths, URLs and inline code",
    [
        human(KO_ASK),
        say(
            KO_REPLY
            + " `plugins/reply-language/hooks/hooks.json` https://example.com/a/b /Users/you/x.md"
        ),
    ],
)
silent("short English line", [human(KO_ASK), say("Done.")])
silent(
    "user wrote in English",
    [
        human("Please update the documentation site to the latest release."),
        say(EN_REPLY),
    ],
)
silent(
    "English before a mid-turn Korean message, Korean after it",
    [human(KO_ASK), say(EN_REPLY), queued("한국어로 답해 주세요."), say(KO_REPLY)],
)
silent(
    "an earlier turn's English, already restated, is not judged again at a notification's stop",
    [human(KO_ASK), say(EN_REPLY * 3), say(KO_REPLY), notification(), say(KO_REPLY)],
)
blocks(
    "English written after a notification, in a turn the user did not open",
    [human(KO_ASK), say(KO_REPLY), notification(), say(EN_REPLY)],
)
silent(
    "user wrote in English, then a notification opened the turn",
    [
        human("Please update the documentation site to the latest release."),
        notification(),
        say(EN_REPLY),
    ],
)
api_error = say(
    "API Error: Your computer went to sleep mid-response. The response above may be incomplete. "
    * 2
)
api_error["isApiErrorMessage"] = True
silent(
    "a harness API error rendered as an assistant message",
    [human(KO_ASK), say(KO_REPLY), api_error],
)
# --- the 30% boundary, on one block of exactly 100 counted letters ---
blocks("29% target script blocks", [human(KO_ASK), say("가" * 29 + " " + "a" * 71)])
silent("30% target script passes", [human(KO_ASK), say("가" * 30 + " " + "a" * 70)])

silent(
    "a four-backtick fence hides the three-backtick example inside it",
    [
        human(KO_ASK),
        say(KO_REPLY + "\n\n````markdown\n```text\n" + EN_REPLY * 4 + "\n```\n````\n"),
    ],
)

silent(
    "a backtick string inside code does not close the fence",
    [
        human(KO_ASK),
        say(
            KO_REPLY
            + '\n\n```python\nmarker = "```"\n'
            + ("# " + EN_REPLY + "\n") * 4
            + "```\n"
        ),
    ],
)

legacy_image_prompt = {
    "type": "user",
    "message": {
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": ""},
            },
            {
                "type": "text",
                "text": "이 화면에서 버튼 정렬이 어긋난 이유를 한국어로 설명해 주세요",
            },
        ],
    },
}
legacy_english = {
    "type": "user",
    "message": {"role": "user", "content": "Please update the documentation site."},
}
legacy_command = {
    "type": "user",
    "message": {
        "role": "user",
        "content": (
            "<command-name>/review</command-name>\n<command-args>한국어로 문서 사이트 변경을 검토해 주세요</command-args>"
        ),
    },
}
blocks(
    "an origin-less slash command is the user's latest message",
    [legacy_english, say(KO_REPLY), legacy_command, say(EN_REPLY)],
)
blocks(
    "an origin-less prompt sent with an image is the user's latest message",
    [legacy_english, say(KO_REPLY), legacy_image_prompt, say(EN_REPLY)],
)
blocks(
    "a session resumed from the SDK into the CLI is checked",
    [
        human(KO_ASK, "sdk-cli"),
        say(KO_REPLY, entrypoint="sdk-cli"),
        human(KO_ASK),
        say(EN_REPLY),
    ],
)

sidechain_brief = human(
    "Survey the repository and report every hook script with its event in English."
)
sidechain_brief["isSidechain"] = True
blocks(
    "a subagent's English brief is neither the user's message nor a turn boundary",
    [human(KO_ASK), sidechain_brief, say(EN_REPLY)],
)
silent(
    "subagent (sidechain) English is not shown to the user",
    [human(KO_ASK), say(EN_REPLY * 3, sidechain=True), say(KO_REPLY)],
)
silent(
    "stop_hook_active: one rewrite per stop",
    [human(KO_ASK), say(EN_REPLY)],
    stop_hook_active=True,
)
silent(
    "headless sdk run", [human(KO_ASK, "sdk-cli"), say(EN_REPLY, entrypoint="sdk-cli")]
)
silent("no language configured", [human(KO_ASK), say(EN_REPLY)], language=None)
silent(
    "Latin-script language is unsupported",
    [human(KO_ASK), say(EN_REPLY)],
    language="French",
)
silent("no transcript_path", None)
silent(
    "transcript_path that does not exist",
    None,
    transcript_path=str(Path(WORK, "missing.jsonl")),
)
silent("empty input", raw="")
silent("malformed input", raw="{not json")

# --- opt-out prints nothing and still drains a large payload ---
code, out, err = _optout.run_piped(
    HOOK, DISABLE_VAR, json.dumps({"hook_event_name": "Stop"}), True
)[1:4]
check(
    "opt-out: exit 0 and silent",
    code == 0 and out == "" and err == "",
    f"exit={code} out={out!r}",
)
fails += _optout.drain(HOOK, DISABLE_VAR)


# --- CC_REPLY_LANGUAGE_MODELS limits the check to the named models ---
def say_as(model, text):
    entry = say(text)
    entry["message"]["model"] = model
    return entry


blocks(
    "model scope: an English answer from a named model",
    [human(KO_ASK), say_as("claude-opus-5-5", EN_REPLY)],
    models="opus-5-5",
)
silent(
    "model scope: an English answer from another model",
    [human(KO_ASK), say_as("claude-fable-5-2", EN_REPLY)],
    models="opus-5-5",
)
blocks(
    "model scope: a transcript without a model is still checked",
    [human(KO_ASK), say(EN_REPLY)],
    models="opus-5-5",
)

print(f"\n{'ALL PASSED' if not fails else f'{fails} FAILED'}")
sys.exit(1 if fails else 0)
