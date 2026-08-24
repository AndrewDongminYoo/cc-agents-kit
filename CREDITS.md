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
| `pathless-rewriter-guard.sh` | original | Apache-2.0 | Written for this repository. |
| `staged-secret-guard.sh` | original | Apache-2.0 | Written for this repository. |
| `lockfile-drift-check.sh` | original | Apache-2.0 | Written for this repository. |
| `shellcheck-on-edit.sh` | original | Apache-2.0 | Written for this repository. |

## context-handoff

| Component | Upstream | Licence | Adaptation |
| --- | --- | --- | --- |
| `handoff` | original | Apache-2.0 | Written for this repository. Conceptually in the same family as the session-continuity skills in [oh-my-opencode](https://github.com/alvinunreal/oh-my-opencode-slim); no text is shared. |
| `session-export` | original | Apache-2.0 | Written for this repository. |
| `log-it` | original | Apache-2.0 | Written for this repository. |
| `wayfinder` | [mattpocock/skills](https://github.com/mattpocock/skills), `skills/engineering/wayfinder` | MIT | Rewritten around a `docs/plans` ticket substrate. 14% of the shipped file is verbatim upstream, measured line-wise. |
| `context-budget` | [affaan-m/ecc](https://github.com/affaan-m/ecc), `skills/context-budget` | MIT | **Largely upstream** — 87% of the shipped file is verbatim, measured line-wise. Included as an MIT redistribution rather than as original work. |
| `config-gc` | [affaan-m/ecc](https://github.com/affaan-m/ecc), `skills/config-gc` | MIT | **Substantially upstream** — 54% of the shipped file is verbatim, measured line-wise. |

## repo-gate

| Component | Upstream | Licence | Adaptation |
| --- | --- | --- | --- |
| `setup-trunk` | original | Apache-2.0 | Written for this repository. |
| `ci-babysit` | original | Apache-2.0 | Written for this repository. |
| `semantic-commit` | original | Apache-2.0 | Written for this repository. |
| `fix-osv-vulnerabilities` | original | Apache-2.0 | Written for this repository. |
| `cspell-triage` | original | Apache-2.0 | Written for this repository. |

## MIT notice

`wayfinder`, `context-budget`, and `config-gc` derive from MIT-licensed work.
That licence permits redistribution with its copyright and permission notice preserved, which is the purpose of this file and of the `metadata.origin` key in each of those skills.
Copyright for the upstream portions remains with their authors — Matt Pocock and the `affaan-m/ecc` contributors respectively.
The rest of this repository is Apache-2.0.

Overlap percentages above are line-wise: unique non-blank lines present in both files, over unique non-blank lines in the shipped file.
Re-derive rather than trusting the number:

```bash
comm -12 <(sort -u upstream/SKILL.md) <(sort -u plugins/<plugin>/skills/<skill>/SKILL.md) | grep -c '\S'
```

## Policy for adapted work

Before a derived component is committed here:

1. Read the upstream licence directly — `gh api repos/OWNER/REPO/license -q .license.spdx_id` — rather than inferring it from a README badge.
2. Record it as a row above, and add an `origin:` key to the component's own frontmatter pointing at the upstream repository.
3. If the adaptation is thin enough that the result is effectively vendored upstream code, it does not belong here. Eight components that are clearly ours beat five whose provenance needs an argument.
