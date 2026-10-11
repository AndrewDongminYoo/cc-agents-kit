import { atom, read, update } from "claude-code";
import type { Register, SessionMessage } from "claude-code";

import type { ContextReading } from "../types";

// Why this mod exists: a turn that calls the advisor runs several API
// iterations, and the harness sums their input tokens into one usage record,
// so the status line's percentage reads about twice the real context for that
// turn. One such sample at 51% read as 103% and fired an auto-compact that
// ended the session (memory: advisor-turns-double-count-context). The advisor
// is a server tool: no tool.call, tool.check or classic PreToolUse hook runs
// for it, so it cannot be blocked. It runs inside one API request, so that
// request's usage is itself the sum of the message iterations around it
// (2026-10-07: 593,788 = 294,371 + 299,417). turn.step does not carry the
// iterations, so a request with server tools is read as an estimate. An
// average would run low when an iteration grows the prompt, so the estimate
// is an upper bound on the last iteration instead: the window only grows, so
// the previous request's floor (its measured fill, or for an estimate the
// fill it certainly reached) is no larger than any iteration here, and the
// last one is at most the sum less that floor for every other iteration.
// With no previous reading the sum stands, and nothing is vetoed.
// An estimate is never used to nudge.

const PLUGIN = "context-meter";

/** Below this real reading an auto-compact is a false alarm worth vetoing. */
const SAFE_PERCENT = 70;
/** ...but only when the harness reads at least this much higher. */
const GAP_PERCENT = 20;
/** The handoff-first policy's threshold (handoff-due-nudge.sh used 80). */
const NUDGE_PERCENT = 80;
/** The band stays quiet below this real reading unless the gap shows. */
const SHOW_PERCENT = 50;
/** Characters per token, low on purpose: an overestimate lets a compaction through. */
const CHARS_PER_TOKEN = 3;

/**
 * Tokens the conversation gained after the request a reading came from: that
 * request's own answer and every message after it. A reading is one request
 * old, so a large tool result since then is not in it.
 */
function tokensSince(messages: readonly SessionMessage[]): number {
  let start = messages.length;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i]?.role === "assistant") {
      start = i;
      break;
    }
  }
  let chars = 0;
  for (const message of messages.slice(start)) {
    chars += message.text.length;
    for (const use of message.toolUses) chars += JSON.stringify(use.input).length;
    for (const result of message.toolResults ?? []) chars += result.text.length;
  }
  return Math.ceil(chars / CHARS_PER_TOKEN);
}

// The scan that lists a module's state values needs these spelled as literals.
const reading = atom(
  { plugin: "context-meter", key: "reading" } as const,
  null,
);
const isNudged = atom(
  { plugin: "context-meter", key: "isNudged" } as const,
  false,
);
const isHidden = atom(
  { plugin: "context-meter", key: "isHidden" } as const,
  false,
);

const NUDGE_TEXT =
  "Context usage has crossed 80% of the window (handoff-first policy, measured per request by the context-meter mod). " +
  "Before working on the user's request, write a handoff to ~/.claude/handoffs/: if a handoff skill is available (the context-handoff plugin's, in FILE mode), use it; " +
  "otherwise write a self-contained Markdown file yourself with the goal, the current state, the decisions made, the open problems and the first next step. " +
  "Tell the user the file path, and recommend /clear + a fresh session (a SessionStart hook that surfaces ~/.claude/handoffs/, if one is installed, will find the file). Then continue with the user's request.";

