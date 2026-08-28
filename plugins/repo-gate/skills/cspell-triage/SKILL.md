---
name: cspell-triage
description: Use when cspell reports unknown words or forbidden words in a repository, when adding entries to a cspell dictionary, or when a cspell config needs setting up, consolidating, or auditing.
metadata:
  category: code-quality
---

# cspell Triage

## Overview

An unknown word is a question about where it came from — not a word to add.

Most hits disappear before any word is written down, because the dictionaries the project's own ecosystem ships were never enabled.
Measured on a real repository: 371 unknown words fell to 233 with one `ignorePaths` entry for committed build output, then to 159 by naming six bundled dictionaries.
57% were never dictionary candidates.

## The gate — most requests are step 3 alone

Run the repo's own gate command first (`npx -y cspell .`, or whatever `grep -rn cspell .trunk/trunk.yaml package.json` says actually runs). What it reports decides how much of this skill applies:

| The run shows                                                                                  | Scope                                                        |
| ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| A handful of unknown words, and a root config exists                                           | **Step 3 only.** Dispose of the words, re-run, canary, stop. |
| Unknown words dominated by ecosystem vocabulary (`pytest` flagging in Markdown, `xcassets`, …) | Step 2, then step 3.                                         |
| No root config, several configs, or a gate command carrying scope flags the config should own  | Step 1, then onward.                                         |
| An inherited dictionary suspected of dead weight, or an explicit audit request                 | Step 4.                                                      |

A setup step you did not enter is not skipped work — it is work that was never needed.
In the basic case the whole task is four commands: run, dispose, re-run, canary.
Do not modify a working config's scan surface on the way past it.

When setup IS needed, work in this order.
Skipping to step 3 there is what produces 300-entry dictionaries full of stemmer fragments.

## Step 1 — one config, at the repo root

Only root-level config names are auto-discovered.
`.github/cspell.json` is **never** picked up on its own; trunk's linter definition lists root names only.
A config in a boilerplate or template directory is usually dead weight — find every config, then find what actually invokes cspell:

```bash
grep -rn cspell .trunk/trunk.yaml .github/workflows/ package.json Makefile 2>/dev/null
```

If a runner deliberately points at a non-root path, keep the root config authoritative and have the other one `import:` it.
Otherwise consolidate to the root and delete the orphan.

Set `useGitignore: true` while you are there — without it, ignored trees are still scanned.

**Put the scan surface in the config, never in the gate command — and only widen it when the repo has something to widen it for.**
By default cspell skips every path beginning with `.`. Whether that hides anything is one command:

```bash
git ls-files | grep '^\.'    # tracked dot-paths — what enableGlobDot would add
```

**Empty output → leave `enableGlobDot` alone and add nothing.** There is nothing to check behind the dot, so enabling it buys zero coverage and forces a `.git` ignore to exist purely to patch the setting's side effect.
Non-empty (`.github/workflows/`, `.trunk/`, dotfiles carrying prose) → those files go unchecked and a green result is scoped rather than real. Then, and only then, set `enableGlobDot` in the config (the CLI `--dot` is only its per-invocation equivalent) — and turning it on pulls in the git database, so it is always paired with a `.git` ignore:

```yaml
useGitignore: true
enableGlobDot: true # only because tracked dot-paths exist — see the ls-files check
ignorePaths:
  - .git # required exactly when enableGlobDot is on; the git database is not prose
```

The gate is then a bare `cspell .` with no arguments, and the config alone describes what gets checked.
A config that only behaves correctly under a particular set of CLI flags is an incomplete config.

## Step 2 — enable the dictionaries the stack already ships

59 dictionaries ship with cspell.
Detect from the manifest, do not hardcode:

| Present in repo                       | Add to `dictionaries:`                |
| ------------------------------------- | ------------------------------------- |
| `pubspec.yaml`                        | `dart`, `flutter`                     |
| `package.json`                        | `node`, `npm`, `typescript`           |
| `pyproject.toml` / `requirements.txt` | `python`                              |
| `Cargo.toml`                          | `rust`                                |
| `*.xcodeproj` / `Podfile`             | `swift`                               |
| `build.gradle*`                       | `java`, `kotlin`                      |
| `go.mod`                              | `golang`                              |
| `Dockerfile` / `*.tf` / k8s manifests | `docker`, `terraform`, `k8s`          |
| any repo                              | `softwareTerms`, `filetypes`, `fonts` |

They must go under the **top-level `dictionaries:` key**.
A language dictionary left to its own `languageId` activation only covers its own file types, so `pytest` still flags inside Markdown.

Verify a specific word rather than guessing:

```bash
cspell trace <word>     # shows every dictionary that has it, and where that dictionary lives
```

