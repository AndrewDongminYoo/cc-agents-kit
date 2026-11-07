# Compaction Brief

A compaction and a handoff are the same artifact seen from two sides: a brief that lets a fresh context continue the work.
This spec gives `context-handoff` one shape for both, taken from the compaction prompt that arXiv 2611.05306 ("You don't need long context", Belcak et al., 2026-11-03) ran in Appendix G, and ships it as a hook that steers every compaction plus a rewritten `handoff` template.

## Approved Scope

1. A `PreCompact` command hook, `plugins/context-handoff/hooks/compaction-brief.sh`, that prints the brief instructions on stdout and exits `0`.
   Claude Code uses a `PreCompact` hook's stdout as the instructions for the compaction summary (hooks reference, "When a PreCompact hook exits 0 and doesn't block, Claude Code uses its stdout as instructions for the compaction summary", 10,000-character cap per hook).
2. A `SessionStart` command hook on the `compact` matcher, `plugins/context-handoff/hooks/post-compact-retrieval.sh`, that adds one short context line naming the transcript path, so history the summary dropped stays retrievable with `grep`.
3. The `handoff` skill's Output Template rewritten to the same section list, split into a FIXED block and a RECAP block.
4. `hooks/hooks.json`, a regression suite beside each hook, README and CHANGELOG entries, and a `context-handoff` version bump from 0.2.3 to 0.3.0.

Out of scope: blocking or vetoing a compaction (the `context-meter` mod owns the veto; the personal `handoff-first-precompact` hook owns the once-per-session advice), writing handoff files automatically, changing `log-it`'s thin handoff, and a Bash-output spill hook (recorded as a later idea in the project memory `context-handoff-compaction-brief-shape`).

## Why this shape

