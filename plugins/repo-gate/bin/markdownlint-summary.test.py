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
        # stdin is closed unless a case feeds it, so a regression that makes
        # the helper read stdin shows up as empty output instead of a hang.
        return subprocess.run(
            ["/bin/bash", str(SCRIPT), *arguments],
            cwd=self.root,
            env=self.environment,
            input=input_text,
            stdin=None if input_text is not None else subprocess.DEVNULL,
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

    def test_cli_warning_severity_is_counted(self):
        # markdownlint-cli prints `warning` for rules configured at that
        # severity; the parser used to accept only `error` or no severity.
        log_text = (
            "docs/a.md:1:81 warning MD013/line-length Line length [Expected: 80; Actual: 103]\n"
            "docs/a.md:3 error MD040/fenced-code-language Fenced code blocks should have a language specified\n"
        )
        result = self.run_script("--log", "-", input_text=log_text)
        self.assertEqual(result.returncode, 0, result.stderr)
        # Equal counts sort by rule id, so MD013 precedes MD040.
        self.assertEqual(
            result.stdout,
            "  1\tLine length\tmarkdownlint/MD013\n"
            "  1\tFenced code blocks should have a language specified\tmarkdownlint/MD040\n",
        )

    def test_empty_log_value_is_rejected(self):
        # `--log ""` must not fall through to run mode, least of all with --fix.
        self.mock_tool("markdownlint")
        for arguments in (("--log", ""), ("--fix", "--log", "")):
            with self.subTest(arguments=arguments):
                self.assertEqual(self.run_script(*arguments).returncode, 2)
                self.assertFalse((self.root / "invocation").exists())

    def test_assignment_shaped_log_name_is_a_file(self):
        # awk would read `markdownlint=errors.log` as a variable assignment
        # and fall through to stdin, which the harness closes.
        log_file = self.root / "markdownlint=errors.log"
        log_file.write_text(CLI_LOG)
        result = self.run_script("--log", "markdownlint=errors.log")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, EXPECTED)

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
        for name in ("markdownlint", "trunk"):
            self.mock_tool(name)
        for selected in ("markdownlint", "trunk"):
            with self.subTest(selected=selected):
                result = self.run_script("--fix", "docs with spaces/a.md")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, EXPECTED)
                self.assertEqual(result.stderr, "")
                invocation = (self.root / "invocation").read_text().splitlines()
                self.assertEqual(invocation[0], str(self.bin_dir / selected))
                self.assertIn("--fix", invocation)
                # Both runners get an end-of-options marker, so a path that
                # starts with a dash is never read as the runner's option.
                self.assertEqual(invocation[-2:], ["--", "docs with spaces/a.md"])
                (self.bin_dir / selected).unlink()

    def test_npx_is_never_a_runner(self):
        # A checkout's .npmrc can point npx at its own registry, so the helper
        # must not auto-install even when npx is the only tool on PATH.
        self.mock_tool("npx")
        result = self.run_script()
        self.assertEqual(result.returncode, 127)
        self.assertFalse((self.root / "invocation").exists())

    def test_paths_after_separator_stay_paths(self):
        self.mock_tool("markdownlint")
        result = self.run_script("--", "report.log")
        self.assertEqual(result.returncode, 1)
        invocation = (self.root / "invocation").read_text().splitlines()
        self.assertEqual(invocation[0], str(self.bin_dir / "markdownlint"))
        self.assertEqual(invocation[-1], "report.log")

    def test_defaults_and_failure(self):
        self.mock_tool("trunk", code=2)
        result = self.run_script()
        self.assertEqual(result.returncode, 2)
        self.assertIn(CLI_LOG, result.stderr)
        invocation = (self.root / "invocation").read_text().splitlines()
        # The current directory, never --all: --all is the whole repository.
        self.assertNotIn("--all", invocation)
        self.assertEqual(invocation[-2:], ["--", "."])
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
