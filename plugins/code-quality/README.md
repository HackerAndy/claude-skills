# code-quality

A deterministic complexity and code-smell gate for Python, JavaScript and TypeScript. The same measurements run for Claude after every edit, for people at the command line, and in CI, so "good enough" means the same thing everywhere.

| Check | Tool | When |
|---|---|---|
| Cyclomatic and cognitive complexity, function length, parameters (per function) | lizard | every edit, `check` |
| Nesting depth, complex conditions, bumpy road (CodeScene's Nested Complexity, Complex Conditional and Bumpy Road; per function) | tree-sitter (`qg_smells.py`) | every edit, `check` |
| File length | built in | every edit, `check` |
| Lint and smells (project's config + bugbear, simplify, comprehensions, pyupgrade) | ruff, biome | every edit, `check` |
| Type errors | the package's mypy if configured, else pyright; the package's tsc | `check --full` (CI) |
| Duplicated code (copies of a block, in the same file or another; a finding, but it costs no score: CodeScene's duplication check is a different one, below) | jscpd | every edit, `check`; skipped if the scan takes over 60 s. Set `duplication = false` under `[edit]` to turn it off |

The limits and scores follow CodeScene's Code Health, measured against its CLI ([`docs/codescene-parity.md`](docs/codescene-parity.md)):

- **Limits** are CodeScene's default thresholds, less one because CodeScene warns *at* a threshold: cyclomatic complexity 8, function length 69 lines, 4 parameters (not counting `self` / `cls`), nesting depth 3, 1 `&&` / `||` per condition, 1 bump, 599 lines per Python file and 999 per JS / TS file. Cognitive complexity (15) is our addition; CodeScene has no such smell.
- **Costs.** Each smell over its limit costs what it costs CodeScene on its 1–10 scale, about 0.16 (bumpy road) to 0.6 (nesting), rising with complexity and length. Costs multiply: a score is 10 × the product of (1 − cost ÷ 10). Lint findings cost nothing, as in CodeScene, but they still block.
- **Functions** are scored 0–100% as a file holding only that function. A function with any finding stops at 94%, so **approved (95% or more) means inside every limit with no findings**.
- **Measured as CodeScene measures.** Cyclomatic complexity is lizard's count corrected to CodeScene's: `raise` / `throw`, a Python `else` and a JS `?.` count; a Python ternary, comprehension `if` and `finally`, and a JS `??` or default value don't. A nested function (a `def`, lambda or callback inside another function) is part of the function around it, so its paths, lines and bumps add to that function's; in JS / TS one of 25 lines or more stays a function of its own. A `try` isn't a nesting level.
- **Code Health** (1–10, two decimals as CodeScene gives it, so 9.46 isn't read as 9.5) is per file. Complex Method, Large Method and Complex Conditional count every function. Nesting, parameters and bumpy road count once per file, at their worst, as in CodeScene. A file pays 0.62 more once for each of these, if it has them: 7 or more functions whose complexity averages over 4 (Overall Code Complexity), and a function of 10 or more lines with a near copy in the same file (Code Duplication; 60% of their 5-token runs shared). The project figure weights files by lines of code. The report also shows a hotspot figure (files changed in the last 180 days) and the worst file.

**Using 9.5 as the bar.** CodeScene recommends 9.5 for code AI agents work in. On a project of 151 files, the gate and CodeScene agree on which side of 9.5 a file is for 135 of the 139 they both score. In 3 of the other 4 the gate is the stricter one. The one file the gate passes and CodeScene doesn't is a duplication case, which is the least certain match (see the parity doc). The average gap is 0.12, and the rank correlation 0.97. Nothing acts on averages.

All tools are free and permissively licensed (MIT / Apache-2.0); nothing needs a subscription or a server. The structure checks read Python, JS and TS syntax trees with `tree-sitter-language-pack` (installed with pip, or fetched through `uvx` at a pinned version); without it those three measures are skipped and `check` says tree-sitter was not found. CodeScene doesn't publish its exact rules, so Bumpy Road and duplication are fitted to its results on a real project. Bumpy Road: each path of an if / switch / match that holds a nested branch or loop is a bump. A loop is one bump if it holds branches; otherwise it's the bumps inside it, plus one if it also has a plain conditional path. `try` and `with` are looked inside. It agrees with CodeScene's yes/no decision on 2,387 of 2,391 functions. Duplication is the least certain: its 60% threshold is fitted on 5 files, so check it against CodeScene on your own code. Not modelled: Brain Method, Low Cohesion, Number of Functions in a Single Module and Primitive Obsession (TS only in CodeScene).

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
