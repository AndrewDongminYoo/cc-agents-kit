#!/usr/bin/env python3
"""Match operator-designated development paths; never read dotenv contents."""
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys

ENV = re.compile(r'''(^|[/\s"'=])(\.env(?:\.[A-Za-z0-9-]+)*)(?=[^A-Za-z0-9_.-]|$)''', re.I)
NAME = re.compile(r"\.env(?:\.[A-Za-z0-9-]+)*", re.I)
TEMPLATES = {".env.example", ".env.sample", ".env.template", ".env.dist", ".env.default", ".env.defaults"}
UNSAFE = re.compile(r'''[\x00-\x1f\x7f*?\[\]{}$`\\;|&<>()='"^#~]''')
TOOLS = {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit", "Bash", "Grep", "Glob"}


def references(text):
    return [m for m in ENV.finditer(text) if m[2].lower() not in TEMPLATES]


def literal_path(value):
    return (isinstance(value, str) and value.startswith("/") and not value.startswith("//")
            and os.path.normpath(value) == value and not UNSAFE.search(value)
            and NAME.fullmatch(Path(value).name) and Path(value).name.lower() not in TEMPLATES)


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
            cwd = data.get("cwd", "")
            if (not isinstance(cwd, str) or not cwd.startswith("/") or cwd.startswith("//")
                    or os.path.normpath(cwd) != cwd or not no_symlinks(cwd, directory=True)):
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
        # Absolute Bash paths avoid guessing cwd after cd/subshells/functions.
        # Keep glob punctuation on the word: zsh's path(:modifier) and path<1-2>
        # can select other files. Splitting them validates only the safe prefix.
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        lexer.commenters = ""
        found = 0
        for word in lexer:
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
            if candidate not in allowed:
                return False
        # Do not drop a legacy match while decoding quotes, such as .env'other'.
        if found != len(original):
            return False
        seen = True
    return seen


if __name__ == "__main__":
    try:
        if should_abstain(json.load(sys.stdin)):
            print("ABSTAIN")
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass  # The original guard decides when configuration/input is uncertain.
