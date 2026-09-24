# Session Export Reading Defaults Plan

## Steps

1. Add synthetic regression cases in `plugins/context-handoff/bin/session-to-md.test.py` for the default and `--toc` outputs.
   Verify that the new cases fail against the previous implementation.
2. Update `plugins/context-handoff/bin/session-to-md` and the session-export HTML template so navigation appears only with `--toc`.
   Verify the script suite and check synthetic HTML controls in a browser.
3. Update the session-export skill instructions to match the CLI.
   Verify with skill validation, `node --check`, and `git diff --check`.

## Completion Check

Run `python3 -B plugins/context-handoff/bin/session-to-md.test.py` and confirm the default and opt-in outputs from synthetic records.
