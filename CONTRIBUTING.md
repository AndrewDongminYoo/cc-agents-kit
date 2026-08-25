# Contributing

## Layout

```log
.claude-plugin/marketplace.json   # the marketplace; one entry per plugin
plugins/<plugin>/
  .claude-plugin/plugin.json      # the plugin manifest
  hooks/hooks.json                # auto-discovered; commands use ${CLAUDE_PLUGIN_ROOT}
  hooks/*.sh                      # the hooks themselves
  hooks/*.test.py                 # one regression suite per hook, beside it
  hooks/_optout.py                # the opt-out contract every suite shares
```

A plugin's `source` in `marketplace.json` must point at a directory that exists in this repository.
An entry pointing at a missing directory breaks installation for everyone, so add the entry and the directory in the same commit.

## Adding a hook

1. Read the hook JSON from stdin and **fail open** — empty, malformed, or key-less input must exit `0` with no output. A guard that errors on unrelated tool calls gets uninstalled.
2. Give it an opt-out: `CC_GUARD_DISABLE_<NAME>=1`, and add it to the README table. Check it *after* stdin is drained, never before — a `Write` payload carries the whole file content, so exiting early leaves the harness writing to a closed pipe and surfaces a hook error exactly when the user asked for the hook to be off.
3. `PreToolUse` guards exit `2` to block. `PostToolUse` hooks must never block — emit `hookSpecificOutput.additionalContext` and exit `0`.
4. Write the regression suite next to the script. It resolves the hook via `Path(__file__).resolve().with_name(...)` and imports `_optout` as a plain sibling module, so all three files stay in the same directory.
5. Cover the opt-out with `_optout.contract(HOOK, DISABLE_VAR, BLOCKING, SAFE)` for a hook that blocks, or `_optout.drain(HOOK, DISABLE_VAR)` for one that only warns and needs its own cases. Do not re-copy the machinery — it was byte-identical in seven suites before 0.3.6 collapsed it.

## Verifying a change

```bash
find . -name '*.sh' -not -path './.git/*' -print0 | xargs -0 shellcheck
cd plugins/guard-hooks/hooks && for t in *.test.py; do python3 "$t" || exit 1; done
```

CI also lints and parses extensionless Bash entries under `plugins/*/bin/`; local verification must include any such entry changed by the contribution.

A passing suite is not on its own evidence.
Before claiming a suite covers the logic, remove that logic and confirm the suite fails: flip `exit 2` to `exit 0`, invert the comparison, or delete the reporting line.
Mutate in a way that still parses — `bash` exits `2` on a syntax error, which is indistinguishable from a block, so a broken mutant produces a vacuous pass.
Run `bash -n` on the mutant first.

Hooks must **run**, not merely parse, under macOS's system `/bin/bash` 3.2 — a stock Mac has no newer bash, so that is what the hook is invoked with there.
The suites therefore call `/bin/bash` rather than `bash`, and CI runs on `macos-latest` alongside Linux for the same reason.
Testing through a newer bash on `PATH` hides whole classes of fault: `"${arr[@]}"` on an empty array aborts under `set -u` in 3.2 but not in 4.4+, and paired with a `|| true` that abort is swallowed, leaving the guard silently disabled on exactly the machines it targets.

## Releasing

Start by comparing `git tag` against `gh release list`.
The tag and the GitHub release are separate steps at the end of a long task and either can be dropped: on 2026-08-25 two releases were found behind in different ways, one with a pushed tag and no release, the other with a merged changelog section and no tag. Finish whatever is behind before cutting anything new.

CI validates the manifests structurally, but the CLI's own validator knows the schema and is the last word.
It needs the `claude` CLI, so it runs locally rather than in CI:

```bash
claude plugin validate .
```

Then:

1. **Bump each changed plugin's `version` in its own feature or fix commit**, not in the release commit. A reviewer reading that commit should see the behaviour change and the version that carries it together.
2. `chore(release): cut X.Y.Z` — **CHANGELOG.md alone**. Say in the body which plugins were already bumped and to what, so the release commit is still self-describing with one file in it.
3. Open a PR and let CI go green on both `ubuntu-latest` and `macos-latest`.
4. **Merge with a merge commit, not a squash.** Every tag in this repository points at a two-parent commit.
5. Annotate the tag on that merge commit and push it: `git tag -a vX.Y.Z -m "<one line>" <merge-sha>`.
6. `gh release create vX.Y.Z --verify-tag --latest` with notes written for a reader deciding whether to update — what changed, why it matters, and the upgrade command — rather than the changelog text pasted over.

The repository version and the plugin versions are independent: a `vX.Y.Z` tag does not track any one plugin, and the runtime keys its cache on the plugin version alone. `marketplace.json` carries no version field (dropped in 0.3.6) because nothing reads one — the client records a version per plugin in `installed_plugins.json`, and only source, install path, and timestamp in `known_marketplaces.json`.

Close the release notes with each plugin's delta, and **read those numbers out of the previous tag** rather than from what you remember bumping:

```bash
git show vPREV:plugins/<plugin>/.claude-plugin/plugin.json
```

The v0.3.2 notes shipped calling a plugin "unchanged" that had moved a patch version, and had to be corrected after publishing.

After publishing, verify the new version actually loads rather than assuming it did: `claude plugin update <plugin>@cc-agents-kit`, start a fresh session, and confirm a hook that exists only in the new version fires with `${CLAUDE_PLUGIN_ROOT}` in its error.
Pick a probe that is harmless when it is *not* blocked — `prettier --write` fails on its own without a formatter installed, whereas `jsonsort` would quietly rewrite the tree.

## Commits

Conventional commits, grouped by concern.
