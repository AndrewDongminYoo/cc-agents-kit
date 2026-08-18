---
name: log-it
description: Use when the user asks to record what a session discovered or learned ("기록해줘", "로그 남겨줘", "log this", "/log-it"), when a session ends after non-obvious findings or trial-and-error, or before /clear would lose them.
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
| Engineering record for humans in the repo                                            | `docs/notes/` (global CLAUDE.md convention)                                                                                                                                   | repo readers                          |

Rules the routing depends on:

- **A repo note does not replace memory — different readers.** `docs/notes/` is discoverable; memory is _surfaced_. If the fact changes what the next session does before it reads anything, it goes to memory even when a docs/notes copy exists.
- **Never write `wiki/journal/`.** The daily-journal launchd job generates it FROM memory files; writing memory well is how something reaches the journal. A direct journal write collides with the job.
- **A wiki page you create must pass the vault's own gate before the session ends.** Read the vault's `schema.md` first (frontmatter shape; the scope facet forbids `account:`/`project:` under `scope: global`), register the page in `wiki/index.md`, then run `pnpm wiki:clean` in the vault and leave it green. A page dropped in without this is debt another session has to diagnose — observed 2026-08-15, when two concept pages left unindexed with an invalid `account:` field turned the shared gate red for every other session.
- Keep accounts and contexts separate: work written for one account's store never lands in another's.
- Classify scope out loud (project vs global vs wiki) for each fact — memory-scope requires the decision at save time, and saying it is what keeps it from being skipped.

## 시행착오 is the payload

The failed approaches are worth more than the fix: they stop the next agent from retrying them.
For each dead end record the approach, why it failed, and the evidence — error string, count, device-vs-simulator split.
"500ms delay — worked on simulator, failed 1-in-5 on device" prevents a retry; "we tried delays" does not.
No evidence in hand for a failure? Mark it `[UNCERTAIN]` rather than asserting it.

A closed post-mortem and a living status fact never share a file, even when found in the same hour (memory-scope's lifetime axis).

## Thin handoff

Only when work is genuinely unfinished — a handoff with no next mission is noise.
Write `~/.claude/handoffs/<project>-<yyyymmdd-hhmm>.md` with:

- a line reading exactly `cwd: <absolute project root>` — the pickup hook greps that literal line (`grep -x`); without it the handoff is never surfaced
- `## NEXT MISSION` — the single next action, concrete enough to start cold
- the state that matters: branch, uncommitted files, blockers

Keep it ≤ 30 lines. The full template belongs to the handoff skill; this is the thin variant for "mostly done, one thread open".

## Gate

Don't log what the repo already records (commit messages, CLAUDE.md, the diff) — cite it instead.
One file, one fact.
Anything written to memory gets its MEMORY.md index line in the same pass.

**A fact "too small to earn its own file" still gets a file.** MEMORY.md carries pointers only — an index-inline fact has no frontmatter, no type, no links, and vanishes the first time the index is regenerated from the files. The smallest valid memory is three frontmatter lines and one sentence; that is cheaper than losing the fact.
