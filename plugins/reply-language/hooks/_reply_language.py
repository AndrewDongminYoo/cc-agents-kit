"""Shared logic for the reply-language hooks. Run as a helper, never as a suite.

Usage (the hook's JSON on stdin):

    python3 -I -S _reply_language.py remind   # prints the reminder sentence, or nothing
    python3 -I -S _reply_language.py check    # prints a Stop block decision, or nothing

Both modes print nothing, and exit 0, whenever they cannot judge: no target
language, a language this helper has no script for, an unreadable transcript,
or too little text. The leading underscore keeps this file out of CI's
`*.test.py` glob.
"""

import json
import os
import re
import sys
import unicodedata

# Script name prefixes (unicodedata.name) that count as each target language.
# Only languages with a script of their own: a Latin-script target cannot be
# told apart from English by script alone, so it is left unsupported.
SCRIPTS = {
    "korean": ("HANGUL",),
    "japanese": ("HIRAGANA", "KATAKANA", "CJK UNIFIED", "CJK COMPATIBILITY"),
    "chinese": ("CJK UNIFIED", "CJK COMPATIBILITY"),
    "russian": ("CYRILLIC",),
    "ukrainian": ("CYRILLIC",),
    "bulgarian": ("CYRILLIC",),
    "serbian": ("CYRILLIC",),
    "persian": ("ARABIC",),
    "arabic": ("ARABIC",),
    "urdu": ("ARABIC",),
    "hindi": ("DEVANAGARI",),
    "thai": ("THAI",),
    "greek": ("GREEK",),
    "hebrew": ("HEBREW",),
}

# How a `language` value names each target. Lower-cased before lookup; a
# region suffix ("ko-KR", "zh_TW") is dropped first.
ALIASES = {
    "ko": "korean",
    "한국어": "korean",
    "kor": "korean",
    "ja": "japanese",
    "日本語": "japanese",
    "jpn": "japanese",
    "zh": "chinese",
    "中文": "chinese",
    "简体中文": "chinese",
    "繁體中文": "chinese",
    "traditional chinese": "chinese",
    "simplified chinese": "chinese",
    "ru": "russian",
    "русский": "russian",
    "uk": "ukrainian",
    "українська": "ukrainian",
    "bg": "bulgarian",
    "sr": "serbian",
    "fa": "persian",
    "farsi": "persian",
    "فارسی": "persian",
    "ar": "arabic",
    "العربية": "arabic",
    "ur": "urdu",
    "hi": "hindi",
    "हिन्दी": "hindi",
    "th": "thai",
    "ไทย": "thai",
    "el": "greek",
    "ελληνικά": "greek",
    "he": "hebrew",
    "עברית": "hebrew",
}

# The reminder defines English by who reads it: the wording that held in the
# replay measurements on anthropics/claude-code#96326. Written in the target
# language where one is provided here; English otherwise.
REMINDERS = {
    "korean": (
        "사용자가 읽는 텍스트는 도구 호출 사이의 짧은 진행 안내까지 모두 한국어로 씁니다. "
        "영어는 사용자가 아닌 독자가 읽는 것(서브에이전트에게 보내는 브리프, 코드, 식별자, "
        "커밋 메시지, PR과 이슈 본문, 저장하는 파일)과 원문 그대로의 인용에만 씁니다."
    ),
    "japanese": (
        "ユーザーが読むテキストは、ツール呼び出しの間の短い進捗報告も含めて日本語で書きます。"
        "英語は、ユーザー以外が読むもの（サブエージェントへの指示、コード、識別子、"
        "コミットメッセージ、PR と Issue の本文、保存するファイル）と原文どおりの引用にだけ使います。"
    ),
}
REMINDER_EN = (
    "Text the user reads, including the short status lines between tool calls, is "
    "written in {name}. English is allowed only for what someone other than the user "
    "reads (briefs to subagents, code, identifiers, commit messages, PR and issue "
    "text, saved files) and for verbatim quotes."
)

# The short line that follows every other tool result: the text after a tool
# result is where the drift concentrates, so it sits right before the next
# text the model writes, at about a tenth of the full sentence's tokens.
TAILS = {
    "korean": "사용자에게 보이는 다음 텍스트는 한국어로 씁니다.",
    "japanese": "ユーザーに見える次のテキストは日本語で書きます。",
}
TAIL_EN = "The next text the user sees is written in {name}."

