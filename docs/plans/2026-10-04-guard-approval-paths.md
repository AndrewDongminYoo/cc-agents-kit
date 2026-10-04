# Implementation plan

1. Observe failing synthetic mode/path/normal-sourcing regressions on the previous candidate.
2. Replace exact-command approval with an isolated, default-off development-path matcher that emits only an abstention token.
   Remove the consumer policy, inspector and obsolete tests.
3. Rewrite documentation around operator classification, value access, normal sourcing and overlapping deny rules.
   Prepare an inactive empty path inventory and permission-diff worksheet outside this repository.
4. Run all suites, system Bash, shellcheck, manifests, CLI validation and meaningful mutants.
   Review the changed contract and implementation independently before publication.
5. Commit and push, explain how removal of the old executable guarantee addresses the valid shell-function finding, and observe exact-head CI/reviews.
   Use at most the two remaining hosted rounds; do not merge or install.

Owned paths: guard-hooks dotenv hook/helper/tests and obsolete inspector files, README, CLAUDE.md, environment guide, spec and plan.
Do not change staged-secret-parser files or live settings.
Git-local loop state is never committed.
