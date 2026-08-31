# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A Claude Code **plugin marketplace** — not an application. Nothing here is imported or built; the artifacts are shell hooks plus the JSON manifests that make an installer find them.
Every change is therefore judged on two things: does the manifest still resolve, and does the hook still hold its contract.

## Commands

```bash
shellcheck plugins/*/hooks/*.sh
cd plugins/guard-hooks/hooks && for t in *.test.py; do python3 "$t" || exit 1; done
python3 plugins/guard-hooks/hooks/<name>.test.py     # a single suite
/bin/bash -n plugins/guard-hooks/hooks/<name>.sh     # macOS system bash 3.2, not your shell's bash
```

There is no build, no package manager, and no test framework.
Suites are plain `python3` scripts requiring `bash` and `jq`; `shellcheck` is optional (`shellcheck-on-edit.test.py` skips its findings checks and asserts the silent no-op instead).
`.github/workflows/ci.yml` runs exactly the commands above plus manifest validation.

## Layout contract

```log
.claude-plugin/marketplace.json   # marketplace.json ONLY — no plugin.json here
plugins/<plugin>/
  .claude-plugin/plugin.json      # each plugin carries its own manifest
  hooks/hooks.json                # auto-discovered; commands reference ${CLAUDE_PLUGIN_ROOT}
  hooks/*.sh
  hooks/*.test.py                 # beside its hook, never in a tests/ directory
  hooks/_optout.py                # shared suite helper; leading _ keeps it out of the *.test.py glob
```

This mirrors Anthropic's own multi-plugin marketplace (`claude-code-plugins`), which is the layout to check against — **not** `rn-agents-kit`, whose single plugin uses `"source": "./"` and says nothing about nesting.

Two placements are load-bearing:

- A `source` in `marketplace.json` that names a missing directory breaks installation for every user of the marketplace. Add the entry and the directory in the same commit.
- Each suite resolves its hook with `Path(__file__).resolve().with_name(...)`, and imports `_optout` as a plain sibling module. Moving either into its own directory silently breaks that, so they stay next to the scripts.

## Hook contract

Enforced by the suites; break one and the corresponding case fails.

- **Fail open.** Empty, malformed, or key-less input exits `0` with no output. `jq` is parsed with `|| true`, so a machine without `jq` makes every guard stop guarding *silently* — that is deliberate, and it is why `jq` is documented as a hard prerequisite rather than checked at runtime.
- **`PreToolUse` guards exit `2` to block. `PostToolUse` hooks never block** — they emit `hookSpecificOutput.additionalContext` (a warning) or `hookSpecificOutput.updatedToolOutput` (`output-secret-mask` rewriting a Bash result) and exit `0`.
- **The `CC_GUARD_DISABLE_*` opt-out is checked *after* `HOOK_INPUT=$(cat ...)`, never before.** A `Write` payload carries the whole file content, so exiting before draining stdin leaves the harness writing to a closed pipe and surfaces a hook error at exactly the moment the user asked for the hook to be off. Pinned by a 200KB-payload case in `hooks/_optout.py`, shared by every suite, that runs the hook behind a real pipe and reads the writer's `PIPESTATUS` — Python's `subprocess` swallows `BrokenPipeError`, so an `input=`-style test cannot see this bug.
- Scripts must parse under macOS's system `/bin/bash` 3.2, not just a newer bash on `PATH`.

## Verifying a change

A passing suite is not on its own evidence that it covers anything.
Before claiming coverage, remove the logic and confirm the suite fails: `exit 2` → `exit 0`, `-ot` → `-nt`, drop the reporting line, or move the opt-out above the read.

Mutate in a way that still parses. `bash` exits `2` on a syntax error, which is indistinguishable from a block, so an unparseable mutant yields a vacuous pass — run `/bin/bash -n` on the mutant first, and treat a mutation that matched nothing (a "skipped" file) as a failed check rather than a pass.

## Releasing

The procedure is `CONTRIBUTING.md` §Releasing, and it is not obvious from the history: plugin versions ride their own feature commit, the release commit is CHANGELOG-only, the PR merges with a merge commit, and the tag goes on that merge commit.
Before cutting anything, compare `git tag` against `gh release list` and finish whatever is behind — the tag and the GitHub release are separate trailing steps and both have been dropped before.

## Working in this repo, the guards are usually live

The same hooks are typically installed in the developing session's own `~/.claude/settings.json`, so they inspect the tool calls used to edit them.
Writing documentation or fixtures that *mention* a blocked shape — a download-and-execute pipeline, `rm -rf` on the home directory, a secrets filename — gets blocked when the text passes through `Bash`.
Use the `Write` tool for that content, or split the literal in a script (`".e" + "nv"`). This is documented as a known limit in the README, not a bug to fix.

## Provenance

`CREDITS.md` is the single place origin is recorded; a hook or skill never restates its own.
Before committing anything derived from upstream work, read the upstream licence directly (`gh api repos/OWNER/REPO/license -q .license.spdx_id`) rather than inferring it, and add an `origin:` key to that component's frontmatter.
A component may be mostly upstream — `context-budget` is 87% verbatim — but then it ships as a declared redistribution, not as original work: CREDITS.md states the measured overlap and names the copyright holder, and the licence has to permit it. What does not belong here is upstream work presented as this repository's own.
