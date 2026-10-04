# Environment access without copying secrets

The default guard still denies direct reads, writes and `source .env`. Sourcing
executes shell code; it is not a key lookup. Do not ask for values in chat, encode
them into a command, rename the file, or copy them into another gitignored script
or `local.properties` to escape a refusal. A gitignore entry is not authorization.

## Inspect state

Maintain a tracked `.env.example` with required key names, empty assignments and
comments explaining each key. Do not place real defaults or credentials there.
After reviewing the plugin installation, request its **absolute** `bin/env-status`
executable with exactly `--schema .env.example --file .env`, from the project root.
The secrets hook returns `ask`, not `allow`, for this call. Do not pre-allow a
general interpreter or a wildcard command to run it. Other deny rules still win.

The inspector returns only schema keys, `present` and `empty`. A missing key has
`present: false, empty: null`; an empty assignment has both booleans true. Extra
source keys are omitted. Failures return no partial data or input fragments.
Both files must be relative paths beneath the working directory, regular files,
without symlink components and no larger than 1 MiB each.

This is a strict literal dotenv subset: one assignment per line, optional
`export`, blank lines and comments, unquoted values without whitespace, or simple
single/double quoted values. Empty quotes are empty. Duplicate keys, interpolation,
backticks, escapes and multiline values are rejected. It neither evaluates shell
code nor promises to reproduce every framework's dotenv semantics.

## Approve one recurring consumer

For a small number of recurring jobs, the operator can opt in to an exact purpose
script instead of repeatedly pasting a whole script through `!`. No runner that
accepts arbitrary commands is supplied. Review a purpose-specific executable that
loads only the needed keys and performs the fixed development operation without
printing secrets. It must not forward arbitrary arguments to a shell/interpreter.

Install the following policy **outside all agent-writable roots**, owned by the
operator and not group/world writable. The host must enforce this location and
protect the hook configuration; the hook cannot infer host access from `cwd` or
Unix ownership. Configure `CC_GUARD_ENV_POLICY` to its absolute path and pin its
file digest in `CC_GUARD_ENV_POLICY_SHA256`, both in the operator-controlled hook
environment. Changing the policy requires operator review and a new digest. The
agent must not write the live policy or either setting. No policy is installed by
this plugin. Missing/mismatched digest leaves the original denial in place.

```json
{
  "version": 1,
  "consumers": [{
    "cwd": "/path/to/project",
    "argv": ["/path/to/project/scripts/check-development", "--config", ".env"],
    "code_sha256": "<sha256 of the reviewed entry script>",
    "purpose": "Check the development service",
    "env_files": [".env"],
    "keys": ["DEV_API_TOKEN"],
    "destinations": ["https://development.example.invalid"]
  }]
}
```

Use only a few stable jobs. Record the canonical command from Python's
`shlex.join(argv)` when registering one; the recognizer requires that exact
quoting form. It rejects shell operators, expansion, substitution and wrappers.
The executable must be an absolute script path with a shebang, with no symlinks
in its path or the policy path. The hook compares
the canonical working directory, full argv and entry-script hash, then returns
an approval request describing the declared purpose, files, keys and destinations.
A changed script needs operator review and a new hash, never an automatic update.
An unregistered command gets the existing guard decision.

**The policy describes the trust boundary; it does not enforce key or network
isolation.** The code hash covers only the entry script, not imports, dependencies,
interpreters, tools on PATH or files opened later. The check is before approval,
not an atomic check-and-execute; keep the reviewed code stable through execution
and use a protected snapshot if another process could change it. The approved process can read
and disclose everything the surrounding sandbox permits. Review its dependency
and logging behavior and enforce any required network/filesystem limits in that
sandbox. Approval covers secret access and the operation, not permission to emit
values. Ordinary tests should use synthetic values and no network instead.

This path is a hook approval request, not an automatic grant. Explicit deny rules
and other hooks remain effective. In an interactive Claude Code version supporting
hook `ask` in auto mode (the relevant fix shipped in 2.1.211), it can show a normal
approval prompt. Noninteractive or unsupported surfaces may refuse it. Tests here
validate hook JSON with synthetic data, not the live approval UI. Codex adapters
are separate and are not covered by these Claude hook tests.

## Abstention and retained protection

Only in `permission_mode: auto`, a canonical `/usr/bin/printf` with a fixed `%s`
or `%s\\n` format and literal arguments is recognized as inert data. It returns
no decision; normal harness permissions still apply. This is not `allow` and does
not assert that every action reaches a classifier. Other modes and ambiguous
syntax retain the old denial. The Keychain-derived protected file remains denied.

Python 3.9+ enables these paths. If the recognizer is unavailable or fails, the
existing shell guard still decides. Auto mode is not a replacement for secret
protection: some ordinary reads need no classifier review. Output masking is a
fallback with known gaps, not a license to print secrets.

## Temporary artifacts

Create one task-owned directory beneath an approved temporary root. Keep a
manifest with task/session identity, creator, canonical paths, creation time,
purpose, retention and completion state. Never store secret values in it. On
normal exit, clean only the owned artifacts explicitly authorized for cleanup;
after interruption, offer a metadata-only dry run on the next session.

The dry run lists exact paths, ownership, size, age and unresolved active use.
Exclude shared app caches, active sessions, symlinks, unknown-owner artifacts and
anything not in the manifest. A recent mtime or a matching owner is not proof that
a file is safe to remove. If a path is refused, stop; another deletion command is
not an alternate permission path.

Offer an explicit confirmation for those exact artifacts before moving them to
Trash. Trash is recoverable and **does not immediately free disk space** on the
same volume. Permanent removal/emptying Trash is a separate destructive decision.
Do not equate broad `rm -rf /*` permission patterns with a root-only protection:
that pattern also matches scoped absolute paths. Review settings separately from
the plugin, with the previous and proposed protection boundaries side by side.
