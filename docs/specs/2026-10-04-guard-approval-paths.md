# Explicit development environment paths

The operator accepts that the agent can read values from explicitly designated development dotenv files.
For those paths in auto mode, this hook leaves the decision to existing harness permissions and auto evaluation.
It must not emit `allow`, claim value-free execution, or require repeated manual pasting of a whole script.

## Approved scope

- Default off: operator-controlled `CC_GUARD_DEV_ENV_PATHS` is a JSON array of exact absolute development dotenv paths.
- Only `permission_mode: auto` can abstain for registered paths.
- Direct file tools accept absolute paths or relative paths against the supplied absolute cwd.
- Bash must spell the registered absolute path literally, including in ordinary `source`/`.` commands chained with a development job.
  Relative Bash paths, globs and ambiguous expressions retain the existing decision.
- Every live dotenv reference recognized by the existing guard must be registered before abstaining.
  A registered path cannot exempt a second unregistered reference.
- The operator classifies development and production files; names never classify them automatically.
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
Run all repository checks and current-head CI/reviews within the operator-approved review boundary.
Visual approval is not applicable.
