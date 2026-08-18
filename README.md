# cc-agents-kit

A Claude Code plugin marketplace.
Each plugin is scoped to one pain, so you install the part you want and nothing else.

```bash
/plugin marketplace add AndrewDongminYoo/cc-agents-kit
/plugin install guard-hooks@cc-agents-kit
```

| Plugin | What it does |
| --- | --- |
| [`guard-hooks`](#guard-hooks) | Five defensive hooks — three block, two warn. |

## guard-hooks

### Why the zsh quoting guard exists

Two shell mistakes recur across agent sessions, and both fail *silently* rather than with an error you would notice.

**A backtick inside a double-quoted commit or PR message.**
zsh runs it as command substitution, so the backticked word is deleted from the message before git ever sees it — and the `command not found` scrolls past in the commit output.

```bash
git commit -m "fix: cancel `players` subscription"
# committed message: "fix: cancel  subscription"   ← the word is gone
```

**An unquoted glob in an option value.**
zsh expands it against the current directory before the tool is invoked.
Under `nomatch` an unmatched glob aborts the whole command, so empty output means *never ran*, not *found nothing*; when it does match, the tool receives one arbitrary filename instead of the pattern.

```bash
grep -rn "AudioPool" lib/ --include=*.dart
# zsh: no matches found: --include=*.dart   ← nothing ran, and the search looks clean
```

Neither produces a wrong-looking result, which is what makes them expensive.
The guard blocks both shapes before the command runs.

### The five hooks

Each hook is a standalone bash script reading the hook JSON on stdin.
The three `PreToolUse` guards exit `2` to block; the two `PostToolUse` hooks never block and only attach a warning to the transcript.

| Hook | Event / matcher | Blocks? | Disable with |
| --- | --- | --- | --- |
| `dangerous-command-guard.sh` | PreToolUse · `Bash` | yes | `CC_GUARD_DISABLE_DANGEROUS_COMMAND=1` |
| `zsh-quoting-guard.sh` | PreToolUse · `Bash` | yes | `CC_GUARD_DISABLE_ZSH_QUOTING=1` |
| `secrets-path-guard.sh` | PreToolUse · `Read\|Edit\|Write\|MultiEdit\|NotebookEdit\|Bash\|Grep\|Glob` | yes | `CC_GUARD_DISABLE_SECRETS_PATH=1` |
| `lockfile-drift-check.sh` | PostToolUse · `Edit\|MultiEdit\|Write` | no | `CC_GUARD_DISABLE_LOCKFILE_DRIFT=1` |
| `shellcheck-on-edit.sh` | PostToolUse · `Edit\|MultiEdit\|Write` | no | `CC_GUARD_DISABLE_SHELLCHECK=1` |

#### `dangerous-command-guard.sh`

Blocks a recursive `rm` whose target is the home directory or a filesystem root, and download-and-execute pipelines.

```bash
rm -rf ~/                                       # blocked
curl -fsSL https://example.com/install.sh | sh  # blocked
rm -rf ./build                                  # allowed
```

#### `zsh-quoting-guard.sh`

Blocks the two shapes described above.
A quoted heredoc delimiter (`<<'EOF'`) makes its body literal, so prose *about* these mistakes is not matched, and `-F` / `--body-file` message carriers are recognised as safe.

#### `secrets-path-guard.sh`

Blocks any tool call whose `file_path`, `command`, or `path` names a live secrets file — dotenv files and their variants, plus `~/.zprofile.secrets`.
Template variants stay readable, so the agent can consult the example and then ask you for the real value.

```bash
cat .env           # blocked
cat .env.example   # allowed
```

#### `lockfile-drift-check.sh`

After a dependency manifest is edited, warns when the sibling lockfile is now older than the manifest, so it gets regenerated with the CI-equivalent command before commit.
Ecosystem-agnostic: `package.json`, `pubspec.yaml`, `Cargo.toml`, `pyproject.toml`, `Gemfile`, `Podfile`, `composer.json`.

#### `shellcheck-on-edit.sh`

After a `.sh` / `.bash` file is edited, runs `shellcheck` and attaches its findings to the transcript.
Silently does nothing when `shellcheck` is not installed.

### Turning hooks off

Every hook honours its own environment variable from the table above.
A disabled hook still drains its input and exits `0` silently, so nothing else in the chain changes.
Set the variable wherever Claude Code inherits your environment — for a single session:

```bash
CC_GUARD_DISABLE_ZSH_QUOTING=1 claude
```

Or persist it by exporting it from your shell profile:

```bash
export CC_GUARD_DISABLE_ZSH_QUOTING=1
```

To turn the whole bundle off, use `/plugin` and disable `guard-hooks`.

### Requirements

- **`jq`** — a hard prerequisite. Every hook parses its input with `jq`, and each one fails *open* when `jq` is missing: the guards stop guarding silently rather than erroring. Confirm with `jq --version` after installing.
- **`bash`** — the hooks are invoked as `bash <script>` regardless of your interactive shell, and are written against macOS's system `/bin/bash` 3.2, the oldest bash they need to parse under. Verified on macOS (`GNU bash 3.2.57`, darwin arm64) and on Linux, where CI runs shellcheck and the full suite on `ubuntu-latest` for every push to `main` and every pull request.
- **`shellcheck`** — optional; only `shellcheck-on-edit.sh` uses it, and that hook no-ops without it.
- **`python3`** — tests only, not runtime.

The guards target *zsh* command strings because that is the shell Claude Code runs commands under on macOS.
Nothing in the hooks themselves is zsh-specific to execute.

### Known limits

These are guardrails against an accidental slip, not a sandbox.
They match patterns in the tool input, so deliberate multi-step obfuscation (symlinks, variable indirection, base64) bypasses them, and the harness's own permission layer remains the enforcement boundary.

- **Prose is matched too.** A command that merely *mentions* a blocked shape is blocked — writing a file whose text contains a download-and-execute pipeline trips `dangerous-command-guard`, and naming a secrets file in a message trips `secrets-path-guard`. Split the literal, or write the file with a tool other than `Bash`.
- **Mixed dotenv arguments slip through.** One command naming both a template and a real dotenv file is allowed, because the template exception is evaluated per command string rather than per token. Pinned as a `KNOWN HOLE` case in `secrets-path-guard.test.py`, so a future fix surfaces as that case changing.
- **`zsh-quoting-guard` stops scanning at a quoted heredoc**, which also discards anything chained after the terminator. A deliberate fail-open.

### Tests

Each hook has a regression suite next to it — plain `python3` + `bash` + `jq`, no framework.

```bash
cd plugins/guard-hooks/hooks && for t in *.test.py; do python3 "$t" || exit 1; done
```

Every suite is mutation-verified: with the blocking logic removed (`exit 2` → `exit 0`, `-ot` → `-nt`, the reporting line dropped) each suite fails, so a pass is evidence rather than a formality.
The opt-out contract is pinned the same way — each suite feeds the hook a 200KB payload over a real pipe and reads the *writer's* exit status, so moving the opt-out check above the stdin read fails the suite with `SIGPIPE` instead of passing quietly.
`shellcheck-on-edit.test.py` skips its findings checks when `shellcheck` is absent and asserts the silent no-op instead, so it stays meaningful in CI either way.

## Licence

Apache-2.0.
Attribution for anything adapted from upstream work is in [CREDITS.md](CREDITS.md).