# Tools after which the full sentence is repeated: a subagent's report or a
# brief just written to one is the English input the drift follows most.
FULL_AFTER = ("Agent", "SendMessage")

REWRITE = {
    "korean": (
        "이번 응답에서 사용자에게 보인 텍스트가 대부분 한국어가 아닙니다. "
        "새 도구 작업 없이, 그 내용을 한국어로 다시 써서 전달하세요. "
        "코드, 식별자, 경로, 원문 인용은 그대로 둡니다."
    ),
    "japanese": (
        "今回の応答でユーザーに見えたテキストの大部分が日本語ではありません。"
        "新しいツール作業はせず、その内容を日本語で書き直して伝えてください。"
        "コード、識別子、パス、原文の引用はそのままにします。"
    ),
}
REWRITE_EN = (
    "The text shown to the user in this response is mostly not in {name}. "
    "Without new tool work, restate it in {name}. Leave code, identifiers, paths and "
    "verbatim quotes as they are."
)

MIN_LETTERS = 40  # below this, a short line of paths or names decides nothing
MAX_SHARE = 0.30  # under this share of target-script letters counts as drift
USER_SHARE = 0.10  # a user message under this share was written in another language

FENCE = re.compile(r"```.*?(```|\Z)|~~~.*?(~~~|\Z)", re.S)
INLINE = re.compile(r"`[^`\n]*`")
URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I)
LINK_TARGET = re.compile(r"\]\([^)]*\)")
PATH = re.compile(
    r"(?:~|\.{1,2})?/[\w.@%+~-]+(?:/[\w.@%+~-]+)*|\b[\w.-]+\.[a-z0-9]{1,5}\b", re.I
)
QUOTE = re.compile(r"^\s*>.*$", re.M)
TAG = re.compile(r"<[^>\n]{1,200}>")


def target_language(cwd):
    """The configured reply language, from env override or the settings chain."""
    raw = os.environ.get("CC_REPLY_LANGUAGE", "").strip()
    if not raw:
        home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
            os.path.expanduser("~"), ".claude"
        )
        candidates = [os.path.join(home, "settings.json")]
        if cwd:
            candidates += [
                os.path.join(cwd, ".claude", "settings.json"),
                os.path.join(cwd, ".claude", "settings.local.json"),
            ]
        for path in candidates:  # later files override earlier ones
            try:
                with open(path, encoding="utf-8") as fh:
                    value = json.load(fh).get("language")
            except (OSError, ValueError, AttributeError):
                continue
            if isinstance(value, str) and value.strip():
                raw = value.strip()
    if not raw:
        return None
    key = raw.lower()
    if key in SCRIPTS:
        return key
    if key in ALIASES:
        return ALIASES[key]
    base = re.split(r"[-_]", key)[0]
    if base in ALIASES:
        return ALIASES[base]
    return SCRIPTS.get(base) and base


def strip_non_prose(text):
    for pattern in (FENCE, INLINE, LINK_TARGET, URL, TAG, QUOTE, PATH):
        text = pattern.sub(" ", text)
    return text


def script_share(text, language):
    """(letters counted, share of them in the target language's script)."""
    prefixes = SCRIPTS[language]
    letters = hits = 0
    for ch in strip_non_prose(text):
        if not ch.isalpha():
            continue
        letters += 1
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        hits += name.startswith(prefixes)
    return letters, (hits / letters if letters else 1.0)


def _content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        )
    return ""


def _is_human(entry):
    """A message the user typed: a prompt, or a message queued mid-turn."""
    if entry.get("type") == "attachment":
        att = entry.get("attachment") or {}
        return (
            att.get("type") == "queued_command"
            and (att.get("origin") or {}).get("kind") == "human"
        )
    if entry.get("type") != "user" or entry.get("isMeta"):
        return False
    if entry.get("isCompactSummary"):
        return True  # a turn boundary whose language _human_text leaves unknown
    origin = entry.get("origin")
    if isinstance(origin, dict):
        return origin.get("kind") == "human"
    # Older transcripts carry no origin: a plain string prompt that is not a
    # harness wrapper such as <command-name> or <task-notification>.
    content = (entry.get("message") or {}).get("content")
    return isinstance(content, str) and not content.lstrip().startswith("<")


COMMAND_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)
PASTED = re.compile(r"<pasted_content\b[^>]*>.*?(</pasted_content>|\Z)", re.S)


