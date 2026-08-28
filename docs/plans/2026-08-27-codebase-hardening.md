# Codebase Hardening Implementation Plan

**Goal:** Establish a minimum definition of done, restore required MIT notices, remove data-loss and unapproved-mutation guidance, and add regression coverage for guards, CLI tools, and marketplace validation.

**Scope:** This plan changes only the named documentation, skills, hook scripts, CLI tools, tests, workflow validation, and plugin patch versions.

**Spec:** No separate specification exists.
The approved definition of done in this plan is the binding acceptance contract.

## Global Constraints

- Preserve existing public command and hook interfaces unless a listed defect requires a stricter failure.
- Do not add dependencies.
- Use `/bin/bash` 3.2-compatible syntax in shipped shell scripts.
- Add behavior tests before changing guard or CLI behavior, and observe the new test fail for the intended reason before implementing the fix.
- Keep malformed hook input fail-open unless an actual protected command was identified.
- Stage and commit only with explicit authorization.
- Do not push, publish, or change external state.
- Do not edit changelogs because this work does not cut a release.
- Bump each changed plugin manifest by one patch version in the same working-tree change.

## Minimum Definition of Done

1. The repository contains the full MIT copyright and permission notices required by the declared upstream licenses, and `CREDITS.md` points to them without contradicting the redistribution policy.
2. `semantic-commit`, `cspell-triage`, `fix-osv-vulnerabilities`, and `ci-babysit` no longer recommend commands or workflows that can discard unrelated work, replace a lockfile without approval, suppress a reachable vulnerability by default, or commit and push without explicit authority.
3. The three guard regressions that previously exited 0 now exit 2, while `git help commit` exits 0.
4. The new guard tests are proven by a red-green cycle and all existing guard tests still pass.
5. `session-to-md` rejects malformed option values and refuses to overwrite an existing output file.
6. `find-trunk-repos` treats only a repository-content 404 as absence and propagates other GitHub API failures.
7. CI automatically runs the new CLI regression tests and verifies that each marketplace source contains a matching plugin manifest with unique source and plugin names.
8. All changed shell scripts pass ShellCheck and `/bin/bash -n`, all Python and Node regression suites pass, manifests and skill frontmatter parse, plugin validation passes, and repository Markdown links resolve.

## Task 1: Restore Notices and Harden Mutation Guidance

**Files:**

- Create: `THIRD_PARTY_NOTICES.md`
- Modify: `CREDITS.md`
- Modify: `plugins/repo-gate/skills/semantic-commit/SKILL.md`
- Modify: `plugins/repo-gate/skills/cspell-triage/SKILL.md`
- Modify: `plugins/repo-gate/skills/fix-osv-vulnerabilities/SKILL.md`
- Modify: `plugins/repo-gate/skills/ci-babysit/SKILL.md`

**Implementation:**

- Include the full MIT license notice for Affaan Mustafa, copyright 2026, covering `context-budget` and `config-gc`.
- Include the full MIT license notice for Matt Pocock, copyright 2026, covering `wayfinder`.
- Make `CREDITS.md` link to the notices and describe thin vendoring consistently with the repository policy.
- Make semantic commits isolate the exact staged group and verify the full index before every commit.
- Make the cspell canary preserve and compare the pre-existing working-tree diff without `git checkout` or `git restore` on the file.
- Make vulnerability suppression require reachability evidence, explicit approval, a dated reason, and reevaluation ownership.
- Preserve lockfiles by default and require explicit approval before an isolated fresh regeneration.
- Resolve the active pull request number before polling CI, cap empty polls, and require explicit authority before commit or push.

**Verify:**

```bash
rg -n 'git checkout --|rm yarn\.lock|git push|IgnoredVulns|THIRD_PARTY_NOTICES' CREDITS.md THIRD_PARTY_NOTICES.md plugins/repo-gate/skills/{semantic-commit,cspell-triage,fix-osv-vulnerabilities,ci-babysit}/SKILL.md
```

## Task 2: Tokenize and Regress the Guard Hooks

**Files:**

- Modify: `plugins/guard-hooks/hooks/dangerous-command-guard.sh`
- Modify: `plugins/guard-hooks/hooks/dangerous-command-guard.test.py`
- Modify: `plugins/guard-hooks/hooks/staged-secret-guard.sh`
- Modify: `plugins/guard-hooks/hooks/staged-secret-guard.test.py`
- Modify: `plugins/guard-hooks/hooks/pathless-rewriter-guard.sh`
- Modify: `plugins/guard-hooks/hooks/pathless-rewriter-guard.test.py`

