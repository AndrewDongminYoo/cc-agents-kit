# Credits

Provenance for everything shipped in this repository.
This file is the single place attribution is recorded — a skill or hook never restates its own origin, it points here.

Column meanings:

- **Upstream** — the project the work derives from, or `original` when it was written for this repository.
- **Licence** — the upstream project's SPDX identifier, read from the upstream repository rather than assumed.
- **Adaptation** — how much of the shipped version is new work.

## guard-hooks

| Component | Upstream | Licence | Adaptation |
| --- | --- | --- | --- |
| `dangerous-command-guard.sh` | original | Apache-2.0 | Written for this repository. |
| `secrets-path-guard.sh` | original | Apache-2.0 | Written for this repository. |
| `zsh-quoting-guard.sh` | original | Apache-2.0 | Written for this repository. |
| `lockfile-drift-check.sh` | original | Apache-2.0 | Written for this repository. |
| `shellcheck-on-edit.sh` | original | Apache-2.0 | Written for this repository. |

## Policy for adapted work

Before a derived component is committed here:

1. Read the upstream licence directly — `gh api repos/OWNER/REPO/license -q .license.spdx_id` — rather than inferring it from a README badge.
2. Record it as a row above, and add an `origin:` key to the component's own frontmatter pointing at the upstream repository.
3. If the adaptation is thin enough that the result is effectively vendored upstream code, it does not belong here. Eight components that are clearly ours beat five whose provenance needs an argument.
