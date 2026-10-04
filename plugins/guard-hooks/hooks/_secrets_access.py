#!/usr/bin/env python3
"""Recognize narrow approval paths; never execute commands or open secret inputs."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys

ROOT = Path(__file__).resolve().parent.parent


def bounded_read(path, limit):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("noncanonical path")
    parent = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("invalid policy or consumer")
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("oversized policy or consumer")
        return data, info


def ask(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "ask",
        "permissionDecisionReason": reason,
    }}))


def relative_file(value):
    return (isinstance(value, str) and bool(value) and not Path(value).is_absolute()
            and ".." not in Path(value).parts and not value.startswith("-"))


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate response field")
        result[key] = value
    return result


def validate_response():
    data = json.load(sys.stdin, object_pairs_hook=unique_object)
    if not isinstance(data, dict) or set(data) != {"hookSpecificOutput"}:
        return False
    output = data["hookSpecificOutput"]
    return (isinstance(output, dict)
            and set(output) == {"hookEventName", "permissionDecision", "permissionDecisionReason"}
            and output["hookEventName"] == "PreToolUse"
            and output["permissionDecision"] == "ask"
            and isinstance(output["permissionDecisionReason"], str)
            and bool(output["permissionDecisionReason"]))


def registered_consumer(argv, cwd):
    setting = os.environ.get("CC_GUARD_ENV_POLICY")
    digest = os.environ.get("CC_GUARD_ENV_POLICY_SHA256", "")
    if not setting or not re.fullmatch(r"[a-f0-9]{64}", digest) or not Path(setting).is_absolute() or not cwd:
        return None
    policy = Path(setting)
    # The operator installs this outside the agent's checkout. This is an opt-in
    # approval route, not an exemption from the harness or a runtime sandbox.
    if policy.is_symlink() or policy.resolve().is_relative_to(Path(cwd).resolve()):
        return None
    raw, info = bounded_read(policy, 65536)
    if hashlib.sha256(raw).hexdigest() != digest:
        return None
    if info.st_uid != os.getuid() or info.st_mode & 0o022:
        return None
    document = json.loads(raw)
    if document.get("version") != 1:
        return None
    for item in document.get("consumers", []):
        if item.get("argv") != argv or item.get("cwd") != str(Path(cwd).resolve()):
            continue
        if not Path(argv[0]).is_absolute() or Path(argv[0]).is_symlink():
            continue
        code, _ = bounded_read(argv[0], 1048576)
        if not code.startswith(b"#!") or hashlib.sha256(code).hexdigest() != item.get("code_sha256"):
            continue
        files, keys, destinations = (item.get(k) for k in ("env_files", "keys", "destinations"))
        if not isinstance(files, list) or not files or not all(relative_file(f) for f in files):
            continue
        if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k) for k in keys):
            continue
        if not isinstance(destinations, list) or not all(isinstance(d, str) for d in destinations):
            continue
        if not isinstance(item.get("purpose"), str) or not item["purpose"]:
            continue
        return item
    return None


def main():
    data = json.load(sys.stdin)
    if data.get("tool_name") != "Bash":
        return
    inputs = data.get("tool_input", {})
    if inputs.get("file_path") or inputs.get("path"):
        return
    command = inputs.get("command", "")
    # shlex alone is not a shell parser. Reject all operators/expansions first,
    # including quoted instances, instead of guessing what a shell will run.
    if not isinstance(command, str) or re.search(r"[\n\r\x00$`;|&<>()]", command):
        return
    argv = shlex.split(command)
    if not argv:
        return
    # Quote every word, including the executable. shlex.join leaves ordinary
    # words bare and therefore eligible for zsh global-alias expansion.
    quoted = " ".join("'" + arg.replace("'", "'\"'\"'") + "'" for arg in argv)
    if command != quoted or any(arg.startswith("=") for arg in argv):
        return
    if (data.get("permission_mode") == "auto" and argv[0] == "/usr/bin/printf"
            and len(argv) >= 3 and argv[1] in ("%s", "%s\\n")):
        print("ABSTAIN")
        return
    if (argv[0] == str(ROOT / "bin/env-status") and len(argv) == 5
            and argv[1] == "--schema" and argv[3] == "--file"
            and relative_file(argv[2]) and relative_file(argv[4])):
        ask("Inspect schema keys for present/empty status only. This reads the named local file; values are never returned. Approve this exact inspection?")
        return
    item = registered_consumer(argv, data.get("cwd"))
    if item:
        ask("Run the registered environment consumer? " + json.dumps({
            "purpose": item["purpose"], "files": item["env_files"],
            "keys": item["keys"], "destinations": item["destinations"],
        }) + " These are declared boundaries, not enforcement. The script and its dependencies receive secret access; the code hash covers only the entry script.")


if __name__ == "__main__":
    if sys.argv[1:] == ["--validate-response"]:
        try:
            sys.exit(0 if validate_response() else 1)
        except (OSError, ValueError, TypeError, KeyError):
            sys.exit(1)
    try:
        main()
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        # No exception text: neither policy data nor source content belongs in
        # diagnostics. No recognition means the existing guard still decides.
        pass