def _human_text(entry):
    """The words the user typed, for judging which language they wrote in."""
    if entry.get("isCompactSummary"):
        return ""  # written by the harness, not the user
    if entry.get("type") == "attachment":
        text = str((entry.get("attachment") or {}).get("prompt") or "")
    else:
        text = _content_text((entry.get("message") or {}).get("content"))
    if "<command-name>" in text:
        # A slash command: its name says nothing about the user's language,
        # so only the arguments the user typed count.
        text = " ".join(COMMAND_ARGS.findall(text))
    # A pasted log or document is someone else's text, not the user's choice
    # of language.
    return PASTED.sub(" ", text)


def _opens_turn(entry):
    """Any input that starts a model turn: what the user typed, a task
    notification, a subagent's report, a queued message, a compact summary.

    Stop fires at the end of each such turn, so the window a Stop judges
    starts at the last of them; otherwise a draft already restated after one
    block would be judged again at the next notification's Stop.
    """
    if _is_human(entry):
        return True
    if entry.get("type") == "attachment":
        return (entry.get("attachment") or {}).get("type") == "queued_command"
    if entry.get("type") != "user":
        return False
    origin = entry.get("origin")
    if isinstance(origin, dict) and origin.get("kind") in ("task-notification", "peer"):
        return True
    content = (entry.get("message") or {}).get("content")
    return isinstance(content, str) and not entry.get("isMeta")


def stop_window(path):
    """(text blocks shown since the input that opened this turn,
    the user's last message, entrypoint).

    One forward pass. Only lines that can be a turn boundary or an assistant
    message are parsed, so a long transcript stays well inside the timeout.
    """
    texts, human, entrypoint = [], None, ""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if (
                '"assistant"' not in line
                and '"user"' not in line
                and "queued_command" not in line
            ):
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            entrypoint = entrypoint or str(entry.get("entrypoint") or "")
            if _opens_turn(entry):
                texts = []
                if _is_human(entry):
                    human = _human_text(entry)
            elif _model_text(entry):
                texts.append(_model_text(entry))
    return texts, human, entrypoint


def _model_text(entry):
    """Text the main model wrote for the user; not a subagent's, not a
    harness error rendered as an assistant message."""
    if entry.get("type") != "assistant" or entry.get("isSidechain"):
        return ""
    if entry.get("isApiErrorMessage"):
        return ""
    text = _content_text((entry.get("message") or {}).get("content"))
    return text if text.strip() else ""


def drifted(blocks, language):
    """True when the turn as a whole, or its last block, drifted.

    The last block is what the user reads last. When it is too short to
    judge, only the whole-turn share decides; an earlier block never stands
    in for it.
    """
    letters, share = script_share("\n".join(blocks), language)
    if letters >= MIN_LETTERS and share < MAX_SHARE:
        return True
    if not blocks:
        return False
    letters, share = script_share(blocks[-1], language)
    return letters >= MIN_LETTERS and share < MAX_SHARE


def remind(event):
    language = target_language(event.get("cwd"))
    if not language:
        return None
    name = event.get("hook_event_name") or ""
    if name not in ("UserPromptSubmit", "PostToolUse"):
        return None
    label = language.capitalize()
    if name == "PostToolUse" and event.get("tool_name") not in FULL_AFTER:
        text = TAILS.get(language) or TAIL_EN.format(name=label)
    else:
        text = REMINDERS.get(language) or REMINDER_EN.format(name=label)
    return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": text}}


def check(event):
    if event.get("stop_hook_active"):
        return None  # one rewrite per stop; never loop
    language = target_language(event.get("cwd"))
    path = event.get("transcript_path")
    if not language or not isinstance(path, str) or not path:
        return None
    try:
        shown, human, entrypoint = stop_window(path)
    except OSError:
        return None
    if entrypoint.startswith("sdk"):
        return None  # headless runs have no reader to restate for
    if human is not None:
        h_letters, h_share = script_share(human, language)
        if h_letters >= MIN_LETTERS // 2 and h_share < USER_SHARE:
            return None  # the user wrote in another language this turn
    if not drifted(shown, language):
        return None
    reason = REWRITE.get(language) or REWRITE_EN.format(name=language.capitalize())
    return {"decision": "block", "reason": reason}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return
    if not isinstance(event, dict):
        return
    result = (
        remind(event) if mode == "remind" else check(event) if mode == "check" else None
    )
    if result:
        sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # fail open: a broken helper must never block a reply
        pass
