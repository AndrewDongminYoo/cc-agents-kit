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
type Step = { tokens: number; serverTools?: number; isCutShort?: boolean };

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
        ...(one.isCutShort === true ? {} : { endedAt: 0 }),
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

test("reads an advisor request as its last iteration, not the sum", async ($, on) => {
  // A 100k request, then one whose usage sums two iterations of about 102k.
  // The harness reads the sum (102%); the last iteration is at most the sum
  // less the previous reading for the other iteration: 104k, 52%.
  bottom(on, {
    steps: [{ tokens: 100_000 }, { tokens: 204_000, serverTools: 1 }],
    harnessPercent: 102,
  });
  await runStep($, step("t1", 0));
  await runStep($, step("t1", 1));

  const answer = await $.session.compact({
    trigger: "auto",
    messages: ONE_MESSAGE,
  });
  expect(answer.skip).toContain("52%");
  expect(answer.skip).toContain("102%");
});

test("lets an auto-compact through when an advisor iteration grew the prompt", async ($, on) => {
  // Iterations of 100k and 160k after a 95k request: an average (130k, 65%)
  // would veto, but the last iteration may be up to 165k, 83% of the window.
  bottom(on, {
    steps: [{ tokens: 95_000 }, { tokens: 260_000, serverTools: 1 }],
    harnessPercent: 130,
  });
  await runStep($, step("t1", 0));
  await runStep($, step("t1", 1));

  const answer = await $.session.compact({
    trigger: "auto",
    messages: ONE_MESSAGE,
  });
  expect(answer.skip).toBeUndefined();
});

test("bounds a second advisor request by the first one's floor, not its estimate", async ($, on) => {
  // 102k + 102k with no earlier reading (estimate 204k, floor 102k), then
  // 102k + 170k: the last iteration may be up to 170k, 85% of the window.
  bottom(on, {
    steps: [
      { tokens: 204_000, serverTools: 1 },
      { tokens: 272_000, serverTools: 1 },
    ],
    harnessPercent: 136,
  });
  await runStep($, step("t1", 0));
  await runStep($, step("t1", 1));

  const answer = await $.session.compact({
    trigger: "auto",
    messages: ONE_MESSAGE,
  });
  expect(answer.skip).toBeUndefined();
});

test("subtracts the floor once when server calls ran in parallel", async ($, on) => {
  // Two parallel calls share one iteration: 100k and 160k after a 95k
  // request. Subtracting the floor per call would read 87k; once gives 165k.
  bottom(on, {
    steps: [{ tokens: 95_000 }, { tokens: 260_000, serverTools: 2 }],
    harnessPercent: 130,
  });
  await runStep($, step("t1", 0));
  await runStep($, step("t1", 1));

  const answer = await $.session.compact({ trigger: "auto", messages: ONE_MESSAGE });
  expect(answer.skip).toBeUndefined();
});

test("reads a request whose advisor call was cut short as measured", async ($, on) => {
  // The stream ended before the advisor answered: one iteration of 170k, not
  // two, so the window is at 85% and the compaction goes ahead.
  bottom(on, {
    steps: [
      { tokens: 160_000 },
      { tokens: 170_000, serverTools: 1, isCutShort: true },
    ],
    harnessPercent: 85,
  });
  await runStep($, step("t1", 0));
  await runStep($, step("t1", 1));

  const answer = await $.session.compact({ trigger: "auto", messages: ONE_MESSAGE });
  expect(answer.skip).toBeUndefined();
});

test("does not veto from an advisor request with no earlier reading", async ($, on) => {
  bottom(on, {
    steps: [{ tokens: 204_000, serverTools: 1 }],
    harnessPercent: 102,
  });
  await runStep($, step("t1", 0));

  const answer = await $.session.compact({
    trigger: "auto",
    messages: ONE_MESSAGE,
  });
  expect(answer.skip).toBeUndefined();
});

test("vetoes an auto-compact the double count asked for", async ($, on) => {
  bottom(on, {
    steps: [{ tokens: 100_000 }, { tokens: 204_000, serverTools: 1 }],
    harnessPercent: 102,
  });
  await runStep($, step("t1", 0));
  await runStep($, step("t1", 1));

  const answer = await $.session.compact({
    trigger: "auto",
    messages: ONE_MESSAGE,
  });
  expect(answer.skip).toContain("Auto-compact skipped");
});

