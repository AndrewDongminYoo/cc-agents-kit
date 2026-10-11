import { expect, mock, test } from "claude-code/testing";
import type { Engine } from "claude-code/testing";
import type { On, PromptOrigin } from "claude-code";

const CWD = "/repo";
const FILES = new Set([
  "/repo/docs/plan.md",
  "/repo/src/app.ts",
  "/repo/assets/icon.png",
  "/Users/me/notes/today.md",
]);
const ORIGIN: PromptOrigin = { kind: "composer" };
const PRESENTATION = { isFullscreen: true, columns: 160 };

// The world beneath the plugin: a small file system, the session's directory,
// HOME, and a process.spawn that records the argv instead of running anything.
function bottom(on: On) {
  const spawned: string[][] = [];
  const recent: { value: string[] } = { value: [] };
  // The test's $ has no state noun: the list is read where the mod writes it.
  on("state.set", { plugin: "quick-look", key: "recent" }, (_$, e, next) => {
    recent.value = [...(e.value as string[])];
    return next(e);
  });
  on("ui.toast", () => ({ value: undefined }) as never);
  on("fs.exists", (_$, e) => ({ value: FILES.has(e.path) }));
  on("fs.stat", (_$, e) => ({
    value: {
      kind: FILES.has(e.path) ? "file" : "other",
      size: 1,
      mtimeMs: 0,
      isLink: false,
    },
  }));
  on("session.cwd", () => ({ value: CWD }));
  mock.env(on, { HOME: "/Users/me" });
  on("process.spawn", async function* (_$, e) {
    spawned.push([...e.argv]);
    return { value: { code: 0, signal: null } } as never;
  });
  on("tool.call", () => ({ result: { type: "text" } }) as never);
  on("turn.complete", (_$, e) => ({ text: e.answer }));
  on("ui.open", () => ({ value: undefined }) as never);
  return { spawned, recent };
}

async function ql($: Engine, args: string) {
  return $.command.run({
    command: "ql",
    args,
    origin: ORIGIN,
    presentation: PRESENTATION,
  });
}

async function answer($: Engine, text: string) {
  return $.turn.complete({
    reason: "answer",
    answer: text,
    durationMs: 1,
    isAborted: false,
    turnId: "t1",
  } as never);
}

test("records files the agent reads and writes, newest first", async ($, on) => {
  const { recent } = bottom(on);
  await $.tool.call({ tool: "Read", file_path: "/repo/src/app.ts" } as never);
  await $.tool.call({
    tool: "Write",
    file_path: "/repo/docs/plan.md",
    content: "x",
  } as never);

  expect(recent.value).toEqual(["/repo/docs/plan.md", "/repo/src/app.ts"]);
});

test("records backticked paths the answer names, only when they exist", async ($, on) => {
  const { recent } = bottom(on);
  await answer(
    $,
    "See `docs/plan.md`, `~/notes/today.md` and `assets/icon.png:12`; `missing/file.md` and `npm test` are not files.",
  );

  expect(recent.value).toEqual([
    "/repo/docs/plan.md",
    "/Users/me/notes/today.md",
    "/repo/assets/icon.png",
  ]);
});

test("/ql <n> opens that file in Quick Look by argv, no shell", async ($, on) => {
  const { spawned } = bottom(on);
  await $.tool.call({ tool: "Read", file_path: "/repo/src/app.ts" } as never);
  await $.tool.call({ tool: "Read", file_path: "/repo/docs/plan.md" } as never);

  const out = await ql($, "2");
  expect(out.text).toBe("Quick Look opened /repo/src/app.ts");
  expect(spawned).toEqual([["/usr/bin/qlmanage", "-p", "/repo/src/app.ts"]]);
});

test("/ql <path> resolves against the session directory", async ($, on) => {
  const { spawned } = bottom(on);

  await ql($, "docs/plan.md");
  expect(spawned).toEqual([["/usr/bin/qlmanage", "-p", "/repo/docs/plan.md"]]);
});

test("/ql refuses a file that does not exist and runs nothing", async ($, on) => {
  const { spawned } = bottom(on);

  const out = await ql($, "/etc/nope.md");
  expect(out.text).toContain("no such file");
  expect(spawned).toEqual([]);
});

test("/ql with no argument opens the pane and reports the count", async ($, on) => {
  bottom(on);
  await $.tool.call({ tool: "Read", file_path: "/repo/src/app.ts" } as never);

  const out = await ql($, "");
  expect(out.text).toBe("1 file(s) listed.");
});
