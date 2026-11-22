# context-meter

A function-hook mod for Claude Code that reads the real context fill and stops one kind of early auto-compact.

```bash
/plugin marketplace add AndrewDongminYoo/cc-agents-kit
/plugin install context-meter@cc-agents-kit
```

## The problem

A request that runs the advisor reports usage summed over more than one message iteration.
The harness then reads that turn as about twice its real context fill, and it can compact a session that is only half full.

## What the mod does

- It reads the usage of each model request and treats an advisor request as an upper-bound estimate.
- It shows the reading above the prompt after the fill passes 50%, or when the harness figure is 20 points higher than the reading.
- It answers an automatic compaction with a skip when the harness reads at least 20 points higher than the reading and the estimated fill stays below 70%.
- At a measured 80% it sends one handoff nudge. The nudge uses the `handoff` skill of the `context-handoff` plugin when that plugin is installed.

One reading supports one veto at most, so a wrong estimate delays a needed compaction by one request.
Every hook fails open: a compaction that the mod cannot judge goes ahead.

## What the plugin runs

The plugin is one TypeScript module, `hooks/register.tsx`, that Claude Code loads as a mod.
It reads request usage and compaction events inside the session, keeps its last reading in the mod's own store, and adds the handoff nudge to the session as one message.
It starts no program and makes no network request.

## Requirements

A Claude Code version with mods. The mod was tested on 2.1.292 and 2.1.296.

## More

The estimate, its assumptions and their limits are described in the [cc-agents-kit repository](https://github.com/AndrewDongminYoo/cc-agents-kit#context-meter).
Licence: Apache-2.0.
