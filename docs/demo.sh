#!/bin/bash
# Regenerates docs/guard-hooks.gif.
#
#   brew install asciinema agg
#   bash docs/demo.sh
#
# The failure it shows is real and reproducible: with exactly one .md in the
# working directory, zsh expands the unquoted `*.md` before find is invoked, so
# `find . -name *.md` runs as `find . -name README.md` — exit 0, plausible
# output, every nested match missing. The blocked output is the message
# zsh-quoting-guard.sh actually prints; run the suite next to it to check.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
stage=$(mktemp -d)

mkdir -p "$stage/docs"
echo "# README" > "$stage/README.md"
echo "# design notes" > "$stage/docs/DESIGN.md"

# Kept outside the stage: anything in there shows up in the `ls -R` on screen.
play="$stage.play.sh"
trap 'rm -rf "$stage" "$play"' EXIT

cat > "$play" <<'PLAY'
#!/bin/bash
set -u
cd "$1" || exit 1

P=$'\033[38;5;114m'; C=$'\033[38;5;245m'; R=$'\033[38;5;203m'; X=$'\033[0m'

type_out() {
  printf '%s$%s ' "$P" "$X"
  local i
  for ((i = 0; i < ${#1}; i++)); do
    printf '%s' "${1:i:1}"
    perl -e 'select undef,undef,undef,0.024'
  done
  echo
}
beat() { perl -e "select undef,undef,undef,$1"; }
say() { printf '%s%s%s\n' "$1" "$2" "$X"; }

say "$C" "# Two .md files: one here, one nested. A search should find both."
beat 1.0
type_out "ls -R"
ls -R
beat 1.4

say "$C" "# The search an agent writes, run under zsh:"
beat 0.9
type_out "find . -name *.md"
zsh -c 'find . -name *.md'
beat 0.6
say "$R" "# exit 0, and docs/DESIGN.md is missing. Nothing said so."
say "$R" "# zsh expanded *.md first, so find actually ran as:"
say "$R" "#   find . -name README.md"
beat 2.4

say "$C" "# Same command, with guard-hooks installed:"
beat 0.9
type_out "claude -p 'find . -name *.md'"
say "$R" "PreToolUse:Bash hook error: [\${CLAUDE_PLUGIN_ROOT}/hooks/zsh-quoting-guard.sh]"
say "$R" "Blocked: unquoted glob pattern (-name *). zsh expands it against the CWD"
say "$R" "before the tool sees it: no match aborts the whole command, several"
say "$R" "become a filename list the tool rejects, and exactly one silently"
say "$R" "searches that single file instead of the pattern. Quote it:"
say "$R" "--include='*.dart', -name '*.md'."
beat 1.2
say "$P" "# /plugin install guard-hooks@cc-agents-kit"
beat 3.2
PLAY

chmod +x "$play"
asciinema rec "$here/guard-hooks.cast" --headless --overwrite -c "bash $play $stage"
agg "$here/guard-hooks.cast" "$here/guard-hooks.gif" \
  --font-size 16 --theme asciinema --idle-time-limit 1.5
echo "wrote $here/guard-hooks.gif"
