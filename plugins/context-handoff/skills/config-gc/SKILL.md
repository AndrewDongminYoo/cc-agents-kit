---
name: config-gc
description: Garbage collection for ~/.claude — scans skills, memory, hooks, permissions, MCP servers, and caches for redundant, stale, or orphaned items, then walks the user through confirm-each-deletion cleanup. Use on "clean up my config", "config GC", "too many skills", "my .claude is bloated", or a periodic review.
metadata:
  category: claude-config
  origin: https://github.com/affaan-m/ecc (MIT), skills/config-gc — substantially upstream; see CREDITS.md
---

# Config GC — Garbage Collection for Claude Code Setups

Borrowed from runtime garbage collection: periodically scan for objects that are no longer referenced, redundant, expired, or low-value, and reclaim the space. The critical difference: **here, collection requires a human in the loop. Never delete autonomously.**

## When to Activate

- The user asks to clean up, audit, or slim down their Claude Code configuration
- The user complains about too many skills, noisy hooks, or slow session startup
- A monthly/periodic config review is due
- After installing a large skill pack (e.g. this repo), to reconcile overlaps with existing setup

Do NOT activate for: cleaning project source code (that's refactoring), clearing chat history, or uninstalling Claude Code itself.

## Design Philosophy

1. **Append-only configs leak.** Skills, memory files, hooks, and permission entries only ever get added. Without periodic review they rot silently.
2. **Regular audits beat one-time purges.** Scan every ~30 days, propose a small batch of candidates each time.
3. **Per-channel strategies.** Each accumulation type (skills, hooks, permissions, ...) has its own staleness signals — don't apply one rule everywhere.
4. **Soft-delete first.** Rename to `.disabled` > move to `~/.claude/_gc_trash/` > real deletion. Always keep an undo path.
5. **Forced human-in-the-loop.** Every candidate gets its own `[y/n/skip]` confirmation. No "yes to all" shortcut.
6. **Keep a log.** Every GC run appends to `~/.claude/gc_log.md`: what was touched, why, and how to undo it.

## Scan Channels

| #   | Channel                    | Path                                                           | Staleness / redundancy signals                                                                                                                                                    |
| --- | -------------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Skills                     | `~/.claude/skills/*/`                                          | Heavily overlapping names; never triggered in recent transcripts; domain mismatch with the user's actual work; broken or empty SKILL.md                                           |
| 2   | Memory                     | `~/.claude/**/memory/*.md` + its index                         | Multiple index entries for one topic; contents contradicting newer entries; dates that have passed; orphan files missing from the index; sub-100-word fragments that should merge |
| 3   | Hooks                      | `~/.claude/hooks/` + settings                                  | Scripts present on disk but referenced by no hook config; old versions superseded by rewrites                                                                                     |
| 4   | Permissions                | `permissions.allow` in `settings.json` / `settings.local.json` | Duplicate entries; specific entries already covered by a wildcard (e.g. `Bash(git push)` when `Bash(*)` is allowed); one-off grants from past experiments                         |
| 5   | MCP servers                | `~/.claude.json` or project `.mcp.json`                        | Servers that fail to connect; functional duplicates; long-unused                                                                                                                  |
| 6   | Scheduled reminders / jobs | wherever the user keeps them                                   | Fired one-shots older than 30 days; jobs whose target scripts no longer exist                                                                                                     |
| 7   | Project history            | `~/.claude/projects/*/`                                        | Stale handoff snapshots; session records superseded by newer state                                                                                                                |
| 8   | Runtime caches             | `cache/`, `file-history/`, `logs/`, `shell-snapshots/`         | Sort by size and mtime; propose items >30 days old and large                                                                                                                      |

## Workflow

1. **Scan** all channels (or the subset the user names). Collect candidates with: path, channel, signal that flagged it, size, last-modified.
2. **Rank** by confidence (broken/orphaned = high; merely old = low) and present as a numbered table. Cap each run at ~20 candidates — GC is periodic, not exhaustive.
3. **Confirm one by one.** For each candidate show the evidence, then ask `[y/n/skip]`. The user can stop at any point.
4. **Soft-delete confirmed items**: prefer `.disabled` rename for skills/hooks and `_gc_trash/<date>/` move for files. Permission entries live in JSON (no comments possible): back up the settings file, record each removed entry verbatim in `gc_log.md`, then remove it from the `allow` array with `jq`. Only hard-delete when the user explicitly asks.
5. **Log** the run to `~/.claude/gc_log.md`: timestamp, items actioned, undo instructions.
6. **Report**: reclaimed size, channels still healthy, suggested next review date.

## Example Scan Commands

Orphaned hook scripts (channel 3) — scripts on disk that no hook config references.
**Grep each settings file separately.** `settings.local.json` is often absent, and on macOS/BSD an unreadable file makes grep exit 2 even when the pattern matched in the file that does exist — one missing file then reports every script as an orphan:

```bash
for f in ~/.claude/hooks/* ~/.claude/scripts/*; do
  [ -f "$f" ] || continue
  name=$(basename "$f") hit=""
  for cfg in ~/.claude/settings.json ~/.claude/settings.local.json; do
    [ -f "$cfg" ] && grep -qF "$name" "$cfg" && hit=1
  done
  [ -n "$hit" ] || echo "ORPHAN: $f"
done
```

Then clear each hit by hand before proposing it: a script can be wired somewhere settings.json never mentions — a launchd plist, another skill, a README, or "manual by design". Confirm where it is called from, not merely that settings.json omits it.

Redundant permission entries (channel 4) — duplicates, and specific grants shadowed by a wildcard.
Both settings files are optional, so guard the read; `jq` on a missing path aborts the pipeline:

```bash
for cfg in ~/.claude/settings.json ~/.claude/settings.local.json; do
  [ -f "$cfg" ] || continue
  echo "-- $cfg"
  jq -r '.permissions.allow[]?' "$cfg" | sort | uniq -d
  if jq -e '.permissions.allow? | index("Bash(*)")' "$cfg" >/dev/null 2>&1; then
    jq -r '.permissions.allow[]?' "$cfg" | grep '^Bash(' | grep -vF 'Bash(*)'
  fi
done
```

Stale plugin cache versions (channel 8) — `plugins/cache/<marketplace>/<plugin>/<version>/` keeps every version ever synced, while `installed_plugins.json` names the one in use.
Marketplaces that version by git SHA mint a fresh directory on every upstream commit, so this grows without bound:

Key the lookup on the full `plugin@marketplace` id, never on the plugin name alone — the same plugin name ships from more than one marketplace (`commit-commands` and `frontend-design` each exist twice here), and a name-only match reports the surviving twin's version as current for the uninstalled one:

```bash
cd ~/.claude
for pdir in plugins/cache/*/*/; do
  mp=$(basename "$(dirname "$pdir")"); plugin=$(basename "$pdir")
  cur=$(jq -r --arg k "$plugin@$mp" '.plugins[$k][0].version // empty' plugins/installed_plugins.json)
  if [ -z "$cur" ]; then echo "ORPHAN DIR (plugin uninstalled): $pdir"; continue; fi
  for v in "$pdir"*/; do
    [ "$(basename "$v")" = "$cur" ] || echo "STALE: $v"
  done
done
```

There is a single config dir (`~/.claude`) — the `CLAUDE_CONFIG_DIR` flutter worktree was decommissioned 2026-08-08. Historical caveat should a second config dir ever return: its cache records `installPath` pointing at the home config, so `claude plugin uninstall` there deletes nothing and leaves the whole plugin directory behind.

Largest stale caches (channel 8) — `du -k` instead of GNU-only `find -printf`, so it works on macOS/BSD too:

```bash
find ~/.claude/file-history ~/.claude/shell-snapshots -type f -mtime +30 \
  -exec du -k {} + 2>/dev/null | sort -rn | head -20
```

Soft-delete with undo path (capture the date once so the log can't disagree with the directory):

```bash
gc_date=$(date +%Y-%m-%d)
mkdir -p ~/.claude/_gc_trash/$gc_date
mv ~/.claude/skills/dead-skill ~/.claude/_gc_trash/$gc_date/
echo "$(date -Iseconds) moved skills/dead-skill -> _gc_trash/$gc_date/ (undo: mv back)" >> ~/.claude/gc_log.md
```

Removing a confirmed-redundant permission entry (JSON has no comments — back up, log, then edit):

```bash
cp ~/.claude/settings.local.json ~/.claude/settings.local.json.bak
echo "$(date -Iseconds) removed permission entry: Bash(git push) (undo: restore from .bak or re-add)" >> ~/.claude/gc_log.md
jq '.permissions.allow -= ["Bash(git push)"]' ~/.claude/settings.local.json.bak \
  > ~/.claude/settings.local.json
```

## Anti-Patterns

- **Bulk approval.** Asking "delete all 15? [y/n]" defeats the design. One item, one decision.
- **Hard-deleting on first pass.** If there's no `_gc_trash/` copy or `.disabled` rename, you did it wrong.
- **Treating "old" as "dead".** A skill untouched for 60 days may be seasonal (tax season, quarterly reviews). Age is a signal, not a verdict — that's why a human confirms.
- **Cleaning memory by truncation.** Merging two contradicting memory files requires reading both and keeping the newer truth, not deleting the longer one.
- **Touching anything outside `~/.claude`** (or the project's `.claude/`). Config GC never wanders into source trees.

## Best Practices

- Run after big additions, not just on a calendar: installing a 50-skill pack is exactly when overlap with existing skills appears.
- When two skills overlap, prefer disabling the one with the weaker trigger description — it's the one that was probably never firing anyway.
- Permission cleanup is the highest-value channel per minute spent: redundant allow-entries make security review harder.
- Keep `gc_log.md` forever. It's tiny, and "when did I disable that hook and why" comes up more often than you'd think.

## Related Skills

- `fewer-permission-prompts` — the additive counterpart for the permissions channel: it grants, config-gc prunes.
- `audit-knowledge-drift` — audits doc/memory _accuracy_; config-gc audits _existence_. Run it on what survives GC.
- `context-budget` — audits the _context cost_ of what remains loaded; config-gc decides what exists at all.

## Provenance

Vendored from [affaan-m/ecc](https://github.com/affaan-m/ecc) (MIT) on 2026-07-17; maintained locally since — Related Skills rewritten to point at this setup's counterparts.
