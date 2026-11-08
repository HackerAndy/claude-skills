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

Every function gets a score from 0 to 100%. **A function is approved at 90% or more**; that is the bar, per function.

- Each metric (cyclomatic, cognitive, lines, parameters) scores 100 at zero, **90 exactly at its limit**, and loses 30 points per 100% over it. The function's score is its *worst* metric, so one bad metric can't be averaged away. Approved therefore means "inside every limit".
- Each ruff / biome finding inside the function costs another 5 points.
- File and project averages are reported for reading only. Never act on an average; act on the functions below 90%.

`check --json` lists every checked function with `score` and `approved`, and `scores` holds the counts and averages.

## Commands (the user may type `/code-quality <action>`)

| Action | Do |
|---|---|
| `init` | `python3 $QG init` in the project root. It writes `.quality/config.toml`, `.quality/quality_gate.py` (the copy CI runs), `.github/workflows/code-quality.yml`, and a baseline of today's findings. Report in 3 lines: what was written, how many existing findings were baselined, which tools were not found. Suggest committing `.quality/` and the workflow. `--no-ci` skips the workflow. |
| *(none)* / `check` | `python3 $QG check` (files changed since HEAD). `--all` for every file, `--full` adds type checking and duplication. Summarize; fix new findings in code you wrote this session. |
| `report` | `python3 $QG check --all --full --json`, then show: approved / total functions and the average (for reading only), per-file averages, and a table of the functions below 90% (file, function, score, worst metric vs limit), lowest first. |
| `baseline` | Only when the user asks: `python3 $QG baseline` accepts all current findings. Never run it to make a check pass. |
| `doctor` | `python3 $QG doctor`: which tools were found and how each is run. |

## After every edit (the hook)

In a project with `.quality/config.toml`, the plugin's PostToolUse hook checks each edited file. New findings come back as hook feedback, like:

```
code-quality: 2 new finding(s) in 1 file(s) (4 baselined)
app/orders.py
     12  process_order (73%): cyclomatic complexity 14 > 10, cognitive complexity 21 > 15
     40  ruff B006: Do not use mutable data structures for argument defaults
```

Fix them until each function you wrote or changed is at 90% or more:

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
