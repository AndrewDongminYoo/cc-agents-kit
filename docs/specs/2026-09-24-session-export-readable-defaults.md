# Session Export Reading Defaults

## Problem

The Claude Code Markdown and HTML exporters include a turn index by default even when a reader wants to start at the conversation.

## Scope

- Omit the turn index and its Markdown anchors by default.
- Add `--toc` for a turn index in Markdown and HTML.
- Update the session-export skill instructions to describe the default and option.

## Non-goals

- Change tool, thinking, attachment, or sidechain filtering.
- Render source Markdown inside standalone HTML.
- Change the default metadata frontmatter or output filename.

## Acceptance Criteria

1. Default Markdown and HTML contain no turn index; `--toc` restores usable turn links.
2. Tool and thinking controls still work in standalone HTML.
3. Existing filtering, privacy, and private file creation tests continue to pass.
