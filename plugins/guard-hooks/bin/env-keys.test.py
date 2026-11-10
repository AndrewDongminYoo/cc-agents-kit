#!/usr/bin/env python3
"""Prove env-keys prints key names only; every value here is synthetic."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().with_name("env-keys")

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
