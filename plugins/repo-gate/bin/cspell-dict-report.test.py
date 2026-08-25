#!/usr/bin/env python3
"""Prove cspell-dict-report reads trace output correctly and ranks by real gain."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(
    os.environ.get(
        "CSPELL_DICT_REPORT_UNDER_TEST",
        Path(__file__).resolve().with_name("cspell-dict-report"),
    )
)

# A dictionary name of 20+ characters is truncated in trace's name column and
# the truncation is marked with the same trailing asterisk that means
# "enabled", so the fixture carries one of each to prove the location join.
FAKE_CSPELL = '''#!/usr/bin/env python3
import sys

DICTIONARIES = """Dictionary                  Dictionary Location
coding-compound-terms*      node_modules/@cspell/dict-software-terms/dict/coding-compound-terms.txt
custom-dictionary*          .cspell/custom-dictionary.txt
node                        node_modules/@cspell/dict-node/dict/node.txt
npm                         node_modules/@cspell/dict-npm/dict/npm.txt"""

TRACE = {
    "esbuild": [("esbuild", "*", "npm", "node_modules/@cspell/dict-npm/dict/npm.txt"),
                ("esbuild", "*", "node", "node_modules/@cspell/dict-node/dict/node.txt")],
    "hasown": [("hasown", "*", "npm", "node_modules/@cspell/dict-npm/dict/npm.txt")],
    "estree": [("estree", "*", "npm", "node_modules/@cspell/dict-npm/dict/npm.txt")],
    "bigints": [("bigints", "*", "node", "node_modules/@cspell/dict-node/dict/node.txt")],
    "meta": [("meta", "*", "coding-compound-ter*",
              "node_modules/@cspell/dict-software-terms/dict/coding-compound-terms.txt")],
    "lookahead": [("look\\u2022ahead", "*", "npm", "node_modules/@cspell/dict-npm/dict/npm.txt")],
    "worktree": [("worktree", "*", "custom-dictionary*", ".cspell/custom-dictionary.txt")],
    "recieve": [("recieve->(receive)", "-", "en-common-misspelli*",
                 "node_modules/@cspell/dict-en-common-misspellings/dict/dict-en.json")],
}

if sys.argv[1] == "dictionaries":
    print(DICTIONARIES)
elif sys.argv[1] == "trace":
    for word in sys.stdin.read().split():
        print("Word F Dictionary Dictionary Location")
        for row in TRACE.get(word.lower(), []):
            print(" ".join(row))
else:
    sys.exit("unexpected: " + " ".join(sys.argv))
'''


def report(words, *args):
    with tempfile.TemporaryDirectory() as temp_dir:
        fake = Path(temp_dir, "cspell")
        fake.write_text(FAKE_CSPELL)
        fake.chmod(0o755)
        done = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            input="\n".join(words) + "\n",
            capture_output=True,
            text=True,
            env={**os.environ, "PATH": f"{temp_dir}{os.pathsep}{os.environ['PATH']}"},
        )
    if done.returncode != 0:
        raise SystemExit(f"the report exited {done.returncode}:\n{done.stderr}")
    return done.stdout + ("\nSTDERR\n" + done.stderr if done.stderr else "")


def section(out, heading):
    """The lines of one report section, without its heading."""
    body, collecting = [], False
    for line in out.splitlines():
        if line.startswith(heading):
            collecting = True
        elif collecting and line and not line.startswith(" "):
            break
        elif collecting:
            body.append(line)
    return body


WORDS = ["esbuild", "Esbuild", "hasown", "estree", "bigints", "meta", "lookahead", "worktree", "recieve"]
failures = []


def check(label, condition, detail=""):
    if condition:
        print(f"ok   {label}")
    else:
        failures.append(label)
        print(f"FAIL {label}{chr(10) + detail if detail else ''}")


out = report(WORDS)

check(
    "case variants fold into one word with two occurrences",
    "8 unique words, 9 occurrences, 1 case-variant duplicate(s) folded" in out,
    out.splitlines()[0],
)

covered = "\n".join(section(out, "ALREADY COVERED"))
check(
    "a truncated trace name resolves to its full name through the location join",
    "coding-compound-terms" in covered and "coding-compound-ter*" not in covered,
    covered,
)
check("an enabled local dictionary counts as coverage", "worktree" in covered, covered)

check(
    "a misspelling is reported with its suggestion, not as coverage",
    "-> receive" in "\n".join(section(out, "MISSPELLED")),
    out,
)

residue = "\n".join(section(out, "IN NO DICTIONARY"))
check(
    "a compound hit (look•ahead) is not counted as coverage",
    "lookahead" in residue and "warning:" not in out,
    residue + out[out.find("STDERR"):],
)

# esbuild+hasown+estree+bigints are pending. npm covers three of them and node
# covers two, but only bigints is still new once npm is taken - so a ranking
# that scored each dictionary independently would claim node covers two.
candidates = section(out, "DICTIONARY CANDIDATES")
ranked = [line.split() for line in candidates if line.split() and line.split()[0] in {"npm", "node"}]
check(
    "greedy ranking scores each row against what the rows above it leave",
    [r[:4] for r in ranked] == [["npm", "3", "3", "4"], ["node", "1", "2", "1"]],
    "\n".join(candidates),
)
check(
    "every pending word lands in exactly one row",
    sum(int(r[1]) for r in ranked) == 4 and "4 word(s) no enabled dictionary has" in out,
    "\n".join(candidates),
)

excluded = report(WORDS, "--exclude", "custom-dictionary")
check(
    "--exclude drops the dictionary from coverage entirely",
    "worktree" in "\n".join(section(excluded, "IN NO DICTIONARY")),
    excluded,
)

if failures:
    sys.exit(f"{len(failures)} check(s) failed: {', '.join(failures)}")
print(f"all {8} checks passed")
