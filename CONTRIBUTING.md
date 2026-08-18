# Contributing

## Layout

```log
.claude-plugin/marketplace.json   # the marketplace; one entry per plugin
plugins/<plugin>/
  .claude-plugin/plugin.json      # the plugin manifest
  hooks/hooks.json                # auto-discovered; commands use ${CLAUDE_PLUGIN_ROOT}
  hooks/*.sh                      # the hooks themselves
  hooks/*.test.py                 # one regression suite per hook, beside it
```

A plugin's `source` in `marketplace.json` must point at a directory that exists in this repository.
An entry pointing at a missing directory breaks installation for everyone, so add the entry and the directory in the same commit.

## Adding a hook

1. Read the hook JSON from stdin and **fail open** — empty, malformed, or key-less input must exit `0` with no output. A guard that errors on unrelated tool calls gets uninstalled.
2. Give it an opt-out: `CC_GUARD_DISABLE_<NAME>=1`, and add it to the README table. Check it *after* stdin is drained, never before — a `Write` payload carries the whole file content, so exiting early leaves the harness writing to a closed pipe and surfaces a hook error exactly when the user asked for the hook to be off.
3. `PreToolUse` guards exit `2` to block. `PostToolUse` hooks must never block — emit `hookSpecificOutput.additionalContext` and exit `0`.
4. Write the regression suite next to the script. It resolves the hook via `Path(__file__).resolve().with_name(...)`, so the two files stay in the same directory.

## Verifying a change

```bash
shellcheck plugins/*/hooks/*.sh
cd plugins/guard-hooks/hooks && for t in *.test.py; do python3 "$t" || exit 1; done
```

A passing suite is not on its own evidence.
Before claiming a suite covers the logic, remove that logic and confirm the suite fails: flip `exit 2` to `exit 0`, invert the comparison, or delete the reporting line.
Mutate in a way that still parses — `bash` exits `2` on a syntax error, which is indistinguishable from a block, so a broken mutant produces a vacuous pass.
Run `bash -n` on the mutant first.

Hooks must **run**, not merely parse, under macOS's system `/bin/bash` 3.2 — a stock Mac has no newer bash, so that is what the hook is invoked with there.
The suites therefore call `/bin/bash` rather than `bash`, and CI runs on `macos-latest` alongside Linux for the same reason.
Testing through a newer bash on `PATH` hides whole classes of fault: `"${arr[@]}"` on an empty array aborts under `set -u` in 3.2 but not in 4.4+, and paired with a `|| true` that abort is swallowed, leaving the guard silently disabled on exactly the machines it targets.

## Before a release

CI validates the manifests structurally, but the CLI's own validator knows the schema and is the last word.
It needs the `claude` CLI, so it runs locally rather than in CI:

```bash
claude plugin validate .
```

Then bump the changed plugin's `version` in its `plugin.json`.
The marketplace's own `version` is independent and does not track any plugin — the runtime keys its cache on the plugin version alone.

After publishing, verify the new version actually loads rather than assuming it did: `claude plugin update <plugin>@cc-agents-kit`, start a fresh session, and confirm a hook that exists only in the new version fires with `${CLAUDE_PLUGIN_ROOT}` in its error.
Pick a probe that is harmless when it is *not* blocked — `prettier --write` fails on its own without a formatter installed, whereas `jsonsort` would quietly rewrite the tree.

## Commits

Conventional commits, grouped by concern.
