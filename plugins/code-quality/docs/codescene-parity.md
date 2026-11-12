# code-quality vs CodeScene: parity results

How the gate compares with CodeScene's Code Health (CLI 1.0.58, default rules). The corpus is in
`tests/parity/`: 10 Python and 7 TS fixtures, one smell each, plus 4 real files. Re-run it with
`python3 tests/parity/run_parity.py`; the raw output is in `tests/parity/results/parity.json`.

## Summary

| | 0.10.1 (before) | 0.11.0 | 0.12.0 (now) |
|---|---|---|---|
| CodeScene function smells we also flag | 51 / 72 (71%) | 65 / 75 (87%) | 71 / 78 (91%) |
| Our smells CodeScene doesn't flag | 2 | 11 | 1 |
| Mean file-score gap (1-10) | 1.96 | 0.17 | 0.09 |
| Rank correlation of file scores (Spearman) | 0.42 | 0.74 | 0.79 |

0.11.0 adopted CodeScene's thresholds, its cost per smell and the way it combines costs, and a
bump counter fitted to its counts. 0.12.0 measures as CodeScene does: complexity counted by its
rules, nested functions folded into their parent, `try` not a nesting level, and Overall Code
Complexity charged per file (see "How CodeScene measures" below). The miss and extra counts here
include file-level smells we don't model, such as Primitive Obsession on the TS fixture.

## File scores (1-10)

| File | 0.10.1 | 0.11.0 | 0.12.0 | CodeScene |
|---|---|---|---|---|
| py/clean | 9.8 | 10.0 | 10.0 | 10.0 |
| py/primitive_obsession | 9.6 | 10.0 | 10.0 | 10.0 |
| py/dry_violation | 9.0 | 8.8 | 9.4 | 10.0 (\*) |
| py/excess_arguments | 8.9 | 9.7 | 9.7 | 9.68 |
| py/large_method | 8.6 | 9.6 | 9.6 | 9.55 |
| py/complex_method | 7.8 | 9.6 | 9.6 | 9.6 |
| py/complex_conditional | 7.5 | 9.5 | 9.5 | 9.53 |
| py/nested_complexity | 7.0 | 9.4 | 9.4 | 9.38 |
| py/bumpy_road | 2.0 | 9.8 | 9.8 | 9.84 |
| py/brain_method | 1.0 | 8.1 | 8.0 | 7.97 |
| ts/clean | 9.8 | 10.0 | 10.0 | 10.0 |
| ts/primitiveObsession | 9.6 | 10.0 | 10.0 | 9.38 (\*\*) |
| ts/excessArguments | 8.9 | 9.7 | 9.7 | 9.68 |
| ts/complexMethod | 8.3 | 9.6 | 9.6 | 9.6 |
| ts/complexConditional | 8.0 | 9.5 | 9.5 | 9.53 |
| ts/nestedComplexity | 7.5 | 9.4 | 9.4 | 9.38 |
| ts/bumpyRoad | 3.5 | 9.8 | 9.8 | 9.84 |
| real/orders.py | 6.8 | 9.2 | 9.1 | 9.11 |
| real/quality_gate.py | 9.5 | 8.9 | 8.4 | 8.67 |
| real/qg_checks.py | 9.4 | 7.6 | 7.6 | 7.58 |
| real/backend_map.py | 3.0 | 1.8 | 2.0 | 2.09 |

The real files are this repo's own code, so their content (and CodeScene's score) changes as the gate is edited.
(\*) CodeScene's duplication check looks for similar functions within one file and doesn't fire on this fixture. jscpd finds the exact copy, and we charge it once per file (0.11.1).
(\*\*) We don't model Primitive Obsession.

## What CodeScene charges (measured with generated samples)

Each smell costs a fixed amount on the 1-10 scale, and costs multiply: score = 10 × Π(1 − cost ÷ 10).
File size has no effect: the same smell scores the same with 0, 10 or 40 clean functions beside it.

| Smell | Threshold (warns at) | Cost |
|---|---|---|
| Complex Method | cc 9 | max(0.32, 0.026 × cc + 0.03): 0.32 at 9-10, 0.42 at 15, 0.56 at 20, 0.82 at 30 |
| Large Method | 70 LoC | 0.0052 × LoC + 0.035: 0.40 at 70, 0.56 at 100, 1.33 at 250 |
| Complex Conditional | 2 operators | 0.15 × operators + 0.02, summed across the file |
| Deep, Nested Complexity | depth 4 | 0.62 for depth 4-6, then about 0.26 per level |
| Excess Function Arguments | 5, not counting `self` / `cls` | 0.32 flat |
| Code Duplication | functions ≥ 75% similar, 10+ LoC | 0.62 once per file, however many functions (measured on real code in 0.11.1) |
| Bumpy Road Ahead | 2 bumps | 0.16 for 2-4 bumps. Larger counts were inconsistent (6 bumps cost 0.16 in one sample and 0.64 in another) |

