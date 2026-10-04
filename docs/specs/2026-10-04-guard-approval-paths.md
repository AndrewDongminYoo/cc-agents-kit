# Guard approval paths

The dotenv guard currently treats literal documentation, state inspection and
secret disclosure alike. Hard denial has no approval path, and its diagnostic
asks users for secret values. Keep real secret access blocked while providing a
small, explicitly approved way to inspect configuration state.

## Approved scope

- In auto mode only, recognize a single literal `printf` invocation as data and
  abstain. No shell expansion, redirection, pipeline, substitution or execution
  wrapper is eligible. Other guards and the harness still decide whether to run.
- Recognize only the installed plugin's absolute `bin/env-status` executable with
  exactly `--schema PATH --file PATH`. Return `ask`, never `allow`, in every mode.
- The inspector reads a bounded, strict dotenv subset beneath its working root,
  without symlink traversal or shell evaluation. Emit schema keys and boolean
  `present` / nullable boolean `empty` only. Never emit values, lengths or hashes.
- Keep direct secret reads, sourcing, writes, root/home deletion and ambiguous
  commands blocked. Missing parser support must preserve existing denial.
- Add a default-off operator policy for a few recurring purpose scripts. Bind
  recognition to exact cwd, argv and entry-script hash and request `ask`. The
  policy's keys/destinations are declarations, not runtime isolation, and the
  hash does not cover transitive dependencies. Never install a live policy here.
- Explain schema maintenance, purpose-specific environment consumption and
  task-owned temporary storage without supplying a generic secret command runner.

## Non-goals and authority

No live settings, installed hooks, credentials or real dotenv files are changed
or read. No arbitrary shell wrapper, global allow, deletion, Trash operation,
plugin update, merge or deployment. Local settings and review-mode proposals are
separate inactive artifacts, excluded from the public plugin.

## Acceptance

Synthetic regressions must distinguish abstention, ask and denial; preserve the
existing secret and destructive-command cases; reject shell syntax around the
inspector; and prove that data and errors never include fixture values. Inspector
tests cover missing/empty/present keys, duplicate keys, invalid syntax, oversized
files, path escape and symlinks. Review the whole diff for trust-boundary changes.
The recognizer and inspector must ignore project Python shims and startup code;
only a protected isolated system runtime and validated approval output are trusted.
Run the repository CI checks and observe the Draft PR's exact-head checks and
required hosted review signals. Visual approval is not applicable.
