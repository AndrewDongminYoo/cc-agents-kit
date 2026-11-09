# shellcheck shell=bash
# Shared helpers for docs/demo-<name>.sh. Sourced, never run.
#
# A demo script defines play() and ends with `demo_main <name> "$@"`:
#
#   bash docs/demo-<name>.sh           records docs/<name>.cast and .gif
#                                      (brew install asciinema agg)
#   bash docs/demo-<name>.sh --play    prints the scene once
#
# The scenes run the shipped hook scripts, so what the GIF shows is what the
# hook prints. With DEMO_FAST=1 every delay is skipped; CI replays each demo
# that way and compares its text with the committed .cast, so a hook whose
# output changed fails CI until the demo is recorded again.

DEMO_COLS=100
DEMO_ROWS=30

P=$'\033[38;5;114m'
C=$'\033[38;5;245m'
R=$'\033[38;5;203m'
X=$'\033[0m'

demo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

pause() {
  [[ -n "${DEMO_FAST:-}" ]] || perl -e "select undef,undef,undef,$1"
}

say() { printf '%s%s%s\n' "$1" "$2" "$X"; }

type_out() {
  printf '%s$%s ' "$P" "$X"
  local i
  for ((i = 0; i < ${#1}; i++)); do
    printf '%s' "${1:i:1}"
    pause 0.024
  done
  echo
}

# run_hook <plugin>/hooks/<hook>.sh <json> [grep -oE pattern]
# Runs the hook on one payload and prints what it printed: stdout plain,
# stderr in red, then its exit code. The optional pattern trims stdout to the
# matching parts, and the scene types that filter on screen.
run_hook() {
  local hook=$1 payload=$2 pattern=${3:-} out err rc=0
  err=$(mktemp)
  # Only PATH reaches the hook, so a CC_GUARD_* opt-out or dev-path setting in
  # the recorder's shell cannot change what the demo shows.
  out=$(printf '%s' "$payload" | env -i PATH="$PATH" /bin/bash "$demo_root/plugins/$hook" 2>"$err") || rc=$?
  if [[ -n "$pattern" ]]; then
    out=$(printf '%s\n' "$out" | grep -oE "$pattern" || true)
  fi
  [[ -z "$out" ]] || printf '%s\n' "$out" | fold -s -w $((DEMO_COLS - 2))
  if [[ -s "$err" ]]; then
    printf '%s' "$R"
    fold -s -w $((DEMO_COLS - 2)) "$err"
    printf '%s' "$X"
  fi
  rm -f "$err"
  # Only a tool-call guard allows or blocks; other hooks just print.
  [[ "$payload" == *'"tool_name"'* ]] || return 0
  if ((rc == 2)); then
    say "$C" "# exit 2: blocked, so the tool call never ran."
  else
    say "$C" "# exit $rc: allowed, so the tool call runs."
  fi
}

demo_main() {
  local name=$1
  shift
  if [[ "${1:-}" == "--play" ]]; then
    play
    return
  fi
  cd "$demo_root" || return
  asciinema rec "docs/$name.cast" --headless --overwrite \
    --window-size "${DEMO_COLS}x${DEMO_ROWS}" -c "bash docs/demo-$name.sh --play"
  agg "docs/$name.cast" "docs/$name.gif" \
    --font-size 16 --theme asciinema --idle-time-limit 2
  echo "wrote docs/$name.gif"
}
