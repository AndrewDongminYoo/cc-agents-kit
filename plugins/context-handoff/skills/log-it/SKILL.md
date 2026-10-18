---
name: log-it
description: Use when the user asks to record what a session discovered or learned ("기록해줘", "로그 남겨줘", "log this", "/log-it"), when a session ends after non-obvious findings or trial-and-error, or before /clear would lose them.
metadata:
  category: claude-config
---

# Log It

## Overview

A session produces facts with different lifetimes and different readers.
Logging them means routing each fact to the store whose reader needs it — never writing one narrative in the most convenient place.

## Route each fact by who must see it

| The fact is...                                                                       | Write to                                                                                                                                                                      | Its reader                            |
| ------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| What the next session in THIS project must know at start (convention, gotcha, state) | project memory `~/.claude/projects/<slug>/memory/`, per the memory system prompt                                                                                              | auto-loaded via MEMORY.md             |
| A pattern that holds beyond this project                                             | a cross-project store you keep outside any one repo — or, for agent-behaviour guidance confirmed in 2+ projects, `~/.claude/rules/`                                          | whatever retrieves precedent for you  |
| Unfinished work the next session continues                                           | thin handoff (below)                                                                                                                                                          | a SessionStart hook, if you run one   |
| Engineering record for humans in the repo                                            | `docs/notes/`, or the notes location the repo already uses                                                                                                                    | repo readers                          |

Rules the routing depends on:

- **A repo note does not replace memory — different readers.** `docs/notes/` is discoverable; memory is _surfaced_. If the fact changes what the next session does before it reads anything, it goes to memory even when a docs/notes copy exists.
- **Never hand-write a store that a job generates.**
  If a scheduled job builds a journal or digest from memory files, write the memory well and let the job carry the fact there.
  A direct write to the generated store collides with the job.
- **A page you add to a shared knowledge store must meet the conventions that store defines before the session ends.** Before you finish, apply each one the store actually has:
  - If it documents a schema, read the schema first.
  - If it keeps an index, register the page the way the store indexes its pages.
  - If it has a check command, run it and leave it green.

  Do not invent a schema, an index, or a command that the store does not define; a plain directory of Markdown files needs none of these steps.
  A page added without the steps its store requires is debt that another session has to diagnose, and an invalid page can turn the shared check red for every other session.
- Keep accounts and contexts separate: work written for one account's store never lands in another's.
- Classify scope out loud (project vs global vs cross-project store) for each fact.
  Make the decision at save time, and say it, because a decision that is not said is the one that gets skipped.

## 시행착오 is the payload

The failed approaches are worth more than the fix: they stop the next agent from retrying them.
For each dead end record the approach, why it failed, and the evidence — error string, count, device-vs-simulator split.
"500ms delay — worked on simulator, failed 1-in-5 on device" prevents a retry; "we tried delays" does not.
No evidence in hand for a failure? Mark it `[UNCERTAIN]` rather than asserting it.

A closed post-mortem and a living status fact never share a file, even when found in the same hour.
They have different lifetimes: the status file keeps changing, and a post-mortem inside it is edited toward the present until it no longer records what happened.

## Thin handoff

Only when work is genuinely unfinished — a handoff with no next mission is noise.
Write `~/.claude/handoffs/<project>-<yyyymmdd-hhmm>.md` with:

- a line reading exactly `cwd: <absolute project root>` — a SessionStart pickup hook, if you run one, would grep that literal line (`grep -x`) to route the file to the right project
- `## NEXT MISSION` — the single next action, concrete enough to start cold
- the state that matters: branch, uncommitted files, blockers
- a closing line for the receiving session, which never sees this skill: `Re-read the source of any status above before acting on it. After resuming from this file, move it to ~/.claude/handoffs/archive/ so it is not picked up twice.`

Keep it ≤ 30 lines. The full template belongs to the handoff skill; this is the thin variant for "mostly done, one thread open", and it is one of the handoff skill's File Mode triggers. Never commit it.

## Gate

Don't log what the repo already records (commit messages, CLAUDE.md, the diff) — cite it instead.
One file, one fact.
Anything written to memory gets its MEMORY.md index line in the same pass.

**A fact "too small to earn its own file" still gets a file.** MEMORY.md carries pointers only — an index-inline fact has no frontmatter, no type, no links, and vanishes the first time the index is regenerated from the files. The smallest valid memory is three frontmatter lines and one sentence; that is cheaper than losing the fact.
That is an argument against inlining a fact, not an argument for a new file: the step below decides whether the file is new.

## Before writing: extend, retire, then create

A new memory is the last of three moves, not the first.
Read the project's `MEMORY.md` and open the entries this session's findings touch, then in order:

1. **Extend.** If an existing memory already owns this subject, the finding belongs inside it. A second file on the same subject splits the answer, and the reader gets whichever half surfaces first.
2. **Retire.** Say what this session proved obsolete and act on it — a resolved bug's workaround, a superseded procedure, a status file whose state has moved, a memory whose content was promoted to a rule or a skill. Delete the file and its index line, or mark it resolved inside the file if the history is worth keeping. Retiring is part of logging, not cleanup for later.
3. **Create** only what neither of the first two absorbs.

Say which of the three each finding took, so the decision is visible rather than skipped.

**Why this is a gate and not a preference:** `MEMORY.md` is loaded at the start of every session in that project, so every index line costs context in every future session, whether or not that session reads it.
An index that only grows spends more of every session on entries that no longer earn their line.
