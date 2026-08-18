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
2. Give it an opt-out: `CC_GUARD_DISABLE_<NAME>=1`, checked before any input is read, and add it to the README table.
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

Hooks must parse under macOS's system `/bin/bash` 3.2, not just your shell's newer bash: `/bin/bash -n <script>`.

## Commits

Conventional commits, grouped by concern.
