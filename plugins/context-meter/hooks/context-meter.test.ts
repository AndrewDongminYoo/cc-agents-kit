import { expect, mock, test } from "claude-code/testing";
import type { Engine } from "claude-code/testing";
import type {
  On,
  PromptSubmitInput,
  SessionMessage,
  TurnStepInput,
  TurnStepResult,
  TurnUsage,
} from "claude-code";

const WINDOW = 200_000;

// A compaction leaves at least one message, so every compact call carries one.
const ONE_MESSAGE: SessionMessage[] = [
  { role: "user", text: "hello", toolUses: [] },
];

/**
 * One model request as the API reports it. An advisor call runs inside the
 * request: the response carries `serverToolUses`, and its top-level usage is
 * the sum of the message iterations around it (measured 2026-10-07: 593,788 =
 * 294,371 + 299,417 in this config repo's session e4b943b6).
 */
type Step = { tokens: number; serverTools?: number };

function usage(tokens: number): TurnUsage {
  return {
    model: "test-model",
    input_tokens: tokens,
    output_tokens: 10,
    cache_read_input_tokens: 0,
    cache_creation_input_tokens: 0,
  };
}

function step(turnId: string, index: number): TurnStepInput {
  return { turnId, index, model: "test-model", messageCount: 1 };
}

function typed(text: string): PromptSubmitInput {
  return { text, wait: false, origin: { kind: "composer" } };
}

// The bottom of the chain: the engine's own answers, as a test supplies them.
function bottom(on: On, options: { steps: Step[]; harnessPercent: number }) {
  let calls = 0;
  on("turn.step", async function* (_$, e) {
    const one = options.steps[Math.min(calls, options.steps.length - 1)] ?? {
      tokens: 0,
    };
    calls += 1;
    const serverToolUses = Array.from(
      { length: one.serverTools ?? 0 },
      (_, i) => ({
        id: `srv-${i}`,
        name: "advisor",
        input: {},
        startedAt: 0,
        endedAt: 0,
      }),
    );
    const result: TurnStepResult = {
      turnId: e.turnId,
      index: e.index,
      answer: "",
      toolUses: [],
      ...(serverToolUses.length > 0 ? { serverToolUses } : {}),
      stopReason: "end_turn",
      usage: usage(one.tokens),
    };
    return result;
  });
  on("session.usage", () => ({
    value: {
      startedAt: 0,
      context: { window: WINDOW, percent: options.harnessPercent, tokens: 0 },
      rateLimits: [],
    },
  }));
  on("session.compact", () => ({ messages: ONE_MESSAGE }));
  on("prompt.submit", (_$, e) => ({ text: e.text }));
  mock.store(on);
}

// This build's test kit has nothing beneath session.append (a test cannot
// answer it), so the nudge is observed where the mod records it: the one
// write of isNudged to true, which the host's state store serves.
function countNudges(on: On) {
  const count = { value: 0 };
  on(
    "state.set",
    { plugin: "context-meter", key: "isNudged" },
    (_$, e, next) => {
      if (e.value === true) count.value += 1;
      return next(e);
    },
  );
  return count;
}

async function runStep($: Engine, input: TurnStepInput) {
  const stream = $.turn.step(input);
  for await (const _chunk of stream) {
    // drain
  }
  return stream.result;
}

test("reads an advisor request as one message iteration, not their sum", async ($, on) => {
  // One request whose usage sums two message iterations of 102k each. The
  // harness reads the sum (102%); the real fill is one iteration (51%).
  bottom(on, {
    steps: [{ tokens: 204_000, serverTools: 1 }],
    harnessPercent: 102,
  });
  await runStep($, step("t1", 0));

  const answer = await $.session.compact({
    trigger: "auto",
    messages: ONE_MESSAGE,
  });
  expect(answer.skip).toContain("51%");
  expect(answer.skip).toContain("102%");
});

test("vetoes an auto-compact the double count asked for", async ($, on) => {
  bottom(on, {
    steps: [{ tokens: 204_000, serverTools: 1 }],
    harnessPercent: 102,
  });
  await runStep($, step("t1", 0));

  const answer = await $.session.compact({
    trigger: "auto",
    messages: ONE_MESSAGE,
  });
  expect(answer.skip).toContain("Auto-compact skipped");
});

test("lets an honest auto-compact proceed", async ($, on) => {
  bottom(on, { steps: [{ tokens: 170_000 }], harnessPercent: 85 });
  await runStep($, step("t1", 0));

  const answer = await $.session.compact({
    trigger: "auto",
    messages: ONE_MESSAGE,
  });
  expect(answer.skip).toBeUndefined();
});

test("lets an auto-compact proceed before any request was measured", async ($, on) => {
  bottom(on, { steps: [{ tokens: 0 }], harnessPercent: 101 });

  const answer = await $.session.compact({
    trigger: "auto",
    messages: ONE_MESSAGE,
  });
  expect(answer.skip).toBeUndefined();
});

test("lets a manual compact proceed whatever the readings say", async ($, on) => {
  bottom(on, {
    steps: [{ tokens: 204_000, serverTools: 1 }],
    harnessPercent: 102,
  });
  await runStep($, step("t1", 0));

  const answer = await $.session.compact({
    trigger: "manual",
    messages: ONE_MESSAGE,
  });
  expect(answer.skip).toBeUndefined();
});

test("sends the handoff nudge once at a measured 80% of the window", async ($, on) => {
  bottom(on, { steps: [{ tokens: 164_000 }], harnessPercent: 82 });
  const nudges = countNudges(on);
  await runStep($, step("t1", 0));

  const first = await $.prompt.submit(typed("first prompt past the line"));
  const second = await $.prompt.submit(typed("second prompt past the line"));
  expect(first.text).toBe("first prompt past the line");
  expect(second.text).toBe("second prompt past the line");
  expect(nudges.value).toBe(1);
});

test("never nudges on an estimated reading", async ($, on) => {
  // An advisor request summing two 164k iterations: the estimate is 82%, but
  // an estimate is not a measurement, and the shell hook it replaces also
  // skipped multi-iteration samples.
  bottom(on, {
    steps: [{ tokens: 328_000, serverTools: 1 }],
    harnessPercent: 164,
  });
  const nudges = countNudges(on);
  await runStep($, step("t1", 0));

  await $.prompt.submit(typed("a prompt after an advisor turn"));
  expect(nudges.value).toBe(0);
});

test("stays quiet below 80% of the window", async ($, on) => {
  bottom(on, { steps: [{ tokens: 100_000 }], harnessPercent: 50 });
  const nudges = countNudges(on);
  await runStep($, step("t1", 0));

  const entered = await $.prompt.submit(typed("a prompt well under the line"));
  expect(entered.text).toBe("a prompt well under the line");
  expect(nudges.value).toBe(0);
});