**Implementation:**

- Block quoted and braced home-directory roots with or without a trailing slash.
- Tokenize the full command before deciding whether malformed quoting is relevant.
- Block an unparseable command only after locating an actual `git commit` invocation.
- Recognize `git commit` after command prefixes or newline-separated commands, and allow `git help commit`.
- Recognize `npx --yes`, `npx -y`, version-qualified known rewriter names, and `pnpm exec`.
- Avoid implementing a general-purpose shell parser.

**Red verify before implementation:**

```bash
cd plugins/guard-hooks/hooks && python3 dangerous-command-guard.test.py && python3 staged-secret-guard.test.py && python3 pathless-rewriter-guard.test.py
```

The command must fail because at least one newly added regression case still exits 0 or blocks `git help commit`.

**Green verify after implementation:**

```bash
cd plugins/guard-hooks/hooks && for test_file in *.test.py; do python3 "$test_file" || exit 1; done
```

## Task 3: Harden CLI Failure Semantics

**Files:**

- Modify: `plugins/context-handoff/bin/session-to-md`
- Create: `plugins/context-handoff/bin/session-to-md.test.py`
- Modify: `plugins/repo-gate/bin/find-trunk-repos`
- Modify: `plugins/repo-gate/bin/find-trunk-repos.test.py`

**Implementation:**

- Accept only exact positive integers for `--last`.
- Accept only `collapsed`, `none`, or `full` for `--tools`.
- Accept at most one positional session identifier.
- Create output files exclusively and report a concise error without a stack trace if the path already exists or cannot be written.
- Continue past repository-content 404 responses in `find-trunk-repos` and propagate every other repository-content API failure with repository context.

**Red verify before implementation:**

```bash
python3 plugins/context-handoff/bin/session-to-md.test.py && python3 plugins/repo-gate/bin/find-trunk-repos.test.py
```

The command must fail because the current implementations accept an invalid option, overwrite an output, or hide a non-404 API failure.

**Green verify after implementation:**

```bash
for test_file in plugins/*/bin/*.test.py; do python3 "$test_file" || exit 1; done
```

## Task 4: Strengthen Marketplace CI and Version Metadata

**Files:**

- Modify: `.github/workflows/ci.yml`
- Modify: `plugins/context-handoff/.claude-plugin/plugin.json`
- Modify: `plugins/guard-hooks/.claude-plugin/plugin.json`
- Modify: `plugins/repo-gate/.claude-plugin/plugin.json`

**Implementation:**

- Validate that marketplace sources and names are unique.
- Require each source directory to contain `.claude-plugin/plugin.json`.
- Parse each source manifest and require its plugin name to match the marketplace entry.
- Bump `context-handoff` from `0.1.3` to `0.1.4`, `guard-hooks` from `0.2.4` to `0.2.5`, and `repo-gate` from `0.1.4` to `0.1.5`.

**Verify:**

```bash
python3 -c 'import json, pathlib; [json.load(path.open()) for path in pathlib.Path(".").glob("plugins/*/.claude-plugin/plugin.json")]'
```

## Task 5: Run the Full Local Gate and Review the Integrated Diff

**Files:** No product files are assigned unless a verification failure identifies a defect in the named scope.

**Verify:**

```bash
for test_file in plugins/guard-hooks/hooks/*.test.py; do python3 "$test_file" || exit 1; done
for test_file in plugins/*/bin/*.test.py; do python3 "$test_file" || exit 1; done
find plugins -type f -name '*.sh' -print0 | xargs -0 shellcheck
shellcheck plugins/repo-gate/bin/find-trunk-repos
find plugins -type f -name '*.sh' -print0 | xargs -0 -n1 /bin/bash -n
/bin/bash -n plugins/repo-gate/bin/find-trunk-repos
node --check plugins/context-handoff/bin/session-to-md
claude plugin validate .
```

- Run the CI Python validators for manifests, skill frontmatter, marketplace source manifests, wired hooks, executable plugin commands, and private references.
- Run the repository Markdown link validator used in the existing review workflow.
- Inspect `git diff --check`, `git diff --stat`, the full diff, and `git status --short`.
- Complete an independent whole-diff code review and an adversarial cross-check before reporting completion.
