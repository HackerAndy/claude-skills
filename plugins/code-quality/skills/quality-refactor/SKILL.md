---
name: quality-refactor
description: Refactor existing code until each target function scores at least 95% on the code-quality gate, with the project's tests passing and at most 3 attempts per function. Use when the user asks to "refactor for quality", "fix the worst functions", "raise the code-quality scores", "pay down complexity", "refactor the hotspots", or runs /code-quality:quality-refactor, in a project that has a .quality/ folder.
---

# quality-refactor

Takes functions the code-quality gate scores below 95% and restructures them, one at a time, until each one is approved (95% or more) while behavior stays the same. The gate decides what "done" means, so the result doesn't depend on taste.

Script: `../code-quality/scripts/quality_gate.py` from this skill's base directory (call it `$QG`). The project must have `.quality/config.toml`; if it doesn't, offer `/code-quality init` first.

## 1. Pick the targets

- The user named files, folders or functions: `python3 $QG targets <paths>`.
- Otherwise: `python3 $QG targets --limit 10`. It lists functions below 95%, ordered by `(100 - score) x (1 + commits to the file in the last 180 days)`, so code that is both bad and often changed comes first.

Show the list (score, file:line, function, why) and say how many you'll take. Don't ask for confirmation unless the list is longer than 10 or the user only asked for a report.

## 2. Make sure the tests are green first

Find the project's test command: CLAUDE.md, `package.json` scripts (`test`, `vitest`, `jest`), `pyproject.toml` / `pytest.ini` (pytest), a Makefile. In a monorepo, use the package's own command, from the package folder.

Run it once before changing anything. If it fails, stop and report: refactoring on a red suite can't show behavior is kept.

For each target, check that some test exercises it (grep the test folders for its name or its module). If nothing does, write a small characterization test first that pins its current behavior (the main paths and edge cases you can see in the code), run it green, and say so in the report. Don't change the function while writing that test.

## 3. Refactor one function: at most 3 attempts

One attempt is: restructure, then `python3 $QG score <file> --symbol <name>`, then the tests.

- `score` exits 0 when that function is at 95% or more and the file has no new findings (helpers you extract count: each must also be inside the limits). Exit 1 prints every function in the file with its score and why.
- An anonymous target (`(anonymous)`, `(anonymous)#7`): give it a name as part of the refactor (extract the callback into a named function or component), then score that name.
- Approved and tests pass: done. Move on; don't polish further.
- Otherwise, read what `score` and the test output say and make another attempt. Each attempt has to change the approach in response to them, not repeat it.
- After the 3rd attempt without approval: keep the best attempt only if its tests pass and its score is higher than where it started, else restore the original (`git checkout -- <file>` only if the file had no uncommitted changes before you started; otherwise restore from the copy you read). Record it as **needs a human**, with the last score and why, and move on.

Behavior must stay identical: same inputs give the same outputs, errors, side effects and calls, in the same order. Never edit a test's expected values to make it pass; a failing test means the attempt changed behavior.

How to bring the metrics down:

| Over the limit | Do |
|---|---|
| cyclomatic / cognitive | return early instead of nesting; replace `if/elif` or `switch` chains with a lookup table; extract each branch body into a named helper; split a function that does two things |
| lines | extract cohesive steps into named helpers; in UI components, extract sub-components and hooks |
| parameters | group related parameters into a dataclass / object type |
| lint findings | fix what the rule says |

Don't game it: no `noqa`, `biome-ignore`, `type: ignore`, no meaningless splits (`part1`, `helper2`), no moving logic into a lambda or string to hide it from the counter, no editing `.quality/`. Names of extracted helpers should say what they do.

## 4. Many targets at once

Up to 3 targets: do them yourself, in order. More than 3 in different files: you may hand them to subagents with `isolation: "worktree"`, one file per agent (never two agents on one file), each given this skill's step 3, the target list for its file, the test command, and the rule to report per function: approved / needs a human, start and end score, attempts used. Apply each agent's changes back, then run the full test suite once more in the main tree.

## 5. Finish

1. `python3 $QG check --all`: must exit 0 (no new findings anywhere). It also lowers `.quality/baseline.json` for what improved; that change belongs in the commit.
2. The full test suite, green.
3. Report a table: function, score before → after, attempts, result (approved / needs a human with why), plus any characterization tests added. Then the project's approved count and average from `check --all` (the average is for reading only).

Don't commit unless the user asks. Leave the needs-a-human functions as they are; suggest what a person should decide (for example a function that needs a design change, or a limit that seems wrong for this code: the user decides, never you).
