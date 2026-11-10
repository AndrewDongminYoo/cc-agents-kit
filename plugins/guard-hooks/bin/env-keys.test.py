#!/usr/bin/env python3
"""Prove env-keys prints key names only; every value here is synthetic."""

import importlib.util
import os
import random
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

TOOL = Path(__file__).resolve().with_name("env-keys")
# The parser in-process, so the differential check spawns only bash. No
# bytecode: a __pycache__ beside the tool would land in the plugin's bin/.
sys.dont_write_bytecode = True
_LOADER = SourceFileLoader("env_keys", str(TOOL))
_MODULE = importlib.util.module_from_spec(
    importlib.util.spec_from_loader("env_keys", _LOADER)
)
_LOADER.exec_module(_MODULE)
KEYS_OF = _MODULE.keys

FIXTURE = """\
# comment=VALUE_IN_COMMENT
PLAIN=plain-value
export EXPORTED=exported-value
  SPACED = spaced-value
EMPTY=
PEM="-----BEGIN KEY-----
QUJDREVGR0hJSktMTU5PUFFSU1RVVldY==
padded=continuation-value
-----END KEY-----"
SINGLE='first line
inner=single-continuation
last line'
ESCAPED="a \\" b
escaped=escaped-continuation
"
AFTER=after-value
not a key line
lower_case=lower-value
FEED=feed-value\fformfeed=feed-continuation
MIDDLE=abc"
middle=middle-continuation"
JOINED=first \\
joined=joined-continuation
ANSI=$'first\\'
QUJDREVGR0g==
'
ONELINE=$'it\\'s' "$(echo ok)" `echo ok`
COMMENTED=commented-value # it's fine
TRAILING=trailing-value\r
"""
KEYS = [
    "PLAIN",
    "EXPORTED",
    "SPACED",
    "EMPTY",
    "PEM",
    "SINGLE",
    "ESCAPED",
    "AFTER",
    "lower_case",
    "FEED",
    "MIDDLE",
    "JOINED",
    "ANSI",
    "ONELINE",
    "COMMENTED",
    "TRAILING",
]


class EnvKeysTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = self.root / ".env"
        self.env.write_text(FIXTURE, encoding="utf-8")

    def run_tool(self, *args):
        return subprocess.run(
            [str(TOOL), *map(str, args)], capture_output=True, text=True
        )

    def test_prints_exactly_the_keys(self):
        result = self.run_tool(self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), KEYS)
        for value in (
            "value",
            "QUJD",
            "padded",
            "inner",
            "escaped",
            "continuation",
            "comment",
        ):
            self.assertNotIn(value, result.stdout)

    def test_multiple_files_prefix_each_key_with_its_file(self):
        other = self.root / ".env.local"
        other.write_text("LOCAL=local-value\n", encoding="utf-8")
        result = self.run_tool(self.env, other)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            [f"{self.env}:{k}" for k in KEYS] + [f"{other}:LOCAL"],
        )

    def test_unclosed_quote_hides_the_rest_of_the_file(self):
        self.env.write_text('A="open\nB=hidden-value\n', encoding="utf-8")
        self.assertEqual(self.run_tool(self.env).stdout, "A\n")

    def test_crlf_lines_keep_a_backslash_continuation(self):
        self.env.write_bytes(b"A=first \\\r\nleak=crlf-value\r\nB=b\r\n")
        self.assertEqual(self.run_tool(self.env).stdout, "A\nB\n")

    def test_a_hash_inside_a_word_is_not_a_comment(self):
        # bash reads each SECRET line here as part of a quoted value.
        for text in (
            'A=prefix\\ #"\nSECRET0==\n"\nB=b\n',
            'A=prefix\\\n#"\nSECRET0==\n"\nB=b\n',
            "A=x#'\nSECRET0==\n'\nB=b\n",
        ):
            with self.subTest(text=text):
                self.env.write_text(text, encoding="utf-8")
                self.assertEqual(self.run_tool(self.env).stdout, "A\nB\n")

    def test_bash_never_reads_a_printed_key_as_part_of_a_value(self):
        """Differential check against bash over generated shell syntax.

        Each SECRETn== line is a key when bash assigns it at the top level and
        part of a value otherwise. Words are uppercase and PATH is empty, so a
        generated word runs neither a builtin nor a program. A file bash
        cannot parse is skipped: sourcing stops at the error, so later real
        assignments would read as undefined.
        """
        tokens = ["X", " ", "\t", "'", '"', "\\", "\\ ", "#", "$", "$'", "$(",
                  "${", "(", ")", "{", "}", "`", ";", "="]  # fmt: skip
        rng = random.Random(4)
        env = {"PATH": "/nonexistent"}
        checked = 0
        for _ in range(5000):
            lines, secret = [], 0
            for _ in range(rng.randint(3, 9)):
                junk = "".join(rng.choice(tokens) for _ in range(rng.randint(0, 6)))
                roll = rng.random()
                if roll < 0.4:
                    lines.append(f"K{len(lines)}={junk}")
                elif roll < 0.75:
                    lines.append(f"SECRET{secret}==")
                    secret += 1
                else:
                    lines.append(junk)
            text = "\n".join(lines) + "\n"
            printed = [k for k in KEYS_OF(text) if k.startswith("SECRET")]
            if not printed:
                continue
            self.env.write_text(text, encoding="utf-8")
            # bash 3.2 -n can report a syntax error and still exit 0.
            parse = subprocess.run(
                ["/bin/bash", "-n", str(self.env)],
                env=env,
                capture_output=True,
                text=True,
            )
            if parse.returncode or parse.stderr:
                continue
            script = f'source "{self.env}" >/dev/null 2>&1 </dev/null; compgen -v'
            defined = subprocess.run(
                ["/bin/bash", "-c", script],
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.split()
            checked += 1
            self.assertEqual(
                [k for k in printed if k not in defined],
                [],
                self.env.read_text(encoding="utf-8"),
            )
        self.assertGreater(
            checked, 100, "the generator stopped producing comparable files"
        )

    def test_a_heredoc_ends_the_listing(self):
        for text in (
            "A=$(cat <<EOF\nbody=heredoc-value\nEOF\n)\nB=b\n",
            "A=a\ncat <<EOF\nbody=heredoc-value\nEOF\nB=b\n",
        ):
            with self.subTest(text=text):
                self.env.write_text(text, encoding="utf-8")
                self.assertEqual(self.run_tool(self.env).stdout, "A\n")

    def test_an_open_substitution_or_group_ends_the_listing(self):
        for value in (
            "$(printf '%s' x\nsubst=subst-value\n)",
            '"$(echo "\nnested=nested-value\n")"',
            '"`echo "\nbacktick=backtick-value\n"`"',
            '`echo "\nplain=plain-value\n"`',
            "${X:-\nbrace=brace-value\n}",
            "(\narray=array-value\n)",
            "$(case x in\na) echo x\ncase=case-value ;; esac)",
        ):
            with self.subTest(value=value):
                self.env.write_text("A=" + value + "\nB=b\n", encoding="utf-8")
                self.assertEqual(self.run_tool(self.env).stdout, "A\n")

    def test_refuses_other_file_names_before_reading_anything(self):
        secret = self.root / "id_rsa"
        secret.write_text("KEY=private-value\n", encoding="utf-8")
        result = self.run_tool(self.env, secret)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("not a dotenv file name", result.stderr)

    def test_refuses_a_dotenv_named_link_and_other_file_types(self):
        secret = self.root / "id_rsa"
        secret.write_text("QUJDREVG==\nKEY=private-value\n", encoding="utf-8")
        link = self.root / ".env.link"
        link.symlink_to(secret)
        directory = self.root / ".env.dir"
        directory.mkdir()
        fifo = self.root / ".env.fifo"
        os.mkfifo(fifo)
        for target in (link, directory, fifo):
            with self.subTest(target=target.name):
                result = self.run_tool(target)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("QUJD", result.stderr)
        # A linked parent directory still names the dotenv file itself.
        parent = self.root / "linked"
        parent.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(self.run_tool(parent / ".env").stdout.splitlines(), KEYS)

    def test_errors_never_repeat_content(self):
        result = self.run_tool(self.root / ".env.missing")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        for args in ((), ("-v", self.env)):
            result = self.run_tool(*args)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertNotIn("value", result.stderr)


if __name__ == "__main__":
    unittest.main()
