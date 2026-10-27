import { atom, read, update } from "claude-code";
import type { EngineInterface, Register } from "claude-code";

// Quick Look for the files the agent works with, in any terminal. Warp draws
// no inline picture the engine's Image element can rely on (its types name
// kitty and Ghostty), so the preview is macOS's own Quick Look panel, opened
// with `qlmanage -p`. The panel opens on this Mac's screen, not on a remote
// viewer's. Nothing here opens a window unless the person asks: /ql or a press.

const PANE = "quick-look";
const QLMANAGE = "/usr/bin/qlmanage";
/** One hotkey digit per entry, 1 to 9. */
const LIMIT = 9;
/** Paths taken from one answer, at most. */
const PER_ANSWER = 5;

const recent = atom({ plugin: "quick-look", key: "recent" } as const, []);

/**
 * A whole backtick span on one line. Spaces and non-ASCII names are common on
 * macOS, so the file system, not a character class, decides what is a path.
 */
const BACKTICKED = /`([^`\n]+)`/g;
/** Longer spans are code, not a path a person would name. */
const MAX_SPAN = 1024;
/** Spans checked against the file system per answer, at most. */
const MAX_CHECKS = 40;

function remember(list: readonly string[], path: string): string[] {
  return [path, ...list.filter((one) => one !== path)].slice(0, LIMIT);
}

function basename(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1) || path;
}

function dirname(path: string): string {
  const cut = path.lastIndexOf("/");
  return cut > 0 ? path.slice(0, cut) : "/";
}

/** Resolves a path an answer named against the session's directory. */
function resolve(
  raw: string,
  cwd: string,
  home: string | undefined,
): string | null {
  const trimmed = raw.replace(/:\d+(:\d+)?$/, "");
  if (trimmed.startsWith("~/"))
    return home ? `${home}${trimmed.slice(1)}` : null;
  if (trimmed.startsWith("/")) return trimmed;
  const parts = `${cwd}/${trimmed}`.split("/");
  const out: string[] = [];
  for (const part of parts) {
    if (part === "" || part === ".") continue;
    if (part === "..") out.pop();
    else out.push(part);
  }
  return `/${out.join("/")}`;
}

async function isFile($: EngineInterface, path: string): Promise<boolean> {
  try {
    if (!(await $.fs.exists(path))) return false;
    return (await $.fs.stat(path)).kind === "file";
  } catch {
    return false;
  }
}

// The panel left open by the last preview; the next preview replaces it.
let current: AsyncGenerator<unknown, unknown> | null = null;

async function preview($: EngineInterface, path: string): Promise<string> {
  if (!(await isFile($, path))) return `quick-look: no such file: ${path}`;
  if (current !== null) {
    void current.return(undefined);
    current = null;
  }
  const stream = $.process.spawn({ argv: [QLMANAGE, "-p", path] });
  current = stream;
  void (async () => {
    try {
      // qlmanage prints a line or two; the panel's life is the loop's.
      let step = await stream.next();
      while (step.done !== true) step = await stream.next();
      const { code } = step.value;
      if (current === stream && code !== null && code !== 0)
        $.ui.toast(`quick-look: qlmanage exited ${code} for ${basename(path)}`);
    } catch {
      // A replaced panel ends without throwing, so this one could not start.
      if (current === stream)
        $.ui.toast(
          `quick-look: could not start Quick Look for ${basename(path)}`,
        );
    } finally {
      if (current === stream) current = null;
    }
  })();
  $.ui.toast(`Quick Look: ${basename(path)}`);
  return `Quick Look opening ${path}`;
}

export const register: Register = (on) => {
  on("session.start", async ($, e, next) => {
    await $.command.register({
      name: "ql",
      description:
        "Quick Look a file the agent touched: /ql opens the list, /ql 2 the second, /ql <path> any file",
    });
    return next(e);
  });

  // The files the agent reads or writes, once the call has succeeded.
  on("tool.call", async ($, e, next) => {
    const ran = await next(e);
    if (
      e.agentId !== undefined ||
      ran.deny !== undefined ||
      ran.isError === true
    )
      return ran;
    const path =
      e.tool === "Read" || e.tool === "Write" || e.tool === "Edit"
        ? e.file_path
        : e.tool === "NotebookEdit"
          ? e.notebook_path
          : undefined;
    if (typeof path === "string" && path.startsWith("/")) {
      await update($, recent, (list) => remember(list, path));
    }
    return ran;
  });

  // The files the agent names in its answer, in backticks, that exist.
  on("turn.complete", async ($, e, next) => {
    if (e.agentId === undefined && e.answer.length > 0) {
      const cwd = await $.session.cwd();
      const home = await $.env.get("HOME");
      const found: string[] = [];
      let checks = 0;
      for (const match of e.answer.matchAll(BACKTICKED)) {
        const raw = match[1];
        if (
          raw === undefined ||
          raw.length > MAX_SPAN ||
          raw !== raw.trim() ||
          (!raw.includes("/") && !raw.includes("."))
        )
          continue;
        const path = resolve(raw, cwd, home);
        if (path === null || found.includes(path)) continue;
        if (++checks > MAX_CHECKS) break;
        if (await isFile($, path)) found.push(path);
        if (found.length >= PER_ANSWER) break;
      }
      if (found.length > 0) {
        await update($, recent, (list) =>
          found.reduceRight((acc, path) => remember(acc, path), list),
        );
      }
    }
    return next(e);
  });

  on("command.run", { command: "ql" }, async ($, e) => {
    const arg = e.args.trim();
    const list = await read($, recent);
    if (arg === "") {
      await $.ui.open({
        id: PANE,
        title: "Quick Look",
        focus: true,
        closeOnEscape: true,
      });
      return {
        text:
          list.length === 0
            ? "No files yet."
            : `${list.length} file(s) listed.`,
      };
    }
    if (/^[1-9]$/.test(arg)) {
      const path = list[Number(arg) - 1];
      if (path === undefined)
        return { text: `quick-look: there is no file ${arg}.` };
      return { text: await preview($, path) };
    }
    const path = resolve(arg, await $.session.cwd(), await $.env.get("HOME"));
    if (path === null) return { text: `quick-look: cannot resolve ${arg}` };
    return { text: await preview($, path) };
  });

  on("ui.render", { component: "Pane", requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e);
    const list = await read($, recent);
    if (list.length === 0) {
      return (
        <Text dimColor>
          No files yet: the agent has not read, written or named one.
        </Text>
      );
    }
    return (
      <Box flexDirection="column">
        {list.map((path, i) => (
          <Box key={`row-${i}`}>
            <Button
              key={`open-${i}`}
              label={basename(path)}
              hotkey={String(i + 1)}
              plain
              onPress={() => {
                void preview($, path);
              }}
            />
            <Text dimColor wrap="truncate-start">
              {" "}
              {dirname(path)}
            </Text>
          </Box>
        ))}
      </Box>
    );
  });
};
