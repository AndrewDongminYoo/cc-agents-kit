#!/usr/bin/env python3
"""Prove secrets-path-guard.sh blocks live secret files across every input field."""

import json
import subprocess
import time
from pathlib import Path

import _optout

HOOK = str(Path(__file__).resolve().with_name("secrets-path-guard.sh"))

CASES = [
    # (expected_exit, label, tool_input)
    # --- the Keychain-derived secrets file, in each field the hook reads ---
    (2, "file_path: secrets file", {"file_path": "/Users/me/.zprofile.secrets"}),
    (2, "command: cat secrets file", {"command": "cat ~/.zprofile.secrets"}),
    (2, "path: grep over secrets file", {"path": "/Users/me/.zprofile.secrets"}),
    (2, "case-insensitive (APFS)", {"file_path": "/Users/me/.ZPROFILE.SECRETS"}),
    # --- live .env files ---
    (2, "file_path: .env", {"file_path": "/proj/.env"}),
    (2, "command: cat .env", {"command": "cat .env"}),
    (2, "command: source .env", {"command": "source .env"}),
    (2, ".env.local", {"file_path": "/proj/.env.local"}),
    (2, ".env.production", {"file_path": "/proj/.env.production"}),
    (2, ".env.production.local", {"file_path": "/proj/.env.production.local"}),
    (2, "quoted .env in a command", {"command": 'grep KEY ".env"'}),
    # --- must NOT block: template variants ---
    (0, "safe: .env.example", {"file_path": "/proj/.env.example"}),
    (0, "safe: .env.sample", {"file_path": "/proj/.env.sample"}),
    (0, "safe: .env.template", {"file_path": "/proj/.env.template"}),
    (0, "safe: .env.dist", {"file_path": "/proj/.env.dist"}),
    (0, "safe: .env.default", {"file_path": "/proj/.env.default"}),
    (0, "safe: .env.defaults", {"file_path": "/proj/.env.defaults"}),
    # --- must NOT block: .env as a property access, not a path component ---
    (0, "safe: process.env.HOME", {"command": "node -e 'console.log(process.env.HOME)'"}),
    (0, "safe: import.meta.env", {"command": "grep -rn import.meta.env src/ --include='*.ts'"}),
    (0, "safe: unrelated file", {"file_path": "/proj/README.md"}),
    (0, "safe: unrelated command", {"command": "ls -la"}),
    # A template token must not exempt a separate live dotenv token.
    (2, "template + real .env in one command",
     {"command": "cat .env.example .env"}),
]

