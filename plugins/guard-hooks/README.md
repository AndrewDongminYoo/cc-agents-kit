# guard-hooks

Nine defensive hooks for Claude Code.
Five block a tool call before it runs, three attach a warning after it, and one masks credential-shaped values in Bash output before the model reads them.

```bash
/plugin marketplace add AndrewDongminYoo/cc-agents-kit
/plugin install guard-hooks@cc-agents-kit
```

## The hooks

| Hook                          | Event and matcher                 | Blocks | What it does                                                                          |
| ----------------------------- | --------------------------------- | ------ | ------------------------------------------------------------------------------------- |
| `dangerous-command-guard.sh`  | PreToolUse, `Bash`                | yes    | Refuses a recursive delete of the home directory and a download-and-execute pipeline. |
| `zsh-quoting-guard.sh`        | PreToolUse, `Bash`                | yes    | Refuses two zsh quoting mistakes that fail with no error.                             |
| `pathless-rewriter-guard.sh`  | PreToolUse, `Bash`                | yes    | Refuses a formatter or bulk rewrite that names no path.                               |
| `staged-secret-guard.sh`      | PreToolUse, `Bash`                | yes    | Refuses a commit whose staged diff contains a credential.                             |
| `secrets-path-guard.sh`       | PreToolUse, file and search tools | yes    | Refuses access to secrets files such as dotenv files.                                 |
| `lockfile-drift-check.sh`     | PostToolUse, `Edit`, `Write`      | no     | Warns when a manifest changed and its lockfile did not.                               |
| `shellcheck-on-edit.sh`       | PostToolUse, `Edit`, `Write`      | no     | Reports shellcheck findings for an edited shell script.                               |
| `output-secret-mask.sh`       | PostToolUse, `Bash`               | no     | Replaces credential-shaped values in the tool result.                                 |
| `security-review-findings.sh` | PostToolUse, `Bash`               | no     | Surfaces the findings of an automatic security review after a commit.                 |

## What the plugin runs

Each hook is a Bash script that reads the hook input on standard input.
The scripts name dangerous command shapes and credential patterns only to detect them: the plugin does not download or execute remote code, does not read a credential to use it, and makes no network request.

A blocking hook exits with status 2 and prints the reason.
No hook approves a tool call or changes its input.
`output-secret-mask.sh` is the one hook that changes a tool result, and it only removes values.

The plugin also puts `env-keys` on `PATH`, a Python 3 program that prints the key names of a dotenv file and never the values.

## Requirements and opt-outs

- `jq` is required. A hook fails open without it, so the guards stop guarding and report no error.
- `bash` 3.2 or later. `git` for `staged-secret-guard.sh`.
- Optional: `shellcheck` for `shellcheck-on-edit.sh` and `gitleaks` 8.x for `output-secret-mask.sh`. Each hook does nothing without its tool.
- Each hook has its own `CC_GUARD_DISABLE_*` variable. A disabled hook still reads its input and exits with status 0.

## More

The reasons for each guard, the known limits, the opt-out variables and the test suites are in the [cc-agents-kit repository](https://github.com/AndrewDongminYoo/cc-agents-kit#guard-hooks).
Licence: Apache-2.0.
