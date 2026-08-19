#!/usr/bin/env node
// Render a Claude Code session .jsonl transcript as readable markdown.
// Usage: node session-to-md.mjs [sessionIdOrJsonlPath] [--out <file|dir>] [--tools collapsed|none|full] [--thinking] [--list] [--last N]
// Defaults: latest session of the project for $PWD, tools collapsed, thinking omitted, output to ~/Downloads.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const RESULT_LIMIT = 1200; // chars kept per tool result in collapsed mode
const INPUT_VALUE_LIMIT = 400; // chars kept per tool-input string value

function mungeCwd(p) {
  return p.replace(/[^A-Za-z0-9]/g, "-");
}

function projectDir() {
  // Transcripts live under the active config dir, which CLAUDE_CONFIG_DIR may
  // move off $HOME. Falling back to ~/.claude reads a stale directory there.
  return path.join(
    process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), ".claude"),
    "projects",
    mungeCwd(process.cwd()),
  );
}

function listSessions(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith(".jsonl"))
    .map((f) => {
      const full = path.join(dir, f);
      const st = fs.statSync(full);
      return {
        file: full,
        id: f.replace(/\.jsonl$/, ""),
        mtime: st.mtime,
        size: st.size,
      };
    })
    .sort((a, b) => b.mtime - a.mtime);
}

function parseArgs(argv) {
  const args = {
    tools: "collapsed",
    thinking: false,
    list: false,
    last: 1,
    out: null,
    target: null,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--out") args.out = argv[++i];
    else if (a === "--tools") args.tools = argv[++i];
    else if (a === "--thinking") args.thinking = true;
    else if (a === "--list") args.list = true;
    else if (a === "--last") args.last = parseInt(argv[++i], 10) || 1;
    else args.target = a;
  }
  return args;
}

function readEntries(file) {
  const lines = fs.readFileSync(file, "utf8").split("\n").filter(Boolean);
  const entries = [];
  for (const line of lines) {
    try {
      entries.push(JSON.parse(line));
    } catch {
      /* skip malformed line */
    }
  }
  return entries;
}

function fmtTime(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function truncate(s, limit) {
  if (typeof s !== "string" || s.length <= limit) return s;
  let cut = s.slice(0, limit);
  // Don't split a surrogate pair — a lone surrogate becomes U+FFFD on write.
  if (/[\uD800-\uDBFF]$/.test(cut)) cut = cut.slice(0, -1);
  return `${cut}\n… (+${s.length - cut.length} chars truncated)`;
}

// Tool results carry raw terminal output; ANSI CSI/OSC sequences and stray
// control chars render as mojibake in markdown viewers.
function stripAnsi(s) {
  return s
    .replace(
      /\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)?|[@-Z\\-_])/g,
      "",
    )
    .replace(/\r\n?/g, "\n")
    .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, "");
}

function stripReminders(text) {
  return text
    .replace(/<system-reminder>[\s\S]*?<\/system-reminder>/g, "")
    .replace(/<local-command-stdout>[\s\S]*?<\/local-command-stdout>/g, "")
    .replace(/^Caveat: The messages below were generated.*$/m, "")
    .trim();
}

function userTextOf(entry) {
  const c = entry.message?.content;
  if (typeof c === "string") return stripReminders(c);
  if (Array.isArray(c)) {
    const texts = c.filter((b) => b.type === "text").map((b) => b.text);
    if (texts.length) return stripReminders(texts.join("\n\n"));
  }
  return null;
}

function commandLineOf(text) {
  const name = text
    .match(/<command-name>([\s\S]*?)<\/command-name>/)?.[1]
    ?.trim();
  if (!name) return null;
  const cmdArgs = text
    .match(/<command-args>([\s\S]*?)<\/command-args>/)?.[1]
    ?.trim();
  return `\`${name}${cmdArgs ? ` ${cmdArgs}` : ""}\``;
}

function compactInput(input) {
  const shrink = (v) => {
    if (typeof v === "string") return truncate(v, INPUT_VALUE_LIMIT);
    if (Array.isArray(v)) return v.map(shrink);
    if (v && typeof v === "object")
      return Object.fromEntries(
        Object.entries(v).map(([k, x]) => [k, shrink(x)]),
      );
    return v;
  };
  return JSON.stringify(shrink(input ?? {}), null, 2);
}

function resultTextOf(block) {
  const c = block.content;
  if (typeof c === "string") return stripAnsi(c);
  if (Array.isArray(c))
    return stripAnsi(
      c
        .filter((b) => b.type === "text")
        .map((b) => b.text)
        .join("\n"),
    );
  return "";
}