RECURSIVE = [
    # (expected_exit, label, command) - sent as tool_name Bash, like issue #44's probe.
    # --- grep family: a recursive flag reads every dotenv file under the directory ---
    (2, "grep -rn over a directory (#44 probe)", "grep -rn API_KEY /tmp/some-repo"),
    (2, "grep -r", "grep -r KEY ."),
    (2, "grep -R", "grep -R KEY ."),
    (2, "grep --recursive", "grep --recursive KEY src"),
    (2, "grep --dereference-recursive", "grep --dereference-recursive KEY src"),
    (2, "grep -d recurse", "grep -d recurse KEY src"),
    (2, "grep --directories=recurse", "grep --directories=recurse KEY src"),
    (2, "bundled -Rli", "grep -Rli KEY src"),
    (2, "bundled -nr", "grep -nr KEY src"),
    (2, "egrep -r", "egrep -r 'KEY|TOKEN' ."),
    (2, "fgrep -r", "fgrep -r KEY ."),
    (2, "absolute program path", "/usr/bin/grep -rn KEY ."),
    (2, "after NAME=value and command", "LC_ALL=C command grep -rn KEY ."),
    (2, "after xargs", "find . -type f | xargs grep -l KEY -r"),
    # A runner's operand or option value is not the program word.
    (2, "after timeout and its duration", "timeout 5 grep -r SECRET ."),
    (2, "after timeout options and its duration", "timeout -s KILL -k 2 5s grep -r SECRET ."),
    (2, "after timeout --", "timeout -- 5 grep -r SECRET ."),
    (2, "after nice", "nice grep -r SECRET ."),
    (2, "after nice -n value", "nice -n 5 grep -r SECRET ."),
    (2, "after sudo -u value", "sudo -u root grep -r SECRET ."),
    (2, "after env -u value", "env -u HOME grep -r SECRET ."),
    (2, "after xargs -n value", "find . | xargs -n 1 grep -r SECRET"),
    (2, "after nested runners", "sudo -u root timeout 5 nice -n 5 grep -r SECRET ."),
    (0, "timeout of a non-recursive grep", "timeout 5 grep -n KEY a.txt"),
    (0, "sudo -u value named like grep", "sudo -u grep ls -r"),
    (2, "inside a subshell", "(cd src && grep -rn KEY .)"),
    (2, "only one segment is recursive", "grep -n KEY a.txt; grep -rn KEY src"),
    (2, "second pipeline stage", "ls | grep -r KEY ."),
    (2, "second line of the command", "pwd\ngrep -rn KEY ."),
    (2, "exclusion of something else", "grep -rn KEY . --exclude='*.md'"),
    (2, "exclusion of only .env", "grep -rn KEY . --exclude=.env"),
    (2, "--include=* still reads dotenv", "grep -rn KEY . --include='*'"),
    (2, "--include=*.local matches .env.local", "grep -rn KEY . --include='*.local'"),
    (2, "--include=*.env matches .env", "grep -rn KEY . --include=*.env"),
    (2, "dotenv suffix in upper case", "grep -rn KEY . --include=*.LOCAL"),
    (2, "one dotenv include among safe ones", "grep -rn KEY . --include=*.ts --include=*.production"),
    (2, "--include of a bare name", "grep -rn KEY . --include=config"),
    (2, "-e value does not hide a later -r", "grep -e KEY -r ."),
    (2, "exclusion after -- is an operand", "grep -rn KEY -- . --exclude=.env*"),
    (2, "a later --include=* overrides the exclusion", "grep -rn KEY . --exclude='.env*' --include='*'"),
    (0, "a later exclusion overrides --include=*", "grep -rn KEY . --include='*' --exclude='.env*'"),
    (0, "a later safe include keeps the exclusion", "grep -rn KEY . --exclude='.env*' --include='*.ts'"),
    # Brief decision 2: safe includes exclude dotenv, whatever option comes first.
    (0, "safe include after an unrelated exclude", "grep -rn KEY . --exclude='*.md' --include='*.ts'"),
    (0, "safe include before an unrelated exclude", "grep -rn KEY . --include='*.ts' --exclude='*.md'"),
    (0, "non-recursive --directories value", "grep -n KEY a.txt --directories skip"),
    # getopt_long accepts an unambiguous prefix of a long option.
    (2, "abbreviated --recurs", "grep --recurs KEY ."),
    (2, "abbreviated --rec", "grep --rec KEY ."),
    (2, "abbreviated --deref", "grep --deref KEY ."),
    (2, "abbreviated --dir=recurse", "grep --dir=recurse KEY ."),
    (2, "abbreviated --direc recurse as two words", "grep --direc recurse KEY ."),
    (2, "abbreviated --inc='*' after the exclusion", "grep -rn KEY . --exclude='.env*' --inc='*'"),
    (2, "abbreviated --incl '*' as two words", "grep -rn KEY . --exclude='.env*' --incl '*'"),
    (0, "abbreviated recursion with the exclusion", "grep --recurs KEY . --exclude='.env*'"),
    (0, "abbreviated safe include", "grep -rn KEY . --inc='*.ts'"),
    (0, "abbreviated --dir=skip", "grep -n KEY a.txt --dir=skip"),
    (0, "two-letter --re is not read as --recursive", "grep --re KEY a.txt"),
    # --- grep: accepted exclusions ---
    (0, "--exclude='.env*'", "grep -rn API_KEY /tmp/some-repo --exclude='.env*'"),
    (0, '--exclude=".env*"', 'grep -rn API_KEY . --exclude=".env*"'),
    (0, "--exclude=.env* unquoted", "grep -rn API_KEY . --exclude=.env*"),
    (0, "--exclude '.env*' as two words", "grep -rn API_KEY . --exclude '.env*'"),
    (0, '--exclude ".env*" as two words', 'grep -rn API_KEY . --exclude ".env*"'),
    # Unquoted as two words, the shell expands .env* into dotenv file operands.
    (2, "--exclude .env* as two unquoted words", "grep -rn API_KEY . --exclude .env*"),
    (2, "--exclude .env* as two unquoted words, before the pattern", "grep --exclude .env* -rn KEY ."),
    (2, "an accepted exclusion leaves a separate .env operand", "grep -rn KEY . --exclude '.env*' .env"),
    (2, "an attached exclusion leaves a separate .env.local operand", "grep -rn KEY . --exclude=.env* .env.local"),
    (2, "the accepted exclusion is case-sensitive", "grep -rn KEY . --exclude='.ENV*'"),
    (2, "a live dotenv token in another case", "cat .ENV"),
    (0, "an exclusion value names no file in any command", "tar czf out.tgz --exclude='.env*' src"),
    (0, "an exclusion at the very start of the command", "--exclude='.env*'"),
    (0, "--include=*.ts", "grep -rn foo src --include=*.ts"),
    (0, "several safe includes", "grep -rn foo src --include='*.ts' --include '*.tsx'"),
    (0, "exclusion before the pattern", "grep --exclude='.env*' -rn foo src"),
    (0, "exclusion then a pipe", "grep -rn foo src --exclude='.env*' | head -5"),
    # --- grep: not recursive ---
    (0, "non-recursive grep", "grep -n KEY src/main.ts"),
    (0, "-r is the -e pattern", "grep -e -r notes.txt"),
    (0, "a cluster value is not a flag", "grep -nA3r KEY notes.txt"),
    (0, "piped grep", "ps aux | grep -i node"),
    (0, "grep -rn as prose in a quoted string", 'echo "run grep -rn KEY . to find it"'),
    (0, "separator inside a quoted commit message",
     'git commit -m "docs: say why; grep -rn KEY . reads dotenv"'),
    (0, "git grep is out of scope", "git grep -n KEY"),
    (0, "a word that merely contains grep", "ls node_modules/grepper -R"),
    # --- an exclusion does not exempt another live dotenv token ---
    (2, "exclusion plus cat .env", "grep -rn KEY . --exclude='.env*' && cat .env"),
    (2, "exclusion value with a suffix stays a token", "grep -n KEY . --exclude=.env.local"),
    (2, "exclusion glued to more text stays a token", "grep -rn KEY . --exclude='.env*'x"),
    # The exemption is a plain pattern over the command, so it holds in a
    # non-recursive grep too; the unquoted two-word form stays refused there.
    (2, "non-recursive grep, unquoted two-word exclude", "grep API_KEY --exclude .env*"),
    (2, "non-recursive grep, two-word exclude and a file", "grep -n API_KEY --exclude .env* config.txt"),
    (0, "non-recursive grep, quoted exclude", "grep -n KEY a.txt --exclude='.env*'"),
    (0, "non-recursive grep, quoted two-word exclude", "grep -n KEY a.txt --exclude '.env*'"),
    # A quoted two-word value loses its quotes to a second parse, which expands
    # .env* into dotenv operands, and after -- it is an operand. It is exempt only
    # in a grep command read from the start of the command.
    (2, "two-word exclusion after -- in a grep", "grep KEY -- --exclude '.env*'"),
    (2, "two-word exclusion after a quoted --", "grep -rn KEY '--' --exclude '.env*'"),
    (2, "two-word exclusion in a non-grep command", "cat -- --exclude '.env*'"),
    (2, "two-word exclusion under eval", "eval cat -- --exclude '.env*'"),
    (2, "two-word exclusion in a grep under eval", "eval grep -r KEY . --exclude '.env*'"),
    (2, "two-word exclusion in unquoted $(...) output", "grep KEY $(echo --exclude '.env*')"),
    (2, "two-word exclusion piped into a shell", "echo grep KEY --exclude '.env*' | sh"),
    (2, "two-word exclusion inside nested sh -c quotes", "sh -c 'x; grep -r --exclude '.env*' .'"),
    (2, "two-word exclusion as an echo argument", "echo grep -n KEY a.txt --exclude '.env*' x"),
    (2, "two-word exclusion after a $ the hook cannot read", "grep -r \"$K\" --exclude '.env*' ."),
    (0, "two-word exclusion after a quoted pattern", "grep -rn \"API KEY\" --exclude '.env*' ."),
    (0, "two-word exclusion in a later command", "cd src && grep -rn KEY --exclude '.env*' . | head"),
    (0, "two-word exclusions in two grep commands", "grep -r A --exclude '.env*' .; grep -r B --exclude \".env*\" ."),
    (0, "two-word exclusion beside an attached one", "/usr/bin/grep -r --exclude '.env*' --exclude=\"*.md\" KEY ."),
    (2, "a two-word exclusion leaves a quoted .env operand", "grep -rn KEY . --exclude '.env*'; cat '.env'"),
    (2, "a .env operand before a two-word exclusion in the same grep", "grep -rn KEY .env --exclude '.env*'"),
    (2, "a .env.local operand between two-word exclusions", "grep -r --exclude '.env*' .env.local --exclude \".env*\" ."),
    # The attached value keeps its --exclude= prefix through any parse, so it
    # never globs into a dotenv operand.
    (0, "attached exclusion under eval after --", "eval cat -- --exclude='.env*'"),
    # --- rg: skips hidden files unless told to read them ---
    (0, "plain rg", "rg -n API_KEY /tmp/some-repo"),
    (0, "rg -u (gitignored, still not hidden)", "rg -u KEY ."),
    (0, "rg -U is multiline, not -u", "rg -U 'a.b' ."),
    (0, "rg -t value is not a flag", "rg -tuu -n KEY ."),
    (2, "rg --hidden", "rg --hidden KEY ."),
    (2, "rg -.", "rg -. KEY ."),
    (2, "rg -.n", "rg -.n KEY ."),
    (2, "rg -uu", "rg -uu KEY ."),
    (2, "rg -uuu", "rg -uuu KEY ."),
    (2, "rg -uuH", "rg -uuH KEY ."),
    (2, "rg -u -u", "rg -u -u KEY ."),
    (2, "rg --unrestricted twice", "rg --unrestricted --unrestricted KEY ."),
    (2, "rg --hidden with another glob", "rg --hidden -g '*.ts' KEY ."),
    (2, "rg --hidden with !.env only", "rg --hidden -g '!.env' KEY ."),
    (0, "rg --glob= of something else", "rg --glob='*.ts' KEY ."),
    (2, "rg --hidden --glob= of something else", "rg --hidden --glob='*.ts' KEY ."),
    (2, "rg --hidden --glob of something else", "rg --hidden --glob '*.ts' KEY ."),
    (0, "rg --hidden -g '!.env*'", "rg --hidden -g '!.env*' KEY ."),
    (0, "rg -uu --glob='!.env*'", "rg -uu --glob='!.env*' KEY ."),
    (0, "rg -. --glob '!.env*'", "rg -. --glob '!.env*' KEY ."),
    (0, "rg --hidden --iglob='!.env*'", "rg --hidden --iglob='!.env*' KEY ."),
    (0, "rg --hidden -g!.env* bundled", "rg --hidden -g!.env* KEY ."),
    # ripgrep lets a later glob override an earlier one.
    (2, "rg: a later -g '*' re-includes dotenv", "rg --hidden KEY . -g '!.env*' -g '*'"),
    (2, "rg: a later --glob=*.local re-includes", "rg -uu --glob='!.env*' --glob='*.local' KEY ."),
    (0, "rg: a later safe glob keeps the exclusion", "rg --hidden -g '!.env*' -g '*.ts' KEY ."),
    (0, "rg: a later negated glob keeps the exclusion", "rg --hidden -g '!.env*' -g '!*.md' KEY ."),
    (0, "rg: the exclusion after -g '*' wins", "rg --hidden -g '*' -g '!.env*' KEY ."),
    # A positive glob whitelists what it matches, hidden files included (ripgrep 15.2.0).
    (2, "rg -g '*' reads hidden dotenv files", "rg -g '*' KEY ."),
    (2, "rg --glob='*'", "rg --glob='*' KEY ."),
    (2, "rg --iglob '*'", "rg --iglob '*' KEY ."),
    (2, "rg -g '*.local'", "rg -n -g '*.local' KEY ."),
    (2, "rg -g '**'", "rg -g '**' KEY ."),
    (2, "rg -g 'src/**'", "rg -g 'src/**' KEY ."),
    (2, "rg brace glob with a dotenv suffix", "rg -g '*.{ts,local}' KEY ."),
    (0, "rg -g '*' then the exclusion", "rg -g '*' -g '!.env*' KEY ."),
    (0, "rg brace glob of safe suffixes", "rg -g '*.{ts,tsx}' KEY ."),
    (0, "rg path glob ending in a safe suffix", "rg -g 'src/**/*.ts' KEY ."),
    (0, "rg glob of a plain name", "rg -g Makefile KEY ."),
    (0, "rg glob that cannot start with a dot", "rg -g 'a*' KEY ."),
    # ripgrep reads a backslash as an escape, so \. is a literal dot (ripgrep 15.2.0).
    (2, "rg escaped-dot glob reads hidden files", "rg -g '\\.*' KEY ."),
    (2, "rg escaped-dot glob names .env", "rg -g '\\.env' KEY ."),
    (2, "rg: a later escaped-dot glob re-includes dotenv", "rg --hidden -g '!.env*' -g '\\.*' KEY ."),
    (0, "rg escaped dot in a safe suffix glob", "rg -g '*\\.ts' KEY ."),
    (0, "rg escaped ! is a literal name, not an exclusion", "rg -g '\\!.env*' KEY ."),
    # A selected type whitelists its files too; the built-in sh type lists .env.
    (2, "rg -t sh", "rg -t sh KEY ."),
    (2, "rg -tsh bundled", "rg -tsh KEY ."),
    (2, "rg --type=sh", "rg --type=sh KEY ."),
    (2, "rg --type all", "rg --type all KEY ."),
    (2, "rg --type-add of a dotenv-capable glob", "rg --type-add 'x:*' -t x KEY ."),
    (2, "rg --type-add=include:", "rg --type-add=x:include:sh -t x KEY ."),
    (0, "rg -t ts", "rg -t ts KEY ."),
    (0, "rg --type-add of a safe suffix", "rg --type-add 'web:*.html' -t web KEY ."),
    (0, "rg -t sh with the exclusion", "rg -t sh -g '!.env*' KEY ."),
    (0, "rg: the exclusion before -t sh still wins", "rg -g '!.env*' -t sh KEY ."),
    # --- $'...' and $"...": the shell drops the $ and decodes the ANSI-C escapes ---
    (2, "grep $'-r'", "grep $'-r' KEY ."),
    (2, "rg $'--hidden'", "rg $'--hidden' KEY ."),
    (2, 'grep $"-r"', 'grep $"-r" KEY .'),
    (2, "grep $'\\x2dr' (hex escape)", "grep $'\\x2dr' KEY ."),
    (2, "grep $'\\055r' (octal escape)", "grep $'\\055r' KEY ."),
    (2, "rg $'-\\x2e' (hex escape in the cluster)", "rg $'-\\x2e' KEY ."),
    # $'...' is not one of the accepted exclusion shapes, so its value stays a token.
    (2, "an ANSI-C quoted exclusion", "grep -r KEY . --exclude=$'.env*'"),
    (2, "an ANSI-C quoted exclusion still leaves cat .env", "grep -r KEY . --exclude=$'.env*' && cat .env"),
    (0, "\\' does not end $'...'", "grep -n $'it\\'s -r' a.txt"),
    (0, "a NUL ends the decoded argument", "grep -e $'a\\0-r' -n x"),
    (0, "$'...' glued to a word is not an option", "grep x$'-r' KEY ."),
    (0, "$'...' inside double quotes is literal", "grep -n \"$'-r'\" a.txt"),
    (0, "a search inside $'...' prose is not run", "echo $'grep -r KEY .'"),
    (2, "$'...' after a plain word part keeps the decoded option", "grep -$'r' KEY ."),
    # --- heredocs: a quoted delimiter makes the body data, not commands ---
    (0, "quoted heredoc body is data", "cat > /tmp/x.sh <<'EOF'\ngrep -rn TODO src\nEOF"),
    (0, "double-quoted heredoc delimiter", 'cat > x.sh <<"EOF"\ngrep -rn TODO src\nEOF'),
    (0, "<<-'EOF' with a tab-indented terminator", "cat > x.sh <<-'EOF'\n\tgrep -rn TODO src\n\tEOF"),
    (0, "<< 'EOF' as two words", "cat > x.sh << 'EOF'\ngrep -rn TODO src\nEOF"),
    (0, "two quoted heredocs on one line",
     "cat <<'A' > a.sh; cat <<'B' > b.sh\ngrep -rn x .\nA\ngrep -rn y .\nB"),
    (2, "unquoted heredoc body expands, so it is read", "cat > x.sh <<EOF\ngrep -rn TODO src\nEOF"),
    (2, "a shell runs the quoted heredoc", "bash <<'EOF'\ngrep -rn KEY .\nEOF"),
    (2, "a line after the heredoc is a command", "cat > x.sh <<'EOF'\necho hi\nEOF\ngrep -rn KEY ."),
    (2, "a quoted <<EOF is not a heredoc", 'echo "<<EOF"\ngrep -rn KEY .'),
    (2, "a herestring is not a heredoc", "cat <<<'EOF'\ngrep -rn KEY ."),
    (2, "a heredoc body still gets the .env check", "cat > x.sh <<'EOF'\ngrep -rn KEY .\ncat .env\nEOF"),
    (0, "an fd before a quoted heredoc operator", "cat 3<<'EOF'\ngrep -r KEY .\nEOF"),
    (0, "a {name} before a quoted heredoc operator", "cat {fd}<<'EOF'\ngrep -r KEY .\nEOF"),
    (0, "an fd before << 'EOF' as two words", "cat 3<< 'EOF'\ngrep -r KEY .\nEOF"),
    (0, "an fd before <<-'EOF'", "cat 0<<-'EOF'\n\tgrep -r KEY .\n\tEOF"),
    (2, "an fd before an unquoted heredoc", "cat 3<<EOF\ngrep -r KEY .\nEOF"),
    (2, "an fd before a herestring", "cat 3<<<'EOF'\ngrep -r KEY ."),
    # --- comments: a # that starts a word hides the rest of the line from the shell ---
    (2, "an exclusion inside a comment does not count", 'grep -r KEY . # --exclude=".env*"'),
    (2, "a safe include inside a comment does not count", "grep -r KEY . # --include=*.ts"),
    (0, "a search inside a comment is not run", "echo ok # ; grep -r KEY ."),
    (0, "a comment right after a separator", "echo a;# ; grep -r KEY ."),
    (0, "a whole-line comment", "# grep -rn KEY .\nls"),
    (2, "a comment ends at the newline", "echo ok # note\ngrep -rn KEY ."),
    (2, "a # inside a word is not a comment", "echo a#b ; grep -rn KEY ."),
    (0, "a comment after a quoted heredoc operator", "cat > x.sh <<'EOF' # note\ngrep -rn TODO src\nEOF"),
    # --- command substitution: the enclosing command keeps its options ---
    (2, "-r after $(...)", "grep $(printf KEY) -r ."),
    (0, "an exclusion after $(...)", 'grep -r $(printf KEY) . --exclude=".env*"'),
    (2, "-r after a backtick substitution", "grep `printf KEY` -r ."),
    (0, "an exclusion after a backtick substitution", "grep -r `printf KEY` . --exclude='.env*'"),
    (2, "a recursive grep inside $(...)", "echo $(grep -rn KEY .)"),
    (2, "a recursive grep inside backticks", "echo `grep -rn KEY .`"),
    (2, "a recursive grep inside <(...)", "diff <(grep -rn KEY a) b"),
    (2, "an unterminated $(...) is still read", "echo $(grep -rn KEY ."),
    (2, "a subshell ) inside $(...) does not end it", "grep $( (printf KEY) ) -r ."),
    (2, "$((...)) arithmetic keeps the enclosing grep", "grep $((1+2)) -r ."),
    (0, "nested exclusions are cut in command order",
     "grep -r --exclude='.env*' $(grep -r --exclude='.env*' -l KEY .) ."),
    (2, "nested exclusions still leave cat .env",
     "grep -r --exclude='.env*' $(grep -r --exclude='.env*' -l KEY .) . && cat .env"),
    # --- a redirection before the program ---
    (2, "2>/dev/null before grep", "2>/dev/null grep -r KEY ."),
    (2, "2>&1 before grep", "2>&1 grep -r KEY ."),
    (2, "&>/dev/null before grep", "&>/dev/null grep -rn KEY ."),
    (2, "a redirection target as a separate word", "> out.txt grep -rn KEY ."),
    (2, "a redirection after NAME=value and command", "LC_ALL=C 2>/dev/null command grep -rn KEY ."),
    (2, "2>&1 after grep, then a pipe", "grep -r KEY . 2>&1 | head"),
    (0, "a redirection before an excluding grep", "2>/dev/null grep -rn KEY . --exclude='.env*'"),
    # --- a redirection after the program: the shell drops it and its target ---
    (2, "> then an --include target is not an option", "grep -r KEY . > --include=*.ts"),
    (2, ">> then an --include target is not an option", "grep -r KEY . >> --include=*.ts"),
    (2, "2> then an --exclude target is not an option", "grep -r KEY . 2> --exclude=.env*"),
    (2, "an attached > target is not an option", "grep -r KEY . >--include=*.ts"),
    (2, "rg: > then a --glob target is not an option", "rg --hidden KEY . > --glob=!.env*"),
    (2, "rg: a bare > between -g and its value", "rg -g > out '*' KEY ."),
    (2, "rg: an attached > between -g and its value", "rg -g >out '*' KEY ."),
    (2, "a quoted '>' is a pattern, not a redirection", "grep '>' -r ."),
    (0, "a quoted '>' keeps the next option", "grep -r '>' --include=*.ts ."),
    (0, "an excluding grep with a redirection after it", "grep -rn KEY . --exclude='.env*' > out.txt"),
    # The plain exclusion pattern does not read past a redirection.
    (2, "a redirection between --exclude and its value", "grep -rn KEY . --exclude > /dev/null '.env*'"),
    (0, "an excluding rg with 2>/dev/null after it", "rg --hidden -g '!.env*' KEY . 2>/dev/null"),
    (2, "rg: a process substitution is a path, not a redirect target", "rg -e KEY <(true) --hidden ."),
    (2, "grep: a process substitution is a path, not a redirect target", "grep -e KEY <(true) -r ."),
    (2, "a grep with only a redirection, then a dotenv read", "grep > out; cat .env"),
    (2, "an rg with only a redirection, then a dotenv read", "rg 2>/dev/null; cat .env"),
    # --- an unquoted <, > or &> ends the word before it, as in the shell ---
    (2, "< attached to grep", "grep</dev/null -r KEY ."),
    (2, "< attached to rg", "rg</dev/null --hidden KEY ."),
    (2, "> attached to grep", "grep>out -r KEY ."),
    (2, ">| attached to grep", "grep>|out -r KEY ."),
    (2, "< attached to a grep path", "/usr/bin/grep</dev/null -r KEY ."),
    (2, "&> attached to grep", "grep&>/dev/null -r KEY ."),
    (2, "&>> attached to grep", "grep&>>log -r KEY ."),
    (2, "&> does not end the segment", "grep -n KEY a.txt &>/dev/null -r ."),
    (2, "<( attached to a word", "diff<(grep -rn KEY a) b"),
    (0, "a quoted attached < is prose", "echo 'grep</dev/null -r'"),
    (0, "2>&1 keeps a later exclusion", "grep -r KEY . 2>&1 --exclude='.env*'"),
    (0, "{fd}> keeps a later exclusion", "grep -r KEY . {fd}>out --exclude='.env*'"),
    (0, "> attached to the exclusion value", "grep -r KEY . --exclude='.env*'>out"),
    (2, "> attached to the exclusion value still leaves cat .env", "grep -r KEY . --exclude=.env*>out; cat .env"),
    (0, "a quoted heredoc attached to cat is data", "cat<<'EOF'\ngrep -r KEY .\nEOF"),
    # --- rg --iglob excludes case variants too ---
    (0, "rg --iglob '!.env*'", "rg --hidden --iglob '!.env*' KEY ."),
    (0, "rg --glob-case-insensitive with the exclusion", "rg --hidden --glob-case-insensitive -g '!.env*' KEY ."),
    # --- rg: the last of --hidden, -., the second -u and --no-hidden wins ---
    (0, "rg --hidden then --no-hidden", "rg --hidden --no-hidden KEY ."),
    (0, "rg -uu then --no-hidden", "rg -uu --no-hidden KEY ."),
    (0, "rg -. then --no-hidden", "rg -. --no-hidden KEY ."),
    (0, "rg: a third -u leaves --no-hidden", "rg -uu --no-hidden -u KEY ."),
    (2, "rg --no-hidden then --hidden", "rg --no-hidden --hidden KEY ."),
    (2, "rg --no-hidden then -uu", "rg --no-hidden -uu KEY ."),
    (2, "rg --no-hidden then -.", "rg --no-hidden -. KEY ."),
    (2, "rg: the second -u after --no-hidden", "rg -u --no-hidden -u KEY ."),
    (2, "rg --no-hidden keeps a dotenv glob", "rg --no-hidden -g '*' KEY ."),
    # --- rg --type-add only defines a type; -t selects it, in either order ---
    (0, "rg --type-add without -t", "rg --type-add 'custom:*' KEY ."),
    (0, "rg --type-add of a dotenv glob, another type selected", "rg --type-add 'x:*' -t ts KEY ."),
    (2, "rg -t before its --type-add", "rg -t x --type-add 'x:*' KEY ."),
    (2, "rg --type-add then --type", "rg --type-add 'x:*' --type x KEY ."),
    # --- rg --ignore-file: the hook cannot see whether the file whitelists !.env ---
    (2, "rg --ignore-file", "rg --ignore-file x KEY ."),
    (2, "rg --ignore-file=", "rg --ignore-file=x KEY ."),
    (0, "rg --ignore-file with the exclusion last", "rg --ignore-file x KEY . -g '!.env*'"),
    (0, "rg --ignore-file= with --glob= exclusion", "rg --ignore-file=x --glob='!.env*' KEY ."),
    (2, "rg --ignore-file with a later dotenv-capable glob", "rg --ignore-file x -g '!.env*' -g '*' KEY ."),
    # The exclusion must be the last glob: the ignore file is unseen, and *.ts reads .env.production.ts.
    (2, "rg --ignore-file with any later glob", "rg --ignore-file x -g '!.env*' -g '*.ts' KEY ."),
    (0, "rg --ignore-file with a type after the last-glob exclusion", "rg --ignore-file x -g '!.env*' -t ts KEY ."),
    (2, "rg --ignore-file with a later negative glob", "rg --ignore-file x -g '!.env*' -g '!*.md' KEY ."),
    (0, "plain rg still passes", "rg KEY ."),
    (0, "rg --ignore-file-case-insensitive is a flag", "rg --ignore-file-case-insensitive KEY ."),
]

