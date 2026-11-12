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

## Held-out check: the 9.5 decision

CodeScene recommends 9.5 for code AI agents work in, so what matters most is whether the gate puts a
file on the same side of 9.5. "Risky" below means the gate passes a file (9.5 or more) that CodeScene
fails; "stricter" is the other way round.

### Seven projects (0.15.0)

Three projects of mine (A-C) and four work repositories (D-G, about 1,700 source files, half Python and
half TypeScript / React), none of D-G seen before tuning 0.15.0's rules on them.

| Project | Files scored | Same side of 9.5 | Risky | Stricter | Mean gap | Spearman |
|---|---|---|---|---|---|---|
| A: Python (0.11.1-0.13.0 fitted on it) | 139 | 133 (96%) | 1 | 5 | 0.13 | 0.96 |
| B: Python + TypeScript | 128 | 125 (98%) | 0 | 3 | 0.07 | 0.90 |
| C: Python + JS | 77 | 73 (95%) | 0 | 4 | 0.14 | 0.98 |
| D-G: work repos, Python + TS / TSX | 1,473 | 1,394 (95%) | 18 | 61 | 0.24-0.34 | 0.93-0.94 |
| **All** | **1,817** | **1,725 (94.9%)** | **19** | **73** | | |

**Of the 1,070 files the gate scores 9.5 or more, CodeScene agrees on 1,051 (98.2%).** On D-G, 0.14.0 had
70 risky files (91.8% agreement); 0.15.0's changes, found on those repos, brought that to 18.

- **The risky files that remain** are mostly CodeScene-style duplication the similarity check misses, plus
  one-offs from rules we don't model (Primitive Obsession, Global Conditionals, Low Cohesion).
- **Where the gate is stricter:**
  - Files the similarity check flags as duplicates and CodeScene doesn't.
  - React components where CodeScene ignores the code after a long named nested function (left as is: the
    gate scores that code).
  - Our cognitive-complexity rule.

| Smell, all seven projects | Matched | CodeScene only | Gate only |
|---|---|---|---|
| Complex Method | 1,368 | 47 | 158 |
| Large Method | 420 | 8 | 68 |
| Complex Conditional | 345 | 23 | 32 |
| Bumpy Road | 399 | 27 | 45 |
| Deep Nesting | 82 | 6 | 3 |
| Excess Arguments | 681 | 2 | 1 |

### What 0.15.0 changed (found on D-G)

- **Lines of code** are every line a non-comment token touches: docstrings, multi-line strings and every
  JSX line count, blank and comment-only lines don't. lizard missed docstrings and much of multi-line JSX
  (e.g. 76 of 151 lines). Large Method misses on D-G went from 99 to 8.
- **Cyclomatic complexity** is counted from the syntax tree with CodeScene's rules instead of lizard's
  count plus a correction. lizard misparses some JSX: a component CodeScene counts at 18 came out as 1.
- **Nested JS / TS functions:** a 25+ line nested function stays its own only if CodeScene can name it (a
  declaration, or the value of a variable, property or assignment). An inline callback, like
  `{items.map(x => { ... })}` in JSX, always folds into the component, however long.
- **Excess Arguments costs 0.62 instead of 0.32** when a file has 7+ functions averaging more than 4
  parameters, mirroring Overall Code Complexity. This explained every real file's argument cost.
- **Duplication threshold 0.5** (was 0.6), chosen on all 1,817 files. Overall agreement barely changes
  (95.0% against 95.3%), but risky files drop from 27 to 19 for 13 more stricter ones. No similarity
  measure tried (raw tokens, names masked, node types) separates CodeScene's duplication flags well.
- **Arrow-function components are named** after their variable (`const Card = () => ...` is `Card`), as
  CodeScene names them, instead of lizard's `(anonymous)`.

### JSX, TSX and JS rules (0.14.0)

Found with samples on CodeScene 1.0.58:

