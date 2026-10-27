# Changelog

All notable, user-facing changes to this kit are recorded here.
Entries are grouped by release; the topmost section collects work that has not yet been tagged.

## [Unreleased]

## [0.8.3] — 2026-10-25

`repo-gate`'s `setup-trunk` records how a first run in a brand-new repository behaves and what a generated `.shellcheckrc` should become (#82, #83, #84), `ci-babysit` and `fix-osv-vulnerabilities` record two lessons from a Dependabot sweep (#81), and `context-handoff`'s `handoff` and `log-it` name the source of each external status (#79).
`repo-gate` moves from 0.2.6 to 0.2.9 and `context-handoff` from 0.2.2 to 0.2.3; `guard-hooks` (0.5.1), `context-meter` (0.1.0) and `quick-look` (0.1.0) are unchanged.

### Changed

- `context-handoff` 0.2.3 `handoff` asks for the source of each external status (a URL, an ID, or a path) in CURRENT STATE, and its fixed closing line tells the receiving session to re-read status from that named source and to treat a status with no named source as unverified (#79).
  `log-it`'s thin handoff asks for the same source and closes with the same instruction, because a receiver without the earlier conversation cannot re-read a status it cannot locate.
- `repo-gate` 0.2.7 `ci-babysit` says that a `skipping` bucket ends the watch without proving anything about the change, and asks for each skipped job and its condition before a PR is reported green: a bot-actor `if:` makes every Dependabot PR look green (#81).
- `repo-gate` 0.2.7 `fix-osv-vulnerabilities` explains that a yarn berry resolution key must name the exact descriptor a parent requested, so an exact pin needs an exact key, and that such a key stops working when the parent moves its pin (#81).
- `repo-gate` 0.2.8 `setup-trunk` covers a first run in a brand-new repository: `trunk init` exits 1 until one commit exists, `trunk init -n` leaves an empty gate that still reports success, and `trunk actions enable` installs no git hooks until `trunk git-hooks sync` runs (#82, #83).
  It asks for the hook to be proved with a real commit rather than by running the hook script, and for a checkout's own custom actions to be read and approved before its hooks are installed, because a definition can bind arbitrary shell to `pre-commit`.
- `repo-gate` 0.2.8 `setup-trunk` replaces the generated `.shellcheckrc`'s `enable=all` with `severity=info` and warns against a repository-wide `disable=SC1087`, because that check is an error that reports a real array-expansion defect (#82, #83).
  It also notes that `trunk fmt` clears `markdownlint/MD060` table findings and that neither shellcheck nor shfmt parses zsh.
- `repo-gate` 0.2.9 `setup-trunk` no longer points at a configuration file on one author's machine or at a repository readers cannot reach, and states its `shellcheck` measurement by tool version and date instead (#84).
  The `SC1087` guidance and the measured counts are unchanged.

## [0.8.2] — 2026-10-18

`context-handoff`'s `log-it` and `handoff` skills catch up with the copies maintained outside the plugin, and drop text that only fit one author's setup (#77).
`context-handoff` moves from 0.2.1 to 0.2.2; `guard-hooks` (0.5.1), `repo-gate` (0.2.6), `context-meter` (0.1.0) and `quick-look` (0.1.0) are unchanged.

### Changed

- `context-handoff` 0.2.2 `log-it` adds an extend, retire, then create step before a new memory is written, applies a shared store's schema, index and check steps only when the store defines them, and no longer names one author's wiki, journal job or rule files.
  Its thin handoff states that it follows its own rules rather than `handoff`'s, tells the user how to deliver it, and ends with a line telling the receiving session to re-read stated status.
- `context-handoff` 0.2.2 `handoff` names when File Mode applies (a context-threshold nudge or an explicit request), says how to deliver the file without a pickup hook, and never commits a handoff file.
  Every handoff carries a fixed line telling the receiving session to re-read tracker, review, store or inbox status before acting on it, because the receiver reads the handoff and never the skill.
  Archiving stays with the pickup hook that surfaces a file, and the skill no longer names a PreCompact hook that this plugin does not ship.

## [0.8.1] — 2026-10-14

`guard-hooks`' `staged-secret-guard` no longer spends about 8 s, close to its 10 s fail-open timeout, on a long word made of `$NAME` references repeated; it reads such a run in one step.
`guard-hooks` moves from 0.5.0 to 0.5.1; `repo-gate` (0.2.6), `context-handoff` (0.2.1), `context-meter` (0.1.0) and `quick-look` (0.1.0) are unchanged.

### Fixed

- `guard-hooks` 0.5.1 `staged-secret-guard` reads a run of simple references such as `$a$b$c` in one step, so a 64 KB word made of one reference repeated takes well under a second instead of about 8 s, close to the hook's 10 s timeout past which the commit runs unscanned (#72).

## [0.8.0] — 2026-10-14

`guard-hooks` closes a set of ways a `git commit` could run past `staged-secret-guard` unscanned (`env -S` strings and their nested or glued `-S` layers, runner options, function-call words, variables the same command assigns) and a recursive search that `secrets-path-guard` let print dotenv contents; both hooks refuse more commands than before, and README §Known limits lists the over-refusals.
`guard-hooks` moves from 0.4.0 to 0.5.0; `repo-gate` (0.2.6), `context-handoff` (0.2.1), `context-meter` (0.1.0) and `quick-look` (0.1.0) are unchanged.

### Fixed

- `guard-hooks` 0.5.0 `secrets-path-guard` blocks a recursive search that can print dotenv contents without naming a `.env` file (#44).
  A recursive `grep`, `egrep` or `fgrep` (`-r`, `-R`, `--recursive`, `-d recurse`, bundled forms included) passes only when `--exclude='.env*'` or `*.<ext>` includes for extensions off a fixed list of dotenv suffixes keep dotenv files out under grep's last-match-wins order, and an `rg` that can read a hidden dotenv file (`--hidden`, `-.` or `-uu` with no later `--no-hidden`, a positive glob such as `-g '*'`, or a selected type such as `-t sh`; a `--type-add` alone selects nothing) passes only with `-g '!.env*'` and no later glob that re-includes them; plain `rg` skips hidden files and still passes.
  An unambiguous prefix of a grep long option counts as that option (`--recurs`, `--dir=recurse`, `--incl='*'`), as getopt_long reads it.
  Every grep long option that GNU grep 3.11 or macOS grep 2.6.0 gives a required value (`--group-separator`, `--label`, `--max-count`, `--exclude-dir`, `--include-dir` and the rest), and every prefix either grep resolves to one (`--g`, `--la`, `--exclude-`), takes the next word as its value, so an exclusion written there does not count; `--context` takes no separate word, because macOS grep reads its value only when attached with `=`, and `--binary` is an option of its own.
  Every `rg` option that ripgrep 15.2.0 gives a value, now including `--hostname-bin`, `--hyperlink-format`, `--dfa-size-limit`, `--regex-size-limit` and `--generate`, takes the next word as its value, so a `-g '!.env*'` written there does not count as the exclusion.
  An `rg` that names `--ignore-file` passes only with `-g '!.env*'` as its last glob, because the hook cannot see whether the file whitelists `!.env`; ignore files in the repository are not read (README §Known limits).
  The whole-command `.env` token check now runs first, so a dotenv read refused in 0.4.0 is refused however long the recursive-search check would take; a tokenizer that stops at a limit or times out costs only the recursive-search check.
  That first stage reads the command in small windows, so a command of up to 64 KiB with thousands of template names or exclusions no longer takes seconds to check.
  The `.env*` value of a grep exclusion is no longer refused as a dotenv path in any command of up to 64 KiB (over that it still is, as in 0.4.0) when it is attached and its `*` is quoted: `--exclude='.env*'`, `--exclude=".env*"`, `--exclude=.env'*'`, `--exclude=.env"*"` or `--exclude=.env\*`.
  The quoted two-word `--exclude '.env*'` and `--exclude ".env*"` are accepted only in a `grep`, `egrep` or `fgrep` command of up to 4 KiB read from the start of the command, with no `--` before the value, because `eval`, `sh -c` or unquoted `$(…)` output strips the quotes and expands `.env*` into dotenv files; elsewhere they are refused with a pointer to the attached form.
  An exclusion counts only when its `*` is shell-quoted, because the shell expands an unquoted one against the file names in the directory, and a planted file such as `--exclude=.envjunk` or `-g!.envjunk` then replaces the exclusion (#56): the unquoted `--exclude .env*` and `--exclude=.env*` are refused with a message naming the quoted forms, an unquoted rg `-g!.env*`, `-g !.env*`, `--glob=!.env*` or `--iglob=!.env*` counts as no exclusion, also for the `--ignore-file` last-glob rule; every other dotenv token still is refused.
  A program or prefix name that bash looks up on `PATH` matches in any case, because the default case-insensitive APFS volume runs `GREP`, `/usr/bin/GREP`, `Rg`, `SUDO` or `TIMEOUT` as the lower-case tool; `exec`, `builtin` and the shell keywords, which bash matches only in lower case, and every option letter keep their case (#59).
  For the same reason a `sh`, `bash`, `zsh`, `dash`, `ksh` or `ssh` word in any case, such as `BASH <<'EOF'`, makes the hook read a quoted-delimiter heredoc body on that line as commands.
  The program is found behind every bash assignment form, `NAME=value`, `NAME+=value`, `NAME[subscript]=value` and `NAME[subscript]+=value` (#58), and behind `command`, `builtin`, `env`, `exec`, `nohup`, `time`, `xargs`, `sudo`, `nice` and `timeout` (the external ones also by path and as Homebrew's g-prefixed GNU tools) with every option that the macOS or GNU version, bash's `exec` or sudo 1.9 gives a value, such as `exec -a name`, `env -P`, `sudo -U`, `xargs -J`, `time -o`, as the next word, attached in a short-option cluster (`sudo -nu root`) or under a long-option prefix (`sudo --us root`); GNU xargs `--max-lines`, `--replace` and `--eof` read only an attached value, and `env -S` (`--split-string`) with a `grep` or `rg` word in its string or after it is refused, since the hook cannot replay how env splits that string.
  The check reads `Bash` commands segment by segment, finds the program past a leading redirection such as `2>/dev/null` and before one attached to it (`grep</dev/null`, `grep&>out`), drops a redirection and its target from the options it reads wherever they stand, reads an unquoted `$(…)` or backtick substitution as its own segments while the options around it still count for the enclosing command, does not treat a quoted string, a comment or a quoted-delimiter heredoc body as a command, decodes `$'…'` ANSI-C quoting and `$"…"` as the shell does, reads a backslash in an `rg` glob as an escape, stops at 64 KiB, 4,000 tokenizer passes, 16 nested or 256 substitutions so the hook stays inside its timeout, and leaves the development-path abstention unchanged; README §Known limits lists what it does not recognise.
- `guard-hooks` 0.5.0 `staged-secret-guard` refuses `xargs --max-lines git commit` like every other xargs commit, instead of letting it pass unscanned (#57).
  A bare GNU xargs `--max-lines`, `--eof` or `--replace` takes no value, because GNU xargs reads their optional value only when attached (`--max-lines=2`); macOS xargs `-J`, `-R`, `-S` and sudo `-a`, `-c`, `-U` (`--auth-type`, `--login-class`, `--other-user`) take the next word as their value.
  `env -C` (`--chdir`) and `env -P` take their value, so the word after it is the program: a visible commit after `env -C` with a value that is not a command substitution is refused like one through `sudo`, since it commits in another directory's index, and one after `env -P` is scanned.
- `guard-hooks` 0.5.0 `staged-secret-guard` reads the rest of `env`'s options before `git commit` (#61): `-v`, a bare `-` and short clusters (`-iu NAME`, `-uNAME`) are walked so the git after them is scanned, `-0` (`--null`), `--help`, `--version` and an `=value` on a long option that takes none (`--debug=x`) end the command because `env` runs nothing given with them, `-S` (`--split-string`) is refused when a word of its string is `git` or ends in `/git` (`legit.py` still passes, and so does a git in a comment that starts with an unquoted `#` word), and a string whose program the hook cannot read refuses a git after it or a `commit` in or after it, a git after `-a` (`--argv0`) with a `git-` name is refused, a visible commit after `--env0-from` or after a `-C` value that is a command substitution is refused, and an `env` option the hook does not know, or a long-option prefix GNU `env` finds ambiguous, refuses a git after it, while a unique prefix (`--deb`, `--un=NAME`) is read as its option.
- `guard-hooks` 0.5.0 `staged-secret-guard` refuses a git after a redirection where a `nice`, `timeout`, `sudo` or `xargs` option's value should be (`nice -n >/tmp/out 5 git commit`), or where `timeout`'s duration should be after `--`, instead of letting the commit pass unscanned (#64).
  The shell removes the redirection, so the runner takes the next word as its value, while the hook took the real value as the program; which word the runner takes is not followed, so a read-only git later in the same command is refused too.
  A value glued before a redirection (`timeout -s KILL>/dev/null 5 git log`) stays the value, as it does in the shell, and is read as before; a file descriptor number or a `{name}` there (`nice -n 5>/dev/null`) is part of the redirection, and is refused.
- `guard-hooks` 0.5.0 `staged-secret-guard` refuses `env -S '-S' 'git commit -m x'` instead of letting it pass unscanned (#66).
  GNU `env` re-parses the options an `-S` string supplies, so a string that starts with an option can supply another `-S` that splits a later word.
  After such a string every later word of the command is read as an `-S` string, and a `git` or `/git` word in one is refused, as after a redirection in the `-S` value slot.
  The option-leading string itself is read the same way, and so are glued `-S` layers: where any word of a string starts with `-`, a word is also read as starting after every `=` and every `S` in it, so `env -S '-i -Sgit commit'`, `env -S '-i' '-S-Sgit commit'` and `env -S '-i' '--split-string=-Sgit commit'` are refused.
  That can only refuse more, and it refuses `env -S '-i' 'x -Sgit'`, where `env` looks for a program named `x -Sgit` and runs no git.
- `guard-hooks` 0.5.0 `staged-secret-guard` scans `f() { git "$2" -m x; }; f '5'>/dev/null commit` instead of letting it pass unscanned (#68).
  When the hook collects a shell function call's words, a word whose part before its first unquoted `<` or `>` was quoted or escaped (`'5'>out`, `"5">out`, `\5>out`, `''>out`) keeps that part as a word, as bash passes it, and only the redirection is removed; an unquoted `5>out` or `{fd}>out` still names a file descriptor and is removed whole.
- `guard-hooks` 0.5.0 `staged-secret-guard` refuses `X=-S env -S '${X}' 'git commit -m x'`, `env -S '-S' '${G} commit -m x'` and `env -S >/tmp/out '${G} commit -m x'` instead of letting them pass unscanned (#69).
  GNU `env -S` expands its own `${NAME}` references, so an `-S` string whose first word holds an expansion can supply another `-S`: that string and every later word of the command are now read as `-S` strings, as after an option-leading string.
  In the words read that way, a word that holds a `$` names a program the hook cannot read, so a `commit` word after it in the same word, or a later word that is `commit` (`env -S >/tmp/out '${G}' commit`, also `commit>/dev/null`), is refused; `env -S '${PY:-python3}' script.py` still passes.
  That can only refuse more, and it refuses a later word that `env` takes as the program's name without expanding it, as in `env -S '-i' '${G} commit -m x'`, `env -S '-S' '-i' '${G} commit -m x'` and `env -S '-i' '${G}' commit>/dev/null -m x`, where `env` looks for a program named `${G} commit -m x` or `${G}` and runs no git.
- `guard-hooks` 0.5.0 `staged-secret-guard` refuses `C='git commit'; $C -m x`, `G=git; "$G" -c alias.ci=commit ci` and `X='-Sgit commit' env -S '${X} -m x'` instead of letting them pass unscanned (#71).
  A variable that the same command visibly assigns a value holding a `git`, `/git` or `commit` word, read as an `env -S` string word is read (quotes dropped, and a word also starting after every `=`, `S`, `\` and `_`, so glued `-S` layers count), is refused as a program this hook cannot read, with a message of its own that names no `commit`, where it is expanded as the program word (`$C`, `${C}`, also behind `env`, `command` or `exec`) or in an `env -S` string that starts with an option, an assignment or an expansion; in a later word such a string lets `env` split, only a `git` or `/git` word counts.
  A program word whose expansions are all double-quoted stays one word, so it is refused only for a `git` or `/git` value, and only when the text after its last expansion could still end it in `git` or `/git`: `"$G"` and `"/usr/bin/$G"` are refused, `"$G/bin/tool"`, `"./scripts/$KIND.sh"` and `step=commit; "$SCRIPTS/$step"` pass.
  Every word shaped `NAME=`, `NAME+=`, `NAME[...]=` or `NAME[...]+=` counts, wherever it stands: a prefix or plain assignment, `export`, `declare`, `typeset`, `local` and `readonly`, an array's words (`C=(git log)`), and a value that expands a name an earlier word marked (`G='git commit'; C=$G`).
  Values are not evaluated, and where an assignment stands relative to the word that expands it is not followed, so a name assigned in a later command, a prefix assignment the shell does not keep, or a word that assigns nothing (`echo C=git; $C status`) can only refuse more.
  Refused on a clean index too: a read-only git through a marked name (`G=git; $G log`, `g=git; $g --git-dir .git log`), an unquoted path under a directory named `git` (`ROOT=~/src/git; $ROOT/configure`), a program that is not git whose value holds a `commit` word (`CZ='cz commit'; $CZ`), and `C=(git commit); ${C[@]} -m x`, where the array's words were scanned as a commit before.
  A name with no visible assignment keeps its verdict: `env -S '${PY:-python3}' script.py` and `"$CMD" -m x` still pass, and so do `PY=python3; $PY script.py`, `X=-i env -S '${X} python3 legit.py'` and `MSG='fix commit'; env -S '${PY:-python3}' script.py --msg "$MSG"`.

## [0.7.1] — 2026-10-12

`repo-gate`'s `semantic-commit` no longer stops on its own staged work as if another writer had made it, and it now says which parallel edits it cannot detect.
`repo-gate` moves from 0.2.5 to 0.2.6; `guard-hooks` (0.4.0), `context-handoff` (0.2.1), `context-meter` (0.1.0) and `quick-look` (0.1.0) are unchanged.

### Fixed

- `repo-gate` 0.2.6 `semantic-commit` counts the index as found at Step 1 as planned work.
  `planned.patch` compares `HEAD` with the working tree, so a line that was staged and later changed back in the working tree was in the index but not in the patch, and Step 4.3 stopped on it, or on a later group's reversal of it, as a parallel edit; Step 1 now also saves `git diff --cached` as `staged.patch` and `git diff` as `unstaged.patch`, the two steps from `HEAD` through the index to the working tree, and content from any of the three patches passes (#48).
  The parallel-edit detection is now stated as best-effort: it covers what reaches the index, and a formatter, a self-staging script, or a new non-ignored file in the candidate, but not a pre-commit hook that rewrites files without staging them, which can change withheld hunks and later-group files in the main checkout while every check passes (#50).

## [0.7.0] — 2026-10-12

Two function-hook mods join the marketplace: `context-meter` shows the real context fill and skips an automatic compaction that only an advisor request's summed usage asked for, and `quick-look` opens the files the agent touched in macOS Quick Look.
`guard-hooks` lets the operator designate development dotenv paths that auto mode may read, and `staged-secret-guard` follows runner commands and quoted substitutions and stays inside its timeout on large inputs.
`repo-gate`'s `semantic-commit` verifies a partially staged commit in a detached worktree instead of stashing the shared tree.
`guard-hooks` moves from 0.3.4 to 0.4.0 and `repo-gate` from 0.2.4 to 0.2.5; `context-meter` 0.1.0 and `quick-look` 0.1.0 are new, and `context-handoff` (0.2.1) is unchanged.

### Added

- `context-meter` 0.1.0, a function-hook mod, reads each model request's own usage instead of the advisor request's sum over its message iterations, which made the harness read such a turn as about twice its real context fill and auto-compact a session that was only half full.
  It treats an advisor request as an upper-bound estimate, skips an automatic compaction only when the harness reads at least 20 points higher and the estimate plus what arrived after the request stays below 70%, and lets one reading back one veto at most, so a wrong estimate delays a needed compaction by one request and never more.
  It draws the reading above the prompt past 50% or a 20-point gap, sends one handoff nudge at 80% (through `context-handoff` when it is installed, otherwise as a request for a self-contained handoff file), and fails open: a compaction it cannot judge goes ahead.
- `quick-look` 0.1.0, a function-hook mod for macOS, keeps the nine files the main agent most recently read, wrote or edited, plus existing files named in backticks in its answers, and previews them with `/usr/bin/qlmanage -p` from `/ql`, `/ql <n>`, or `/ql <path>`.
  It works in a terminal that draws no inline images, Warp included, and reports a preview that could not start or exited with an error.
  CI checks only that each mod's wired module exists; `claude plugin validate` and `claude plugin test` check their behaviour and run locally.
- `guard-hooks` 0.4.0 `secrets-path-guard` reads a default-off `CC_GUARD_DEV_ENV_PATHS` JSON array of exact development dotenv paths that the operator designates.
  Only in auto mode, a recognized reference to one of those paths is left to the normal permissions and auto-mode evaluation instead of being denied, including an absolute-path `source`; the hook never emits `allow` or `ask`.
  Unregistered or mixed dotenv references stay denied, path validation rejects symlinks, traversal, and shell or glob syntax, and Keychain protection and the other deny rules are unchanged.
  The agent can read and use the values in a designated file; `docs/environment-access.md` states that tradeoff and that the guard covers literal-path access only, not indirect access, which still depends on host permissions and the sandbox.

### Fixed

- `repo-gate` 0.2.5 `semantic-commit` isolates a partially staged commit candidate in a detached worktree built from `HEAD` plus the staged diff, instead of `git stash push --keep-index --include-untracked` on the shared tree.
  The stash reset files that the user was still editing: the next save landed on the reverted copy, `git stash apply` then refused to overwrite it, and the stash was dropped by another actor before it could be applied.
  A throwaway-repository probe confirms that the worktree receives only the staged hunks, staged new and binary files, and none of a later group's untracked files, while the original tree stays untouched.
  A stash kept as a last resort is identified by a unique message rather than by `stash@{0}`, which another session's stash can take over between the push and the lookup.
  Verification in the worktree must leave it unchanged (no unstaged diff, the same `write-tree` as the reviewed index, and no new non-ignored untracked file), so a formatter, a self-staging script, or a generator that wrote a non-ignored file into the candidate cannot pass while different content is committed; output under an ignored path is out of scope, since the candidate holds only `HEAD` plus the staged diff.
  A main index that no longer matches the reviewed tree after verification stops the run as a parallel edit instead of being read as a verifier rewrite.
  The worktree is removed with `--force` after every verification attempt, whether it passed or failed, because it always holds staged changes and `git worktree add` refuses a path that already exists.
  Parallel edits are now caught where they enter a commit, the index: Step 1 saves the planned change as one patch (including each untracked file through `git diff --no-index`), each group's `git diff --cached` must contain no content outside that patch (compared by content, since hunk shapes change as the run splits and commits), and after the commit the full `git diff "$reviewed" HEAD` must show at most a hook's formatting of the group's own files.
  Probes confirmed that this catches a rewritten or newly executable file inside a new directory, a parallel `git add -p` on an already modified path, and a pre-commit hook that re-stages another path, each of which a working-tree probe of status, content hash, or mode had missed.
- `guard-hooks` 0.3.8 `staged-secret-guard` follows `nohup`, `nice` and `timeout` to the git command they run and scans it, and refuses a visible commit through `sudo` or `xargs`, whose user, working directory, or appended input can change the candidate.
  Double-quoted `$(...)` and backticks are parsed in their own quote context, so a staged credential no longer passes through a quoted substitution, and a substitution that interrupts a function's arguments no longer drops trailing `-a` or pathspec arguments from the candidate.
  A final quoted heredoc that only feeds `git commit -m`, `echo`, or `gh ... --body` stays data; arbitrary evaluation and complex heredocs remain the known limits tracked in #24.
- `guard-hooks` 0.3.7 `staged-secret-guard` indexes shell function names, so a call no longer scans every unrelated definition; a workload of 500 definitions and 3,000 calls dropped from 10.90 s to 3.12 s on Linux.
  Arbitrarily large definition or token streams remain outside the timeout guarantee (#26).
- `guard-hooks` 0.3.6 `staged-secret-guard` reads its command through a small byte buffer and appends ordinary character runs together, keeping large executable heredocs and quoted words below the hook's 10 s timeout in the regression fixtures.
  Quotes, escapes, operators, expansions and heredoc safety decisions keep their existing parsing; buffer-edge and UTF-8 regressions verify that a real commit following large input still scans the staged credentials.
  This addresses the remaining tokenizer cost in #26; the function-name lookup follows in 0.3.7.
- `guard-hooks` 0.3.5 `staged-secret-guard` refuses an unresolved external-git or builtin-exec fallback after a shell function may have been unset and its arguments end at a substitution redirection.
  `git() { :; }; unset -f git; git > >(cat) commit -m x` and `exec() { :; }; unset -f exec; exec git > $(echo f) commit -m x` previously committed staged credentials without a scan.
  The fallback now reads the original call through the existing git/exec parser, which can refuse the unresolved redirection without losing the remaining arguments; certain no-op functions and already identified read-only commands such as `git log -1 > $(echo f)` retain their verdicts.
  Process and command substitution targets, nested targets, aliases, and exec option placements are covered by regressions.
  This addresses the fallback finding deferred from #34; the other known limits tracked in #24 remain open.

## [0.6.1] — 2026-10-03

`repo-gate`'s `cspell-triage` now warns that a cspell run in a linked git worktree inside another repository's working tree can check no files at all and still read as a pass, and says how to stop it with one config line.
`repo-gate` moves from 0.2.3 to 0.2.4; `guard-hooks` (0.3.4) and `context-handoff` (0.2.1) are unchanged.

### Fixed

- `repo-gate` 0.2.4 `cspell-triage` names the zero-file trap: with `useGitignore: true`, a linked worktree inside another repository's working tree can report `Files checked: 0, Issues found: 0`, which reads as a pass.
  A throwaway-repository probe with cspell 9 isolates the enclosing repository as the trigger, and the skill now says to pair `useGitignore: true` with `gitignoreRoot: "."` in the config, which stops the `.gitignore` lookup at the repository root without depending on the gate command forwarding a flag (`--gitignore-root .` for a one-off direct call), and to read the `Files checked` count before quoting a result.
  Its description also fires before a result from a git worktree, or one reporting no checked files, is trusted, since that run reports no unknown word to trigger the skill on its own.

## [0.6.0] — 2026-10-01

`staged-secret-guard` now reads a commit in many more shell shapes: through a shell function, inside a brace group, behind `exec`, after a redirection, and past a heredoc that nothing runs, and its tokenizer no longer slows down under a multibyte locale.
A new `guard-hooks` hook surfaces Claude Code's automatic security-review findings after a commit, `repo-gate`'s `fix-osv-vulnerabilities` covers Bundler, and `session-to-md` makes its turn index opt-in.
`guard-hooks` moves from 0.2.8 to 0.3.4, `repo-gate` from 0.2.0 to 0.2.3, and `context-handoff` from 0.2.0 to 0.2.1.

### Added

- `repo-gate` 0.2.2 `fix-osv-vulnerabilities` covers Bundler.
  Bundler has no overrides, so a gem moves only as far as every requirement on it allows: the skill lists the Gemfile's (or gemspec's) and each parent's requirement from `Gemfile.lock`, finds for each blocking parent the first release that admits the patch through the rubygems.org API, and updates the gem and every blocking parent in one `bundle lock --update <gem> <parents> --conservative`.
  It then says what to check: the versions the lockfile actually resolved (`--update` goes to the newest release the requirements admit, for every gem it names), one fix per lockfile, the other gems a parent moved, the Ruby floor, and which code paths only a real lane exercises.
  The workflow diagram routes Bundler direct and transitive dependencies to that section.
  It also says how to make a clean `trunk check` fail first: on the pre-fix tree trunk reports the vulnerability as an existing issue and exits 0, so pass `--show-existing` and read the output, and pin that tree by SHA rather than `HEAD`, which a parallel commit can move past the fix.
- `guard-hooks` 0.3.0 adds a ninth hook, `security-review-findings`, which surfaces Claude Code's automatic security-review findings after a `git commit`.
  Those reviews run in background sessions that commit and change nothing, so a finding they produced had no way to reach the session that made the edit; the hook reads the ones stored for this session's project in the last two days and adds them to the commit's result as a warning.
  It never blocks, fires only on a `git … commit` (read by position past git's global options, so `git log --grep commit` is not one), reports a given set of findings once per session, and caps the report at 200 lines.
  `security-review-findings.sh --print [--full] [cwd]` prints the same list as plain text for a pre-commit action outside Claude Code.
  The commit shapes it recognises are the ones Claude Code's own Bash calls produce; the README states that scope.

### Changed

- `context-handoff` 0.2.1 `session-to-md` leaves the turn index out of Markdown and HTML exports by default.
  Pass `--toc` to include it; transcript filtering and the tool and thinking controls are unchanged, and the `session-export` skill adds `--toc` only when navigation is asked for.
  The change shipped in #22 without a version bump, so installed copies kept 0.2.0 until this one.

### Fixed

- `guard-hooks` 0.3.4 `staged-secret-guard` recognises a commit behind `exec`, and one whose subcommand follows a redirection.
  `exec` is read past as `command` is, with any cluster of its `-c` and `-l` options and `-a NAME`, so `exec git commit -m x` and `exec -clc git commit -m x` are scanned, and so is `command exec` or `builtin exec` past a function named `exec`, or a plain `exec` past one that may have been unset.
  The name may be attached (`exec -afoo git commit`), and git run under a name starting `git-` takes the rest as its subcommand, so a git after `exec -a git-commit` is refused.
  A redirection before the program or between `git` and its subcommand is stepped over, target and all, as the shell removes it, so `>/dev/null git commit`, `exec 3>&1 git commit`, `git >/dev/null commit`, `git 2>&1 commit`, `git >| out.txt commit`, `git &>out.txt commit`, `git {fd}>out commit`, `git > out.txt commit`, `git <<- EOF commit` and `git -C . 2>/dev/null commit` are scanned; a word glued to a redirection stays a word, so `git>/dev/null commit` and `git commit>out.txt` are scanned too.
  Each of these ran `git commit` unscanned before, with a credential staged.
  Where a redirection cannot be followed, git is refused outright rather than guessed at, since its subcommand can be spelled many ways (`-c alias.ci=commit ci`): a process or command substitution target (`git > >(cat) log`, `> >(cat) git log`, `git > $(echo f) log`), one where `-C`'s path should be (`git -C >out . log`), one whose last operator may be quoted (`>"${sink}>"`), a `-C` value holding a quoted `>` (`-C"/a>b">/dev/null`), and a glued word whose target is the next word (`-C.> log`).
  A redirection with a quoted part is otherwise stepped over (`git >"/tmp/out" commit` is scanned).
  A shell function's arguments lose `&>`, `>|`, `{fd}>` and `2>&-` redirections as the shell removes them, so none of them narrows the scan to a path (`g() { git "$@"; }; g commit -m x &>/dev/null` scans the whole index), and a function call whose redirection target is a substitution leaves its arguments unresolved, so a git in the function that takes them is refused.
  `&>` and `&>>` are now read as redirections rather than a background `&`, so among commit's own arguments (`git commit -m x &>/dev/null`) they are refused as `>` already was, where before the commit was scanned.
  A command substitution inside double quotes (`out="$(git commit …)"`), runners such as `nohup`, `sudo` and `xargs`, and backticks remain unrecognised; #24 records why the double-quoted substitution is not a small change after the heredoc skip.
  Tracked as #24.
- `guard-hooks` 0.3.3 `staged-secret-guard` tokenizes a command in bytes whatever the caller's locale.
  Its tokenizer reads one character at a time, and under a multibyte locale, the macOS default, each read walked the command from its start, so a large command ran past the hook's 10 s timeout, where it fails open: a 59 KB command took 45 s under `en_US.UTF-8` against 10 s under `C`, and a 22 KB one took 6 s against 1 s.
  Every delimiter it looks for is ASCII and no byte of a multibyte UTF-8 character equals one, so bytes give the same tokens: replayed under `en_US.UTF-8` against the previous version, 1,216 distinct transcript commands that open a heredoc and mention `commit` got the same verdict in a clean repository and with a credential staged.
  The locale is set to `C` for the tokenizing loop only and restored after it.
  The 59 KB command still takes about 10 s, now in the per-character loop itself; that remainder stays open in #26.
- `guard-hooks` 0.3.2 `staged-secret-guard` no longer reads a heredoc body as commands where nothing can run it.
  Writing a script or a Makefile through a heredoc (`cat > r.sh <<'X'` with `$GIT commit` inside) was refused although the file is only being written, even with a clean index.
  A body is now skipped as data only when it is fed to a literal `cat` or `tee` with a quoted delimiter, after nothing but a short allowlist of programs that cannot change how the shell finds `cat`; the full set of conditions is under Known limits in the README.
  Every other body is still read as commands, because reading it is what catches a commit in `bash <<X`, `cat <<X | sh`, `cat <<X > >(sh)`, `{ cat <<'X' … } | bash`, `` eval ` `` or `eval $(` around a `cat <<'X'`, a `$(…)` inside an unquoted `cat <<X` body, a `cat <<'Y'` nested in a body that is itself run, and a `cat` repointed by `hash -p`, however `hash` is spelled.
  The quote-state conditions exist because the tokenizer can disagree with the shell: in `eval "$( # "` the `"` sits in a comment for zsh and bash 5, which run the following `cat <<'Y'` body, while the tokenizer took it as the closing quote.
  The two costs are listed under Known limits: a script written through `cat` is no longer scanned when it later runs, and a heredoc inside a double-quoted substitution is still read as commands.
  Skipping a body also stops an apostrophe in its prose from flipping the tokenizer's quoting and swallowing the commands after the terminator, so a commit that follows a message written through `cat` is now seen.
  Replayed against 1,297 distinct transcript commands that open a heredoc and mention `commit`, 51 commands whose commit the previous version never read are now scanned, and 2 commands that only wrote files are no longer refused; no command that runs a commit stopped being scanned.
  One visible consequence: 13 of those 51 are now refused even with a clean index, because the commit the hook finally reads has a shape it already refuses to parse (a pipe or redirection on the commit, an unquoted `-F $S/msg.txt`, a `-C "$WT"`).
  Run the commit on its own with literal paths, as the refusal says.
  Tracked as #25.
- `shellcheck-on-edit.test.py` passes without `shellcheck`, as `CLAUDE.md` says it does.
  Its opt-out case expected a warning that only `shellcheck` can produce; with no binary reachable it now asserts the silent no-op instead.
  The suite also stopped counting `~/.claude/.trunk/tools/shellcheck` as available, because the hook never looks there, so a machine with only that copy failed the findings cases too.
  Tracked as #27.
- `repo-gate` 0.2.3 `fix-osv-vulnerabilities` counts a parent release that no longer depends on the vulnerable gem as a fix.
  The rubygems.org lookup prints only the release's `ruby_version` for such a release, and the Bundler section used to read that as "no release admits the patch", which routed a reachable fix to suppression.
  Step 2b now applies only when a blocking parent has no release that admits the patch or drops the gem, and verification checks that a dropped gem is gone from every `Gemfile.lock` and that no code still requires it.
  Raised by Codex on #28 and tracked as #29.
- `repo-gate` 0.2.1 `ci-babysit` no longer reads an empty `steps` array as a billing or runner block on its own.
  This supersedes the 0.3.9 wording, "a billing or runner block upstream of the workflow, read from the run's annotation, not from a diff": the guidance now requires the annotation on `gh run view <id>` to name the upstream cause — billing, a spending limit, or the runner — before the failure is classified Environmental.
  An annotation that names an ordinary cause is the diagnosis instead, and only when the annotation is absent or inconclusive does the reader move on to the run's other jobs and the normal failure diagnosis: a reusable-workflow caller fails with the same `steps: []` for an ordinary reason.
  Raised by CodeRabbit on #9 and left out of that pull request; tracked as #10.
- `guard-hooks` 0.3.1 `staged-secret-guard` follows a shell function defined in the same command.
  A call is read as the function's body with the call's words in place of `"$@"` and `$1`–`$9`, so `g() { git "$@"; }; g commit -m x` is scanned, `g status` is left alone, and a wrapper that adds `-c` is refused exactly as the same command written inline would be.
  A redirection among the call's words is removed before they become its parameters, as bash removes it, so `g >/dev/null commit -m x` and `g 2>&1 commit -m x` are scanned.
  An unquoted `$1`, `$@` or `$*` splits each word as bash's default `IFS` does, so `run() { echo "+ $*"; $*; }; run git commit -m x` and `run "git commit -m x"` through `$@` are scanned too; in a command that names `IFS`, however quoted or escaped (`I\F\S`), the split is unknown, so the parameter is left unresolved and a literal word holding `commit` is refused (`f() { IFS=:; git $1; }; f commit:-m:x`).
  A definition that may not have taken effect (inside a subshell, a brace group, a branch or a loop; joined by `&&`, `||`, `|` or `&`, even across a newline; after a heredoc has opened; or since removed by `unset`, where an expanded name may be any function's) does not hide the one before it, so `f() { git commit -m x; }; ( f() { :; } ); f` is scanned; the call is read as every definition back to the latest one certain to have run.
  Where the words cannot be placed (`shift`, `set`, a function defined inside the body, a word before them that can split) they are left unresolved, and the parse refuses what it then cannot identify; a recursion stops being read 8 deep, where every level above has been, and past 4096 added tokens a call is no longer read either; either way it is refused if its words say `commit`, and past the token budget also if anything it can reach, function by function, names `git` or `commit`.
  A definition whose body is a brace group is no longer read at all: the parser used to skip only the first command of a body, so `f() { echo; git commit -m x; }` was scanned although nothing ran.
  Where the body's end is in doubt the rest is read as though it ran, never skipped: every unquoted `}` ends a body, even one that is only an argument, and a body that holds a heredoc is read whole, because the heredoc's prose is parsed as commands and its braces cannot be trusted.
- `staged-secret-guard` scans a commit inside a brace group.
  `{ git commit -m x; }` went unscanned because `{` could not be told apart from a function body; with definitions recognised by their name, it can.
  Words after a command substitution among a command's arguments are no longer read as a new command, so `echo $(date) git commit` is not treated as a commit, and a substitution glued to more of an assignment no longer hides the command after it: `out=$(date)x git commit` was unscanned before this release.
- `staged-secret-guard` refuses `commit` behind a program name it cannot read.
  `g=git; $g commit`, `"${GIT:-git}" commit` and `$(command -v git) commit` ran a commit with only the word `commit` visible, and a name that expands to git can carry its own `-C` or `-c`, so there is no candidate to scan.
  The refusal fires only where git would read its subcommand, so `$PYTHON -c …` and `"$EDITOR" "$f"` pass as before; the word after one of git's own options that take a separate value (`--git-dir`, `--work-tree`, `--namespace`, `--attr-source`, `--config-env`) counts as that value, so `$g --git-dir .git commit` is refused as well.
  Tracked as #12.
- `staged-secret-guard` reads an unquoted `#` at the start of a word as a comment.
  `git commit -m x # note` passed `#` and `note` as pathspecs, scanned a candidate git never commits, and let a staged credential through; this was true before this release.
- `guard-hooks` 0.2.9 `staged-secret-guard` names an unquoted expansion as the reason it refuses a git command whose subcommand it cannot identify.
  The refusal itself is unchanged, but it used to say `could not safely parse this git commit command`, although the command is usually not a commit (`V=/tmp; git -C $V log`, a `for` loop over an unquoted path); it now says the command may not be a commit and that quoting the expansion is the fix.
  A commit that was identified and then could not be scanned (`-F -`, an unresolvable `-F $VAR`, a pipe on the commit line) keeps the parse message.

## [0.5.0] — 2026-09-10

Session exports now support Markdown, standalone HTML, and structured JSON through the existing `session-to-md` command.
`context-handoff` moves to 0.2.0 for the new formats, report theme, and record preservation.
`guard-hooks` remains at 0.2.8, and `repo-gate` remains at 0.2.0.

### Added

- `context-handoff` 0.2.0 adds `session-to-md --format html` and `--format json` alongside the default Markdown export.
  HTML includes a light report theme, a turn index, export counts, and tool expansion controls without external resources.
  JSON uses a versioned, filtered record structure with export diagnostics.

### Changed

- `session-to-md` defaults to prose only.
  Use `--tools collapsed` or `--tools full` to include complete tool inputs and results.
  Folding no longer truncates content, and `--tool-limit` provides an explicit character limit.
  Default filenames use the session ID instead of prompt text, and `--list` prints metadata without prompt previews.
- `session-export` passes the current session ID through Claude's skill substitution instead of assuming the newest transcript is active.
  Direct CLI calls without an ID still select by modification time and report that choice.

### Fixed

- All export formats preserve user text recorded alongside tool results, pair each call with all recorded results, and distinguish empty results from missing results.
  Export notes report malformed lines, unsupported content, missing or ambiguous results, and explicit truncation.
- Quoted command tags preserve their surrounding prose, and nested or unclosed internal wrappers are removed.
- Exports use file mode `0600` and retain exclusive file creation.
  HTML escapes transcript markup and restricts resource loading with a content security policy.

## [0.4.0] — 2026-09-09

A sixth `repo-gate` skill, markdownlint triage, with a `bin/` helper hardened through six hosted review rounds, and one more home-directory `rm` shape refused by `guard-hooks`.
`repo-gate` moves to 0.2.0: a sixth skill and a second `bin/` tool.
`guard-hooks` moves to 0.2.8 for one more `rm` shape the home-directory guard now refuses.

### Added

- `repo-gate` `markdownlint-triage` turns a markdownlint log into a per-rule count, decides which content rules stay on, and fixes the remaining backlog one file per worker. Its helper `markdownlint-summary` is on PATH whenever the plugin is enabled; it runs `markdownlint` or `trunk`, never an auto-installed package, or summarizes an existing log, and its suite sits beside it in `bin/`. The skill also carries what the cleanup that produced it paid for twice: workers get a fence-language table up front, the whole gate reruns on changed files because a fence language wakes Prettier, and mirrored copies of a document go to one worker.

### Changed

- `repo-gate` `setup-trunk` seeds `.trunk/configs/.markdownlint.yaml` from the Prettier-compatible baseline gist instead of a remembered rule list, and routes an existing backlog to `markdownlint-triage`.
- `repo-gate` `fix-osv-vulnerabilities` names the 0.x boundary: below 1.0.0 a caret stops at the minor, so an advisory patched only at `0.5.0` is a boundary crossing, not a patch bump. It also says how to prove a forced version loads before shipping it: load it from the consumer's own resolution path, with `require` for CommonJS or `import()` for ESM, and call what the consumer calls.

### Fixed

- `guard-hooks` 0.2.8 `dangerous-command-guard` refuses `rm -rf "${HOME%/}"` and the other suffix-trimmed spellings of the home directory, which slipped past the braced-expansion pattern. A `${HOMEWORK}`-shaped variable still passes.

## [0.3.9] — 2026-09-03

The guard that scans a commit for credentials stops refusing read-only git commands, and closes six ways a real commit reached the scan unseen.
`repo-gate` moves to 0.1.6 so that its two skill changes below, first written on 1 September without a bump, reach an installed copy: the client caches a plugin under its version string, so a change that leaves the version alone never arrives.

### Fixed

- `guard-hooks` 0.2.7 stops `staged-secret-guard` from blocking read-only git commands. A global option the parser could not resolve — a shell variable in `-C`, a `--no-pager` — refused the command before the subcommand was known, so `for d in */; do git -C "$d" log; done` was rejected as an unparsable commit. The verdict now waits until the subcommand is identified and fires only on a real `git commit`.
- `staged-secret-guard` no longer assumes a git long option carries its value with `=`. git accepts the separate form, so `git --git-dir /repo/.git commit -m x` had its path read as the subcommand. The options recognised as taking no value are git's own list; anything else is refused rather than guessed at.
- `staged-secret-guard` treats `"$@"` and `"${name[@]}"` as multiword. Quoted, they still emit one word per element, so `git -C "${args[@]}" log` could carry a `commit` the hook never saw. `"$*"` and `"${name[*]}"` join to a single word and stay allowed, and the array form is matched as `${...[@]...}`, which covers the modified spellings such as `${args[@]:0}` while leaving a path that merely contains those characters alone.
- `staged-secret-guard` scans a commit behind the `time` reserved word, and refuses a commit option value that can expand to several words. `time git commit` went unscanned, and `git commit -m "${args[@]}"` could smuggle `-a`, which commits tracked files the index scan never sees. Both were true before this release.
- `staged-secret-guard` recognises a git command that follows a shell keyword. `if git commit ...`, and any invocation in the body of a `for`/`while` loop, were treated as though the keyword were the command and went unscanned. Present before this release; found by replaying every git command in a local transcript archive against both versions. A brace is not treated as such a keyword, so defining a function whose body contains a commit is not itself refused.
- `staged-secret-guard` now refuses a git subcommand that is itself a shell expansion. `git "$cmd" -m x` and `git "$(printf commit)" -m x` run a commit while the hook sees only the unexpanded word, so the staged diff went unscanned. This was true before this release as well, not a regression.
- `staged-secret-guard` still refuses `-c` and `--config-env` in front of a subcommand it cannot identify, and now says so in its own message rather than reporting an unparsable commit. Command-scoped config can rename `commit` through an alias, either directly or through an include, and no reading of the config key separates the safe case from the dangerous one. `git -c core.pager=cat log` is refused for that reason; the same command without `-c` is not.

### Changed

- `repo-gate` `ci-babysit` names the zero-steps failure shape: a run that fails in seconds with an empty `steps` array is a billing or runner block upstream of the workflow, read from the run's annotation, not from a diff.
- `repo-gate` `cspell-triage` warns that a local dictionary registered under a bundled dictionary's name silently masks the bundled one; check candidate names against `cspell dictionaries` before registering. The `cspell dictionaries` correction is #13, the first outside contribution.

## [0.3.8] — 2026-08-31

The output side of secret handling: the guards already refused to read or commit a credential; this release masks one that a command prints.

### Added

- `guard-hooks` 0.2.6 adds `output-secret-mask`, a `PostToolUse` hook on `Bash` that runs gitleaks over the command's stdout and stderr and rewrites every credential-shaped value to `[REDACTED]` before the model sees the result. No-op without `gitleaks`; about 30 ms per call with it.

### Fixed

- `wayfinder`'s ticket-list template no longer renders its placeholder as a link to a file that does not exist.

## [0.3.7] — 2026-08-28

A hardening release for marketplace installation, safety hooks, and repository workflow skills.

### Fixed

- `staged-secret-guard` now scans staged content after `command -p git commit` and `env -u NAME git commit`. Valid wrapper options can no longer bypass credential scanning.
- Guard hooks now recognize more shell, package-runner, and rewriter forms. Commands that target protected locations or invoke a rewriter without a path no longer bypass the relevant guard.
- `session-to-md` rejects malformed option values, accepts at most one session identifier, and refuses to overwrite an existing output file.
- `find-trunk-repos` treats only a repository-content 404 as absence. Other GitHub API failures now name the affected repository.

### Changed

- Marketplace CI now requires an in-repository `./` source, rejects traversal and external resolved paths, and validates each plugin manifest against its marketplace entry.
- `ci-babysit` keeps watch-only requests read-only. Reruns, repairs, commits, and pushes require explicit authority.
- `cspell-triage` requires a clean cspell baseline before its canary edit, then requires the failure output to name the inserted token.

### Added

- `THIRD_PARTY_NOTICES.md` now carries the full MIT notices for declared upstream redistributions.

## [0.3.6] — 2026-08-25

An over-engineering audit of the whole tree, and what it turned up. Nothing users invoke changes except one flag-parsing fix.

### Fixed

- `session-to-md` treated any argument it did not recognise as the session id, so `--tools none` typed as `--tool none` silently exported a different session instead of complaining. Its flags are parsed with `node:util`'s `parseArgs` now, which is strict; the error names the offending flag on one line rather than as a stack trace. Its usage line also still named `session-to-md.mjs`, the path the script had before 0.3.1 moved it into `bin/`.

### Changed

- The opt-out contract every guard-hooks suite runs — feeding the hook over a real pipe, checking a disabled hook still drains a 200KB payload — was byte-identical in all seven suites, and its three blocking cases were byte-identical in four of them. It now lives in `hooks/_optout.py`, beside the suites so their `Path(__file__).with_name()` hook lookup is unaffected, and named with a leading underscore so CI's `*.test.py` glob does not run it as a suite. 324 lines of copies became 29 lines of calls. `staged-secret-guard`'s opt-out cases gained the silence assertion the other four already had.
- `staged-secret-guard` spelled its `-C <path>` expansion out at twelve call sites and selected its diff through three branches by two sub-branches of one command. A `gitq()` wrapper and a pathspec array reduce that to one condition and one call. The `check-attr` call stays spelled out, because backgrounding a function makes `$!` the subshell's pid and the kill and wait around it would then never reach git — the suite caught exactly that.
- CI listed the shell scripts to check twice, in two byte-identical heredocs. One step writes the list now and asserts it is non-empty, because a discovery that matched nothing would leave both consumers passing on empty stdin.
- `marketplace.json` drops `version`. The schema does not require it, it never moved through five releases, and a reader would take `0.1.0` for the marketplace's version.

### Provenance

- CLAUDE.md said a component thin enough to be effectively vendored upstream code does not belong here, while `context-budget` ships at 87% verbatim with CREDITS.md saying so. The rule now matches the practice: mostly-upstream is allowed as a declared redistribution — measured overlap, copyright holder named, licence permitting it — and what is barred is upstream work presented as this repository's own.

## [0.3.5] — 2026-08-25

### Fixed

- **`staged-secret-guard` let a staged credential through under `git commit -u -m <msg>`.** Its `git commit` flag table put `-u` / `--untracked-files` among the options that take the _next_ token as their value, but git defines them as `-u[<mode>]` — the value is attached and optional, never a separate token. So the guard read `-m` as `-u`'s value and the message as a pathspec, built a commit candidate for a path that does not exist, scanned nothing, and exited 0 while git committed the staged content. `-S` / `--gpg-sign` carry the same optional-attached shape and are now handled with it. Both the separate-token forms and the attached forms (`-uall`, `-S<key-id>`) are covered by regression cases that exit 0 against the previous table. The defect entered in 0.3.2 and was present in 0.3.3 and 0.3.4; releases before that are unaffected.
- **`git commit -q` was blocked as unparseable.** `-q` / `--quiet` was absent from the no-value flag list, so it fell through to the catch-all that refuses an unrecognised flag — a benign, extremely common flag failing closed. Added along with the other no-value flags the table had omitted, each read off `git commit`'s own option list rather than recalled: `-z` / `--null`, `--verify`, `--no-signoff`, `--reset-author`, `--allow-empty`, `--allow-empty-message`, `--status` / `--no-status`, `--no-gpg-sign`.

`-e` / `--edit` is deliberately still refused: it opens `$EDITOR`, and the agent shell has no TTY, so admitting it would trade a millisecond refusal for a hung tool call. Bundled short flags (`-sq`) are refused as before — the table matches whole flags, which the README now states as a limit rather than implying the list is exhaustive.

Flags that change _which_ content is committed stay fail-closed, and a case now pins that: `-p`, `--interactive`, and any unrecognised flag are still refused rather than guessed at. The four mutations covering this change — restoring `-u` to the value-consuming list, dropping `-q`, dropping the attached-value arm, and widening the list far enough to admit `-p` — each fail a case.

## [0.3.4] — 2026-08-25

### Added

- `cspell-dict-report` gives `cspell-triage` a bulk form of its one-word `cspell trace` check. It reads a word list on stdin, traces every unique word in a single process, and separates what a dictionary knows as a misspelling, what an enabled dictionary already covers, which unenabled dictionaries are worth adding, and what nothing has. The candidate ranking is a greedy set cover rather than a per-dictionary count: each row is scored against the words the rows above it leave behind, so `NEW` is what enabling that dictionary actually buys. Overlap is the norm — a common word sits in twenty dictionaries — and a per-dictionary count credits the second one for words the first already took. Run backwards, `--exclude <name>` answers "if this dictionary did not exist, what would still be covered?" without editing the config, which is step 4's prune with no scratch copy. Three ways `cspell trace` output misleads a parser are handled: the name column truncates at 20 characters and marks the truncation with the same trailing asterisk that means "enabled", so the join runs on the on-disk location taken from `cspell dictionaries`, which prints both columns in full; a compound hit renders as `look•ahead` and clears the word only under `allowCompoundWords`, so counting it would overstate coverage; and a word carrying a separator is decomposed, each part traced under its own heading.

### Changed

- CI runs every `plugins/*/bin/*.test.py` instead of naming one suite, so a second `bin/` regression suite is covered on the day it lands, and pins `actions/checkout` at v7.

### Provenance

- CREDITS.md gains rows for `find-trunk-repos` and `cspell-dict-report`. `find-trunk-repos` shipped in 0.3.1 with no entry — the same omission 0.3.3 corrected for two hooks.

## [0.3.3] — 2026-08-25

### Added

- `semantic-commit` splits a file at hunk level when it genuinely spans two concerns, instead of assigning it wholesale to the dominant intent. It documents driving `git add -p` over a pipe — it reads answers from stdin, so no TTY is needed — with the `git diff --cached` confirmation made mandatory rather than optional, because on EOF `git add -p` quits and an answer-count mismatch under-stages silently. Also the patch-editing fallback for two concerns interleaved inside one hunk, where `s` splits on line counts and rarely lands on the concern boundary — applied with `--recount`, since deleting lines from inside a hunk leaves the `@@` counts stale and `git apply` then rejects the file outright — and `git stash push --keep-index --include-untracked` so verification runs against the commit candidate rather than a working tree that no longer matches it. Without `--include-untracked` a new file belonging to a later group stays in the tree and test discovery still finds it.

### Provenance

- CREDITS.md gains rows for `pathless-rewriter-guard.sh` and `staged-secret-guard.sh`. Both are original work, but the two hooks shipped in 0.2.0 without entries, so the file that claims to cover everything published did not.

## [0.3.2] — 2026-08-24

### Fixed

- `staged-secret-guard`'s two `sk-` key patterns had no left boundary, so a kebab-case word whose tail clears the 20-character floor — `live-task-status-transitioning` contains `sk-status-transitioning` — read as an OpenAI key and blocked a real commit. Both patterns now require a non-word character (or line start) before `sk-`, with regression tests for the slug and for a key at line start.
- Guard hooks now cover git global options and separated long-option globs, every dangerous command segment and absolute pipeline interpreters, multi-suffix and mixed live dotenv paths, effective `commit -a` and pathspec candidates, value-taking rewriter options, and large ShellCheck findings without advisory SIGPIPE failures.
- `find-trunk-repos` now propagates GitHub authentication and repository-list failures instead of reporting a false empty success.
- `config-gc` now derives one active root from `CLAUDE_CONFIG_DIR` or `~/.claude`, and `setup-trunk` selects linters from repository evidence before proposing scoped changes.

### Changed

- CI now lints and parses extensionless Bash plugin `bin/` entries as well as `*.sh`; the previous claim that every shipped shell artifact was covered was broader than the implemented gate.

## [0.3.1] — 2026-08-19

### Fixed

- `session-export` could not run as an installed plugin. Its skill told the agent to execute `~/.claude/skills/session-export/scripts/session-to-md.mjs`, a path that exists only where the skill was originally authored — never for anyone who installs the plugin. `CLAUDE_PLUGIN_ROOT` is substituted for hooks and is unset in the Bash tool, so the fix is the documented `bin/` mechanism: the script now ships as `context-handoff/bin/session-to-md`, on PATH whenever the plugin is enabled, and the skill calls it by bare name. Verified by resolving and running it through `--plugin-dir`.
- `setup-trunk` pointed at a `trunk-quality-gate` agent that is not part of this repository. The paragraph now states the scope boundary instead of naming something the reader does not have.
- `find-trunk-repos.sh` shipped inside `setup-trunk` with nothing referencing it. It now lives in `repo-gate/bin/find-trunk-repos` and the skill documents it for what it is good at: reading a trunk config you already wrote instead of inventing one.

### Changed

- CI lints and parses every `*.sh` script in the repository rather than only `plugins/*/hooks/*.sh`. Two scripts that ship to users, including one inside a skill, had been outside the gate; both were clean, but extensionless Bash `bin/` entries were not yet covered.
- The hook-wiring existence check no longer hardcodes `guard-hooks`, so a second plugin adding hooks is covered on the day it does.
- New check: every `plugins/*/bin/*` entry is executable and carries a shebang — on PATH and unrunnable is exactly the failure a skill calling it by bare name cannot see.
- New check: the demo recording is compared against what `zsh-quoting-guard` actually prints, by running it, rather than against its source. It caught a real mismatch on the first run — the recording had been shortening the message's final line — which is now corrected and the GIF regenerated.

## [0.3.0] — 2026-08-18

### Added

- `context-handoff` 0.1.0 — six skills for work that outlives one session: `handoff` (brief a successor, printed or as a file), `session-export` (transcript to readable markdown), `log-it` (route what a session learned to whoever must read it), `wayfinder` (chart an effort too big for one sitting as decision tickets), `context-budget` and `config-gc` (find and remove what is eating the context window).
- `repo-gate` 0.1.0 — five skills for the stretch between working code and a push: `semantic-commit`, `setup-trunk`, `ci-babysit`, `fix-osv-vulnerabilities`, `cspell-triage`.
- CI parses every skill's frontmatter and asserts its `name` matches its directory — a skill that fails either installs silently and never triggers — and rejects absolute home paths in published plugins, the class of leak the first plugin's path-shaped grep had missed.

### Provenance

Three skills carry MIT-licensed upstream work, with the overlap measured line-wise rather than described: `wayfinder` 14% verbatim from mattpocock/skills, `config-gc` 54% and `context-budget` 87% from affaan-m/ecc. Each names its source in `metadata.origin`, and CREDITS.md carries the command to re-derive the numbers.

## [0.2.1] — 2026-08-18

### Changed

- `zsh-quoting-guard.sh` describes the glob trap accurately. It said an unquoted glob "substitut[es] one arbitrary filename when something does" match, which holds only when exactly one file matches; several expand to a list the tool rejects outright. The message now names all three outcomes and which one is quiet. Behaviour is unchanged — only what it tells you.

## [0.2.0] — 2026-08-18

### Added

- `pathless-rewriter-guard.sh` — blocks a formatter or rewriter invoked with no path argument, where its no-path default is everything reachable (`jsonsort`, `trunk fmt`, `ruff format`, and write-mode `prettier` / `eslint` / `shfmt`). Package runners and absolute binary paths are seen through; tools that already error out without a path are not listed.
- `staged-secret-guard.sh` — scans the added lines of the staged diff for credential shapes before `git commit` runs, and blocks the commit. Removing a secret is never blocked, and `git -C <path>` is honoured.

### Fixed

- `staged-secret-guard.sh` never scanned anything under bash 3.2, the `/bin/bash` on a stock Mac: an empty array expansion aborts under `set -u`, and the adjacent `|| true` swallowed it, so the hook exited 0 having read no diff. The suites missed it by invoking `bash` from `PATH`; they now invoke `/bin/bash`, and CI runs on macOS alongside Linux.

## [0.1.0] — 2026-08-18

First distribution snapshot. Ships one plugin:

- `guard-hooks` — five defensive hooks. Three `PreToolUse` guards block a recursive `rm` aimed at the home directory or a filesystem root, download-and-execute pipelines, access to live secrets files, and the two zsh quoting mistakes that fail silently. Two `PostToolUse` hooks warn without blocking: a stale lockfile after a manifest edit, and `shellcheck` findings after a shell-script edit.

Each hook carries a regression suite beside it: 117 cases, 49 of which fail when the logic they cover is deleted.
Each hook can be disabled individually through its own `CC_GUARD_DISABLE_*` environment variable, checked after stdin is drained so a disabled hook cannot break a large `Write`.

Verified on macOS (`/bin/bash` 3.2) and on Linux through CI, and confirmed to load and fire as an installed plugin via `${CLAUDE_PLUGIN_ROOT}`.
