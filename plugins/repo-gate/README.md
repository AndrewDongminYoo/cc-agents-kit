# repo-gate

Six skills for the stretch between "the code works" and "it is pushed".

```bash
/plugin marketplace add AndrewDongminYoo/cc-agents-kit
/plugin install repo-gate@cc-agents-kit
```

## Skills

| Skill                     | Use it when                                                                                        |
| ------------------------- | -------------------------------------------------------------------------------------------------- |
| `semantic-commit`         | Unrelated changes are mixed and must be split into conventional commits, verified before each one. |
| `setup-trunk`             | You add trunk.io to a repository, or configure its linters over code with existing violations.     |
| `ci-babysit`              | A pushed branch or an open pull request needs CI monitoring. A watch-only request stays read-only. |
| `fix-osv-vulnerabilities` | `osv-scanner` or `trunk check` reports GHSA advisories that need triage, not a blanket upgrade.    |
| `cspell-triage`           | cspell reports unknown words, or its dictionaries need consolidating.                              |
| `markdownlint-triage`     | A markdownlint log needs a summary by rule, or a backlog needs fixing file by file.                |

The skills read the project's own declared scripts and do not assume a stack.

## What the plugin runs

The plugin has no hooks.
It puts three helper programs on `PATH` while it is enabled:

- `markdownlint-summary` (Bash) runs `markdownlint` from `PATH`, or `trunk` when `markdownlint` is absent, and groups the result by rule. It downloads nothing.
- `cspell-dict-report` (Python 3) reads a word list on standard input and ranks the cspell dictionaries that would clear it.
- `find-trunk-repos` (Bash) lists public repositories that contain `.trunk/trunk.yaml`. It calls the GitHub CLI, so it makes requests to GitHub with the account that `gh` is signed in to.

`semantic-commit` runs `git` commands in the current repository, including `git add`, `git commit`, `git stash` and `git worktree`.
The other skills tell Claude which project commands to run, and each command passes through the usual permission prompt.

## Requirements

`git`, plus the tool that each skill is about: `trunk`, `gh`, `osv-scanner`, `cspell` or `markdownlint-cli`.

## More

The full documentation and the licence are in the [cc-agents-kit repository](https://github.com/AndrewDongminYoo/cc-agents-kit#repo-gate).
Licence: Apache-2.0.