| Rule | CodeScene |
|---|---|
| Complex Method in `.jsx` / `.tsx` | warns at cc 10 (9 in `.js` / `.ts`); same cost |
| Large Method in `.jsx` / `.tsx` | warns at 120 lines (70 in `.js` / `.ts`); same cost. The function's name doesn't matter, only the extension |
| Other limits in `.jsx` / `.tsx` | same as `.js` / `.ts` (arguments, nesting, conditions, Overall Code Complexity) |
| JS / TS ternary condition | never a Complex Conditional (a Python ternary's is) |
| Unbraced `if (...) stmt` in JS / TS | its condition counts only when that statement or the next one ends in a semicolon, so semicolon-free code goes unchecked |
| Duplication in JSX | markup doesn't count: two components alike only in their JSX aren't duplicates |
| JSX `&&`, ternaries, attribute expressions | count toward cyclomatic complexity, as lizard counts them |

Not matched: in JS / TS, when a function holds a nested function long enough to stand alone (25+ lines),
CodeScene reports the code before it as `outer (top-level context)` and doesn't score the code after it.
The gate still scores the whole function, so it can be stricter there.

### Project A, version by version

Project A was the first held-out check and was then used to fit 0.11.1 to 0.13.0:

| | 0.11.0 | 0.11.1 | 0.12.0 | 0.13.0 |
|---|---|---|---|---|
| **Same side of 9.5** | 132 | 133 | 133 | **135 / 139** |
| Gate passes, CodeScene fails | 4 | 3 | 2 | **1** |
| Gate fails, CodeScene passes | 3 | 4 | 4 | 3 |
| Mean file-score gap | 0.23 | 0.17 | 0.14 | 0.12 |
| Spearman | 0.93 | 0.95 | 0.96 | 0.97 |
| Complex Method hit / miss / extra | 119 / 26 / 21 | 124 / 21 / 13 | 143 / 2 / 3 | 143 / 2 / 3 |
| Deep Nesting | 13 / 1 / 7 | 14 / 0 / 6 | 14 / 0 / 0 | 14 / 0 / 0 |
| Excess Arguments | 45 / 6 / 28 | 50 / 0 / 12 | 50 / 0 / 1 | 50 / 0 / 1 |
| Bumpy Road | 38 / 20 / 25 | 39 / 19 / 24 | 41 / 17 / 24 | 55 / 3 / 1 |

The one file the gate passes and CodeScene fails is a test file CodeScene flags for duplication
(gate 10.0, CodeScene 9.38). The 3 it fails and CodeScene passes are test files with similar functions
the gate counts as duplicates and CodeScene doesn't. Low Cohesion, Number of Functions in a Single
Module and Brain Method appear only in files CodeScene scores 7.55 or lower, so they don't change any
9.5 decision here.

## Bump counting (0.13.0)

Fitted to CodeScene's flags on 2,391 functions (58 flagged) of the held-out project. CodeScene charges
the same 0.16 for 2-4 bumps, so the yes/no decision (2 or more) matters most.

- Each path of an if / elif / else, switch or match that holds a nested branch or loop is a bump. In
  Python, so is a path that assigns a ternary (`x = a if c else b`); a ternary elsewhere isn't.
- A loop holding branches is one bump. If the branches inside it make bumps of their own, it's those,
  plus one if the loop also has a plain conditional path (an `if` / `elif` / `case` with nothing nested).
- `try` and `with` are looked inside, not counted as paths.
- Nested functions fold in (Python always; JS / TS under 25 lines).

| Counter | Decision wrong (of 2,391) | Exact count (of 58) |
|---|---|---|
| 0.11.0 / 0.12.0 rule | 41 | 26 |
| 0.13.0 | 4 | 49 |

## Code Duplication (0.13.0)

CodeScene reports duplication as functions in one file that are similar. Its settings say 10+ lines and
75% similarity, but not how similarity is measured. Plain token similarity didn't separate its flags
well. The best fit found is the share of 5-token runs two functions have in common (Jaccard) at 0.6 or
more, for functions of 10+ code lines with nested functions folded in. It costs 0.62 once per file.

- **Per file:** 4 of the 5 files CodeScene flags, plus 4 it doesn't. Two of those already fail for other
  reasons.
- **Fitted on 5 files only:** this is the least certain rule, so check it on more code.
- **jscpd copies** (mostly across files, which CodeScene ignores) are still findings that block, but cost no score.

## Not modelled

## Not modelled

- **Brain Method:** neither `cs review` nor `cs delta` reported it on the corpus.
- **Primitive Obsession and String Heavy Function Arguments:** TS only in CodeScene, and only once a file has about 15 primitive-argument functions.
- **Low Cohesion and Number of Functions in a Single Module:** file-level rules we don't have. On the held-out project they only appear in files scored 7.55 or lower.
- **Python `match`:** CodeScene's count for `case` is unclear, so lizard's stands.
- **Lint:** costs nothing in the score, as in CodeScene, but still blocks.
- **Cognitive complexity:** isn't a CodeScene smell. It's charged like Complex Method, but only when cyclomatic complexity is within its limit.
