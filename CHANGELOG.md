# Changelog

All notable, user-facing changes to this kit are recorded here.
Entries are grouped by release; the topmost section collects work that has not yet been tagged.

## [Unreleased]

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
