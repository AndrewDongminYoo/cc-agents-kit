# reply-language

**Temporary.** A workaround for [anthropics/claude-code#99704](https://github.com/anthropics/claude-code/issues/99704): a model writes user-facing text in English although the `language` setting names another language.
Uninstall the plugin after that issue is fixed.

```bash
/plugin marketplace add AndrewDongminYoo/cc-agents-kit
/plugin install reply-language@cc-agents-kit
```

## What it does

The plugin reads the target language from the `language` setting or from `CC_REPLY_LANGUAGE`, and does nothing when neither is set.
It supports languages that have a script of their own: Korean, Japanese, Chinese, Russian and other Cyrillic, Persian, Arabic, Urdu, Hindi, Thai, Greek and Hebrew.
A Latin-script language cannot be told apart from English by script, so the plugin leaves it alone.

| Hook                         | Event                         | What it does                                                                                 |
| ---------------------------- | ----------------------------- | -------------------------------------------------------------------------------------------- |
| `reply-language-reminder.sh` | UserPromptSubmit, PostToolUse | Adds a one-line reminder of the language rule.                                               |
| `reply-language-ask.sh`      | PreToolUse, `AskUserQuestion` | Refuses a question dialog written in English and asks for it in the target language.         |
| `reply-language-check.sh`    | Stop                          | Blocks the stop one time when the response drifted into English, and asks for a restatement. |

To limit the hooks to the models that drift, set `CC_REPLY_LANGUAGE_MODELS` to a comma-separated list of model ID substrings.

## What the plugin runs

Three Bash scripts that call `python3` to count the letters of the target script.
They read the hook input, the settings files that hold `language`, and the session transcript.
They write no file and make no network request.

## Requirements and opt-outs

`bash` and `python3`. Each hook fails open without `python3`.
Each hook has an opt-out variable: `CC_GUARD_DISABLE_REPLY_LANGUAGE_REMINDER=1`, `CC_GUARD_DISABLE_REPLY_LANGUAGE_ASK=1` and `CC_GUARD_DISABLE_REPLY_LANGUAGE_CHECK=1`.

## More

The thresholds, the cases the check stays silent for, and the replay measurements are in the [cc-agents-kit repository](https://github.com/AndrewDongminYoo/cc-agents-kit#reply-language).
Licence: Apache-2.0.
