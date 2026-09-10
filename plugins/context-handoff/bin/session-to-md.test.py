#!/usr/bin/env python3
"""Prove session-to-md renders safe sessions and rejects unsafe output requests."""

import os
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(
    os.environ.get(
        "SESSION_TO_MD_UNDER_TEST",
        Path(__file__).resolve().with_name("session-to-md"),
    )
)


def run(arguments, temp_dir):
    transcript = Path(temp_dir, "session.jsonl")
    transcript.write_text(
        '{"type":"user","timestamp":"2026-08-27T00:00:00.000Z","message":{"content":"hello"}}\n'
    )
    return subprocess.run(
        ["node", str(SCRIPT), str(transcript), *arguments],
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_CONFIG_DIR": temp_dir, "HOME": temp_dir},
    )


def fails(label, arguments, required_text=None):
    with tempfile.TemporaryDirectory() as temp_dir:
        result = run(arguments, temp_dir)
        output = result.stdout + result.stderr
        passed = result.returncode != 0 and (
            required_text is None or required_text in output
        )
        print(f"{'ok  ' if passed else 'FAIL'} {label}: exit={result.returncode}")
        return not passed


failures = 0
for label, arguments, required_text in (
    ("rejects a suffixed --last value", ["--last", "1x"], "--last"),
    ("rejects a zero --last value", ["--last", "0"], "--last"),
    ("rejects an unsupported --tools value", ["--tools", "summary"], "--tools"),
    ("rejects multiple session identifiers", ["other-session"], "session identifier"),
):
    failures += fails(label, arguments, required_text)

with tempfile.TemporaryDirectory() as temp_dir:
    output = Path(temp_dir, "rendered-session.md")
    result = run(["--out", str(output)], temp_dir)
    rendered = output.read_text() if output.is_file() else ""
    passed = (
        result.returncode == 0
        and result.stdout == f"{output}\n"
        and "# hello" in rendered
        and "## 👤 User" in rendered
        and "hello" in rendered
    )
    print(f"{'ok  ' if passed else 'FAIL'} renders a session to the exact output path: exit={result.returncode}")
    failures += not passed

with tempfile.TemporaryDirectory() as temp_dir:
    output = Path(temp_dir, "existing.md")
    original = b"do not replace\x00this"
    output.write_bytes(original)
    result = run(["--out", str(output)], temp_dir)
    passed = result.returncode != 0 and output.read_bytes() == original
    print(
        f"{'ok  ' if passed else 'FAIL'} preserves an existing output file: "
        f"exit={result.returncode}"
    )
    failures += not passed

with tempfile.TemporaryDirectory() as temp_dir:
    output = Path(temp_dir, "missing", "output.md")
    result = run(["--out", str(output)], temp_dir)
    lines = [line for line in (result.stdout + result.stderr).splitlines() if line]
    passed = result.returncode != 0 and len(lines) == 1 and "Error" not in lines[0]
    print(
        f"{'ok  ' if passed else 'FAIL'} reports a write failure without a stack trace: "
        f"exit={result.returncode}"
    )
    failures += not passed

