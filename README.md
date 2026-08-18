# cc-agents-kit

[![ci](https://github.com/AndrewDongminYoo/cc-agents-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/AndrewDongminYoo/cc-agents-kit/actions/workflows/ci.yml)

A Claude Code plugin marketplace.
Each plugin is scoped to one pain, so you install the part you want and nothing else.

```bash
/plugin marketplace add AndrewDongminYoo/cc-agents-kit
/plugin install guard-hooks@cc-agents-kit
```

Upgrading needs `claude plugin update guard-hooks@cc-agents-kit` — the marketplace suffix is required, and installing again is a no-op that reports success.
Refreshing the marketplace alone is not enough: the cache keeps one directory per version, and the runtime loads the version recorded at install time, so `claude plugin details` can report the new version while the old one is still what fires.
Hooks are read when a session starts, so restart any session that is already open.

| Plugin | What it does |
| --- | --- |
| [`guard-hooks`](#guard-hooks) | Seven defensive hooks — five block, two warn. |

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

### Why you should trust it in your shell

A hook bundle runs on every tool call, so "it has tests" is not worth much on its own.
These are the three properties that matter, and each is pinned by a case that fails when the property is removed:

- **A passing suite is not taken as evidence.** 184 cases across the seven hooks; delete the logic they cover — `exit 2` → `exit 0`, `-ot` → `-nt`, drop the reporting line — and 74 of them fail. Mutants are parse-checked first, because `bash` exits `2` on a syntax error and an unparseable mutant would otherwise produce a vacuous pass.
- **Guards fail open, never closed.** Empty, malformed, or key-less input exits `0` silently. A broken guard degrades to no guard, and never to a blocked tool call.
- **The two `PostToolUse` hooks cannot block you.** They only attach a warning. Every hook also has its own kill switch, and a disabled hook still drains its input, so turning one off cannot itself break a large `Write`.

Nothing here is a sandbox — see [Known limits](#known-limits) for what these guards do not stop.

### The seven hooks

Each hook is a standalone bash script reading the hook JSON on stdin.
The five `PreToolUse` guards exit `2` to block; the two `PostToolUse` hooks never block and only attach a warning to the transcript.

| Hook | Event / matcher | Blocks? | Disable with |
| --- | --- | --- | --- |
| `dangerous-command-guard.sh` | PreToolUse · `Bash` | yes | `CC_GUARD_DISABLE_DANGEROUS_COMMAND=1` |
| `zsh-quoting-guard.sh` | PreToolUse · `Bash` | yes | `CC_GUARD_DISABLE_ZSH_QUOTING=1` |
| `pathless-rewriter-guard.sh` | PreToolUse · `Bash` | yes | `CC_GUARD_DISABLE_PATHLESS_REWRITER=1` |
| `staged-secret-guard.sh` | PreToolUse · `Bash` | yes | `CC_GUARD_DISABLE_STAGED_SECRET=1` |
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

#### `pathless-rewriter-guard.sh`

Blocks a formatter or rewriter invoked with no path argument, where its no-path default is "everything reachable".
`jsonsort` with no file opens an interactive picker and walks the tree; `trunk fmt` formats every changed file; `ruff format` defaults to the working directory.
Write-mode tools are only blocked once they are actually writing, and package runners (`npx`, `pnpm dlx`, `uv run`) are seen through.

```bash
jsonsort                      # blocked
prettier --write              # blocked
npx prettier --write          # blocked
jsonsort package.json         # allowed
prettier --check              # allowed - reports, does not write
```

Tools that already error out without a path (`black`, `dart format`) are deliberately not listed.

#### `staged-secret-guard.sh`

Before a `git commit` runs, scans the *added* lines of the staged diff for credential shapes: npm auth tokens, GitHub / Slack / Google / PyPI tokens, OpenAI- and Anthropic-style keys, AWS access key ids, and private key blocks.
Deleting a secret is never blocked, only adding one.
`git -C <path>` is honoured, so the scan reads the repository being committed to.

This is the commit-time counterpart to `secrets-path-guard.sh`, which blocks *reading* secret files - a value still reaches a diff by being typed, pasted, or written by a generator.
High-confidence patterns only: a guard that cries wolf gets switched off.
It is not a replacement for entropy-based scanning; run trufflehog or gitleaks in CI as well.

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
- **`git`** — only `staged-secret-guard.sh` uses it, to read the staged diff; outside a repository the hook exits `0`.
- **`shellcheck`** — optional; only `shellcheck-on-edit.sh` uses it, and that hook no-ops without it.
- **`python3`** — tests only, not runtime.

The guards target *zsh* command strings because that is the shell Claude Code runs commands under on macOS.
Nothing in the hooks themselves is zsh-specific to execute.

### Known limits

These are guardrails against an accidental slip, not a sandbox.
They match patterns in the tool input, so deliberate multi-step obfuscation (symlinks, variable indirection, base64) bypasses them, and the harness's own permission layer remains the enforcement boundary.

- **Prose is matched too.** A command that merely *mentions* a blocked shape is blocked — writing a file whose text contains a download-and-execute pipeline trips `dangerous-command-guard`, and naming a secrets file in a message trips `secrets-path-guard`. Split the literal, or write the file with a tool other than `Bash`.
- **Mixed dotenv arguments slip through.** One command naming both a template and a real dotenv file is allowed, because the template exception is evaluated per command string rather than per token. Pinned as a `KNOWN HOLE` case in `secrets-path-guard.test.py`, so a future fix surfaces as that case changing.
- **`staged-secret-guard` matches shapes, not entropy.** A credential with no recognisable prefix - a bare password, a random hex string, a private API host - is not detected. Treat it as a floor, not a scanner.
- **`pathless-rewriter-guard` only knows the tools it lists.** A rewriter outside that list, or one reached through a shell alias or a package script (`npm run format`), is invisible to it.
- **`zsh-quoting-guard` stops scanning at a quoted heredoc**, which also discards anything chained after the terminator. A deliberate fail-open.

### Tests

Each hook has a regression suite next to it — plain `python3` + `bash` + `jq`, no framework.

```bash
cd plugins/guard-hooks/hooks && for t in *.test.py; do python3 "$t" || exit 1; done
```

The mutation counts above are re-derived from these files, not quoted from a past run.

Two details worth knowing if you extend them.
The opt-out cases feed the hook a 200KB payload over a real pipe and read the *writer's* exit status, because Python's `subprocess` swallows `BrokenPipeError` — an `input=`-style test cannot see the bug they exist to catch, and moving the opt-out check above the stdin read fails them with `SIGPIPE` rather than passing quietly.
`shellcheck-on-edit.test.py` skips its findings checks when `shellcheck` is absent and asserts the silent no-op instead, so it stays meaningful in CI either way.

## Licence

Apache-2.0.
Attribution for anything adapted from upstream work is in [CREDITS.md](CREDITS.md).
