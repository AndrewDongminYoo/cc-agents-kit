# context-handoff

Six skills and two hooks for work that outlives one Claude Code session, and for the configuration that work drags along.

```bash
/plugin marketplace add AndrewDongminYoo/cc-agents-kit
/plugin install context-handoff@cc-agents-kit
```

## Skills

| Skill            | Use it when                                                                           |
| ---------------- | ------------------------------------------------------------------------------------- |
| `handoff`        | Context is long or degrading and the next session needs a self-contained brief.       |
| `session-export` | You want the transcript as Markdown, standalone HTML, or structured JSON.             |
| `log-it`         | A session found something that is not obvious and it must outlive the window.         |
| `wayfinder`      | The effort is too big for one session and needs decision tickets under `docs/plans/`. |
| `context-budget` | You want to know what fills the context window, ranked by what you would get back.    |
| `config-gc`      | The Claude Code config root has accumulated stale, redundant or orphaned items.       |

## What the plugin runs

- `hooks/compaction-brief.sh` runs on `PreCompact`. It prints the section list that the compaction summary must follow. It does not block or delay a compaction.
- `hooks/post-compact-retrieval.sh` runs on `SessionStart` after a compaction. It adds one line that names the transcript file on disk.
- `bin/session-to-md` is a Node.js program that `session-export` runs. It reads a session transcript from the local Claude Code project directory and writes the export to a local file.
- `handoff` runs `git diff --stat` and `git status --porcelain` to read the state of the repository.

Nothing in the plugin makes a network request.
A handoff file is written only on request, to `~/.claude/handoffs/`.

## Requirements

`bash` and `jq` for the hooks, and `node` for `session-to-md`.
Each hook has an opt-out variable: `CC_GUARD_DISABLE_COMPACTION_BRIEF=1` and `CC_GUARD_DISABLE_POST_COMPACT_RETRIEVAL=1`.

## More

The full documentation, the origin of each skill and the licence are in the [cc-agents-kit repository](https://github.com/AndrewDongminYoo/cc-agents-kit#context-handoff).
Licence: Apache-2.0, with upstream MIT components recorded in the repository's `CREDITS.md`.
