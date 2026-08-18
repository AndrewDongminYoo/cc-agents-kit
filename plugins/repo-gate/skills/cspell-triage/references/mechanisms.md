# cspell mechanisms

Behaviour verified against cspell 10.0.1.
Re-check version-sensitive claims before relying on them.

## Editor config does not reach the CLI

The VS Code Code Spell Checker extension reads `cSpell.*` keys from user and workspace settings — `cSpell.dictionaries`, `cSpell.ignorePaths`, `cSpell.useGitignore`, `cSpell.userWords`.
**None of it reaches `cspell` on the command line, in CI, or under trunk.**

This produces a specific and confusing failure: a word never flags while editing, then flags in CI, gets hand-added to that repo's dictionary, and the cycle repeats in the next repo.
Cross-repo duplicate dictionary entries are the symptom.

`cSpell.userWords` is worth harvesting — it is a hand-curated cross-project list, and its entries that no bundled dictionary covers are the natural seed for a shared personal dictionary.
Audit it rather than copying it wholesale; accumulated lists collect real misspellings that then get whitelisted permanently.

`cspell link list` shows globally linked dictionary packages for the CLI, but a link is machine-local and never reaches CI.
Do not rely on it for anything a gate checks.

## Enabling dictionaries

Top-level `dictionaries:` enables a dictionary for every file type.
Left out of that list, a language dictionary only activates for its own `languageId`, so vocabulary that appears in prose, Makefiles, or TOML still flags.

```bash
cspell trace <word>          # which dictionaries contain it, and their on-disk paths
cspell --words-only --unique <paths>   # the raw candidate list — never pipe to head before counting
```

## Custom and shared dictionaries

A local dictionary is a plain text file, one word per line, `#` for comments:

```yaml
dictionaryDefinitions:
  - name: project-words
    path: ./.cspell/project-words.txt
    addWords: true
dictionaries:
  - project-words
```

`addWords: true` marks it as the target for "add to dictionary" actions.
That is exactly the mechanism that fills a dictionary with generated-file noise when `ignorePaths` is empty — set it deliberately, not by default.

Forbidden entries use a `!` prefix (`!behaviour`).
`ignoreWords` overrides a forbidden word; `words` does not.
The same asymmetry holds for inline directives: `cspell:words` clears an unknown word but not a forbidden one, while `cspell:ignore` and `cspell:ignoreWords` clear both.

### Sharing across repositories

| Mechanism                                         | Works without `package.json` | Works offline       | Notes                                                                                 |
| ------------------------------------------------- | ---------------------------- | ------------------- | ------------------------------------------------------------------------------------- |
| Committed file in the repo                        | yes                          | yes                 | Duplicated per repo; no single source of truth                                        |
| npm package exporting `cspell-ext.json`           | **no**                       | yes, once installed | The canonical form; unusable in Dart/Flutter/Python repos that have no `package.json` |
| Remote `https://` path in `dictionaryDefinitions` | yes                          | **no**              | Verified working; see failure mode below                                              |
| `cspell link`                                     | yes                          | yes                 | Machine-local only — never reaches CI                                                 |

For a mixed-ecosystem set of repositories, the combination that works everywhere is **bundled dictionaries enabled by name plus a small committed dictionary file**.
No network, no manifest.

A shareable dictionary package is an npm package whose `exports` point at `cspell-ext.json`:

```json
{
  "name": "@scope/dict-example",
  "exports": { ".": "./cspell-ext.json" },
  "files": ["dict/example.txt", "cspell-ext.json"]
}
```

`cspell-ext.json` may itself carry `dictionaryDefinitions`, `patterns`, `languageSettings`, and `overrides`, so a dictionary package can also ship the regex patterns its ecosystem needs.
Consumed with `import: ["@scope/dict-example/cspell-ext.json"]`.
`cspell-tools-cli build` compiles a source word list into the distributed form; a Yeoman generator (`pnpm create-dictionary`) scaffolds the layout.

Configs compose through `import:`, which accepts other config files.
That is the mechanism for "extend an existing setup" — dictionary _files_ do not extend each other, configs do.

### Remote dictionary failure mode

Remote paths resolve and work.
When one is unreachable, cspell prints `Dictionary Error with (<name>) FetchUrlError: URL not found.` and exits 1 — **above** the issue list, so it reads as an ordinary failure in CI logs.

The asymmetry matters: for an _allowed_-words dictionary the run fails loudly, but a _forbidden_-words dictionary that fails to load silently stops enforcing anything the run would otherwise catch.
Weigh that before making a gate depend on a remote URL.

## Identifier tokenization

cspell splits alphanumeric identifiers on digit boundaries: `393JTTV68D` is reported as the token `JTTV`.
Either the token or the full identifier in `words:` resolves it, so prefer the full identifier for self-documentation.
Bracket syntax in ignore files produces similar fragments — `[Dd]esktop.ini` yields `esktop`.

## Trunk integration

Trunk's cspell linter definition:

- `files: [ALL]` — every file is a target.
- `run: cspell --no-progress --no-summary --show-suggestions --no-cache ${target}`.
  `--no-cache` means remote dictionaries are refetched on every run.
- `sandbox_type: copy_targets`, with the upstream note _"cspell doesn't read symlinked config files, so we must create a copied sandbox."_
  Files are copied under the system temp directory; on a full root volume this surfaces as a wrapped linter crash mentioning `No space left on device` rather than an obviously disk-related error.
- `direct_configs` lists root-level config filenames only.
  `.github/cspell.json` and other non-root paths are never auto-discovered.
- `known_good_version` may lag the version a repo pins; behaviour differences between cspell majors are real, so check the pinned version before reproducing a trunk finding locally.

Enabling cspell in trunk requires it in `lint.enabled`.
A repo can carry a full cspell config that no gate runs while the editor extension still checks it — local-clean then does not imply CI-clean.
