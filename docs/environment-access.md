# Development environment access

Keep real values in their intended local dotenv file or secret store.
Never copy them into chat, another gitignored script, `local.properties`, encoded command text or a renamed file to escape a refusal.
A gitignore entry is not authorization.
Maintain a tracked `.env.example` containing key names, empty assignments and comments, without real defaults or credentials.

## Choose the development paths explicitly

By default this guard denies live dotenv paths, including names that look like development files.
The user can designate exact files for development access through `CC_GUARD_DEV_ENV_PATHS`, a JSON array in the user-controlled hook environment.
The setting is empty/unset by default; the plugin does not install it or select paths.
For example, a user could review this settings fragment for their own chosen path:

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
The user must verify that each selected file contains development credentials suitable for agent access.
File names do not decide purpose: `.env.local` is not automatically safe, and a user-designated path is not reclassified from its suffix.
Do not register production secrets or authentication stores.

Each entry must be an absolute, normalized dotenv file path, with no glob, traversal, shell metacharacters or symlink components.
This excludes zsh extended-glob operators `^`, `#` and `~` anywhere in a designated path, even when the command quotes it.
Spaces are supported; matching is exact and case-sensitive even on case-insensitive filesystems.
A missing leaf is permitted for initial setup, but existing leaves must be regular files.
The setting accepts at most 64 paths and 64 KiB of JSON.
Any invalid entry disables this optional policy for the call.
The helper inspects path metadata, never dotenv contents.
Its symlink check is not atomic with the later tool operation; keep selected paths stable.

## Use the ordinary development workflow

For designated paths, only `permission_mode: auto` is eligible; the key-name listing below is the one exception that needs neither.
For a tool call whose recognized live dotenv references all identify designated paths, this hook exits silently without a permission decision.
It does not return `allow` or `ask`.
Existing auto evaluation, explicit permissions, other hooks and the sandbox still decide whether the action runs.
Auto mode can ask or refuse; abstention does not promise a classifier call or automatic success.
Every other mode retains the existing dotenv denial for designated paths.

Direct file tools can use an exact absolute path or a relative path resolved against the tool event's normalized, absolute, existing and symlink-free `cwd`.
Bash commands spell the designated absolute path literally, quoted when needed, with one exception: the operand of a `source` or `.` that is the first command, or that follows only an exact leading `set -a;`, may be relative.
It resolves against the same `cwd` as a direct tool path, because no `cd`, function or subshell can run before the first command.
The hook assumes the event's `cwd` is the directory the Bash command starts in, including a `cd` carried over from an earlier call.
The resolved file must exist, since zsh `source` searches `PATH` for a missing one.
A name without a slash (`.env.development`) is also refused when a directory on the hook's `PATH` holds that name, because bash `source` and `.` search `PATH` first; `./.env.development` skips that search.
For example, after the user designates their actual development file:

```bash
source '/absolute/project/.env.development' && npm run dev
source .env.development && npm run dev
set -a; . ./.env.development; set +a; npm test
python3 development-job.py --env-file='/absolute/project/.env.development'
```

These commands go through the normal tool/permission workflow without a special runner or repeated whole-script pasting through `!`.
Other relative Bash dotenv references, globs, ambiguous expressions and an additional unregistered dotenv reference keep the original guard decision.
An option or assignment prefix before `=` cannot hide another live dotenv reference.
Exact template variants such as `.env.example` retain their existing treatment.
The Keychain-derived `.zprofile.secrets` check runs before this policy and cannot be exempted.

**The agent can read and use the values of a designated development file.**
This is the accepted tradeoff, not value-free inspection.
Sourcing executes shell code, so review the development file's provenance as well as its contents.
Use the values only for the requested development work; avoid unnecessary printing, logging or replication.
No entry-script hash, command identity, dependency safety or output/network isolation is promised.
The old inspector approval and exact-command consumer policies are not part of this design.

## List key names without values

`env-keys <dotenv file>...` ships in the plugin's `bin/` and prints only the names that start an assignment line, one per line, prefixed with the file when more than one is named.
It reads the file the way the shell would split it: lines inside an open `'...'`, `"..."` or `$'...'` quote print nothing, and the listing ends at a heredoc, at a line that ends in a backslash outside `'...'` (bash joins the next line, so a token such as `$` and `'...'` can span the break), and at a `$(...)`, backtick, `(...)` or `${...}` left open at the end of a line.
A `#` starts a comment only at the start of a line or after unescaped whitespace.
A misread can hide a later key but is meant never to print part of a value; `bin/env-keys.test.py` checks that against bash itself over 5,000 generated files, and the check fails on the two earlier parsers that review found leaking.
It refuses a file whose name is not a dotenv name, a dotenv name that is a symbolic link or not a regular file (a `.env` link to a private key would otherwise pass the name check), and never repeats file content in a message.

A Bash command that is exactly that one command, with plain or single-quoted path words, needs no designation and abstains in every permission mode.
The program word is the bare `env-keys` or the plugin's own absolute path.
Anything else in the command (a pipe, a redirection, a second command, a variable, a glob, an assignment or runner prefix, a function definition) keeps the original decision, because an abstention skips every later check of the command.

The exemption reads the command text, not what the shell will run.
A shell function, an alias or an earlier `PATH` entry named `env-keys`, defined outside the command, runs instead of the plugin's tool and could print values; the same shell-function lookup is why the old inspector's value-free guarantee was withdrawn (#41).
This listing therefore inherits the guard's accidental-access scope: it expects no such name in the user's shell, and it is not protection against an agent that plants one.

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
