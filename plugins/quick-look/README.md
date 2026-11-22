# quick-look

A function-hook mod for Claude Code on macOS that opens the files a session touched in Quick Look.

```bash
/plugin marketplace add AndrewDongminYoo/cc-agents-kit
/plugin install quick-look@cc-agents-kit
```

## What it does

The mod keeps the nine files that the main agent most recently read, wrote or edited, plus existing files that its answers name in backticks.

- `/ql` opens a pane that lists them with the hotkeys 1 to 9.
- `/ql <n>` previews one file from the list.
- `/ql <path>` previews any file.

The preview works in any terminal, Warp included.
It opens on the screen of the Mac that runs the session, not on a Remote Control device.
Nothing opens a window unless you ask: the model has no tool for it.

## What the plugin runs

The plugin is one TypeScript module, `hooks/register.tsx`, that Claude Code loads as a mod.
It records the paths of the files that tool calls and answers name.
For a preview it checks that the file exists and then starts `/usr/bin/qlmanage -p <file>` without a shell.
It starts no other program and makes no network request.

## Requirements

macOS, and a Claude Code version with mods. The mod was tested on 2.1.292 and 2.1.296.

## More

The source and the licence are in the [cc-agents-kit repository](https://github.com/AndrewDongminYoo/cc-agents-kit#quick-look).
Licence: Apache-2.0.
