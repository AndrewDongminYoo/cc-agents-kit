# Explicit development environment paths

It is accepted that the agent can read values from explicitly designated development dotenv files.
For those paths in auto mode, this hook leaves the decision to existing harness permissions and auto evaluation.
It must not emit `allow`, claim value-free execution, or require repeated manual pasting of a whole script.

## Approved scope

- Default off: user-controlled `CC_GUARD_DEV_ENV_PATHS` is a JSON array of exact absolute development dotenv paths.
- Only `permission_mode: auto` can abstain for registered paths.
- Direct file tools accept absolute paths or relative paths against the supplied absolute cwd.
- Bash must spell the registered absolute path literally, including in ordinary `source`/`.` commands chained with a development job.
  Relative Bash paths, globs and ambiguous expressions retain the existing decision.
- Every live dotenv reference recognized by the existing guard must be registered before abstaining.
  A registered path cannot exempt a second unregistered reference.
- The user classifies development and production files; names never classify them automatically.
- Preserve Keychain protection, unregistered dotenv denial, other hooks, explicit deny rules and sandbox restrictions.
  The setting is not an exemption for auth or credential files.
- Remove the exact-command/script-hash consumer model and inspector-specific approval path.
  Do not authenticate or claim to know what a mutable shell executes.
- Keep template-schema, no-secret-copying and task-owned temporary-file guidance.

## Non-goals and authority

This is a literal-input guardrail, not runtime access control.
Aliases, functions, variable indirection and later script reads cannot be inferred from the input string.
The agent can read and use designated development values; auto mode can still ask or refuse.
Production/auth protection against indirect access belongs in permissions and the OS sandbox.

No live settings, installed hooks, credentials or real dotenv files are changed or read.
No actual development paths are selected here.
Installation, permission changes, deletion, merge and deployment remain separate decisions.
Do not touch staged-secret-parser code being developed in another branch.

## Acceptance

Synthetic hook inputs cover default-off, modes, exact/relative direct paths, absolute Bash sourcing, mixed references, templates, invalid settings, neighbors, traversal, symlinks and Keychain protection.
No test executes a secret-consuming payload or reads a real dotenv file.
Caller Python shims must not manufacture abstention.
Run all repository checks and current-head CI/reviews within the approved review boundary.
Visual approval is not applicable.

## Reconciliation, 2026-11-10 (guard-hooks 0.6.0)

Two statements above no longer describe the shipped code; `plugins/guard-hooks/hooks/_dev_env_paths.py` and `docs/environment-access.md` are the authority.

- "Relative Bash paths ... retain the existing decision": a relative designated path is now accepted as the operand of a `source` or `.` that starts the command, optionally after `set -a;`, because nothing can change the directory before the first command. Tests: `test_leading_relative_source_resolves_against_cwd` and its two neighbours in `dev-env-paths.test.py`.
- "Remove ... inspector-specific approval path": a key-name listing came back as `bin/env-keys`, exempt in every mode when it is the whole command. It does not restore the withdrawn guarantee: the shell-function lookup that invalidated the inspector applies to it too, and the environment guide says so. Tests: `KeysOnlyTests` in `dev-env-paths.test.py` and `bin/env-keys.test.py`.

The change was made because a guard that refused every key listing and every relative `source` was turned off entirely, which protected nothing.
