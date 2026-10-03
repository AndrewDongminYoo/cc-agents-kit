# Changelog

All notable, user-facing changes to this kit are recorded here.
Entries are grouped by release; the topmost section collects work that has not yet been tagged.

## [Unreleased]

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

- **`staged-secret-guard` let a staged credential through under `git commit -u -m <msg>`.** Its `git commit` flag table put `-u` / `--untracked-files` among the options that take the *next* token as their value, but git defines them as `-u[<mode>]` — the value is attached and optional, never a separate token. So the guard read `-m` as `-u`'s value and the message as a pathspec, built a commit candidate for a path that does not exist, scanned nothing, and exited 0 while git committed the staged content. `-S` / `--gpg-sign` carry the same optional-attached shape and are now handled with it. Both the separate-token forms and the attached forms (`-uall`, `-S<key-id>`) are covered by regression cases that exit 0 against the previous table. The defect entered in 0.3.2 and was present in 0.3.3 and 0.3.4; releases before that are unaffected.
- **`git commit -q` was blocked as unparseable.** `-q` / `--quiet` was absent from the no-value flag list, so it fell through to the catch-all that refuses an unrecognised flag — a benign, extremely common flag failing closed. Added along with the other no-value flags the table had omitted, each read off `git commit`'s own option list rather than recalled: `-z` / `--null`, `--verify`, `--no-signoff`, `--reset-author`, `--allow-empty`, `--allow-empty-message`, `--status` / `--no-status`, `--no-gpg-sign`.

`-e` / `--edit` is deliberately still refused: it opens `$EDITOR`, and the agent shell has no TTY, so admitting it would trade a millisecond refusal for a hung tool call. Bundled short flags (`-sq`) are refused as before — the table matches whole flags, which the README now states as a limit rather than implying the list is exhaustive.

Flags that change *which* content is committed stay fail-closed, and a case now pins that: `-p`, `--interactive`, and any unrecognised flag are still refused rather than guessed at. The four mutations covering this change — restoring `-u` to the value-consuming list, dropping `-q`, dropping the attached-value arm, and widening the list far enough to admit `-p` — each fail a case.

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