fails = 0
for expected, label, command in RECURSIVE:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    proc = subprocess.run(["/bin/bash", HOOK], input=payload, capture_output=True, text=True)
    ok = proc.returncode == expected
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} exit={proc.returncode} (want {expected})  recursive: {label}")
    if not ok and proc.stderr:
        print(f"       stderr: {proc.stderr.strip()[:160]}")

# The refusal names both accepted exclusion forms.
proc = subprocess.run(
    ["/bin/bash", HOOK],
    input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "grep -rn KEY ."}}),
    capture_output=True,
    text=True,
)
ok = proc.returncode == 2 and "--exclude='.env*'" in proc.stderr and "-g '!.env*'" in proc.stderr
fails += not ok
print(f"{'ok  ' if ok else 'FAIL'} exit={proc.returncode} (want 2)  recursive refusal names both exclusion forms")

DOTENV_MSG = "Blocked: dotenv path"

# The two-word refusal names every accepted exclusion form.
proc = subprocess.run(
    ["/bin/bash", HOOK],
    input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "grep -rn KEY . --exclude .env*"}}),
    capture_output=True,
    text=True,
)
ok = proc.returncode == 2 and all(
    form in proc.stderr
    for form in ("--exclude='.env*'", "--exclude=.env*", '--exclude=".env*"', "--exclude '.env*'", '--exclude ".env*"')
)
fails += not ok
print(f"{'ok  ' if ok else 'FAIL'} exit={proc.returncode} (want 2)  two-word refusal names every accepted exclusion form")