test("lets an auto-compact through when a large result arrived after the advisor request", async ($, on) => {
  // The advisor request measured 52%, but a 180,000-character tool result came
  // back after it: about 60k more tokens, so the window is now past 70%.
  bottom(on, {
    steps: [{ tokens: 100_000 }, { tokens: 204_000, serverTools: 1 }],
    harnessPercent: 102,
  });
  await runStep($, step("t1", 0));
  await runStep($, step("t1", 1));

  const messages: SessionMessage[] = [
    { role: "assistant", text: "Reading the log.", toolUses: [] },
    {
      role: "user",
      text: "",
      toolUses: [],
      toolResults: [
        {
          tool_use_id: "r1",
          text: "x".repeat(180_000),
          isError: false,
        } as never,
      ],
    },
  ];
  const answer = await $.session.compact({ trigger: "auto", messages });
  expect(answer.skip).toBeUndefined();
});

test("counts a Korean tool result by its bytes, not as ASCII", async ($, on) => {
  // 15,000 Hangul syllables are 45,000 UTF-8 bytes. A three-characters-per-
  // token guess (5k) would keep the window at 55% and veto; the byte bound
  // (45k) puts it at 75%, so the compaction goes ahead.
  bottom(on, {
    steps: [{ tokens: 100_000 }, { tokens: 204_000, serverTools: 1 }],
    harnessPercent: 102,
  });
  await runStep($, step("t1", 0));
  await runStep($, step("t1", 1));

  const messages: SessionMessage[] = [
    { role: "assistant", text: "로그를 읽습니다.", toolUses: [] },
    {
      role: "user",
      text: "",
      toolUses: [],
      toolResults: [
        { tool_use_id: "r1", text: "가".repeat(15_000), isError: false } as never,
      ],
    },
  ];
  const answer = await $.session.compact({ trigger: "auto", messages });
  expect(answer.skip).toBeUndefined();
});

test("a compaction that ran drops the reading, so the next prompt does not nudge", async ($, on) => {
  bottom(on, { steps: [{ tokens: 164_000 }], harnessPercent: 82 });
  const nudges = countNudges(on);
  await runStep($, step("t1", 0));

  await $.session.compact({ trigger: "manual", messages: ONE_MESSAGE });
  await $.prompt.submit(typed("a prompt after /compact"));
  expect(nudges.value).toBe(0);
});

test("vetoes once per reading, so a wrong estimate delays a compaction by one request at most", async ($, on) => {
  bottom(on, {
    steps: [{ tokens: 100_000 }, { tokens: 204_000, serverTools: 1 }],
    harnessPercent: 102,
  });
  await runStep($, step("t1", 0));
  await runStep($, step("t1", 1));

  const first = await $.session.compact({ trigger: "auto", messages: ONE_MESSAGE });
  const second = await $.session.compact({ trigger: "auto", messages: ONE_MESSAGE });
  expect(first.skip).toContain("Auto-compact skipped");
  expect(second.skip).toBeUndefined();
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
    steps: [{ tokens: 100_000 }, { tokens: 204_000, serverTools: 1 }],
    harnessPercent: 102,
  });
  await runStep($, step("t1", 0));
  await runStep($, step("t1", 1));

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

test("retries the nudge on the next prompt when the append was refused", async ($, on) => {
  const appends = { tried: 0, stored: 0 };
  // A refusal resolves to `{ deny }`; next(e) reaches the kit's own store.
  on("session.append", (_$, e, next) => {
    appends.tried += 1;
    if (appends.tried === 1) return { deny: "refused for the test" };
    appends.stored += 1;
    return next(e);
  });
  bottom(on, { steps: [{ tokens: 164_000 }], harnessPercent: 82 });
  await runStep($, step("t1", 0));

  await $.prompt.submit(typed("first prompt, append refused"));
  await $.prompt.submit(typed("second prompt, append stored"));
  await $.prompt.submit(typed("third prompt, already nudged"));
  expect(appends.tried).toBe(2);
  expect(appends.stored).toBe(1);
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