For a whole lint run rather than one word, `cspell-dict-report` (this plugin's `bin/`, on PATH) traces the list in one process and ranks the unenabled dictionaries by what each one *newly* covers:

```bash
cspell lint . --words-only --no-progress --no-summary | cspell-dict-report
```

Run it from the repo root so cspell discovers the real config.
The ranking is evidence, not a decision — a dictionary that clears words is still yours to reject if it does not match the stack.

## Step 3 — dispose of what remains

Each surviving word gets exactly one disposition.
Prefer the earliest one that fits.

| #   | Disposition                    | Use when                                                                                                                                                                                                                                 |
| --- | ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Fix the source**             | A genuine typo. Grep for siblings — copy-pasted comments repeat the same misspelling.                                                                                                                                                    |
| 2   | **Register the word**          | Real vocabulary, including identifiers whose meaning you can state. Repo-specific → repo dictionary; recurring across projects → shared personal dictionary.                                                                             |
| 3   | **Inline directive**           | The term appears in one file only. `<!-- cspell:words foo bar -->` keeps shared config untouched.                                                                                                                                        |
| 4   | **Scoped override or pattern** | The term is legitimate only in one kind of file, or the noise has a regular shape. An `overrides:` entry keyed to a `filename` glob carries its own `ignoreWords` / `dictionaries`; `ignoreRegExpList` / `patterns` handle shaped noise. |
| 5   | **Ignore the path**            | **Last resort.** Generated or vendored trees only: build output, lock files, minified bundles.                                                                                                                                           |

A new dictionary file must be staged in the same commit as the config that references it — a config pointing at an untracked path gives a fresh checkout a broken dictionary reference, and cspell reports that as a `Dictionary Error` rather than as a missing file.

**Do not relocate a working repo-wide `ignoreWords` into `overrides`.**
Scoping it removes the entry everywhere else, which makes the word flag in places it did not before — including inside the config file that names it — and each new flag invites another override.
Add an `overrides` entry only for a term that must stay flagged outside its one legitimate file type; leave everything else at the top level.
An entry that is simply unused gets deleted, not scoped.

Do not add `.git` to `ignorePaths` while `enableGlobDot` is off — cspell already skips dot-paths then, and the entry is dead weight; the `.git` ignore exists only as `enableGlobDot`'s mandatory pair (step 1). Never ignore the dictionary's own directory: there is no reason to stop checking your own word lists.

**Never blanket-ignore a file that carries direct human input.**
A path ignore is permanent and silent — it also stops catching real typos in that file forever.

**An identifier you can name is vocabulary, not noise.**
An Apple Team ID, a project ref, a product name belong in the dictionary as semantic units.
Prefer the full identifier over the fragment cspell reports — it is self-documenting for the next reader.

**Write the entry exactly as it appears in the source.**
Matching is case-insensitive by default — `WCONDITIONAL`, `Wconditional`, and `wconditional` as dictionary entries all cover all three spellings — so normalising the case buys nothing and costs the reader the meaning.
`Wconditional` reads as the compiler flag it is; `wconditional` does not. `393JTTV68D` is recognisable as a Team ID; `393jttv68d` is not.

Lowercase only when the term genuinely occurs in several casings in the repo (`Unmute`, `UNMUTE`, `unmute`).
There, picking one form would misrepresent the source, and the lowercase entry says "any casing" honestly.

**Keep the file a flat list, sorted case-insensitively, with no section headings.**
The editor's "add to dictionary" action re-sorts the whole file, so category groupings and their comments are destroyed the first time anyone uses it — and a layout only an agent maintains will not survive collaboration.
If you want the file to stay hand-curated, set `addWords: false` so the editor writes elsewhere instead.

### Worked example — why `*.xcodeproj` should stay checked

A real `project.pbxproj` looks unusable at first: 39 unknown words.
It is not.

| Step                                                                    | Unknown words |
| ----------------------------------------------------------------------- | ------------- |
| No dictionaries enabled                                                 | 39            |
| After step 2 (`swift`, `flutter`, `dart`, `softwareTerms`, `filetypes`) | 22            |

The 22 split into 18 Xcode build-setting terms identical in every iOS project (`xcassets`, `appex`, `SRCROOT`, `INFOPLIST`, `iphoneos`, `wholemodule`, …) → shared dictionary; and 4 project-specific (product name, team ID, plugin names) → repo dictionary.
The 24-character hex object IDs that fill the file are never flagged at all.

Blanket-ignoring the bundle would have hidden all of it, including any future typo in a product name or bundle identifier.

## Step 4 — prune a dictionary you inherited

Dictionaries get copied between projects and then never shrink.
Measured across five repositories, **37–74% of entries were dead** — matching nothing in the repo — while dozens of words those repos actually needed were missing from the same file.
The worst case had 86 entries of which 73 were byte-identical to an unrelated project's dictionary, 64 were dead, and exactly 3 needed words were absent.

A dictionary that overlaps heavily with an unrelated project's was copied, not earned; `comm -12` between the two files shows it in one command.

To find the live set, feed the dictionary to `cspell-dict-report --exclude <its name>`.
That reports as if the file were not configured, without editing anything: the covered section is what something else already has — delete those entries — and the in-no-dictionary section is what the file is actually carrying its weight for.

```bash
cspell-dict-report --exclude custom-dictionary < .cspell/custom-dictionary.txt
```

That reads the dictionary against itself, which finds dead-by-redundancy entries but not dead-by-nothing-uses-them ones.
For those, **edit the config in place on a scratch copy** — see the `-c` trap below:

1. Enable the ecosystem dictionaries from step 2.
2. Remove the local dictionary from `dictionaries:`.
3. Run cspell. The unknown words that remain are the true requirement.
4. Keep the intersection of that set with the current dictionary; delete every other entry; add what was missing.

Removing a dictionary should make the issue count **rise**.
If it does not move at all, the config you edited is not the one being used.

## Forbidden words

Imported style dictionaries (e.g. Very Good Ventures') mark words forbidden.
Some are misclassified for a given stack — `meta-data` is flagged prose but is valid `AndroidManifest.xml` syntax.

**`ignoreWords` clears a forbidden word.
`words` does not.** Adding it to `words:` is the reflex and it leaves the run failing.

```yaml
ignoreWords:
  - meta-data # valid AndroidManifest.xml element, flagged by the imported style dictionary
```

Scope it to where the syntax is legitimate rather than repo-wide:

```yaml
overrides:
  - filename: "**/AndroidManifest.xml"
    ignoreWords:
      - meta-data
```

The same split applies to inline directives, which is easy to get wrong:

| Directive                              | Clears unknown | Clears forbidden |
| -------------------------------------- | -------------- | ---------------- |
| `cspell:words`                         | yes            | **no**           |
| `cspell:ignore` / `cspell:ignoreWords` | yes            | yes              |

## Common mistakes

- **Widening a working config's scan surface as a side quest.**
  A word-triage request on a repo with no tracked dot-paths does not need `enableGlobDot`, and enabling it there forces a `.git` ignore into existence purely to patch the setting's own side effect (observed twice by the operator, 2026-08-12). The gate at the top routes this case to step 3 alone.
- **`-c` does not replace the repo's own config — it merges with it.**
  Running `cspell -c probe.json .` inside a repo that has `cspell.json` still loads that `cspell.json`, dictionaries and all.
  A/B tests built on `-c` therefore show no difference and read as "the dictionary contributes nothing."
  To test a config change, edit the real config in place on a scratch copy of the repo.
- **`ignorePaths` globs resolve relative to the config file's directory**, not the working directory — the schema says they are relative to that config's `globRoot`, which defaults to where the config lives.
  A config passed with `--config` from elsewhere silently matches nothing and the hit count does not move — which reads exactly like "the ignore did not help."
- **Listing an override's words inline makes them unknown words in the config file itself.**
  The override scopes them to its glob, so everywhere else — including the config that names them — they now flag, and each new flag invites another override.
  Once an override needs more than a couple of words, put them in their own dictionary file and reference it with `dictionaries:`, adding that file to the override's `filename` globs so it covers itself.
- **Declaring the gate green from a scoped run.**
  Run the same command the gate runs, then break it once before trusting the pass.
  Inject the canary typo into a file you are **already** editing.
  Preserve its pre-existing working-tree diff before the change, then remove only the injected typo with the same editor used for the change.

  ```bash
  canary_before=$(mktemp)
  canary_after=$(mktemp)
  git ls-files --error-unmatch -- <file> >/dev/null
  git diff -- <file> > "$canary_before"
  # Run the repository cspell gate and require it to pass before injection.
  # Add one unique temporary typo, then run the same gate.
  # Require the gate to fail and report the exact canary token.
  # Remove only that typo.
  git diff -- <file> > "$canary_after"
  cmp -s "$canary_before" "$canary_after"
  ```

  The canary file must already be tracked.
  Stop if `git ls-files --error-unmatch` fails.
  The unmodified cspell gate must pass before canary injection.
  After injection, the same gate must fail and its output must name the exact canary token.
  If `cmp` fails, restore the pre-existing diff manually before continuing.
  Never create or delete a file in a source directory to test a spell checker — in a Flutter repo, `lib/main.dart` is the conventional entry point, so both creating and removing it carry meaning far beyond this task, and `rm` in a tracked tree is not a scratch operation.
- **Adding tokenization fragments.**
  `abli`, `alism`, `aliti`, `singl`, `failur` are stemmer output from a committed search index.
  They mean a generated tree is being scanned — that is disposition 5, not 200 dictionary entries.
- **Trusting a truncated word list.**
  `cspell --words-only --unique` piped to `head` under-reports; quote `wc -l` from the full run.

## Reference

`references/mechanisms.md` — verified behaviour of remote dictionaries, shareable dictionary packaging (`cspell-ext.json`), trunk's cspell sandbox, and editor-vs-CLI config divergence.
