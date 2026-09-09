#!/usr/bin/env python3
"""Prove markdownlint-summary parses both CLI and trunk output and picks runners in order."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(
    os.environ.get(
        "MARKDOWNLINT_SUMMARY_UNDER_TEST",
        Path(__file__).resolve().with_name("markdownlint-summary"),
    )
)
CLI_LOG = (
    'docs/a.md:2 MD036/no-emphasis-as-heading Emphasis used instead of a heading [Context: "one"]\n'
    'docs/a.md:4:1 MD036/no-emphasis-as-heading Emphasis used instead of a heading [Context: "two"]\n'
    "docs/a.md:6 MD040/fenced-code-language Fenced code blocks should have a language specified\n"
)
EXPECTED = (
    "  2\tEmphasis used instead of a heading\tmarkdownlint/MD036\n"
    "  1\tFenced code blocks should have a language specified\tmarkdownlint/MD040\n"
)


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        for executable in ("awk", "sort", "mktemp", "rm", "cat"):
            (self.bin_dir / executable).symlink_to(shutil.which(executable))
        self.environment = dict(os.environ, PATH=str(self.bin_dir))

    def run_script(self, *arguments, input_text=None):
        # /bin/bash on purpose: macOS ships 3.2, the oldest bash this bin entry claims.
        return subprocess.run(
            ["/bin/bash", str(SCRIPT), *arguments],
            cwd=self.root,
            env=self.environment,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
        )

    def mock_tool(self, name, code=1):
        executable = self.bin_dir / name
        executable.write_text(
            '#!/bin/bash\nprintf "%s\\n" "$0" "$@" > invocation\n'
            "cat <<'EOF'\n" + CLI_LOG + f"EOF\nexit {code}\n"
        )
        executable.chmod(0o755)

    def test_cli_log_and_stdin(self):
        result = self.run_script("--log", "-", input_text=CLI_LOG)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, EXPECTED)
        log_file = self.root / "input.log"
        log_file.write_text(CLI_LOG)
        self.assertEqual(self.run_script(str(log_file)).stdout, EXPECTED)

    def test_trunk_ansi_and_noise(self):
        log_text = (
            "docs/a.md\n"
            "  2:1  warning  Emphasis used instead of a heading  markdownlint/MD036\n"
            "\033[33m  4:1  Emphasis used instead of a heading  markdownlint/MD036\033[0m\r\n"
            "  6:1  Fenced code blocks should have a language specified  markdownlint/MD040\n"
            "  2 Emphasis used instead of a heading markdownlint/MD036\n"
            "Checked 1 file\n"
        )
        self.assertEqual(
            self.run_script("--log", "-", input_text=log_text).stdout, EXPECTED
        )

    def test_priority_and_arguments(self):
        for name in ("markdownlint", "npx", "trunk"):
            self.mock_tool(name)
        for selected in ("markdownlint", "npx", "trunk"):
            with self.subTest(selected=selected):
                result = self.run_script("--fix", "docs with spaces/a.md")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, EXPECTED)
                self.assertEqual(result.stderr, "")
                invocation = (self.root / "invocation").read_text().splitlines()
                self.assertEqual(invocation[0], str(self.bin_dir / selected))
                self.assertIn("--fix", invocation)
                self.assertEqual(invocation[-1], "docs with spaces/a.md")
                if selected == "npx":
                    self.assertEqual(
                        invocation[1:5],
                        ["--yes", "--package", "markdownlint-cli", "markdownlint"],
                    )
                (self.bin_dir / selected).unlink()

    def test_defaults_and_failure(self):
        self.mock_tool("trunk", code=2)
        result = self.run_script()
        self.assertEqual(result.returncode, 2)
        self.assertIn(CLI_LOG, result.stderr)
        invocation = (self.root / "invocation").read_text().splitlines()
        self.assertIn("--all", invocation)
        self.assertIn("--no-fix", invocation)
        self.mock_tool("markdownlint", code=0)
        self.assertEqual(self.run_script().returncode, 0)
        invocation = (self.root / "invocation").read_text().splitlines()
        self.assertNotIn("--fix", invocation)
        self.assertIn("**/*.{md,markdown}", invocation)

    def test_empty_missing_and_invalid(self):
        self.assertEqual(self.run_script("--log", "-", input_text="").stdout, "")
        self.assertNotEqual(self.run_script("missing.log").returncode, 0)
        self.assertEqual(self.run_script("--fix", "--log", "-").returncode, 2)
        self.assertEqual(self.run_script().returncode, 127)


if __name__ == "__main__":
    unittest.main()
