---
name: session-export
description: Export a Claude Code session as Markdown, HTML, or JSON. Use when the user wants to save, archive, share, or re-read a transcript. For a continuation summary, use /handoff instead.
allowed-tools: Bash, Read
metadata:
  category: claude-config
---

# Session Export

Export a local Claude Code JSONL transcript as Markdown, standalone HTML, or structured JSON.
Markdown is the default format.
Tool details and thinking are excluded unless the user requests them.

## Usage

`session-to-md` ships in the plugin's `bin/` and is on PATH when the plugin is enabled.
Use the same command for all formats.

```bash
session-to-md "${CLAUDE_SESSION_ID}"
session-to-md "${CLAUDE_SESSION_ID}" --format html
session-to-md "${CLAUDE_SESSION_ID}" --format json
```

Claude substitutes the current session ID into this skill before execution.
This does not depend on a shell environment variable.
If the substitution is unavailable, use `--list` and select an exact ID.
Do not describe the newest transcript as the active session without that evidence.

## Formats

| Format | Output |
| --- | --- |
| `md` | Conversation sections, a turn index, and expandable tool blocks. |
| `html` | A standalone report with a turn index, export counts, tool expansion controls, and a responsive layout. |
| `json` | Filtered records, metadata, and export diagnostics under `schema_version: 1`. |

HTML displays message text literally, including Markdown syntax.
It escapes transcript markup and does not load external resources.
The light report theme uses a single reading column, compact navigation, and distinct tool cards.
The font stack uses Inter when available locally, with system fonts as a fallback.
Summary counts describe included records, not all activity in the source session.
Markdown folding requires a viewer that supports HTML details.

All formats use the same record filter and tool limits.
An explicit `.md`, `.html`, or `.json` output extension must match `--format`.

## Session Selection

The script reads the current project's transcripts under `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects/<munged-cwd>/`.
The project key comes from the working directory with non-alphanumeric characters replaced by hyphens.

```bash
session-to-md --list
session-to-md <session-id>
session-to-md /absolute/path/to/session.jsonl
session-to-md --last 2
```

`--list` prints IDs, update times, and file sizes without transcript prose.
A direct CLI call without an ID selects the newest file by modification time.
`--last N` selects the Nth newest file in that project.
Use an absolute transcript path if the working directory no longer matches the session's project.

## Output Files

```bash
session-to-md <session-id> --out /absolute/path/to/session.md
session-to-md <session-id> --format html --out /absolute/path/to/output-directory
```

The default output is `~/Downloads/<date>-<session-id>.<format>`.
The destination directory must exist.
Files are created with mode `0600`.
The exporter refuses to overwrite an existing file or follow a file symlink.

## Tool Details

Include tool activity only when the user requests it:

```bash
session-to-md <session-id> --tools collapsed
session-to-md <session-id> --format html --tools full
session-to-md <session-id> --tools collapsed --tool-limit 1200
```

`collapsed` starts tool blocks closed, and `full` starts them open.
Both preserve complete inputs and results by default.
`--tool-limit` limits each input and each result to a positive character count.
Truncated values state how many characters were omitted.
Terminal escape sequences are removed from tool results.

Tool results appear with their call, in recorded result order.
Each result retains its timestamp and error flag.
An empty result is distinct from a missing result.
Unmatched results and results with ambiguous call IDs are omitted and counted.
Calls without results are marked as possibly pending or interrupted.

The earlier default was `--tools collapsed`, with automatic input and result truncation.
The new default is `--tools none`.

## Record Preservation

The exporter preserves user and assistant text, including indentation.
It retains user text that shares a record with tool results.
Sidechains, system messages, meta messages, compaction summaries, and known bookkeeping records are excluded.
System reminders and local command output wrappers are removed from user text.
Nested wrappers are removed as a unit, and an unclosed wrapper is removed through the end of its message.
Standalone slash-command records render as a single command line.
Command tags quoted inside ordinary prose keep their surrounding text.

Image, audio, document, file, and unsupported content blocks become placeholders.
Their attachment payloads, URLs, and paths are not copied.
Export notes report malformed lines, unsupported records, placeholders, missing results, and explicit truncation.
A partially written final JSONL line does not prevent readable records from being exported.
An input with no exportable records fails before an output file is created.

Keep thinking excluded unless the user explicitly requests it:

```bash
session-to-md <session-id> --thinking
```

The HTML thinking toggle changes visibility without removing content from the file.

## JSON Contract

JSON exports contain `schema_version`, `metadata`, `privacy_notice`, `diagnostics`, `notes`, and `records`.
Raw transcript records are not copied into JSON.
Each record has a document-local `id`, `turn`, validated `timestamp`, and `type`.
User messages start turns, and records before the first user message belong to turn zero.

Message records contain `role` and `text`.
Opt-in thinking records contain `role` and `text` with `type: thinking`.
Tool records contain `name`, `call_id`, `input`, `outputs`, `output_state`, and `truncated_values`.
Each output contains `text`, `timestamp`, and `is_error`.
`output_state` is `recorded`, `missing`, or `excluded`.
Tool values are readable text, and inputs are formatted JSON text.

## Workflow

1. Use the current session command above unless the user specifies a different session.
2. Select the requested format, with Markdown as the default.
3. Keep tools and thinking excluded unless explicitly requested.
4. Report the output path printed by the script.
5. Report export notes about omissions or truncation.
6. Tell the user to review the export before sharing it.

## Verification

Run the sibling regression suite after changes:

```bash
python3 -B plugins/context-handoff/bin/session-to-md.test.py
```

The suite uses synthetic transcripts to check content preservation, format behavior, filtering, and file creation.
For HTML changes, open a synthetic export in a browser and verify the controls with actual tool and thinking records.

## Boundaries

The script reads local transcripts and writes one local file.
It does not upload, publish, commit, or send the export.
Record filtering does not remove secrets or private paths embedded in ordinary prose or tool payloads.
Do not inspect or quote transcript content beyond the export requested by the user.