export const register: Register = (on) => {
  let lastSkippedTurn: string | null = null;
  // A refused append leaves the nudge unsent, so it is retried on the next
  // prompt; the operator is told only once.
  let isRefusalToasted = false;

  // One reading per request, from the request's own usage, main loop only.
  on("turn.step", async function* ($, e, next) {
    const response = yield* next(e);
    if (e.agentId !== undefined || response.usage === null) return response;

    const {
      input_tokens,
      cache_read_input_tokens,
      cache_creation_input_tokens,
    } = response.usage;
    const summedTokens =
      input_tokens + cache_read_input_tokens + cache_creation_input_tokens;
    const serverTools = response.serverToolUses?.length ?? 0;
    // Every iteration here is at least the previous floor, and the last one is
    // at least their average, since each iteration's prompt holds the one before.
    const previousFloor = (await read($, reading))?.floorTokens ?? 0;
    const average = Math.round(summedTokens / (serverTools + 1));
    const tokens =
      serverTools === 0
        ? summedTokens
        : Math.max(average, summedTokens - serverTools * previousFloor);
    const floorTokens =
      serverTools === 0 ? summedTokens : Math.max(average, previousFloor);
    const { context } = await $.session.usage();
    const window = context.window;
    if (!(window > 0)) return response;

    const next_: ContextReading = {
      turnId: e.turnId,
      tokens,
      floorTokens,
      window,
      percent: Math.round((tokens / window) * 100),
      harnessPercent: context.percent ?? null,
      summedTokens,
      isEstimated: serverTools > 0,
    };
    await update($, reading, () => next_);
    try {
      // A copy the operator (or a later session) can read from disk, since
      // the band is drawn only on the operator's screen.
      await $.store.set("lastReading", next_);
    } catch {
      // Diagnostic only: a store that refuses must not cost the reading.
    }
    return response;
  });

  // Veto the auto-compact that only the double count asked for. Fail open:
  // a compaction this hook cannot judge proceeds as the engine meant it to.
  on("session.compact", { trigger: "auto" }, async ($, e, next) => {
    if (e.agentId !== undefined) return next(e);
    const real = await read($, reading);
    if (real === null) return next(e);
    const harness =
      (await $.session.usage()).context.percent ?? real.harnessPercent;
    if (harness === null) return next(e);

    const gap = harness - real.percent;
    // The window now: the reading plus what arrived after its request.
    const nowPercent = Math.round(
      ((real.tokens + tokensSince(e.messages)) / real.window) * 100,
    );
    if (nowPercent < SAFE_PERCENT && gap >= GAP_PERCENT) {
      if (lastSkippedTurn !== real.turnId) {
        lastSkippedTurn = real.turnId;
        $.ui.toast(
          `${PLUGIN}: auto-compact skipped, real context ${real.percent}% (harness read ${harness}%)`,
        );
      }
      return {
        skip: `${PLUGIN}: the last request carried ${real.percent}% of the window; the harness read ${harness}% (an advisor double count). Auto-compact skipped.`,
      };
    }
    return next(e);
  }).catch(($, e, next) => next(e));

  // A compaction that ran leaves the reading one window old: drop it, so the
  // next request measures again. A precompute keeps the window as it is.
  on("session.compact", async ($, e, next) => {
    const result = await next(e);
    if (e.agentId === undefined && e.trigger !== "precompute" && !("skip" in result)) {
      await update($, reading, () => null);
    }
    return result;
  });

  // The handoff nudge, once per session, by the real reading. The row the
  // model reads goes through session.append; the operator gets a toast.
  on("prompt.submit", async ($, e, next) => {
    const real = await read($, reading);
    if (
      real !== null &&
      !real.isEstimated &&
      real.percent >= NUDGE_PERCENT &&
      !(await read($, isNudged))
    ) {
      let isStored = false;
      try {
        // A refusal resolves to `{ deny }`; a run no plugin may shape
        // (settings hooks off, a delegated observation) throws instead.
        const appended = await $.session.append({
          message: {
            type: "user",
            content: [{ type: "text", text: NUDGE_TEXT }],
          },
        });
        isStored = appended.deny === undefined;
      } catch {
        isStored = false;
      }
      if (isStored) {
        await update($, isNudged, () => true);
        $.ui.toast(
          `${PLUGIN}: real context ${real.percent}%, handoff nudge sent to the model`,
        );
      } else if (!isRefusalToasted) {
        // The prompt still goes through; the nudge is tried again next prompt.
        isRefusalToasted = true;
        $.ui.toast(
          `${PLUGIN}: real context ${real.percent}%, run /handoff before continuing`,
        );
      }
    }
    return next(e);
  });

  // /clear empties the window; the reading and the nudge start over.
  on("session.end", async ($, e, next) => {
    if (e.reason === "clear") {
      await update($, reading, () => null);
      await update($, isNudged, () => false);
      isRefusalToasted = false;
    }
    return next(e);
  });

  on("ui.render", { component: "AbovePrompt" }, async ($, e, next) => {
    const real = await read($, reading);
    if (e.props.hasSurvey || real === null || (await read($, isHidden)))
      return next(e);

    // The figure recorded at turn.step is the harness's previous one: it takes
    // in the summed usage only after the step (2026-10-07: recorded 40 where
    // the summed request read 81). Read it live, as the compact veto does.
    const harnessPercent =
      (await $.session.usage()).context.percent ?? real.harnessPercent;
    const gap = harnessPercent === null ? 0 : harnessPercent - real.percent;
    if (real.percent < SHOW_PERCENT && gap < GAP_PERCENT) return next(e);

    const { Box, Button, Text } = $.ui.resolve(e);
    const harness =
      harnessPercent === null ? "" : ` · harness ${harnessPercent}%`;
    const flag = gap >= GAP_PERCENT ? " · inflated" : "";
    const value = real.isEstimated
      ? `ctx ~${real.percent}% est`
      : `ctx ${real.percent}% real`;

    return (
      <Box>
        <Text dimColor>
          {value}
          {harness}
          {flag}{" "}
        </Text>
        <Button
          key="hide"
          label="Hide"
          onPress={() => update($, isHidden, () => true)}
        />
      </Box>
    );
  });
};
