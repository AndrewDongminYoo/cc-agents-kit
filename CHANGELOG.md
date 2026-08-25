# Changelog

All notable, user-facing changes to this kit are recorded here.
Entries are grouped by release; the topmost section collects work that has not yet been tagged.

## [0.3.3] — 2026-08-25

### Added

- `semantic-commit` splits a file at hunk level when it genuinely spans two concerns, instead of assigning it wholesale to the dominant intent. It documents driving `git add -p` over a pipe — it reads answers from stdin, so no TTY is needed — with the `git diff --cached` confirmation made mandatory rather than optional, because on EOF `git add -p` quits and an answer-count mismatch under-stages silently. Also the patch-editing fallback for two concerns interleaved inside one hunk, where `s` splits on line counts and rarely lands on the concern boundary, and `git stash push --keep-index` so verification runs against the commit candidate rather than a working tree that no longer matches it.

### Provenance

- CREDITS.md gains rows for `pathless-rewriter-guard.sh` and `staged-secret-guard.sh`. Both are original work, but the two hooks shipped in 0.2.0 without entries, so the file that claims to cover everything published did not.

## [0.3.2] — 2026-08-24

### Fixed

- `staged-secret-guard`'s two `sk-` key patterns had no left boundary, so a kebab-case word whose tail clears the 20-character floor — `live-task-status-transitioning` contains `sk-status-transitioning` — read as an OpenAI key and blocked a real commit. Both patterns now require a non-word character (or line start) before `sk-`, with regression tests for the slug and for a key at line start.
- Guard hooks now cover git global options and separated long-option globs, every dangerous command segment and absolute pipeline interpreters, multi-suffix and mixed live dotenv paths, effective `commit -a` and pathspec candidates, value-taking rewriter options, and large ShellCheck findings without advisory SIGPIPE failures.
- `find-trunk-repos` now propagates GitHub authentication and repository-list failures instead of reporting a false empty success.
- `config-gc` now derives one active root from `CLAUDE_CONFIG_DIR` or `~/.claude`, and `setup-trunk` selects linters from repository evidence before proposing scoped changes.

### Changed

- CI now lints and parses extensionless Bash plugin `bin/` entries as well as `*.sh`; the previous claim that every shipped shell artifact was covered was broader than the implemented gate.

## [0.3.1] — 2026-08-19

### Fixed

- `session-export` could not run as an installed plugin. Its skill told the agent to execute `~/.claude/skills/session-export/scripts/session-to-md.mjs`, a path that exists only where the skill was originally authored — never for anyone who installs the plugin. `CLAUDE_PLUGIN_ROOT` is substituted for hooks and is unset in the Bash tool, so the fix is the documented `bin/` mechanism: the script now ships as `context-handoff/bin/session-to-md`, on PATH whenever the plugin is enabled, and the skill calls it by bare name. Verified by resolving and running it through `--plugin-dir`.
- `setup-trunk` pointed at a `trunk-quality-gate` agent that is not part of this repository. The paragraph now states the scope boundary instead of naming something the reader does not have.
- `find-trunk-repos.sh` shipped inside `setup-trunk` with nothing referencing it. It now lives in `repo-gate/bin/find-trunk-repos` and the skill documents it for what it is good at: reading a trunk config you already wrote instead of inventing one.

### Changed

- CI lints and parses every `*.sh` script in the repository rather than only `plugins/*/hooks/*.sh`. Two scripts that ship to users, including one inside a skill, had been outside the gate; both were clean, but extensionless Bash `bin/` entries were not yet covered.
- The hook-wiring existence check no longer hardcodes `guard-hooks`, so a second plugin adding hooks is covered on the day it does.
- New check: every `plugins/*/bin/*` entry is executable and carries a shebang — on PATH and unrunnable is exactly the failure a skill calling it by bare name cannot see.
- New check: the demo recording is compared against what `zsh-quoting-guard` actually prints, by running it, rather than against its source. It caught a real mismatch on the first run — the recording had been shortening the message's final line — which is now corrected and the GIF regenerated.

## [0.3.0] — 2026-08-18

### Added

- `context-handoff` 0.1.0 — six skills for work that outlives one session: `handoff` (brief a successor, printed or as a file), `session-export` (transcript to readable markdown), `log-it` (route what a session learned to whoever must read it), `wayfinder` (chart an effort too big for one sitting as decision tickets), `context-budget` and `config-gc` (find and remove what is eating the context window).
- `repo-gate` 0.1.0 — five skills for the stretch between working code and a push: `semantic-commit`, `setup-trunk`, `ci-babysit`, `fix-osv-vulnerabilities`, `cspell-triage`.
- CI parses every skill's frontmatter and asserts its `name` matches its directory — a skill that fails either installs silently and never triggers — and rejects absolute home paths in published plugins, the class of leak the first plugin's path-shaped grep had missed.

### Provenance

Three skills carry MIT-licensed upstream work, with the overlap measured line-wise rather than described: `wayfinder` 14% verbatim from mattpocock/skills, `config-gc` 54% and `context-budget` 87% from affaan-m/ecc. Each names its source in `metadata.origin`, and CREDITS.md carries the command to re-derive the numbers.

## [0.2.1] — 2026-08-18

### Changed

- `zsh-quoting-guard.sh` describes the glob trap accurately. It said an unquoted glob "substitut[es] one arbitrary filename when something does" match, which holds only when exactly one file matches; several expand to a list the tool rejects outright. The message now names all three outcomes and which one is quiet. Behaviour is unchanged — only what it tells you.

## [0.2.0] — 2026-08-18

### Added

- `pathless-rewriter-guard.sh` — blocks a formatter or rewriter invoked with no path argument, where its no-path default is everything reachable (`jsonsort`, `trunk fmt`, `ruff format`, and write-mode `prettier` / `eslint` / `shfmt`). Package runners and absolute binary paths are seen through; tools that already error out without a path are not listed.
- `staged-secret-guard.sh` — scans the added lines of the staged diff for credential shapes before `git commit` runs, and blocks the commit. Removing a secret is never blocked, and `git -C <path>` is honoured.

### Fixed

- `staged-secret-guard.sh` never scanned anything under bash 3.2, the `/bin/bash` on a stock Mac: an empty array expansion aborts under `set -u`, and the adjacent `|| true` swallowed it, so the hook exited 0 having read no diff. The suites missed it by invoking `bash` from `PATH`; they now invoke `/bin/bash`, and CI runs on macOS alongside Linux.

## [0.1.0] — 2026-08-18

First distribution snapshot. Ships one plugin:

- `guard-hooks` — five defensive hooks. Three `PreToolUse` guards block a recursive `rm` aimed at the home directory or a filesystem root, download-and-execute pipelines, access to live secrets files, and the two zsh quoting mistakes that fail silently. Two `PostToolUse` hooks warn without blocking: a stale lockfile after a manifest edit, and `shellcheck` findings after a shell-script edit.

Each hook carries a regression suite beside it: 117 cases, 49 of which fail when the logic they cover is deleted.
Each hook can be disabled individually through its own `CC_GUARD_DISABLE_*` environment variable, checked after stdin is drained so a disabled hook cannot break a large `Write`.

Verified on macOS (`/bin/bash` 3.2) and on Linux through CI, and confirmed to load and fire as an installed plugin via `${CLAUDE_PLUGIN_ROOT}`.
