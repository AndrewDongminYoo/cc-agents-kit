# Development environment access

Keep real values in their intended local dotenv file or secret store.
Never copy them into chat, another gitignored script, `local.properties`, encoded command text or a renamed file to escape a refusal.
A gitignore entry is not authorization.
Maintain a tracked `.env.example` containing key names, empty assignments and comments, without real defaults or credentials.

## Choose the development paths explicitly

By default this guard denies live dotenv paths, including names that look like development files.
The operator can designate exact files for development access through `CC_GUARD_DEV_ENV_PATHS`, a JSON array in the operator-controlled hook environment.
The setting is empty/unset by default; the plugin does not install it or select paths.
For example, an operator could review this settings fragment for their own chosen path:

```json
{
  "env": {
    "CC_GUARD_DEV_ENV_PATHS": "[\"/absolute/project/.env.development\"]"
  }
}
```

This is an example, not an instruction to copy a whole settings file or register that placeholder.
Store the setting outside agent-writable configuration and review changes as permission changes.
Do not let the agent expand the list after a refusal.
The operator must verify that each selected file contains development credentials suitable for agent access.
File names do not decide purpose: `.env.local` is not automatically safe, and an operator-designated path is not reclassified from its suffix.
Do not register production secrets or authentication stores.

Each entry must be an absolute, normalized dotenv file path, with no glob, traversal, shell metacharacters or symlink components.
Spaces are supported; matching is exact and case-sensitive even on case-insensitive filesystems.
A missing leaf is permitted for initial setup, but existing leaves must be regular files.
The setting accepts at most 64 paths and 64 KiB of JSON.
Any invalid entry disables this optional policy for the call.
The helper inspects path metadata, never dotenv contents.
Its symlink check is not atomic with the later tool operation; keep selected paths stable.

## Use the ordinary development workflow

Only `permission_mode: auto` is eligible.
For a tool call whose recognized live dotenv references all identify designated paths, this hook exits silently without a permission decision.
It does not return `allow` or `ask`.
Existing auto evaluation, explicit permissions, other hooks and the sandbox still decide whether the action runs.
Auto mode can ask or refuse; abstention does not promise a classifier call or automatic success.
Every other mode retains the existing dotenv denial.

Direct file tools can use an exact absolute path or a relative path resolved against the tool event's absolute `cwd`.
Bash commands must spell the designated absolute path literally, quoted when needed.
This avoids guessing the working directory after `cd`, subshells or functions.
For example, after the operator designates their actual development file:

```bash
source '/absolute/project/.env.development' && npm run dev
set -a; . '/absolute/project/.env.development'; set +a; npm test
python3 development-job.py --env-file='/absolute/project/.env.development'
```

These commands go through the normal tool/permission workflow without a special runner or repeated whole-script pasting through `!`.
Relative Bash dotenv references, globs, ambiguous expressions and an additional unregistered dotenv reference keep the original guard decision.
Exact template variants such as `.env.example` retain their existing treatment.
The Keychain-derived `.zprofile.secrets` check runs before this policy and cannot be exempted.

**The agent can read and use the values of a designated development file.**
This is the accepted tradeoff, not value-free inspection.
Sourcing executes shell code, so review the development file's provenance as well as its contents.
Use the values only for the requested development work; avoid unnecessary printing, logging or replication.
No entry-script hash, command identity, dependency safety or output/network isolation is promised.
The old inspector approval and exact-command consumer policies are not part of this design.

## Protection boundaries and overlapping denials

This remains an accidental-access guard based on literal tool inputs, not a shell interpreter or filesystem sandbox.
Aliases, functions, variable indirection and files read later by a script are not inferred from the command string.
Do not use those mechanisms to bypass a refusal.
Unregistered dotenv references visible to the existing guard remain denied.
Production or authentication data requiring protection against indirect access must also be excluded by host permissions or an OS sandbox.
This setting applies only to the dotenv decision in this hook; it grants no exemption for auth files, credential stores, other tools or other guards.

Before applying a path list, review overlapping rules such as `Read(**/.env*)`, `Bash(source *)`, project permissions, managed policy and other secret hooks.
An explicit deny may still block a designated path.
Show a before/after permission diff and get approval for each necessary change instead of removing a broad deny silently.
Claude and Codex hook adapters/configuration are separate; this change does not update Codex settings or guarantee equivalent Codex behavior.
Actual approval UI and real-secret use are not tested here.

The optional matcher uses protected `/usr/bin/python3` 3.9+ with `-I -S`; it never chooses a project Python from `PATH`.
The hook uses `/bin/bash -p` and accepts only the exact `ABSTAIN` token.
Protect the installed plugin and hook settings from agent writes.
Missing Python, malformed settings or uncertain input leaves the existing guard in control.
Output masking remains a fallback with known gaps, not permission to disclose values.

## Temporary artifacts

Create one task-owned directory beneath an approved temporary root.
Keep a manifest with task/session identity, creator, canonical paths, creation time, purpose, retention and completion state, without secret values.
On normal exit, clean only owned artifacts explicitly authorized for cleanup.
After interruption, offer a metadata-only dry run.

The dry run lists exact paths, ownership, size, age and unresolved active use.
Exclude shared app caches, active sessions, symlinks, unknown-owner artifacts and anything not in the manifest.
Recent mtime or a matching owner is not proof that a file is disposable.
If a path is refused, stop; another deletion command is not an alternate permission path.

Confirm the exact artifacts before moving them to Trash.
Trash is recoverable and **does not immediately free disk space** on the same volume.
Permanent removal or emptying Trash is a separate destructive decision.
A broad `rm -rf /*` permission pattern also matches scoped absolute paths; it is not root-only protection.
Review such settings separately, with previous and proposed boundaries side by side.
