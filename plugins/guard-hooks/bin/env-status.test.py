#!/usr/bin/env python3
"""Exercise only fresh synthetic files; no user dotenv or credential access."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

TOOL = Path(__file__).resolve().with_name("env-status")
VALUE = "SYNTHETIC_VALUE_MUST_NEVER_APPEAR"


class StatusTests(unittest.TestCase):
    def run_status(self, source, schema="PRESENT=\nEMPTY=\nMISSING=\n", source_path="input.data"):
        self.assertTrue(TOOL.is_file(), "the approved state inspector is not implemented")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "schema.example").write_text(schema)
            (root / "input.data").write_text(source)
            if source_path == "link.data":
                (root / source_path).symlink_to(root / "input.data")
            p = subprocess.run([str(TOOL), "--schema", "schema.example", "--file", source_path],
                               cwd=root, text=True, capture_output=True)
            self.assertNotIn(VALUE, p.stdout + p.stderr)
            return p

    def test_missing_empty_and_present_without_values(self):
        p = self.run_status(f'PRESENT="{VALUE}"\nEMPTY=\nEXTRA={VALUE}\n')
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout), {"keys": [
            {"key": "PRESENT", "present": True, "empty": False},
            {"key": "EMPTY", "present": True, "empty": True},
            {"key": "MISSING", "present": False, "empty": None}]})

    def test_error_paths_never_echo_input(self):
        for data in [f"PRESENT={VALUE}\nPRESENT=again", f"bad syntax {VALUE}",
                     f"PRESENT=$(echo {VALUE})", "PRESENT=x\n" + VALUE * 40000]:
            p = self.run_status(data)
            self.assertNotEqual(p.returncode, 0)
            self.assertEqual(p.stdout, "")

    def test_symlinks_and_escape_are_rejected(self):
        for path in ["link.data", "../input.data", "/outside.data"]:
            p = self.run_status("PRESENT=value\n", source_path=path)
            self.assertNotEqual(p.returncode, 0)
            self.assertEqual(p.stdout, "")

    def test_schema_must_not_contain_values(self):
        p = self.run_status("PRESENT=value\n", schema=f"PRESENT={VALUE}\n")
        self.assertNotEqual(p.returncode, 0)

    def test_empty_quoted_values_and_comments(self):
        p = self.run_status("export PRESENT='literal value' # note\nEMPTY=\"\"\n# comment\n")
        self.assertEqual(p.returncode, 0)
        self.assertEqual([k["empty"] for k in json.loads(p.stdout)["keys"]], [False, True, None])


if __name__ == "__main__":
    unittest.main()
