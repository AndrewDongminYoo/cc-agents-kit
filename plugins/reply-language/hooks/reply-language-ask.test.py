#!/usr/bin/env python3
"""Prove reply-language-ask.sh refuses an AskUserQuestion call only when the question shown to the user drifted out of the reply language."""

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

HOOK = str(Path(__file__).resolve().with_name("reply-language-ask.sh"))
DISABLE_VAR = "CC_GUARD_DISABLE_REPLY_LANGUAGE_ASK"
WORK = tempfile.mkdtemp(prefix="reply-language-ask-")

KO_ASK = "문서 사이트를 최신 릴리스에 맞게 갱신해 주세요."
EN_ASK = "Please update the documentation site to the latest release."


def question(text, header, options, preview=None):
    opts = []
    for label, description in options:
        opt = {"label": label, "description": description}
        if preview is not None:
            opt["preview"] = preview
        opts.append(opt)
    return {
        "question": text,
        "header": header,
        "options": opts,
        "multiSelect": False,
    }


# The shape that reached the user on 2026-11-15: English sentences around
# Korean issue titles in corner brackets.
EN_QUESTION = question(
    "Can I register the auto-deploy CI issues this way? Proposal: parent 「자동 배포 CI 도입」 "
    "with three children. ① 「자동 배포의 신뢰 모델과 트리거 결정」: whether GitHub Actions may "
    "hold the SSH key and the Basic Auth password; the trigger (main merge or manual approval). "
    "② 「배포용 GitHub 환경과 비밀 등록」, blocked by ①. ③ 「README 배포 트랜잭션을 워크플로로 구현」, "
    "blocked by ① and ②.",
    "Issues",
    [
        (
            "Register as proposed (Recommended)",
            "Create the parent and the three children.",
        ),
        ("Single issue", "Create one issue that holds all three steps."),
        ("Decision issue only", "Create only the trust-model decision issue for now."),
    ],
)
KO_QUESTION = question(
    "자동 배포 CI 이슈를 이렇게 등록해도 될까요? 상위 이슈 하나와 하위 이슈 세 개로 나누고, "
    "`ops/README.md`의 배포 절차를 기준으로 삼겠습니다.",
    "이슈 구성",
    [
        ("제안대로 등록 (권장)", "상위 이슈와 하위 이슈 세 개를 만듭니다."),
        ("이슈 하나로 등록", "세 단계를 이슈 하나에 모두 담습니다."),
    ],
)
# English option labels are fine when the question itself is Korean.
KO_QUESTION_EN_LABELS = question(
    "어떤 라이브러리로 날짜를 다룰지 정해 주세요. 지금 코드는 두 군데에서 서로 다른 방식으로 날짜를 계산하고 있어서 하나로 맞추려고 합니다.",
    "날짜 처리",
    [
        ("date-fns", "가볍고 함수 단위로 가져옵니다."),
        ("Luxon", "시간대 처리가 풍부합니다."),
    ],
)
# An English preview is a mockup or code; only the question text is judged.
KO_QUESTION_EN_PREVIEW = question(
    "설정 화면의 배치를 둘 중에서 골라 주세요. 두 안 모두 기존 컴포넌트를 그대로 씁니다.",
    "화면 배치",
    [("왼쪽 탭", "탭을 세로로 둡니다."), ("위쪽 탭", "탭을 가로로 둡니다.")],
    preview="Settings | Account | Privacy | Notifications | About this application "
    * 4,
)
# A Korean approval question whose table lists English issue titles as they
# will be published (2026-11-15 replay of past calls).
TITLE_ROWS = "\n".join(
    f"| {c} | Add an option that sorts only within blank-line-separated groups | code | linux |"
    for c in "ABCDEFGHI"
)
KO_QUESTION_EN_TABLE = question(
    "아래 구성으로 GitHub Issues에 등록할까요?\n\n| 카드 | title | kind | env |\n|---|---|---|---|\n"
    + TITLE_ROWS
    + "\n\n보조 라벨로 `enhancement`를 함께 붙입니다.",
    "이슈 등록",
    [
        ("이대로 등록 (권장)", "라벨을 만들고 상위 이슈부터 차례로 등록합니다."),
        ("수정 후 등록", "고칠 부분을 알려주시면 반영한 뒤 등록합니다."),
    ],
)
# The table rule must not hide an English question that has no table.
EN_QUESTION_WITH_TABLE = question(
    EN_QUESTION["question"] + "\n\n| card | title |\n|---|---|\n| A | 자동 배포 |",
    "Issues",
    [(o["label"], o["description"]) for o in EN_QUESTION["options"]],
)


def human(text, entrypoint="cli"):
    return {
        "type": "user",
        "origin": {"kind": "human"},
        "entrypoint": entrypoint,
        "message": {"role": "user", "content": text},
    }


