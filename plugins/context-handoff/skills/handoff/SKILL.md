---
name: handoff
description: Use when a session's context is getting long or degrading and you need a detailed, self-contained summary to manually paste into a fresh session (or hand to another machine/tool/teammate). For a short durable fact instead, write it to the persistent memory directory (auto-loaded via MEMORY.md).
allowed-tools: Bash, Read
metadata:
  category: claude-config
---

# Handoff

## Overview

Produce a detailed, self-contained context summary that lets work continue in a brand-new session with no access to this one.
The output is printed to the chat for the user to copy and paste — it is NOT written to a file.

## When to Use

- The current context is long and answer quality is degrading.
- You want to start fresh while preserving essential context.
- The context window is approaching capacity.
- You need to carry context to another machine, tool, or teammate.

**Not this skill:** a short durable fact for future sessions → write a memory file in the persistent memory directory and index it in `MEMORY.md` (auto-loaded each session). `handoff` only prints to chat; never write memory files from here — the two channels serve different lifetimes.
**Handoff-first policy:** the first auto-compact of every session is intercepted by the `handoff-first-precompact` PreCompact hook. When that interception message appears, this skill IS the first option: print the handoff immediately and tell the user to `/clear` and paste it into the fresh session. Only if the user chooses to keep the session does the next auto-compact proceed normally.

If the session has no meaningful work to preserve, say so and stop.

## The Gate — should this be a handoff at all?

Ordered tree, run before producing anything; first yes wins.
Every move except Continue trades the session — a primary source — for a summary of it, so rule out the cheap options first.
(Adapted from mattpocock/skills `PHASE-BOUNDARIES.md`; `/compact` drops out as a rung here because compaction is automated and its pressure is visible in the statusline.)

1. **Can the session just continue?** The next phase needs this phase's reasoning verbatim, or there is comfortable context left. Continue costs nothing and loses nothing.
2. **Is the context irrelevant to what comes next?** Then recommend `/clear` and stop — nothing worth carrying, and the old session stays resumable. Clearing a _relevant_ context is the one-way mistake: the why behind the work doesn't come back from reading the diff.
3. **Is the remaining work a tightly-scoped AFK task?** Send it to a subagent and leave this session untouched — no handoff needed.
4. **Is something actually travelling?** A handoff earns its lossiness only when context must cross a boundary: a new harness or tool, a new machine or directory, a teammate, or a side task forked mid-phase. That list is the whole clause.

If nothing travels but the context is degrading anyway, that is the handoff-first case: hand off and `/clear` beats letting auto-compact flatten the decisions.
If a hook triggered this — a PreCompact interception, or a context-threshold nudge — the gate is already answered: skip straight to Steps.
Make the call at a phase boundary ("ok, we're done with that"), never mid-phase.

## File Mode (context-threshold automation)

When the user asks for a handoff FILE, or a context-threshold nudge fires if you run one, write instead of printing:

1. Path: `~/.claude/handoffs/<repo-basename>-<YYYYMMDD-HHMM>.md` (create the directory if needed).
2. First line of the file body must be exactly `cwd: <absolute project root>`. Nothing here requires that line, but it is what a SessionStart pickup hook would grep to route the file to the right project, and writing it costs nothing if you add one later.
3. Then add a `NEXT MISSION` section (one short paragraph: what the successor session must do first), followed by the standard template below.
4. Tell the user the file path and recommend `/clear` or a new session. Paste the file in yourself, or wire a SessionStart hook that surfaces anything in `~/.claude/handoffs/` whose `cwd:` matches the project and archives it once picked up.

File mode is the one sanctioned exception to "print only, never write".

## Steps

1. **Gather concrete data.** The full conversation and current TODO state are already in your context — use them directly (there is no `session_read`/`todoread` tool in Claude Code). For file changes, run:
   - `git diff --stat HEAD~10..HEAD` — recent changes
   - `git status --porcelain` — uncommitted changes
2. **Extract** from the conversation: exact user wording, work completed, decisions, files touched, constraints/preferences established.
3. **Format** using the template below and print it to the chat.

Write in first person ("I did...", "I told you...").
Capture USER REQUESTS and EXPLICIT CONSTRAINTS verbatim — do not paraphrase or invent them.

## Output Template

```plaintext
HANDOFF CONTEXT
===============

USER REQUESTS (AS-IS)
---------------------
- [Exact verbatim user requests - NOT paraphrased]

GOAL
----
[One sentence describing what should be done next]

WORK COMPLETED
--------------
- [First person bullet points of what was done]
- [Include specific file paths when relevant]
- [Note key implementation decisions]

CURRENT STATE
-------------
- [Current state of the codebase or task]
- [Build/test status if applicable]
- [Any environment or configuration state]

PENDING TASKS
-------------
- [Tasks planned but not completed; next logical steps; blockers]
- [Include current TODO state]

KEY FILES
---------
- [path/to/file] - [brief role description]
(Maximum 10 files, prioritized by importance; include files from git diff/status)

IMPORTANT DECISIONS
-------------------
- [Technical decisions made and why; trade-offs; conventions established]

EXPLICIT CONSTRAINTS
--------------------
- [Verbatim constraints only - from the user or existing CLAUDE.md/AGENTS.md]
- If none, write: None

CONTEXT FOR CONTINUATION
------------------------
- [What the next session needs to know; warnings/gotchas; doc references]
```

## Format Rules

- Plain text with dash bullets — no `#` markdown headers, no bold/italic, no code fences inside the content (so it pastes cleanly as one message).
- Workspace-relative file paths.
- Pick a length proportional to complexity; include only what matters for continuation.
- USER REQUESTS (AS-IS) and EXPLICIT CONSTRAINTS are verbatim only.
- Never include secrets (API keys, credentials, tokens).
- Max 10 files in KEY FILES. GOAL is one sentence.

## Continuation Instructions

After printing the summary, tell the user:

```plaintext
TO CONTINUE IN A NEW SESSION:
1. Run /clear (or start a fresh `claude` session / new terminal).
2. Paste the HANDOFF CONTEXT above as your first message.
3. Add: "Continue from the handoff context above. [your next task]"
```

## Common Mistakes

- Writing to a file or committing — this skill only prints to chat, except File Mode above (never commit either way).
- Paraphrasing user requests or inventing constraints — both must be verbatim.
- Using `#` headers / bold / code fences in the content — breaks clean paste.
- Calling non-existent tools (`session_read`, `todoread`) — the conversation is already in context.
