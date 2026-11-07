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
By default, print the output to chat for the user to copy and paste.
Use File Mode (below) only when a context-threshold nudge requests it or the user explicitly asks for a handoff file.

## When to Use

- The current context is long and answer quality is degrading.
- You want to start fresh while preserving essential context.
- The context window is approaching capacity.
- You need to carry context to another machine, tool, or teammate.

**Not this skill:** a short durable fact for future sessions → write a memory file in the persistent memory directory and index it in `MEMORY.md` (auto-loaded each session). Never write memory files from `handoff` — the two channels serve different lifetimes.
**Handoff-first policy:** if you run a PreCompact hook that intercepts the first auto-compact of a session (this plugin's own `PreCompact` hook does not intercept; it only shapes the compaction summary to the template below), its interception message makes this skill the first option: print the handoff immediately and tell the user to `/clear` and paste it into the fresh session. Only if the user chooses to keep the session does the next auto-compact proceed normally.

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

## File Mode

Use File Mode when a context-threshold nudge fires (the `context-meter` plugin sends one, if you run it) or the user explicitly asks for a handoff file.
`log-it` writes its own thin handoff file under its own rules; this section does not govern that file.

1. Write `~/.claude/handoffs/<repo-basename>-<YYYYMMDD-HHMM>.md`, and create the directory if needed.
2. Make the first line exactly `cwd: <absolute project root>`. Nothing here requires that line, but it is what a SessionStart pickup hook would grep to route the file to the right project, and writing it costs nothing if you add one later.
3. Add a `NEXT MISSION` section containing one short paragraph that tells the successor session what to do first, followed by the standard template below.
4. Tell the user the file path and recommend `/clear` or a new session. Without a pickup hook, the user pastes the file's contents as the first message of the new session (copying the file to the other machine first when the session moves). Or wire a SessionStart hook that surfaces anything in `~/.claude/handoffs/` whose `cwd:` matches the project and archives it once picked up.

Archiving belongs to that pickup hook: a hook that surfaces a file archives it, and without a hook nothing surfaces the file a second time, so neither session has an archive step.
Never write a handoff file without one of the triggers above.
Never commit handoff files.

## Steps

1. **Gather concrete data.** The full conversation and current TODO state are already in your context — use them directly (there is no `session_read`/`todoread` tool in Claude Code). For file changes, run:
   - `git diff --stat HEAD~10..HEAD` — recent changes
   - `git status --porcelain` — uncommitted changes
2. **Extract** from the conversation: exact user wording, work completed, decisions, files touched, constraints/preferences established.
3. **Format** using the template below and deliver it through the selected mode.

Write in first person ("I did...", "I told you...").
Capture TASK, DONE WHEN and USER CONSTRAINTS verbatim — do not paraphrase or invent them.

## Output Template

A handoff is a brief for the work still to be done, not a narrative of the work so far: it keeps what the next stretch has to act on and drops repetition, chronology that does not matter, and any weighting by how often a fact came up.
The FIXED block is append-only: every entry from an earlier handoff or compaction is copied word for word, and what the user said since is added after it, in order; the RECAP block is written fresh each time from the current state.
The plugin's `PreCompact` hook gives every compaction this same section list, so a compaction the user lets run is the thin version of this handoff, not a different document.

```plaintext
HANDOFF CONTEXT
===============

FIXED (append-only: earlier entries copied word for word, later requests and corrections added after them in order; where a later one replaces an earlier one, keep both and say which is current)

TASK
----
- [Every user request, in their words, in order]

DONE WHEN
---------
- [The acceptance criteria, in the user's words where they gave them]

USER CONSTRAINTS
----------------
- [Verbatim constraints and preferences from the user, or quoted from CLAUDE.md/AGENTS.md]
- If none, write: None

RECAP (written fresh each time from the current state)

PERSISTENT STATE
----------------
- [Branch, worktree, uncommitted files, running services or background tasks, as they are now]
- [The session transcript path, so dropped history can be grepped]

OBJECTIVE
---------
[One line: the required result of the current stretch]

ESTABLISHED FACTS
-----------------
- [Exact paths, symbols, commands, observed values, important errors or output]
- [Observations first, then unverified ideas, labelled as such]

APPLIED CHANGES
---------------
- [path/to/file] - [what changed] - [verified: yes/no, and how]

VERIFICATION
------------
- [Exact checks run, outcomes, failures, obstacles, workarounds]

DEAD ENDS
---------
- [An approach that failed and must not be retried] - [the evidence that it failed]

REMAINING PLAN
--------------
- [Outstanding subgoals in execution order]
- [The immediate next command or edit]
- [The condition for completion]

RETRIEVAL
---------
- [Narrow commands to re-fetch truncated output or dropped history: a grep or sed -n over the transcript path, a file with a line range]

EXTERNAL STATUS
---------------
- [Each tracker issue, review, store or console, inbox, with the source to re-read it from: a URL, an ID, or a path]
- Before acting on any status recorded above, re-read it from its named source: this handoff records what the writing session believed, and that status may have changed since. Treat a status with no named source as unverified.
```

The last line of EXTERNAL STATUS is fixed text: keep it in every handoff, because the receiving session sees only the handoff and never this skill.

## Format Rules

- Plain text with dash bullets — no `#` markdown headers, no bold/italic, no code fences inside the content (so it pastes cleanly as one message).
- Workspace-relative file paths.
- Pick a length proportional to complexity; include only what matters for continuation.
- TASK, DONE WHEN and USER CONSTRAINTS are verbatim only.
- Never include secrets (API keys, credentials, tokens).
- At most 10 files across ESTABLISHED FACTS and APPLIED CHANGES, prioritized by importance. OBJECTIVE is one line.
- Every DEAD ENDS entry carries its evidence; a failure with no evidence in hand is marked unverified rather than asserted.

## Continuation Instructions

For chat output, tell the user:

```plaintext
TO CONTINUE IN A NEW SESSION:
1. Run /clear (or start a fresh `claude` session / new terminal).
2. Paste the HANDOFF CONTEXT above as your first message.
3. Add: "Continue from the handoff context above. [your next task]"
```

## Common Mistakes

- Writing a file from this skill without one of the File Mode triggers: an explicit request or a context-threshold nudge.
- Putting an instruction for the receiving session only in this skill; the receiver reads the handoff, so anything it must do belongs in the handoff text.
- Committing a handoff file.
- Paraphrasing user requests or inventing constraints — both must be verbatim.
- Using `#` headers / bold / code fences in the content — breaks clean paste.
- Calling non-existent tools (`session_read`, `todoread`) — the conversation is already in context.
- Dropping the fixed re-read line from EXTERNAL STATUS: without it the receiving side builds on stated status (tracker, review, store or console, inbox) that may have changed since the handoff was written.
- Restating the FIXED block in a later handoff: the task and its acceptance criteria drift a little with every paraphrase, so earlier entries are copied and later ones appended, never rewritten.
- Carrying PERSISTENT STATE forward unchanged: uncommitted files and running services move between handoffs, so it is read from the workspace each time.