class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "session.jsonl"
        self.env = {**os.environ, "CLAUDE_CONFIG_DIR": self.temp.name}
        self.entries = [
            self.entry("user", "  첫 요청\n\n    indented code\n"),
            self.entry("assistant", [
                {"type": "text", "text": "Checking **the output**."},
                {"type": "tool_use", "id": "call-1", "name": "Bash", "input": {"command": "echo " + "가" * 1600}},
            ]),
            self.entry("user", [
                {"type": "tool_result", "tool_use_id": "call-1", "content": "\u001b[31m" + "결과" * 1600 + "\u001b[0m"},
                {"type": "text", "text": "Keep this mixed user message."},
            ]),
            self.entry("user", [{"type": "tool_result", "tool_use_id": "call-1", "content": "", "is_error": True}]),
            self.entry("assistant", [{"type": "tool_use", "id": "pending", "name": "Read", "input": {}}]),
            self.entry("assistant", [{"type": "thinking", "thinking": "PRIVATE_THINKING"}, {"type": "text", "text": "Done."}]),
        ]

    @staticmethod
    def entry(role, content, **extra):
        return {"type": role, "timestamp": "2026-09-10T09:00:00Z", "message": {"content": content}, **extra}

    def export(self, fmt="json", *args, entries=None, raw=""):
        records = self.entries if entries is None else entries
        self.source.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in records) + raw)
        output = self.root / f"export-{len(list(self.root.iterdir()))}.{fmt}"
        result = subprocess.run(["node", str(SCRIPT), str(self.source), "--format", fmt, "--out", str(output), *args], capture_output=True, text=True, env=self.env)
        return result, output

    def document(self, *args, **kwargs):
        result, output = self.export("json", *args, **kwargs)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(output.read_text())

    def test_default_excludes_tools_and_preserves_indentation(self):
        doc = self.document()
        self.assertEqual(doc["schema_version"], 1)
        self.assertTrue(all(r["type"] == "message" for r in doc["records"]))
        self.assertEqual(doc["records"][0]["text"], "  첫 요청\n\n    indented code\n")
        self.assertIn("Keep this mixed user message.", [r["text"] for r in doc["records"]])
        self.assertNotIn("PRIVATE_THINKING", json.dumps(doc))

    def test_complete_inputs_and_multiple_outputs_are_paired(self):
        doc = self.document("--tools", "collapsed")
        calls = [r for r in doc["records"] if r["type"] == "tool"]
        self.assertEqual(len(calls), 2)
        self.assertEqual(json.loads(calls[0]["input"])["command"], "echo " + "가" * 1600)
        self.assertEqual([o["text"] for o in calls[0]["outputs"]], ["결과" * 1600, ""])
        self.assertTrue(calls[0]["outputs"][1]["is_error"])
        self.assertEqual(calls[0]["output_state"], "recorded")
        self.assertEqual(calls[1]["output_state"], "missing")
        self.assertEqual(doc["diagnostics"]["missing_tool_outputs"], 1)
        self.assertEqual(doc["diagnostics"]["truncated_values"], 0)

    def test_explicit_limit_is_shared_by_all_formats(self):
        doc = self.document("--tools", "collapsed", "--tool-limit", "30")
        self.assertEqual(doc["diagnostics"]["truncated_values"], 2)
        call = next(r for r in doc["records"] if r["type"] == "tool")
        self.assertIn("truncated", call["input"])
        for fmt in ("md", "html"):
            result, output = self.export(fmt, "--tools", "collapsed", "--tool-limit", "30")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("truncated", output.read_text())
        emoji = self.document("--tools", "full", "--tool-limit", "1", entries=[
            self.entry("assistant", [{"type": "tool_use", "id": "e", "name": "Bash", "input": {}}]),
            self.entry("user", [{"type": "tool_result", "tool_use_id": "e", "content": "😀😀"}]),
        ])
        self.assertEqual(emoji["records"][0]["outputs"][0]["text"], "😀\n… (+1 chars truncated)")

    def test_filters_internal_records_and_attachment_payloads(self):
        entries = [
            self.entry("user", "visible"),
            self.entry("assistant", "SIDECHAIN_SECRET", isSidechain=True),
            self.entry("user", "META_SECRET", isMeta=True),
            self.entry("user", "COMPACTION_SECRET", isCompactSummary=True),
            self.entry("system", "SYSTEM_SECRET"),
            self.entry("assistant", [{"type": "thinking", "thinking": "THINKING_SECRET"}]),
            self.entry("user", [{"type": "image", "source": {"data": "IMAGE_SECRET"}}, {"type": "document", "source": {"url": "FILE_SECRET"}}]),
            self.entry("user", "<system-reminder>REMINDER_SECRET</system-reminder>real text"),
        ]
        for fmt in ("md", "html", "json"):
            result, output = self.export(fmt, entries=entries)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("SECRET", output.read_text())
            self.assertIn("Image omitted", output.read_text())
            self.assertIn("Document omitted", output.read_text())

    def test_thinking_remains_explicit_opt_in(self):
        doc = self.document("--thinking")
        self.assertTrue(any(r["type"] == "thinking" and r["text"] == "PRIVATE_THINKING" for r in doc["records"]))

    def test_command_tags_in_ordinary_prose_preserve_surrounding_text(self):
        text = "prefix <command-name>/fake</command-name> suffix must survive"
        doc = self.document(entries=[self.entry("user", text)])
        self.assertEqual(doc["records"][0]["text"], text)
        command = "<command-name>/test</command-name>\n<command-message>test</command-message>\n<command-args>all</command-args>"
        doc = self.document(entries=[self.entry("user", command)])
        self.assertEqual(doc["records"][0]["text"], "` /test all `")

    def test_nested_and_unclosed_internal_wrappers_are_removed(self):
        for tag in ("system-reminder", "local-command-stdout"):
            for text in (
                f"before <{tag}>OUTER_SECRET<{tag}>INNER_SECRET</{tag}>TAIL_SECRET</{tag}> after",
                f"before <{tag}>UNCLOSED_SECRET",
            ):
                for fmt in ("md", "html", "json"):
                    result, output = self.export(fmt, entries=[self.entry("user", text)])
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn("SECRET", output.read_text())
                    self.assertIn("before", output.read_text())
                    if text.endswith(" after"):
                        self.assertIn(" after", output.read_text())

    def test_titles_respect_internal_exclusions(self):
        for title_type in ("ai-title", "custom-title"):
            for flag in ("isSidechain", "isMeta", "isCompactSummary"):
                for fmt in ("md", "html", "json"):
                    result, output = self.export(fmt, entries=[
                        self.entry("user", "Public title"),
                        {"type": title_type, flag: True, "title": "PRIVATE_TITLE_SECRET"},
                    ])
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn("PRIVATE_TITLE_SECRET", output.read_text(), (title_type, flag, fmt))

    def test_result_timestamps_and_turns_preserve_arrival_order(self):
        doc = self.document("--tools", "full", entries=[
            self.entry("assistant", [{"type": "tool_use", "id": "x", "name": "Read", "input": {}}]),
            self.entry("user", "First user turn"),
            self.entry("user", [{"type": "tool_result", "tool_use_id": "x", "content": "first"}], timestamp="2026-09-10T09:02:00Z"),
            self.entry("assistant", "An intervening message"),
            self.entry("user", [{"type": "tool_result", "tool_use_id": "x", "content": "second"}], timestamp="2026-09-10T09:03:00Z"),
        ])
        self.assertEqual([r["turn"] for r in doc["records"]], [0, 1, 1])
        self.assertEqual([r["id"] for r in doc["records"]], ["record-1", "record-2", "record-3"])
        self.assertEqual([o["text"] for o in doc["records"][0]["outputs"]], ["first", "second"])
        self.assertEqual([o["timestamp"] for o in doc["records"][0]["outputs"]], ["2026-09-10T09:02:00.000Z", "2026-09-10T09:03:00.000Z"])

    def test_relocated_plugin_command_uses_bundled_template(self):
        import shutil
        plugin = self.root / "relocated-plugin"
        binary = plugin / "bin" / "session-to-md"
        binary.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT, binary)
        binary.chmod(0o755)
        template = plugin / "skills/session-export/templates/session.html"
        template.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT.parent.parent / "skills/session-export/templates/session.html", template)
        self.source.write_text(json.dumps(self.entry("user", "Portable plugin")) + "\n")
        output = self.root / "relocated.html"
        result = subprocess.run(["session-to-md", str(self.source), "--format", "html", "--out", str(output)], cwd=self.root, env={**self.env, "PATH": str(binary.parent) + os.pathsep + os.environ["PATH"]}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Portable plugin", output.read_text())

    def test_malformed_lines_unknown_blocks_and_orphan_results_are_visible(self):
        doc = self.document("--tools", "full", entries=[
            self.entry("user", "hello"), None, [],
            {"type": "unknown-future-record"},
            self.entry("assistant", [{"type": "future", "payload": "OMIT_ME"}]),
            self.entry("user", [{"type": "tool_result", "tool_use_id": "orphan", "content": "ORPHAN_SECRET"}]),
        ], raw='{"partial":')
        self.assertEqual(doc["diagnostics"]["malformed_lines"], 1)
        self.assertEqual(doc["diagnostics"]["unsupported_records"], 3)
        self.assertEqual(doc["diagnostics"]["omitted_content_blocks"], 1)
        self.assertEqual(doc["diagnostics"]["orphan_tool_outputs"], 1)
        self.assertNotIn("ORPHAN_SECRET", json.dumps(doc))
        self.assertGreater(len(doc["notes"]), 0)

    def test_ambiguous_ids_cannot_leak_sidechain_results(self):
        call = [{"type": "tool_use", "id": "duplicate", "name": "Bash", "input": {}}]
        doc = self.document("--tools", "full", entries=[
            self.entry("assistant", call),
            self.entry("assistant", call, isSidechain=True),
            self.entry("user", [{"type": "tool_result", "tool_use_id": "duplicate", "content": "AMBIGUOUS_SECRET"}]),
        ])
        self.assertEqual(doc["records"][0]["output_state"], "excluded")
        self.assertEqual(doc["diagnostics"]["ambiguous_tool_outputs"], 1)
        self.assertNotIn("AMBIGUOUS_SECRET", json.dumps(doc))

    def test_html_escapes_source_markup_and_keeps_controls_local(self):
        attack = '</pre><script>alert("bad")</script><img src="https://example.invalid/leak">'
        result, output = self.export("html", "--tools", "full", entries=[
            self.entry("user", attack),
            self.entry("assistant", [{"type": "tool_use", "id": "x", "name": attack, "input": {"x": attack}}]),
            self.entry("user", [{"type": "tool_result", "tool_use_id": "x", "content": attack}]),
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        html = output.read_text()
        self.assertNotIn(attack, html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("Content-Security-Policy", html)
        self.assertIn("default-src 'none'", html)
        self.assertIn("<details open>", html)
        self.assertIn('id="expand-tools"', html)
        self.assertIn('href="#record-1"', html)

    def test_markdown_has_turn_index_and_safe_tool_blocks(self):
        result, output = self.export("md", "--tools", "collapsed")
        self.assertEqual(result.returncode, 0, result.stderr)
        body = output.read_text()
        self.assertIn("## Conversation", body)
        self.assertIn('id="record-1"', body)
        self.assertIn("<pre><code>", body)
        self.assertIn("No output recorded", body)
        self.assertNotIn("<details open>", body)

    def test_html_summary_counts_only_included_records(self):
        for mode, tools_count in (("none", 0), ("full", 2)):
            result, output = self.export("html", "--tools", mode)
            self.assertEqual(result.returncode, 0, result.stderr)
            body = output.read_text()
            for key, count in (("turns", 2), ("messages", 4), ("tools", tools_count)):
                self.assertIn(f'data-stat="{key}">{count}</div>', body)
            self.assertIn("Tool calls included", body)

    def test_bad_input_fails_before_creating_output(self):
        for entries in ([], [None], [self.entry("system", "internal")]):
            result, output = self.export(entries=entries)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no exportable", result.stderr)
            self.assertFalse(output.exists())

    def test_invalid_options_extensions_and_dates(self):
        for args in (("--format", "pdf"), ("--tool-limit", "0"), ("--tool-limit", "1x"), ("--last", "999999999999999999999"), ("--out", str(self.root / "wrong.md"))):
            result, _ = self.export("json", *args)
            self.assertNotEqual(result.returncode, 0, args)
            self.assertNotIn("at main", result.stderr)
        doc = self.document(entries=[self.entry("user", "hello", timestamp="not-a-date")])
        self.assertEqual(doc["records"][0]["timestamp"], "")
        self.assertNotIn("NaN", json.dumps(doc))

    def test_output_mode_and_symlink_refusal(self):
        result, output = self.export()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        target = self.root / "untouched"
        target.write_text("original")
        link = self.root / "linked.json"
        link.symlink_to(target)
        result, _ = self.export("json", "--out", str(link))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), "original")

    def test_selection_and_listing_respect_config_dir_without_prose(self):
        cwd = str(Path.cwd())
        import re
        project = self.root / "projects" / re.sub(r"[^A-Za-z0-9]", "-", cwd)
        project.mkdir(parents=True)
        for index, name in enumerate(("older", "newer")):
            file = project / f"{name}.jsonl"
            file.write_text(json.dumps(self.entry("user", f"PRIVATE_PROMPT_{name}")) + "\n")
            os.utime(file, (index + 1, index + 1))
        def invoke(args):
            return subprocess.run(["node", str(SCRIPT), *args], env=self.env, text=True, capture_output=True)
        listing = invoke(["--list"])
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertIn("newer", listing.stdout)
        self.assertNotIn("PRIVATE_PROMPT", listing.stdout)
        for index, args in enumerate((["older"], ["--last", "2"], [])):
            output = self.root / f"selected-{index}.json"
            result = invoke([*args, "--format", "json", "--out", str(output)])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text())["metadata"]["session"], "newer" if index == 2 else "older")
        rejected = invoke(["../outside"])
        self.assertNotEqual(rejected.returncode, 0)


suite = unittest.defaultTestLoader.loadTestsFromTestCase(ExportTests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
failures += len(result.failures) + len(result.errors)
print("\nALL PASS" if not failures else f"\n{failures} FAILURES")
raise SystemExit(1 if failures else 0)
