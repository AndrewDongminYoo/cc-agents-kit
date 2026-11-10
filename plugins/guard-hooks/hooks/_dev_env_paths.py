#!/usr/bin/env python3
"""Match user-designated development paths; never read dotenv contents."""

import json
import os
import re
import shlex
import stat
import sys
from pathlib import Path

ENV = re.compile(
    r"""(^|[/\s"'=])(\.env(?:\.[A-Za-z0-9-]+)*)(?=[^A-Za-z0-9_.-]|$)""", re.I
)
NAME = re.compile(r"\.env(?:\.[A-Za-z0-9-]+)*", re.I)
TEMPLATES = {
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.dist",
    ".env.default",
    ".env.defaults",
}
UNSAFE = re.compile(r"""[\x00-\x1f\x7f*?\[\]{}$`\\;|&<>()='"^#~]""")
TOOLS = {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit", "Bash", "Grep", "Glob"}
# A plain or single-quoted path word: nothing the shell expands or splits.
KEYS_ARG = r"""(?:~/)?[A-Za-z0-9_./@+-]+|'[^'\x00-\x1f\x7f]+'"""
SOURCE = {"source", "."}


def references(text):
    return [m for m in ENV.finditer(text) if m[2].lower() not in TEMPLATES]


def literal_path(value):
    return (
        isinstance(value, str)
        and value.startswith("/")
        and not value.startswith("//")
        and os.path.normpath(value) == value
        and not UNSAFE.search(value)
        and NAME.fullmatch(Path(value).name)
        and Path(value).name.lower() not in TEMPLATES
    )


def no_symlinks(value, directory=False):
    path = Path(value)
    for part in list(reversed(path.parents)) + [path]:
        try:
            mode = part.lstat().st_mode
        except FileNotFoundError:
            return not directory and part == path
        expected_kind = stat.S_ISDIR if directory else stat.S_ISREG
        if stat.S_ISLNK(mode) or (part == path and not expected_kind(mode)):
            return False
    return True


def designated_paths():
    raw = os.environ.get("CC_GUARD_DEV_ENV_PATHS", "")
    if not raw or len(raw) > 65536:
        return set()
    paths = json.loads(raw)
    if not isinstance(paths, list) or not 0 < len(paths) <= 64:
        return set()
    if not all(literal_path(p) and no_symlinks(p) for p in paths):
        return set()
    return set(paths)


def keys_only(data):
    """True for a Bash command that is exactly `env-keys <dotenv path>...`.

    bin/env-keys prints key names only, so any dotenv file may be named, in any
    permission mode. The whole command must be that one simple command: an
    abstention skips every later check, so a pipe, a second command, a function
    or a PATH prefix would carry them past the guard.
    """
    if data.get("tool_name") != "Bash":
        return False
    command = data.get("tool_input", {}).get("command", "")
    if not isinstance(command, str):
        return False
    tool = str(Path(__file__).resolve().parent.parent / "bin" / "env-keys")
    program = "|".join(re.escape(p) for p in ("env-keys", tool, "'" + tool + "'"))
    pattern = rf"[ \t]*(?:{program})((?:[ \t]+(?:{KEYS_ARG}))+)[ \t]*"
    match = re.fullmatch(pattern, command)
    if not match:
        return False
    words = re.findall(KEYS_ARG, match[1])
    return all(NAME.fullmatch(Path(w.strip("'")).name) for w in words)


def canonical_cwd(data):
    cwd = data.get("cwd", "")
    if (
        not isinstance(cwd, str)
        or not cwd.startswith("/")
        or cwd.startswith("//")
        or os.path.normpath(cwd) != cwd
        or not no_symlinks(cwd, directory=True)
    ):
        return None
    return cwd


def relative_source(words, index, value, data):
    """Resolve a relative dotenv operand of a leading source or . command.

    Nothing runs before the first simple command, so the shell is still in the
    event's cwd; a later command could follow any cd, function or subshell.
    Only an exact leading `set -a ;` may come before it.
    """
    if index == 1:
        head = words[:1]
    elif index == 4 and words[:3] == ["set", "-a", ";"]:
        head = words[3:4]
    else:
        return None
    cwd = canonical_cwd(data)
    if head[0] not in SOURCE or cwd is None or ".." in Path(value).parts:
        return None
    resolved = os.path.normpath(os.path.join(cwd, value))
    if not Path(resolved).is_file():
        return None  # zsh source falls back to PATH when the file is missing.
    if "/" not in value:
        # bash source and . search PATH first for a name without a slash.
        for entry in os.environ.get("PATH", "").split(os.pathsep):
            directory = os.path.join(cwd, entry) if entry else cwd
            if os.path.normpath(directory) != cwd and os.path.lexists(
                os.path.join(directory, value)
            ):
                return None
    return resolved


def should_abstain(data):
    if data.get("permission_mode") != "auto" or data.get("tool_name") not in TOOLS:
        return False
    allowed = designated_paths()
    if not allowed:
        return False
    inputs, seen = data.get("tool_input", {}), False
    for field in ("file_path", "path"):
        value = inputs.get(field, "")
        if not isinstance(value, str):
            return False
        if not references(value):
            continue
        seen = True
        if ".." in Path(value).parts:
            return False
        if not value.startswith("/"):
            cwd = canonical_cwd(data)
            if cwd is None:
                return False
            value = os.path.normpath(os.path.join(cwd, value))
        if value not in allowed:
            return False
    command = inputs.get("command", "")
    if not isinstance(command, str):
        return False
    original = references(command)
    if original:
        if data.get("tool_name") != "Bash":
            return False
        # Tokenization locates literal paths, not executable identity or effects.
        # Bash paths are absolute, except the operand of a leading source or .
        # (relative_source), so no cwd is guessed after cd/subshells/functions.
        # Keep glob punctuation on the word: zsh's path(:modifier) and path<1-2>
        # can select other files. Splitting them validates only the safe prefix.
        # A newline is whitespace here, so a command after one moves the index.
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        lexer.commenters = ""
        words = list(lexer)
        found = 0
        for index, word in enumerate(words):
            matches = references(word)
            if not matches:
                continue
            found += len(matches)
            # Support --env-file=/absolute/path and NAME=/absolute/path.
            # A prefix containing another live reference must never be discarded.
            prefix, separator, value = word.partition("=")
            if separator and references(prefix):
                return False
            candidate = value if separator else word
            if not separator and not word.startswith("/") and not UNSAFE.search(word):
                candidate = relative_source(words, index, word, data) or word
            if candidate not in allowed:
                return False
        # Do not drop a legacy match while decoding quotes, such as .env'other'.
        if found != len(original):
            return False
        seen = True
    return seen


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if keys_only(data) or should_abstain(data):
            print("ABSTAIN")
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass  # The original guard decides when configuration/input is uncertain.
