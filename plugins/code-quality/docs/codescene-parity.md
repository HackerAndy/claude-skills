# code-quality vs CodeScene: parity results

How the gate compares with CodeScene's Code Health (CLI 1.0.58, default rules). The corpus is in
`tests/parity/`: 10 Python and 7 TS fixtures, one smell each, plus 4 real files. Re-run it with
`python3 tests/parity/run_parity.py`; the raw output is in `tests/parity/results/parity.json`.

## Summary

| | 0.10.1 (before) | 0.11.0 (now) |
|---|---|---|
| CodeScene function smells we also flag | 51 / 72 (71%) | 65 / 75 (87%) |
| Our smells CodeScene doesn't flag | 2 | 11 |
| Mean file-score gap (1-10) | 1.96 | 0.17 (0.08 without the 2 unmodelled fixtures) |
| Rank correlation of file scores (Spearman) | 0.42 | 0.74 |

0.11.0 adopted CodeScene's thresholds, its cost per smell and the way it combines costs, and a
bump counter fitted to its counts. The extra findings went up because the limits are now
CodeScene's, which are lower than ours were. Most of the extras are cyclomatic complexity exactly
at 9, where lizard counts `and` / `or` and comprehensions a little differently. Three are nested
functions, which CodeScene folds into their parent.

## File scores (1-10)

| File | 0.10.1 | 0.11.0 | CodeScene |
|---|---|---|---|
| py/clean | 9.8 | 10.0 | 10.0 |
| py/primitive_obsession | 9.6 | 10.0 | 10.0 |
| py/dry_violation | 9.0 | 8.5 | 10.0 (\*) |
| py/excess_arguments | 8.9 | 9.7 | 9.68 |
| py/large_method | 8.6 | 9.6 | 9.55 |
| py/complex_method | 7.8 | 9.6 | 9.6 |
| py/complex_conditional | 7.5 | 9.5 | 9.53 |
| py/nested_complexity | 7.0 | 9.4 | 9.38 |
| py/bumpy_road | 2.0 | 9.8 | 9.84 |
| py/brain_method | 1.0 | 8.1 | 7.97 |
| ts/clean | 9.8 | 10.0 | 10.0 |
| ts/primitiveObsession | 9.6 | 10.0 | 9.38 (\*\*) |
| ts/excessArguments | 8.9 | 9.7 | 9.68 |
| ts/complexMethod | 8.3 | 9.6 | 9.6 |
| ts/complexConditional | 8.0 | 9.5 | 9.53 |
| ts/nestedComplexity | 7.5 | 9.4 | 9.38 |
| ts/bumpyRoad | 3.5 | 9.8 | 9.84 |
| real/orders.py | 6.8 | 9.2 | 9.11 |
| real/quality_gate.py | 9.5 | 8.9 | 8.67 |
| real/qg_checks.py | 9.4 | 7.6 | 8.08 |
| real/backend_map.py | 3.0 | 1.8 | 2.09 |

(\*) The CodeScene CLI doesn't score duplication; we charge 0.5 per copy.
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
| Excess Function Arguments | 5 | 0.32 flat |
| Bumpy Road Ahead | 2 bumps | 0.16 for 2-4 bumps. Larger counts were inconsistent (6 bumps cost 0.16 in one sample and 0.64 in another) |

How repeats count in one file:
- **Complex Method and Large Method:** every function counts. cc 15 + cc 30 scores the same as three cc-15 functions.
- **Complex Conditional:** operators add up across the file.
- **Nesting, Arguments, Bumpy Road:** count once, at the worst function. Five functions with 6 parameters score the same as one. Seven or more, or three nested ones, cost a little more; we don't model that.

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

- **Code Duplication and Brain Method** are CodeScene rules, but neither `cs review` nor `cs delta` reports them, so there is nothing to compare against.
- **Primitive Obsession and String Heavy Function Arguments:** TS only in CodeScene, and only once a file has about 15 primitive-argument functions.
- **Overall Code Complexity (file mean cc ≥ 4) and Low Cohesion:** file-level rules we don't have.
- **Lint:** costs nothing in the score, as in CodeScene, but still blocks.
- **Cognitive complexity:** isn't a CodeScene smell. It's charged like Complex Method, but only when cyclomatic complexity is within its limit.
