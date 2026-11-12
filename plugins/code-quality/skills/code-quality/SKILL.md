---
name: code-quality
description: Deterministic code complexity and code-smell gate for Python, JavaScript and TypeScript (cyclomatic and cognitive complexity, function and file size, parameters, lint, types, duplication) with a baseline so existing code doesn't block work. Use when the user asks to "check code quality", "measure complexity", find code smells, set up a quality gate or CI check, "init code-quality", or when a code-quality hook reports findings after an edit. Also use when writing or changing code in a project that has a .quality/ folder.
---

# code-quality

Measures code with fixed tools and fixed limits, so the result is the same for every run, agent and person.
New code must stay inside the limits; existing code is recorded in a baseline and may only get better.

Script: `scripts/quality_gate.py` in this skill's base directory (call it `$QG` below). Run it with `python3` (3.11+).
The checks live in `scripts/qg_checks.py` next to it.

Tools run per package (the nearest folder with `pyproject.toml`, `package.json`, `biome.json`, `tsconfig.json` ...), with that package's own config and its own `.venv` / `node_modules`, so a monorepo's backend and frontend each keep their settings. Python type checking uses mypy where the package configures it, else pyright. A tool that isn't installed runs through `uvx` / `npx` at a pinned version (never tsc or mypy, which must be the project's own). Files git ignores, and minified or generated files, are skipped.

## Scores

Every function gets a score from 0 to 100%. **A function is approved at 95% or more**; that is the bar, per function: 9.5 on CodeScene's 1–10 Code Health scale, the level it recommends for code AI agents work in.

- The limits are CodeScene's default thresholds less one (CodeScene warns *at* its threshold): cyclomatic 8, cognitive 15 (ours), 69 lines, 4 parameters, nesting 3, 1 `&&` / `||` per condition, 1 bump.
- Each smell over a limit costs what it costs CodeScene on its 1–10 scale, and the costs multiply (`fn.costs` in `check --json`). Lint costs nothing but still blocks. **A function with any finding stops at 94%**, so approved means "inside every limit, no findings".
- Code Health is CodeScene's model per file (nesting, parameters and bumpy road count once per file, at their worst), with files weighted by lines of code for the project, a hotspot figure (files changed in 180 days) and the worst file. `check --json` has `scores.health`, `worst_file`, `worst_file_health`; `report.json` has `health`. Never act on an average; act on the functions below 95%.

`check --json` lists every checked function with `score` and `approved`, and `scores` holds the counts and averages.

## Commands (the user may type `/code-quality <action>`)

| Action | Do |
|---|---|
| `init` | `python3 $QG init` in the project root. It writes `.quality/config.toml`, `.quality/quality_gate.py` (the copy CI runs), `.github/workflows/code-quality.yml`, a baseline of today's findings, and the report (`.quality/report.html`, git-ignored). Report in 3 lines: what was written, how many existing findings were baselined, which tools were not found. Suggest committing `.quality/` and the workflow. `--no-ci` skips the workflow. |
| *(none)* / `check` | `python3 $QG check` (files changed since HEAD). `--all` for every file, `--full` adds type checking and a project-wide duplication scan (a normal check already reports copies of the code in the files it checks). Summarize; fix new findings in code you wrote this session. |
| `report` | `python3 $QG report` (`--full` adds type checking and duplication; `--open` opens it in the browser). It writes `.quality/report.html`, one page that drills down from the share of functions approved to folders, files and each function (its score worked out, each issue explained from the tool's own rule docs, and its code with the branches and lint highlighted), and `.quality/report.json`, which the `code-quality-live` pane reads; each check afterwards refreshes both. Colors: green 95% and up, yellow 70–94%, red below 70%. Then say in 3 lines: approved / total (and the share), red and yellow counts, the top 3 to fix first, and the page's path. |
| `baseline` | Only when the user asks: `python3 $QG baseline` accepts all current findings. Never run it to make a check pass. |
| `targets` | `python3 $QG targets [paths] [--limit N]`: functions below 95%, highest refactoring priority first. To fix them, use the `quality-refactor` skill. |
| `doctor` | `python3 $QG doctor`: which tools were found and how each is run. |

## After every edit (the hook)

In a project with `.quality/config.toml`, the plugin's PostToolUse hook checks each edited file. New findings come back as hook feedback, like:

```
code-quality: 2 new finding(s) in 1 file(s) (4 baselined)
app/orders.py
     12  process_order (73%): cyclomatic complexity 14 > 10, cognitive complexity 21 > 15
     40  ruff B006: Do not use mutable data structures for argument defaults
```

Fix them until each function you wrote or changed is at 95% or more:

- **Complexity / length:** extract well-named helpers, return early instead of nesting, replace `if/elif` chains with a dict or lookup table, split a function that does two things.
- **Parameters:** group related parameters into a dataclass / object type.
- **File size:** move a cohesive group of functions into its own module.
- **Lint:** fix what the rule says; read the rule's docs if unsure.

Rules:

1. Fix the code; don't game the metric. No `# noqa`, `biome-ignore`, `type: ignore`, or splitting a function into meaningless pieces just to pass. A suppression is acceptable only with a comment saying why, and the user should know about it.
2. Never edit `.quality/baseline.json` or raise limits in `.quality/config.toml` to pass. If a limit seems wrong for this project, tell the user and let them decide.
3. Keep behavior identical when restructuring; run the project's tests after.
4. The baseline lowers itself as code improves. If you touch a baselined function anyway, leaving it better is welcome but not required; don't start unrelated refactors.

## Exit codes

`check`: 0 clean, 1 new findings, 3 no `.quality/` (run `init`). CI runs `python3 .quality/quality_gate.py check --full --base origin/<base branch>`.
