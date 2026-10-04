# Implementation plan

1. Add failing synthetic hook regressions for literal-data abstention and the
   exact inspector approval path. Add inspector behavior checks before coding it.
2. Add a conservative command recognizer and a bounded data-only inspector.
   Keep legacy denial when recognition is uncertain or unavailable.
3. Replace secret-copy instructions and document the approval contract, template
   schema, purpose-specific execution and temporary-artifact lifecycle. Bump the
   guard-hooks plugin version with the behavior change.
4. Prepare inactive local settings/review proposals outside this repository.
   Record permission deltas and assess representative review/test scenarios.
5. Run regressions, syntax/lint/manifest checks and the project suites. Review
   security failure paths, repair confirmed findings, commit by concern and open
   a Draft PR. Observe CI and hosted reviews at the pushed SHA; do not merge.

Owned public paths: guard-hooks hooks and bin entries, README, this specification
and plan, and the guard-hooks manifest. Git-local loop state is never committed.
