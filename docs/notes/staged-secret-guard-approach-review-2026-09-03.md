# staged-secret-guard: what the string-parsing approach can and cannot do

A record of what was measured on 2026-09-03 while fixing PR #9, kept so the next
attempt starts from evidence rather than from the same premise.

The hook's job is to stop a credential from reaching a commit.
Its method is to read the shell command an agent is about to run, decide whether
that command will invoke `git commit`, and scan the staged diff if it will.
This note is about the method, not the scanning.

## What it actually catches

Thirteen ways to reach a commit, each run against the installed 0.2.6 and
against the PR #9 branch, in a repository with a credential staged.
`ALLOWED` means the commit would proceed with the credential unscanned.

| shape | 0.2.6 | PR #9 |
| --- | --- | --- |
| `git commit -m x` | refused | refused |
| `git -c alias.ci=commit ci -m x` | refused | refused |
| `autocommit`, a zsh function in the operator's `.zshrc` | ALLOWED | ALLOWED |
| `bash script.sh` | ALLOWED | ALLOWED |
| `sh -c "git commit -m x"` | ALLOWED | ALLOWED |
| `eval "git commit -m x"` | ALLOWED | ALLOWED |
| `g=git; $g commit -m x` | ALLOWED | ALLOWED |
| `GC() { git "$@"; }; GC commit -m x` | ALLOWED | ALLOWED |
| `git ci -m x`, alias from a config file | ALLOWED | ALLOWED |
| `xargs git commit -m x` | ALLOWED | ALLOWED |
| `find . -exec git commit -m x \;` | ALLOWED | ALLOWED |
| `make commit` | ALLOWED | ALLOWED |
| `npm run release` | ALLOWED | ALLOWED |

Two of thirteen.
The guard recognises the command only when it is spelled out literally, and the
operator's own everyday commit function is among the eleven it cannot see.

## What the misses cost, measured

Every refusal in the local transcript archive was paired with the command that
triggered it, and with what the session did next.

| | |
| --- | ---: |
| refusals | 247 |
| sessions affected | 91 |
| the blocked command was a real commit | 125 |
| the blocked command was not a commit at all | 118 |
| the next tool call also ran git | 200 |

Across all eight guards in the plugin, this one's parse refusal is the most
frequent event by a wide margin: 241 refusals over 11 days, against 36 occasions
in 6 days where a credential was actually found. Roughly seven refusals per
catch, and rising — the last five days averaged 38 a day.

The script's own header states the standard it is failing:

> High-confidence patterns only: a guard that cries wolf gets switched off.

## The part that turns cost into risk

Reading what sessions did after a refusal, the two recoveries are: rewrite the
command with literal paths, or move the work into a script file and run that.
The second is measured above as a bypass. So the false positives push agents
into precisely the shape the guard cannot inspect, and the more it refuses, the
more often that happens.

That is the argument against tuning further. A guard that trains its callers to
route around it does not get safer by refusing more accurately.

## Tried, and what each attempt cost

All within PR #9, whose 14 commits are the detail.

- **Refuse anything unparsable.** The original design. Produced the 118
  non-commit refusals.
- **Defer the verdict until the subcommand is known.** Fixed the read-only
  refusals; opened a bypass for every later token spelled `commit`.
- **Judge a `-c` value by its config key.** Refused `alias.*`; missed
  `include.path`, then `includeIf`.
- **Treat any command-scoped config as alias-capable.** Correct, and kept.
- **Judge splitting by whether the token was quoted.** Missed `"$base"$d`.
- **Judge splitting by an unquoted expansion.** Correct for scalars, missed
  `"$@"` and `"${arr[@]}"`, which are quoted and still multiword.
- **Match the array form.** Three spellings of the same pattern, each wrong in a
  different direction, before a regex stated the rule.
- **Treat shell keywords as introducing a command.** Closed a real leak found in
  a repository-cleanup loop; a brace in the same list then refused mere function
  definitions, so the brace came back out.

Six of the findings closed holes that exist on `main` today. Three were
regressions introduced by the fixes themselves. The pattern across all of them
is one thing: deciding what an unexpanded shell string will execute is not
decidable, and each fix narrows one spelling.

## Not tried

- **Scanning the index before parsing.** If nothing sensitive is staged the
  answer is "allow" whatever the command says, so the parse is only needed in the
  rare dirty case. Costs about 12 ms per call against the current 10.
- **A `PostToolUse` net.** Sees what actually happened, so no parsing; acts after
  the commit object exists, and needs state recorded before the call to know
  whether HEAD moved.
- **Moving enforcement into git itself**, where every shape above converges. A
  git `pre-commit` hook sees the commit no matter which of the thirteen spellings
  produced it, because they all end in the same place. This is the direction the
  evidence points; a survey of the existing tools is pending.
- **Routing commits through a single command** the harness can recognise, instead
  of recognising arbitrary shell. Narrower and enforceable, at the cost of
  forbidding direct `git` use.

## Recommendation

Merge PR #9: it halves the refusals, removes 492 distinct false positives, and
closes six real holes, so it is strictly better than what is installed.

Do not tune the parser further. Record the two-of-thirteen result as the
approach's ceiling and pick a different mechanism for the next version.
