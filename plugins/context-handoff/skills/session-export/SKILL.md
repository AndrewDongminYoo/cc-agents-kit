---
name: session-export
description: Export a Claude Code session transcript as clean chat-style markdown with collapsed tool calls. Use when the user wants to save, archive, or re-read a session as a document — "세션 내보내줘", "export this session as markdown". For a compact continuation summary use /handoff instead.
allowed-tools: Bash, Read
metadata:
  category: claude-config
---

# Session Export

Render a session `.jsonl` transcript from `~/.claude/projects/<munged-cwd>/` into a markdown document with `## 👤 User · time` / `## 🤖 Claude · time` sections, prose kept in full, and tool activity collapsed into `<details>` blocks.

## Usage

`session-to-md` is on PATH whenever this plugin is enabled — it ships in the plugin's `bin/`, so there is no path to resolve.

```bash
# Export the current project's most recent session (this session) to ~/Downloads
session-to-md

# List this project's sessions (id, time, size, first-prompt preview)
session-to-md --list

# Export a specific session by id, or the Nth most recent
session-to-md <session-id>
session-to-md --last 2

# Options
#   --out <file|dir>   output path (default: ~/Downloads/<date>-<title>.md)
#   --tools none       prose only — drop tool calls and results
#   --tools full       keep full untruncated tool results (default truncates at 1200 chars)
#   --thinking         include thinking blocks as blockquotes
```

## Workflow

1. Run with no arguments for "export this session"; the newest `.jsonl` for the current cwd is the running session.
2. If the user asks for an older or different session, run `--list` first and let them pick by id or preview line.
3. Print the output path the script echoes, and offer `--tools none` when the user only wants the readable conversation.

## Notes

- Sidechain (subagent) entries, system reminders, and harness bookkeeping events are filtered out; slash-command invocations render as a single `` `/command args` `` line.
- The exporter reads local transcripts only — nothing leaves the machine.
