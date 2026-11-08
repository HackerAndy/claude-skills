# code-quality

A deterministic complexity and code-smell gate for Python, JavaScript and TypeScript. The same measurements run for Claude after every edit, for people at the command line, and in CI, so "good enough" means the same thing everywhere.

| Check | Tool | When |
|---|---|---|
| Cyclomatic and cognitive complexity, function length, parameters (per function) | lizard | every edit, `check` |
| File length | built in | every edit, `check` |
| Lint and smells (project's config + bugbear, simplify, comprehensions, pyupgrade) | ruff, biome | every edit, `check` |
| Type errors | the package's mypy if configured, else pyright; the package's tsc | `check --full` (CI) |
| Duplicated code | jscpd | `check --full` (CI) |

Each function gets a score from 0 to 100%, set by its worst metric (90% exactly at a limit) less 5 points per lint finding inside it. A function at 90% or more is approved. File and project averages are shown for reading; nothing acts on them.

All tools are free and permissively licensed (MIT / Apache-2.0); nothing needs a subscription or a server.

## Install

```
/plugin install code-quality --marketplace HackerAndy/claude-skills
```

## Use

In Claude Code: `/code-quality init` in a project. That writes `.quality/config.toml` (limits), a baseline of today's findings, `.quality/quality_gate.py` (the copy CI runs) and `.github/workflows/code-quality.yml`. Commit them.

From then on the hook checks each file Claude edits and sends new findings back to Claude, which fixes them. Existing code doesn't block anything: it's in the baseline, and the baseline lowers itself as code gets better, so improvements stick.

Without Claude: `bin/quality-gate init`, `bin/quality-gate check [--all] [--full] [--json]`, `bin/quality-gate doctor`.

## Monorepos

Each tool runs per package: the nearest folder with its own config (`pyproject.toml`, `package.json`, `biome.json`, `tsconfig.json` ...), using that package's settings, `.venv` and `node_modules`. Files git ignores and minified files are skipped.

## Opt-in

Nothing runs unless `.quality/config.toml` exists in the project (found by walking up from the edited file, so monorepos work).

## Tests

`python3 -m unittest discover tests` from this folder (uses `examples/demo`).
