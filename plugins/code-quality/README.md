# code-quality

A deterministic complexity and code-smell gate for Python, JavaScript and TypeScript. The same measurements run for Claude after every edit, for people at the command line, and in CI, so "good enough" means the same thing everywhere.

| Check | Tool | When |
|---|---|---|
| Cyclomatic and cognitive complexity, function length, parameters (per function) | lizard | every edit, `check` |
| Nesting depth, complex conditions, bumpy road (CodeScene's Nested Complexity, Complex Conditional and Bumpy Road; per function) | tree-sitter (`qg_smells.py`) | every edit, `check` |
| File length | built in | every edit, `check` |
| Lint and smells (project's config + bugbear, simplify, comprehensions, pyupgrade) | ruff, biome | every edit, `check` |
| Type errors | the package's mypy if configured, else pyright; the package's tsc | `check --full` (CI) |
| Duplicated code (reported in each file that holds a copy; it costs the function 5 points, like a lint finding) | jscpd | every edit, `check`; skipped if the scan takes over 60 s. Set `duplication = false` under `[edit]` to turn it off |

Each function gets a score from 0 to 100%, set by its worst metric (95% exactly at a limit) less 5 points per lint finding inside it. A function at 95% or more is approved. The scores are also shown as **Code Health** on a 1–10 scale (score ÷ 10), modelled on CodeScene's, whose 9.5 is the level it recommends for code that AI agents work in. Each file's and the project's figure weights functions by lines of code, so one large bad function outweighs many small good ones; the report also shows a hotspot figure (files changed in the last 180 days) and the worst file. CodeScene's own formula and thresholds aren't published, so these numbers are comparable in spirit, not identical. Nothing acts on averages.

All tools are free and permissively licensed (MIT / Apache-2.0); nothing needs a subscription or a server. The structure checks read Python, JS and TS syntax trees with `tree-sitter-language-pack` (installed with pip, or fetched through `uvx` at a pinned version); without it those three measures are skipped and `check` says tree-sitter was not found. Bumpy Road and Complex Conditional are approximations: CodeScene doesn't publish its exact rules. Here, a bump is a top-level branch of the function that contains another branch, and a complex condition has more than 2 `&&` / `||` operators.

## Install

```
/plugin install code-quality --marketplace HackerAndy/claude-skills
```

## Use

In Claude Code: `/code-quality init` in a project. That writes `.quality/config.toml` (limits), a baseline of today's findings, `.quality/quality_gate.py` (the copy CI runs) and `.github/workflows/code-quality.yml`. Commit them.

From then on the hook checks each file Claude edits and sends new findings back to Claude, which fixes them. Existing code doesn't block anything: it's in the baseline, and the baseline lowers itself as code gets better, so improvements stick.

Without Claude: `bin/quality-gate init`, `bin/quality-gate check [--all] [--full] [--json]`, `bin/quality-gate targets`, `bin/quality-gate score FILE --symbol NAME`, `bin/quality-gate report [--open]`, `bin/quality-gate doctor`.

## The report

`/code-quality report` (or `bin/quality-gate report --open`) writes `.quality/report.html`: one page, no server, light and dark. At the top, the share of functions approved and how many are green (95% and up), yellow (70–94%) and red (below 70%); then the 10 functions to fix first; then a drill-down from folder to file to function. A function below 95% opens to how its score was worked out, one card per problem (what it means, why it matters, how to fix it, and for lint rules the rule's own docs with a bad/good example), and its code: each place that adds a path to the cyclomatic count is marked with its `+1`, and each lint finding is underlined at the exact characters the tool reported. Click a card to jump to its lines. Every check after that keeps the page and `.quality/report.json` up to date, and both are git-ignored.

In Claude Code, the `code-quality-live` mod shows the same in a pane beside the chat (`/quality-live`), with the approved share in the status line. Press a folder, a file, then a function to see its issues and the lines causing them, highlighted; `‹` goes back. It refreshes after each edit.

## Refactoring existing code

`/code-quality:quality-refactor` takes functions below 95%, worst and most-changed first (`quality-gate targets`), and refactors each one until `quality-gate score <file> --symbol <name>` approves it, with the project's tests green before and after. Each function gets at most 3 attempts; one that still isn't approved is left for a person, with the reason. Untested functions get a characterization test first. The baseline lowers to lock in what improved.

## Monorepos

Each tool runs per package: the nearest folder with its own config (`pyproject.toml`, `package.json`, `biome.json`, `tsconfig.json` ...), using that package's settings, `.venv` and `node_modules`. Files git ignores and minified files are skipped.

## Opt-in

Nothing runs unless `.quality/config.toml` exists in the project (found by walking up from the edited file, so monorepos work).

## Tests

`python3 -m unittest discover tests` from this folder (uses `examples/demo`).