function render(entries, opts) {
  const out = [];
  let sectionRole = null; // 'user' | 'assistant'
  const openSection = (role, ts) => {
    if (sectionRole === role) return;
    sectionRole = role;
    const head = role === "user" ? "## 👤 User" : "## 🤖 Claude";
    out.push(`${head} · ${fmtTime(ts)}`, "");
  };

  for (const e of entries) {
    if (e.isSidechain) continue;
    if (e.type === "assistant") {
      for (const block of e.message?.content ?? []) {
        if (block.type === "text" && block.text?.trim()) {
          openSection("assistant", e.timestamp);
          out.push(block.text.trim(), "");
        } else if (
          block.type === "thinking" &&
          opts.thinking &&
          block.thinking?.trim()
        ) {
          openSection("assistant", e.timestamp);
          out.push("> 💭 " + block.thinking.trim().replace(/\n/g, "\n> "), "");
        } else if (block.type === "tool_use" && opts.tools !== "none") {
          openSection("assistant", e.timestamp);
          out.push(
            `<details><summary>🔧 ${block.name}</summary>`,
            "",
            "```json",
            compactInput(block.input),
            "```",
            "",
            "</details>",
            "",
          );
        }
      }
    } else if (e.type === "user") {
      const content = e.message?.content;
      if (
        Array.isArray(content) &&
        content.some((b) => b.type === "tool_result")
      ) {
        if (opts.tools === "none") continue;
        for (const block of content.filter((b) => b.type === "tool_result")) {
          const text = resultTextOf(block).trim();
          if (!text) continue;
          const label = block.is_error ? "↳ Error" : "↳ Result";
          const body =
            opts.tools === "full" ? text : truncate(text, RESULT_LIMIT);
          out.push(
            `<details><summary>${label}</summary>`,
            "",
            body,
            "",
            "</details>",
            "",
          );
        }
        continue;
      }
      const text = userTextOf(e);
      if (!text) continue;
      openSection("user", e.timestamp);
      out.push(commandLineOf(text) ?? text, "");
    }
  }
  return out.join("\n");
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const dir = projectDir();

  if (args.list) {
    for (const s of listSessions(dir)) {
      const first = readEntries(s.file).find(
        (e) => e.type === "user" && userTextOf(e),
      );
      const preview = (first ? userTextOf(first) : "")
        .split("\n")[0]
        .slice(0, 80);
      console.log(
        `${s.id}  ${fmtTime(s.mtime)}  ${(s.size / 1024).toFixed(0)}KB  ${preview}`,
      );
    }
    return;
  }

  let file = args.target;
  if (file && !file.endsWith(".jsonl")) file = path.join(dir, `${file}.jsonl`);
  if (!file) {
    const sessions = listSessions(dir);
    if (!sessions.length) {
      console.error(`No sessions found under ${dir}`);
      process.exit(1);
    }
    if (
      !Number.isInteger(args.last) ||
      args.last < 1 ||
      args.last > sessions.length
    ) {
      console.error(
        `--last must be 1..${sessions.length} (this project has ${sessions.length} sessions)`,
      );
      process.exit(1);
    }
    file = sessions[args.last - 1].file;
  }
  if (!fs.existsSync(file)) {
    console.error(`Transcript not found: ${file}`);
    process.exit(1);
  }

  const entries = readEntries(file);
  const sessionId = path.basename(file, ".jsonl");
  const aiTitle = entries
    .filter((e) => e.type === "ai-title")
    .map((e) => e.aiTitle ?? e.title ?? e.sessionTitle)
    .filter(Boolean)
    .pop();
  const firstUser = entries.find(
    (e) => e.type === "user" && !e.isSidechain && userTextOf(e),
  );
  const title =
    aiTitle ||
    (firstUser ? userTextOf(firstUser).split("\n")[0].slice(0, 80) : sessionId);
  const model =
    entries.find((e) => e.type === "assistant" && e.message?.model)?.message
      ?.model ?? "unknown";
  const times = entries
    .map((e) => e.timestamp)
    .filter(Boolean)
    .sort();

  const body = render(entries, args);
  const fm = [
    "---",
    `title: ${JSON.stringify(title)}`,
    `session: "${sessionId}"`,
    `cwd: ${JSON.stringify(firstUser?.cwd ?? process.cwd())}`,
    `model: "${model}"`,
    `create_time: "${times[0] ?? ""}"`,
    `update_time: "${times[times.length - 1] ?? ""}"`,
    `exported_at: "${new Date().toISOString()}"`,
    "---",
  ].join("\n");

  const doc = `${fm}\n\n# ${title}\n\n${body}\n`;

  let outPath = args.out;
  const slug =
    title
      .replace(/[\\/:*?"<>|]/g, "-")
      .slice(0, 60)
      .trim() || sessionId;
  // Local date, matching the section headers — a UTC slice would file
  // KST early-morning sessions under the previous day.
  const localDate = times[0] ? fmtTime(times[0]).slice(0, 10) : "session";
  const defaultName = `${localDate}-${slug}.md`;
  if (!outPath) outPath = path.join(os.homedir(), "Downloads", defaultName);
  else if (fs.existsSync(outPath) && fs.statSync(outPath).isDirectory())
    outPath = path.join(outPath, defaultName);

  fs.writeFileSync(outPath, doc);
  console.log(outPath);
}

main();