# A quoted two-word value refused outside a grep command points at the attached form.
proc = subprocess.run(
    ["/bin/bash", HOOK],
    input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "eval grep -r KEY . --exclude '.env*'"}}),
    capture_output=True,
    text=True,
)
ok = proc.returncode == 2 and "Blocked: dotenv path" in proc.stderr and "Write --exclude='.env*'" in proc.stderr
fails += not ok
print(f"{'ok  ' if ok else 'FAIL'} exit={proc.returncode} (want 2)  a refused two-word value points at the attached form")

# The dotenv token check runs before the recursive-search check: a command with
# both is refused for its dotenv token, so a tokenizer timeout cannot reach it.
proc = subprocess.run(
    ["/bin/bash", HOOK],
    input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "grep -rn KEY .; cat .env"}}),
    capture_output=True,
    text=True,
)
ok = proc.returncode == 2 and DOTENV_MSG in proc.stderr and "recursive search" not in proc.stderr
fails += not ok
print(f"{'ok  ' if ok else 'FAIL'} exit={proc.returncode} (want 2)  the dotenv token check runs before the tokenizer")

# rg --ignore-file has its own refusal.
proc = subprocess.run(
    ["/bin/bash", HOOK],
    input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "rg --ignore-file x KEY ."}}),
    capture_output=True,
    text=True,
)
ok = proc.returncode == 2 and "--ignore-file" in proc.stderr and "-g '!.env*'" in proc.stderr
fails += not ok
print(f"{'ok  ' if ok else 'FAIL'} exit={proc.returncode} (want 2)  --ignore-file refusal names the exclusion")

