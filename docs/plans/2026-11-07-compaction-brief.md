# Implementation plan

Spec: `docs/specs/2026-11-07-compaction-brief.md` (approved 2026-11-07).

1. Write `plugins/context-handoff/hooks/compaction-brief.sh` (PreCompact, stdout brief, exit 0, opt-out after the stdin drain) and `post-compact-retrieval.sh` (SessionStart `compact`, one retrieval line) → verify: `/bin/bash -n` and `shellcheck` on both, then each script run by hand with an `auto` payload, a `manual` payload carrying `custom_instructions`, an empty payload and malformed JSON.
2. Write `hooks/hooks.json` wiring both, and extend CI's "Hook regression suites" step from `plugins/guard-hooks/hooks` to every `plugins/*/hooks` directory → verify: the CI hooks.json check (missing-script detection) passes on the archive tree, and the extended loop still runs the guard-hooks suites.
3. Write `compaction-brief.test.py` and `post-compact-retrieval.test.py` beside the hooks; the opt-out drain case imports `_optout` from `plugins/guard-hooks/hooks` by path rather than copying it → verify: both suites pass, then each fails when its hook's output line is removed (mutant parsed with `/bin/bash -n` first), then passes again.
4. Rewrite the `handoff` skill's Output Template and Format Rules to the FIXED/RECAP list, and add the one-sentence link from the handoff-first paragraph to the hook → verify: frontmatter `name` unchanged; `claude plugin validate plugins/context-handoff` passes.
5. README `context-handoff` section gains a hooks table with opt-outs; CHANGELOG `[Unreleased]` names the change; `plugin.json` 0.2.3 → 0.3.0 → verify: the CI private-reference step on `git archive HEAD`, `trunk fmt` + `trunk check` on the changed files.
6. Live measurement, after the plugin is reinstalled from the bumped version in a session that is not this one: a manual `/compact` shows the eight RECAP headings in the summary and the retrieval line in the post-compaction context; a `/compact <text>` shows how `custom_instructions` and the hook's stdout combine → record the date, session id and result in a reconciliation section of this plan. Spec open points 1 and 3 are settled here; open point 2 by the read-only investigation of existing transcripts started the same day.

## Reconciliation 2026-11-07

Spec open point 2 is settled by the read-only transcript survey run the same day: a compaction appends a `system` record with `subtype: compact_boundary` (its `compactMetadata` carries `trigger`, `preTokens`, `postTokens`) followed by a `user` record with `isCompactSummary: true`, and every earlier record stays in the file.
Evidence: 29 boundaries across 2,543 transcript files under the Claude projects directory; one file holds two boundaries at records 1815 and 2406 with records 1 to 1814 intact.
The retrieval line therefore names a file that still holds the pre-compaction history.
Open points 1 and 3 remain for step 6.

Owned paths: `plugins/context-handoff/hooks/**`, `plugins/context-handoff/skills/handoff/SKILL.md`, `plugins/context-handoff/.claude-plugin/plugin.json`, `.github/workflows/ci.yml` (one step), `README.md` (context-handoff section), `CHANGELOG.md`, this spec and plan.
Do not change `~/.claude/scripts/handoff-first-precompact.sh` or `settings.json`; the personal-hook finding is investigated separately and reported, not fixed here.
Push and PR wait for explicit approval.