How repeats count in one file:
- **Complex Method and Large Method:** every function counts. cc 15 + cc 30 scores the same as three cc-15 functions.
- **Complex Conditional:** operators add up across the file.
- **Nesting, Arguments, Bumpy Road:** count once, at the worst function. Five functions with 6 parameters score the same as one. Seven or more, or three nested ones, cost a little more; we don't model that.

## How CodeScene measures (0.12.0)

Found with generated samples and applied in 0.12.0. Each was confirmed on CodeScene 1.0.58.

**Cyclomatic complexity.** CodeScene counts some things differently from lizard (`qg_smells.ccn_fix` corrects lizard's count):

| Construct | lizard | CodeScene |
|---|---|---|
| `raise` / `throw` | 0 | +1 |
| Python `else` after an `if` | 0 | +1 (a JS `else`: 0 in both) |
| JS / TS `?.` | 0 | +1 each |
| Python ternary, incl. inside f-strings | +1 | 0 |
| Python comprehension `if` | +1 | 0 (its `for` counts in both) |
| Python `finally` | +1 | 0 |
| JS / TS `??` | +1 | 0 |
| JS / TS default parameter value | +1 | 0 |
| `or` / `and` in a value, JS ternary, loop `else`, `except` / `catch` | same | same |

**Nested functions** fold into the function around them:
- Their paths add to the parent's (parent + child − 1).
- Their lines add too (lizard counts the inner `def` line in both).
- Their bumps add, their deepest nesting and most complex condition carry over, and their parameters aren't counted.
- Python folds every nested function, even a 100-line one. JS / TS folds one under 25 lines; at 25 or more it's reported on its own (as `outer.inner`).

**Nesting:** a `try` (or `with`) is not a level; `if`, loops and `switch` are.

**Overall Code Complexity:** a file with 7 or more functions whose mean cyclomatic complexity is over 4 pays a flat 0.62. Six functions never trigger it, nor does a mean of exactly 4.

**`*args` / `**kwargs`, keyword-only parameters and JS rest parameters** count as arguments in both; `self` / `cls` don't count in CodeScene (fixed in 0.11.1).

## Held-out check

The gate was also compared on a private project of 151 files (139 scored) that it wasn't tuned on:

| | 0.11.0 | 0.11.1 | 0.12.0 |
|---|---|---|---|
| Mean file-score gap | 0.23 | 0.17 | 0.14 |
| Files within 0.5 | 120 | 123 | 124 |
| Spearman | 0.93 | 0.95 | 0.96 |
| Complex Method hit / miss / extra | 119 / 26 / 21 | 124 / 21 / 13 | 143 / 2 / 3 |
| Deep Nesting hit / miss / extra | 13 / 1 / 7 | 14 / 0 / 6 | 14 / 0 / 0 |
| Excess Arguments hit / miss / extra | 45 / 6 / 28 | 50 / 0 / 12 | 50 / 0 / 1 |
| Bumpy Road hit / miss / extra | 38 / 20 / 25 | 39 / 19 / 24 | 41 / 17 / 24 |

What's left: Bumpy Road, and file-level rules we don't model (Low Cohesion, Number of Functions in a Single Module, CodeScene-style duplication). These dominate the worst files, mostly large test files.

## Bump counting

CodeScene doesn't document Bumpy Road, so the counter was fitted to the 17 functions it reports
bumps for. Rule: each branch of a top-level if / switch / match / try that holds a nested branch,
loop or ternary is a bump. A top-level loop is one bump, unless the branches inside it are bumps
of their own.

| Counter | Exact count | Mean error | Flag decision wrong (of 122 functions) |
|---|---|---|---|
| 0.10.1: top-level branches with a nested branch | 8 / 17 | 2.0 | 2 |
| 0.11.0 | 9 / 17 | 1.0 | 2 |

Still off: `setup` in backend_map.py (CodeScene 8, ours 2) and `scan_py_functions` (4 vs 1).

## Not modelled

- **Brain Method:** neither `cs review` nor `cs delta` reported it on the corpus.
- **Code Duplication is detected differently.** CodeScene reports it on real code: functions in one file that are at least 75% similar. Our fixture of near-identical functions didn't trigger it. jscpd finds exact token copies, across files too, so the two find different things. Only the cost (0.62 once per file) matches.
- **Primitive Obsession and String Heavy Function Arguments:** TS only in CodeScene, and only once a file has about 15 primitive-argument functions.
- **Low Cohesion and Number of Functions in a Single Module:** file-level rules we don't have. They account for most of what's left on large test files.
- **Python `match`:** CodeScene's count for `case` is unclear, so lizard's stands.
- **Lint:** costs nothing in the score, as in CodeScene, but still blocks.
- **Cognitive complexity:** isn't a CodeScene smell. It's charged like Complex Method, but only when cyclomatic complexity is within its limit.