# The dotenv token check reads the command in windows; a token, a template or a
# word that only contains .env must be read the same wherever a window cuts it.
DOT = ".env"
cut_fails = 0
for pad in range(990, 1040):
    for expected, tail in (
        (2, f" cat {DOT} x"),
        (2, f" cat {DOT}.local"),
        (0, f" cat {DOT}.example x"),
        (0, " node -e process.env.HOME"),
        (0, f" grep -n KEY a.txt --exclude='{DOT}*' x"),
        (0, f"; grep -n KEY a.txt --exclude '{DOT}*' x"),
        (2, f" grep -n KEY a.txt --exclude '{DOT}*' x"),
    ):
        command = "echo " + "a" * pad + tail
        proc = subprocess.run(
            ["/bin/bash", HOOK],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
            capture_output=True,
            text=True,
        )
        if proc.returncode != expected:
            cut_fails += 1
            print(f"FAIL exit={proc.returncode} (want {expected})  window cut at pad {pad}: {tail!r}")
fails += cut_fails
print(f"{'ok  ' if not cut_fails else 'FAIL'} window cuts at pads 990-1039")
# A cut token's text can appear earlier in the window (.env inside .envrc); the
# cut is read at the match, not at that earlier copy.
cut_fails = 0
for pad in range(990, 1040):
    for expected, tail in (
        (0, f" {DOT}.example"),
        (0, f" {DOT}.example x"),
        (2, f" {DOT}"),
        (2, f" {DOT} x"),
        (2, f" {DOT}.local"),
    ):
        command = f"cat {DOT}rc " + "a" * pad + tail
        proc = subprocess.run(
            ["/bin/bash", HOOK],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
            capture_output=True,
            text=True,
        )
        if proc.returncode != expected:
            cut_fails += 1
            print(f"FAIL exit={proc.returncode} (want {expected})  window cut after {DOT}rc at pad {pad}: {tail!r}")
