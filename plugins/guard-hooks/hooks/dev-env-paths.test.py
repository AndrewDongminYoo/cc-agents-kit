#!/usr/bin/env python3
"""Synthetic hook inputs only; never execute their source/read commands."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

HOOK = Path(__file__).resolve().with_name("secrets-path-guard.sh")


class DevelopmentPathsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "project with spaces"
        self.project.mkdir()
        self.dev = self.project / ".env.dev"
        self.production = self.project / ".env.production"
        self.dev.touch()
        self.production.touch()

    def invoke(self, inputs, mode="auto", paths=None, tool="Bash", cwd=None, extra=None):
        env = dict(os.environ)
        for name in ("CC_GUARD_DISABLE_SECRETS_PATH", "CC_GUARD_DEV_ENV_PATHS", "CC_GUARD_ENV_POLICY", "CC_GUARD_ENV_POLICY_SHA256"):
            env.pop(name, None)
        if paths is not None:
            env["CC_GUARD_DEV_ENV_PATHS"] = paths if isinstance(paths, str) else json.dumps(paths)
        env.update(extra or {})
        payload = {"tool_name": tool, "permission_mode": mode,
                   "cwd": str(cwd or self.project), "tool_input": inputs}
        return subprocess.run(["/bin/bash", "-p", str(HOOK)], input=json.dumps(payload),
                              capture_output=True, text=True, env=env)

    def expect(self, result, code):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stdout, "", "abstention must never emit allow or ask")
        if code == 0:
            self.assertEqual(result.stderr, "")

    def test_default_off_and_auto_only(self):
        inputs = {"command": "source " + shlex.quote(str(self.dev))}
        self.expect(self.invoke(inputs), 2)
        self.expect(self.invoke(inputs, paths=[]), 2)
        for mode in ("default", "acceptEdits", "plan", "dontAsk", "bypassPermissions", "", "unknown"):
            with self.subTest(mode=mode):
                self.expect(self.invoke(inputs, mode=mode, paths=[str(self.dev)]), 2)
        self.expect(self.invoke(inputs, paths=[str(self.dev)]), 0)

    def test_normal_source_and_jobs_need_no_wrapper(self):
        absolute = shlex.quote(str(self.dev))
        for command in ("source " + absolute, ". " + absolute,
                        "source " + absolute + ' && npm test -- --token "$DEV_TOKEN"',
                        "set -a; . " + absolute + "; set +a; npm run dev",
                        "python3 task.py --env-file=" + absolute, "cat " + absolute):
            with self.subTest(command=command):
                self.expect(self.invoke({"command": command}, paths=[str(self.dev)]), 0)

    def test_direct_tools_resolve_relative_paths_against_cwd(self):
        for tool, field in (("Read", "file_path"), ("Edit", "file_path"), ("Write", "file_path"), ("Grep", "path")):
            for path in (str(self.dev), self.dev.name, "./" + self.dev.name):
                with self.subTest(tool=tool, path=path):
                    self.expect(self.invoke({field: path}, tool=tool, paths=[str(self.dev)]), 0)
        self.expect(self.invoke({"file_path": self.dev.name}, tool="Read", cwd=self.root, paths=[str(self.dev)]), 2)

    def test_unregistered_neighbors_and_mixed_fields_stay_denied(self):
        for other in (self.production, Path(str(self.dev) + ".local"), self.root / ".env.dev"):
            self.expect(self.invoke({"command": "cat " + shlex.quote(str(self.dev)) + " " + shlex.quote(str(other))}, paths=[str(self.dev)]), 2)
        self.expect(self.invoke({"file_path": str(self.dev), "path": str(self.production)}, tool="Read", paths=[str(self.dev)]), 2)
        # Names do not classify purpose: an explicitly selected synthetic path works.
        self.expect(self.invoke({"file_path": str(self.production)}, tool="Read", paths=[str(self.production)]), 0)

    def test_relative_bash_and_ambiguous_paths_keep_denial(self):
        for command in ("source .env.dev", "cd elsewhere && source .env.dev",
                        "cat " + shlex.quote(str(self.dev)) + "*",
                        "cat " + shlex.quote(str(self.project / ".." / ".env.dev")),
                        "eval " + shlex.quote("source " + str(self.dev)),
                        "cat " + shlex.quote(str(self.dev)) + " .env'production'"):
            with self.subTest(command=command):
                self.expect(self.invoke({"command": command}, paths=[str(self.dev)]), 2)

    def test_templates_and_keychain_protection_remain(self):
        self.expect(self.invoke({"command": "cat .env.example " + shlex.quote(str(self.dev))}, paths=[str(self.dev)]), 0)
        for inputs in ({"file_path": "/Users/me/.ZPROFILE.SECRETS"},
                       {"command": "cat " + shlex.quote(str(self.dev)) + " ~/.zprofile.secrets"}):
            self.expect(self.invoke(inputs, paths=[str(self.dev)]), 2)

    def test_invalid_settings_and_non_dotenv_entries_do_not_exempt(self):
        for paths in ("not json", "{}", '[null]', [".env.dev"], [str(self.dev) + "*"],
                      [str(self.project / ".." / ".env.dev")], [str(self.root / "auth.json")],
                      [str(self.dev), "/Users/me/.zprofile.secrets"]):
            with self.subTest(paths=paths):
                self.expect(self.invoke({"file_path": str(self.dev)}, tool="Read", paths=paths), 2)

    def test_symlinks_cannot_retarget_registered_paths(self):
        linked = self.root / "link"
        linked.symlink_to(self.project, target_is_directory=True)
        aliased = linked / self.dev.name
        self.expect(self.invoke({"file_path": str(aliased)}, tool="Read", paths=[str(aliased)]), 2)
        self.dev.unlink()  # Only this test's empty fixture.
        self.dev.symlink_to(self.production)
        self.expect(self.invoke({"file_path": str(self.dev)}, tool="Read", paths=[str(self.dev)]), 2)

    def test_missing_leaf_is_supported_but_parent_must_exist(self):
        leaf = self.project / ".env.new"
        self.expect(self.invoke({"file_path": str(leaf)}, tool="Read", paths=[str(leaf)]), 0)
        missing_parent = self.root / "not-created" / ".env.new"
        self.expect(self.invoke({"file_path": str(missing_parent)}, tool="Read", paths=[str(missing_parent)]), 2)

    def test_caller_runtime_cannot_manufacture_abstention(self):
        shim = self.root / "python3"
        shim.write_text("#!/bin/sh\nprintf ABSTAIN\n")
        shim.chmod(0o700)
        (self.root / "sitecustomize.py").write_text("print('ABSTAIN')\n")
        self.expect(self.invoke({"command": "cat " + shlex.quote(str(self.production))}, paths=[str(self.dev)],
                               extra={"PATH": str(self.root) + os.pathsep + os.environ["PATH"], "PYTHONPATH": str(self.root)}), 2)


if __name__ == "__main__":
    unittest.main()