def say_as(model, text):
    return {
        "type": "assistant",
        "entrypoint": "cli",
        "message": {
            "role": "assistant",
            "model": model,
            "content": [{"type": "text", "text": text}],
        },
    }


def transcript(entries):
    fd, path = tempfile.mkstemp(suffix=".jsonl", dir=WORK)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def payload(questions, tool_name="AskUserQuestion", entries=None, **extra):
    body = {
        "hook_event_name": "PreToolUse",
        "session_id": "s-test",
        "cwd": WORK,
        "tool_name": tool_name,
        "tool_input": {"questions": questions},
    }
    if entries is not None:
        body["transcript_path"] = transcript(entries)
    body.update(extra)
    return json.dumps(body, ensure_ascii=False)


def run(raw, language="Korean", models=None):
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("CC_") and k != "CLAUDE_PROJECT_DIR"
    }
    env.update(CLAUDE_CONFIG_DIR=WORK, HOME=WORK)
    if language is not None:
        env["CC_REPLY_LANGUAGE"] = language
    if models is not None:
        env["CC_REPLY_LANGUAGE_MODELS"] = models
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


def refuses(label, raw, expect="한국어로 다시 써서", **kw):
    code, out, err = run(raw, **kw)
    check(
        f"{label}: exits 2 with a reason in the target language",
        code == 2 and out == "" and expect in err,
        f"exit={code} out={out!r} err={err!r}",
    )


def passes(label, raw, **kw):
    code, out, err = run(raw, **kw)
    check(
        f"{label}: exit 0 and silent",
        code == 0 and out == "" and err == "",
        f"exit={code} out={out!r} err={err!r}",
    )


# --- the case the hook exists for ---
refuses("English question around Korean titles", payload([EN_QUESTION]))
refuses(
    "English question after a Korean prompt",
    payload([EN_QUESTION], entries=[human(KO_ASK)]),
)
refuses(
    "one English question among Korean ones",
    payload([KO_QUESTION, EN_QUESTION]),
)
refuses(
    "Japanese target, English question",
    payload([EN_QUESTION]),
    expect="日本語で書き直して",
    language="Japanese",
)
refuses(
    "Russian target, no template: English reason names the language",
    payload([EN_QUESTION]),
    expect="written in Russian",
    language="Russian",
)

# --- calls that pass ---
passes("Korean question", payload([KO_QUESTION]))
passes("Korean question with English option labels", payload([KO_QUESTION_EN_LABELS]))
passes("an English preview is not judged", payload([KO_QUESTION_EN_PREVIEW]))
passes(
    "a table of English titles under a Korean question",
    payload([KO_QUESTION_EN_TABLE]),
)
refuses(
    "an English question beside a Korean table",
    payload([EN_QUESTION_WITH_TABLE]),
)
passes(
    "short English question",
    payload([question("Proceed?", "Go", [("Yes", ""), ("No", "")])]),
)
passes("another tool", payload([EN_QUESTION], tool_name="Bash"))
passes(
    "user wrote in English",
    payload([EN_QUESTION], entries=[human(EN_ASK)]),
)
passes(
    "headless sdk run",
    payload([EN_QUESTION], entries=[human(KO_ASK, "sdk-cli")]),
)
passes("no language configured", payload([EN_QUESTION]), language=None)
passes(
    "Latin-script language is unsupported", payload([EN_QUESTION]), language="French"
)
passes(
    "model scope: another model",
    payload([EN_QUESTION], entries=[human(KO_ASK), say_as("claude-fable-5-2", "네.")]),
    models="opus-5-5",
)
refuses(
    "model scope: a named model",
    payload([EN_QUESTION], entries=[human(KO_ASK), say_as("claude-opus-5-5", "네.")]),
    models="opus-5-5",
)
passes(
    "transcript_path that does not exist",
    payload([KO_QUESTION], transcript_path=str(Path(WORK, "missing.jsonl"))),
)
refuses(
    "transcript_path that does not exist still judges the question",
    payload([EN_QUESTION], transcript_path=str(Path(WORK, "missing.jsonl"))),
)
passes(
    "questions that are not a list",
    json.dumps(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "AskUserQuestion",
            "tool_input": {"questions": "Can I register the issues this way?" * 5},
        }
    ),
)
passes("empty input", "")
passes("malformed input", "{not json")

# --- opt-out contract: blocking input blocks, opt-out silences it, and a
# disabled hook still drains a large payload ---
saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("CC_")}
os.environ["CC_REPLY_LANGUAGE"] = "Korean"
os.environ["CLAUDE_CONFIG_DIR"] = WORK
fails += _optout.contract(
    HOOK, DISABLE_VAR, payload([EN_QUESTION]), payload([KO_QUESTION])
)
os.environ.update(saved)

print(f"\n{'ALL PASSED' if not fails else f'{fails} FAILED'}")
sys.exit(1 if fails else 0)
