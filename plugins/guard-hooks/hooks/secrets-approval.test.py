#!/usr/bin/env python3
"""Synthetic payloads only: never execute a command carried by a hook payload."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks/secrets-path-guard.sh"
INSPECTOR = ROOT / "bin/env-status"


def invoke(command, mode="auto", cwd="/proj", policy=None, tool="Bash", policy_digest=None):
    env = dict(os.environ)
    env.pop("CC_GUARD_DISABLE_SECRETS_PATH", None)
    env.pop("CC_GUARD_ENV_POLICY", None)
    env.pop("CC_GUARD_ENV_POLICY_SHA256", None)
    if policy:
        env["CC_GUARD_ENV_POLICY"] = str(policy)
        env["CC_GUARD_ENV_POLICY_SHA256"] = policy_digest or hashlib.sha256(policy.read_bytes()).hexdigest()
    return subprocess.run(["/bin/bash", str(HOOK)], input=json.dumps({
        "tool_name": tool, "permission_mode": mode, "cwd": cwd,
        "tool_input": {"command": command},
    }), text=True, capture_output=True, env=env)


class ApprovalTests(unittest.TestCase):
    def test_literal_data_abstains_only_in_auto(self):
        command = "/usr/bin/printf '%s\\n' 'source .env'"
        p = invoke(command)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))
        for mode in ["default", "dontAsk", "bypassPermissions", "", "unknown"]:
            self.assertEqual(invoke(command, mode).returncode, 2)

    def test_secret_commands_stay_denied(self):
        for command in ["cat .env", "source .env", "python3 tool.py .env",
                        "/usr/bin/printf '%s' \"$(cat .env)\"",
                        "/usr/bin/printf '%s' '.env' > output.txt",
                        "/usr/bin/printf '%s' '.env'; source .env"]:
            self.assertEqual(invoke(command).returncode, 2)

    def test_shell_expansion_is_not_literal_data(self):
        for command in ["/usr/bin/printf '%s' .env*", "/usr/bin/printf '%s' ~user/.env",
                        "/usr/bin/printf '%s' .env{,.local}"]:
            self.assertEqual(invoke(command).returncode, 2)

    def test_inspector_requests_approval_never_allow(self):
        command = shlex.join([str(INSPECTOR), "--schema", ".env.example", "--file", ".env"])
        for mode in ["auto", "default", "dontAsk", "unknown"]:
            p = invoke(command, mode)
            self.assertEqual(p.returncode, 0)
            decision = json.loads(p.stdout)["hookSpecificOutput"]
            self.assertEqual(decision["permissionDecision"], "ask")
        for bad in [command + " && cat .env", "sh -c " + shlex.quote(command),
                    command + " --command id", command.replace(str(INSPECTOR), "/tmp/env-status")]:
            self.assertEqual(invoke(bad).returncode, 2)

    def test_opt_in_consumer_is_bound_to_code_cwd_and_exact_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            cwd = base / "project"
            cwd.mkdir()
            code = cwd / "check-development"
            code.write_text("#!/bin/sh\nexit 0\n")
            code.chmod(0o700)
            argv = [str(code), "--config", ".env"]
            policy = base / "policy.json"
            entry = {"cwd": str(cwd), "argv": argv, "code_sha256": hashlib.sha256(code.read_bytes()).hexdigest(),
                     "purpose": "Development connectivity check", "env_files": [".env"],
                     "keys": ["SYNTHETIC_KEY"], "destinations": []}
            policy.write_text(json.dumps({"version": 1, "consumers": [entry]}))
            policy.chmod(0o600)
            command = shlex.join(argv)
            p = invoke(command, cwd=str(cwd), policy=policy)
            self.assertEqual(p.returncode, 0)
            self.assertEqual(json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"], "ask")
            for args in [{}, {"cwd": str(cwd)}, {"cwd": str(base), "policy": policy}]:
                self.assertEqual(invoke(command, **args).returncode, 2)
            self.assertEqual(invoke(command + " --debug", cwd=str(cwd), policy=policy).returncode, 2)
            self.assertEqual(invoke(command, cwd=str(cwd), policy=policy, policy_digest="0" * 64).returncode, 2)
            linked = cwd / "linked"
            linked.symlink_to(cwd, target_is_directory=True)
            entry["argv"][0] = str(linked / code.name)
            policy.write_text(json.dumps({"version": 1, "consumers": [entry]}))
            self.assertEqual(invoke(shlex.join(entry["argv"]), cwd=str(cwd), policy=policy).returncode, 2)
            entry["argv"][0] = str(code)
            policy.write_text(json.dumps({"version": 1, "consumers": [entry]}))
            code.write_text("#!/bin/sh\necho changed\n")
            self.assertEqual(invoke(command, cwd=str(cwd), policy=policy).returncode, 2)


if __name__ == "__main__":
    unittest.main()
