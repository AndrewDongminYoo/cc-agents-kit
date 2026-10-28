# Quality Tooling Refresh Plan

## Work

1. Verify repository identity, instructions, current changes and Oracle precedent.
2. Refresh compatible dependency and linter versions with existing package managers.
3. Run the declared local gates and `trunk check --all --no-fix --jobs=2`.
4. Reconcile affected knowledge and review the scoped candidate.
5. Commit locally and prepare visible evidence before requesting publication approval.

## Declared Gates

- Execute the unchanged validation `run` bodies from `.github/workflows/ci.yml` under `/bin/bash --noprofile --norc -e -o pipefail -c`, with PyYAML available to `python3`.
- Run the embedded checks named `Validate manifests`, `Every marketplace plugin source exists`, `Every wired hook exists`, `Every skill has parseable frontmatter with a name and description`, `No private or machine-specific references`, `Plugin bin/ entries are runnable`, and `Demo quotes the guard's current message`.
- Run CI's `List every shipped shell script` step before `xargs -0 shellcheck <"$RUNNER_TEMP/shell-files.z"` and `xargs -0 -n1 /bin/bash -n <"$RUNNER_TEMP/shell-files.z"`.
- `(cd plugins/guard-hooks/hooks && for t in *.test.py; do python3 "$t" || exit 1; done)`.
- `for t in plugins/*/bin/*.test.py; do python3 "$t" || exit 1; done`.
- `trunk check --all --no-fix --jobs=2`.
- `git diff --check`.

## Verification Scope

The local run covers macOS system Bash and the exact repository validation bodies.
The Linux matrix remains a hosted CI gate.
The optional `claude plugin validate` and `claude plugin test` commands are outside the default CI gate.
There are no tracked project dependency manifests or lockfiles to regenerate.
Registry metadata and exact command results are recorded in the external review directory.