fails += cut_fails
print(f"{'ok  ' if not cut_fails else 'FAIL'} window cuts after an earlier {DOT}rc at pads 990-1039")
for expected, label, command in (
    (2, "a 3 KiB dotenv suffix crosses windows", f"cat {DOT}." + "a" * 3000),
    (0, "a 3 KiB word ending in a template name", "echo " + "a" * 3000 + f"/{DOT}.example"),
    (2, "a dotenv token after 300 KiB", "echo " + "a " * (150 * 1024) + f"; cat {DOT}"),
):
    proc = subprocess.run(
        ["/bin/bash", HOOK],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
    )
    ok = proc.returncode == expected
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} exit={proc.returncode} (want {expected})  {label}")


# hooks.json gives the hook 5 s; past that the harness drops it and fails open.
# Lines that quote the word grep make every line a tokenizer case.
def long_command(size, tail):
    lines, total = [], 0
    while total < size:
        line = f"echo 'line {len(lines)} see grep docs' >> out.txt\n"
        lines.append(line)
        total += len(line)
    return "".join(lines) + tail


AT_CAP = long_command(64 * 1024 - 64, "cat .env")
OVER_CAP = long_command(64 * 1024 + 64, "cat .env")
assert len(AT_CAP) <= 65536 < len(OVER_CAP)
# One pass per byte: every token is a word or a separator.
dense = "x;" * (31 * 1024)
EXCLUSIONS = "--exclude='.env*' " * 3600
# Over the 64 KiB cap an exclusion value is refused as a dotenv token, so these
# are refused at the first exclusion, however large.
EXCLUSIONS_OVER_CAP = "--exclude='.env*' " * (65536 // 18 + 1)
EXCLUSIONS_1MIB = "--exclude='.env*' " * (1024 * 1024 // 18)
assert len(EXCLUSIONS) < 65536 < len(EXCLUSIONS_OVER_CAP)
# Quoted two-word exclusions are read from the start of the command, which each
# grep command found reads again, so only a command of up to 4 KiB is read.
TWO_WORD = "grep KEY --exclude '.env*'; " * 140
TWO_WORD_OVER_CAP = "grep KEY --exclude '.env*'; " * 147
assert len(TWO_WORD + "cat .env") <= 4096 < len(TWO_WORD_OVER_CAP)
# Two passes per x;, so the recursive grep after it is reached under an 8,000
# pass budget only after the shorter fixture, and under 20,000 after both.
UNDER_BUDGET = "x;" * 3500
OVER_BUDGET = "x;" * 5000
for command, expected, limit, label in (
    # --- the dotenv token check runs first and reads any command in well under the timeout ---
    (AT_CAP, 2, 0.5, "64 KiB command ending in cat .env is refused by the first stage"),
    (OVER_CAP, 2, 0.5, "command just over the 64 KiB cap ending in cat .env is refused"),
    ("echo grep\n" + dense + "\ncat .env", 2, 0.5, "dense command past the pass budget, then cat .env"),
    ("echo grep $(" + dense + ")\ncat .env", 2, 0.5, "dense command inside $(...), then cat .env"),
    ("echo grep " + "$(" * 9999 + "\ncat .env", 2, 0.5, "10,000 nested $(, then cat .env"),
    # Each skipped token costs a regex in a small window, so the cost stays linear.
    (EXCLUSIONS + "cat .env", 2, 1.5, "3,600 accepted exclusions, then cat .env"),
    (EXCLUSIONS + "ls", 0, 1.5, "3,600 accepted exclusions are stepped over"),
    (EXCLUSIONS_OVER_CAP + "; cat .env", 2, 0.5, "exclusions just over 64 KiB, then cat .env"),
    (EXCLUSIONS_1MIB + "; cat .env", 2, 2.5, "1 MiB of exclusions, then cat .env"),
    (EXCLUSIONS_OVER_CAP + "; ls", 2, 0.5, "exclusions over 64 KiB are refused as dotenv tokens"),
    (TWO_WORD + "cat .env", 2, 1.5, "140 grep commands with two-word exclusions, then cat .env"),
    (TWO_WORD + "ls", 0, 1.5, "140 grep commands with two-word exclusions are stepped over"),
    (TWO_WORD_OVER_CAP + "ls", 2, 0.5, "two-word exclusions over 4 KiB are refused as dotenv tokens"),
    ("cat .env.example " * 3600 + "cat .env", 2, 1.5, "3,600 template names, then cat .env"),
    (long_command(300 * 1024, "cat .env"), 2, 2.5, "300 KiB command skips the tokenizer, keeps the .env check"),
    ("echo 'grep " + "a" * (2 * 1024 * 1024) + "'\ncat .env", 2, 2.5, "2 MiB quoted word skips the tokenizer"),
    # --- the tokenizer stays inside the timeout; past a budget only its own check is lost ---
    (long_command(24 * 1024, "grep -rn KEY ."), 2, 2.5, "24 KiB command is tokenized to its end"),
    ("echo grep\n" + dense + "\nls", 0, 2.5, "dense 62 KiB command stays inside the timeout"),
    ("echo grep $(" + dense + ")\nls", 0, 2.5, "dense 62 KiB command inside $(...) stays inside the timeout"),
    # Each substitution walks bash 3.2's list arrays, so their number and depth are capped.
    ("echo grep " + "$(" * 9999 + "\nls", 0, 2.5, "10,000 nested $( stop at the depth cap"),
    ("grep " + "$(x) " * 6000 + "\nls", 0, 2.5, "6,000 substitutions stop at the count cap"),
    ("echo grep " + "$(x) " * 300 + "\ngrep -rn KEY . --exclude='.env*'", 0, 2.5,
     "past the substitution cap only the recursive check is lost"),
    # The budget is 8,000 passes: a recursive grep after 7,000 passes is checked,
    # one after 10,000 is not, and a .env token after either is still refused.
    ("echo grep\n" + UNDER_BUDGET + "\ngrep -rn KEY .", 2, 2.5, "a recursive grep inside the pass budget is checked"),
    ("echo grep\n" + OVER_BUDGET + "\ngrep -rn KEY .", 0, 2.5, "past the pass budget only the recursive check is lost"),
    ("echo grep\n" + OVER_BUDGET + "\ngrep -rn KEY .; cat .env", 2, 2.5, "past the pass budget a .env token is still refused"),
    # Splitting an rg glob or --type-add value is quadratic; over 1 KiB it counts as dotenv-capable.
    ("rg -g '*.{" + "ts," * 20000 + "ts}' KEY .", 2, 2.5, "60 KiB rg brace glob is refused inside the timeout"),
    # Decoding a $'...' body copies the rest at each escape, and a two-byte escape
    # tries every escape form; over 256 bytes the body is kept as written.
    ("grep " + ("$'" + "\\\\" * 128 + "' ") * 240 + "\nls", 0, 2.5, "240 decoded 256-byte $'...' words stay inside the timeout"),
    ("grep " + ("$'" + "\\a" * 512 + "' ") * 63 + "\nls", 0, 2.5, "63 escape-dense 1 KiB $'...' words stay inside the timeout"),
    ("grep $'" + "\\x41" * 15000 + "'\nls", 0, 2.5, "a 60 KiB $'...' word stays inside the timeout"),
    ("rg --hidden " + " ".join("--type-add 'x:" + "*.ts," * 203 + "'" for _ in range(55)) + " KEY .",
     2, 2.5, "many 1 KiB --type-add values are split inside the timeout"),
):
    started = time.monotonic()
    proc = subprocess.run(
        ["/bin/bash", "-p", HOOK],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
    )
    elapsed = time.monotonic() - started
    ok = proc.returncode == expected and elapsed < limit
    # A first-stage refusal names the dotenv token, not the recursive search.
    if command.endswith("cat .env"):
        ok = ok and DOTENV_MSG in proc.stderr
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} exit={proc.returncode} (want {expected}) {elapsed:.2f}s (limit {limit}s)  {label}")

for expected, label, tool_input in CASES:
    payload = json.dumps({"tool_name": "Read", "tool_input": tool_input})
    proc = subprocess.run(["/bin/bash", HOOK], input=payload, capture_output=True, text=True)
    ok = proc.returncode == expected
    fails += not ok
    print(
        f"{'ok  ' if ok else 'FAIL'} exit={proc.returncode} (want {expected})  {label}"
    )
    if not ok and proc.stderr:
        print(f"       stderr: {proc.stderr.strip()[:160]}")

# fail-open contract: never block on input the hook cannot parse
for label, payload in (
    ("empty object", "{}"),
    ("no readable field", '{"tool_input": {"pattern": "TODO"}}'),
    ("malformed", "not json at all"),
    ("empty stdin", ""),
):
    proc = subprocess.run(["/bin/bash", HOOK], input=payload, capture_output=True, text=True)
    ok = proc.returncode == 0
    fails += not ok
    print(
        f"{'ok  ' if ok else 'FAIL'} exit={proc.returncode} (want 0)  fail-open: {label}"
    )



DISABLE_VAR = "CC_GUARD_DISABLE_SECRETS_PATH"
BLOCKING = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/proj/.env"}})
SAFE = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/proj/README.md"}})

# --- opt-out contract -------------------------------------------------------
fails += _optout.contract(HOOK, DISABLE_VAR, BLOCKING, SAFE)

print("\nALL PASS" if not fails else f"\n{fails} FAILURES")
raise SystemExit(1 if fails else 0)