The paper's long-horizon results (Claude Opus 4.5 within -3.7 to +5.6 points of full history across 22 threshold settings, with the Appendix G prompt driving every compaction) are the evidence for the section list; Appendix A's prose alone had led to a wrong reading of it, so the prompt text, not the description, is the source.
Appendix A's finding is that the best compactions "are not narratives of the execution history but carefully cherry-picked briefs for further execution".
That excludes equal-weight summarization, not history: the prompt keeps applied changes, verification results and dead ends because each one changes what the next stretch does.
The harness, not the model, re-supplies the task on reset ("Do not invent observations or repeat the full task or document manifest"), which is why the template has a FIXED block the recap never paraphrases.
A second compaction still has to carry requests and corrections made after the first brief, so the block is append-only rather than frozen (Codex review on PR #96, 2026-11-07), and mutable workspace state lives in the RECAP, where it is read fresh each time.
Section 3.1 of the paper gives the fallback for what any lossy compaction loses: keep every message on disk and expose it to selective reading, which Claude Code already does through `transcript_path`.

## The brief

Both the hook and the template use this section list.
Wording differs by channel (second person for the hook, first person for the handoff), the sections do not.

```plaintext
FIXED (append-only: earlier entries copied word for word, later requests and corrections added in order;
       where a later one replaces an earlier one, both stay and the current one is named)
  Task              the user's requests, verbatim, in order
  Done when         the acceptance criteria, verbatim where the user gave them
  User constraints  verbatim constraints from the user or CLAUDE.md/AGENTS.md; "None" if none

RECAP (written fresh on every compaction or handoff from the current state)
  Persistent state  branch, worktree, uncommitted files, running services, and the transcript path, as they are now
  Objective         one line: the required result of the current stretch
  Established facts exact paths, symbols, commands, observed values, key errors;
                    observations separated from unverified ideas
  Applied changes   each changed or created file, what changed, and whether it was verified
  Verification      exact checks run, outcomes, failures, obstacles, workarounds
  Dead ends         failed approaches not to repeat, each with its evidence
  Remaining plan    outstanding subgoals in execution order, the immediate next command or edit,
                    and the condition for completion
  Retrieval         narrow commands to re-fetch truncated output or dropped history
                    (a `grep`/`sed -n` over the transcript path, a file and line range)
  External status   each tracker issue, review, console or inbox with the URL, ID or path to re-read it from
```

`External status` and the fixed closing line ("re-read any status above from its named source; treat a status with no named source as unverified") carry over from `handoff` 0.2.3 unchanged, because they are an existing contract (#79).
`User constraints` is kept although the paper did not test human-in-the-loop sessions: Appendix A names lost user preferences as the common failure of compaction, and every session this plugin serves has a user.

## Hook contracts

### `compaction-brief.sh` (`PreCompact`, matcher `manual|auto`)

- Reads all of stdin first, then checks `CC_GUARD_DISABLE_COMPACTION_BRIEF=1`; when set, exits `0` with no output.
- Prints the brief instructions as plain text on stdout and exits `0`.
  Never exits `2`, never prints `decision`, never prints `systemMessage` (PreCompact discards it).
- Output under 4,000 characters, well inside the 10,000-character cap, so a second PreCompact hook in the same session has room.
- Includes the `transcript_path` from the payload in the Persistent state instruction when present, so the summary can name it.
- On `manual` with a non-null `custom_instructions`, still prints the brief; the docs do not state how the two combine, and the plan's first step measures it.
- Fails open: empty, malformed or key-less stdin exits `0` and prints the brief anyway (printing nothing would silently fall back to the default summary, which is the condition this hook exists to replace; a brief with no transcript path is still a valid brief).
- Parses under macOS `/bin/bash` 3.2; reads `transcript_path` with `jq ... || true` under the kit's rule that `jq` is a documented prerequisite never checked at runtime (README §Prerequisites, CLAUDE.md §Hook contract), so without `jq` the brief carries the generic transcript line and the retrieval hook stays silent, the same fail-open as every other hook.

### `post-compact-retrieval.sh` (`SessionStart`, matcher `compact`)

- Reads all of stdin first, then checks `CC_GUARD_DISABLE_POST_COMPACT_RETRIEVAL=1`.
- When `transcript_path` is present, prints one line of plain text on stdout and exits `0`: the transcript path and the instruction to `grep` it before re-deriving anything the summary does not mention.
  Plain stdout on exit 0 is added as context for `SessionStart`.
- Fails open: no `transcript_path`, empty or malformed stdin exits `0` with no output.
- Under 300 characters, so it costs one line of context per compaction.

### `hooks/hooks.json`

Two entries, `PreCompact` with matcher `manual|auto` and `SessionStart` with matcher `compact`, each `type: command`, `timeout: 5`, commands referencing `${CLAUDE_PLUGIN_ROOT}`.
Adding `hooks/hooks.json` makes the plugin auto-discover hooks; `plugin.json` keeps `"skills": "./skills"` and gains nothing else.

## Interaction with what already runs

- `context-meter` vetoes an auto-compact before any `PreCompact` command hook matters; when it lets one through, this hook shapes the summary.
  No overlap: one decides whether, the other decides what.
- The personal `handoff-first-precompact.sh` prints a `systemMessage` JSON on the first auto-compact.
  Per the hooks reference, `PreCompact` discards `systemMessage` and treats stdout as summary instructions, so that JSON currently reaches the summarizer as text.
  This spec does not change that script (it is personal config, outside the repository), but the plan's first measurement should show whether both outputs are concatenated, and the finding goes back to the owner of that script.
- #77 removed the plugin's mention of a PreCompact hook as text that fit one author's setup.
  This hook is not that hook: it never advises, blocks or writes a file, so it does not reverse #77.

## Template rewrite (`skills/handoff/SKILL.md`)

- Output Template becomes the FIXED/RECAP list above, still plain text with dash bullets and no markdown headers inside the content, so it pastes as one message.
- Format Rules keep: verbatim-only for Task, Done when and User constraints; no secrets; the fixed closing line.
  The "max 10 files" rule moves from a KEY FILES section to Established facts and Applied changes, where files now live.
- File Mode and the Gate are unchanged.
- The "Handoff-first policy" paragraph gains one sentence: the plugin's `PreCompact` hook gives every compaction this same section list, so a compaction the user lets run is the thin version of this handoff, not a different document.

## Acceptance

- `python3 plugins/context-handoff/hooks/compaction-brief.test.py` and `post-compact-retrieval.test.py` pass, and each fails when its hook's output line is removed (mutation parses under `/bin/bash -n`).
- The suites cover: brief printed on `auto` and `manual`; opt-out drains a 200KB payload and prints nothing; empty and malformed stdin exit `0`; transcript path appears in the output when supplied and the output stays valid without it; output length under the stated bounds; `SessionStart` hook prints nothing without `transcript_path`.
- `/bin/bash -n` and `shellcheck` pass on both scripts; the CI shell list picks them up without changes to `ci.yml`.
- Measured once in a live session (recorded in the plan with date and session id): a manual `/compact` after the hook is installed produces a summary with the eight RECAP headings, and the post-compaction context contains the retrieval line.
- README's `context-handoff` section lists both hooks and their opt-outs; CHANGELOG `[Unreleased]` names the change and the bump to 0.3.0; `plugin.json` reads 0.3.0 in the same commit.
- `handoff` SKILL.md frontmatter and `name` unchanged; `claude plugin validate plugins/context-handoff` passes.

## Open points the plan must settle by measurement, not assumption

1. Whether `custom_instructions` from `/compact <text>` and hook stdout are concatenated, and in which order.
2. Whether the transcript file keeps pre-compaction messages after a compaction (the docs do not say); if it is rewritten, the retrieval line names the file but the Retrieval section must say what it can and cannot recover.
3. Whether `SessionStart` with `source: "compact"` adds the hook's stdout to the post-compaction context in the current Claude Code version.

## Publication

Push and PR creation wait for explicit approval.
The PR follows `opening-and-merging-prs`; the version bump rides the feature commit and the release commit stays CHANGELOG-only (CONTRIBUTING §Releasing).
