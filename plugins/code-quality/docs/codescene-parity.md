# code-quality vs CodeScene: parity results

Run on 2026-11-12 with code-quality 0.10.1 (default limits) and CodeScene CLI 1.0.58 (`cs review`,
default rules). Corpus: `tests/parity/` (10 Python and 7 TS fixtures, one smell each) plus 4 real files.
Re-run with `python3 tests/parity/run_parity.py`; raw output is in `tests/parity/results/parity.json`.

## Summary

- **Smells mostly agree, scores don't.** 51 of 72 CodeScene function findings match one of ours
  (71%). Only 2 of ours have no CodeScene match, both caused by nested functions being named
  differently. The file scores are far apart: on average we're 1.96 points off on the 1-10 scale,
  and the two tools rank the 21 files with a Spearman correlation of only 0.42.
- **We're much harsher on single smells.** One smell costs about 0.2-0.6 in CodeScene; it can cost
  us 2-8 points. Three bumps take Bumpy Road to 2.0 for us and 9.84 for CodeScene.
- **We're softer on files with many medium smells.** CodeScene scores `quality_gate.py` 8.67 and
  `qg_checks.py` 8.95; we give 9.5 and 9.4. CodeScene adds up the smells and has file-level rules.
  Our score takes each function's worst metric and averages over the file weighted by lines.
- **Off-by-one limits.** CodeScene warns when a value reaches its threshold; we warn only above
  our limit, and some limits differ too. That accounts for 13 of the 21 misses. The other 8 are
  bump counting (2), one condition count, and file-level rules we don't have (5).

## File scores (1-10)

| File | code-quality | CodeScene | Gap |
|---|---|---|---|
| py/clean | 9.8 | 10.0 | -0.2 |
| py/primitive_obsession | 9.6 | 10.0 | -0.4 |
| py/dry_violation | 9.0 | 10.0 | -1.0 |
| py/excess_arguments | 8.9 | 9.68 | -0.8 |
| py/large_method | 8.6 | 9.55 | -1.0 |
| py/complex_method | 7.8 | 9.6 | -1.8 |
| py/complex_conditional | 7.5 | 9.53 | -2.0 |
| py/nested_complexity | 7.0 | 9.38 | -2.4 |
| py/bumpy_road | 2.0 | 9.84 | **-7.8** |
| py/brain_method | 1.0 | 7.97 | **-7.0** |
| ts/clean | 9.8 | 10.0 | -0.2 |
| ts/primitiveObsession | 9.6 | 9.38 | +0.2 |
| ts/excessArguments | 8.9 | 9.68 | -0.8 |
| ts/complexMethod | 8.3 | 9.6 | -1.3 |
| ts/complexConditional | 8.0 | 9.53 | -1.5 |
| ts/nestedComplexity | 7.5 | 9.38 | -1.9 |
| ts/bumpyRoad | 3.5 | 9.84 | **-6.3** |
| real/orders.py | 6.8 | 9.11 | -2.3 |
| real/quality_gate.py | 9.5 | 8.67 | **+0.8** |
| real/qg_checks.py | 9.4 | 8.95 | +0.5 |
| real/backend_map.py | 3.0 | 2.09 | +0.9 |

CodeScene scores each Python fixture the same as its TS twin. We don't: Bumpy Road gets 2.0 in
Python and 3.5 in TS, and Complex Method gets 7.8 and 8.3.

## Smell by smell

| Smell | Ours | CodeScene | Match | Notes |
|---|---|---|---|---|
| Complex Method | ccn > 10 | cc >= 9 | partial | Misses at cc 9 and 10 (`cmd_hook`, `check_duplication`, `file_report`). CodeScene's cc also runs higher: 16 vs our 13 on `legacy_price`, 13 vs 10 on `traces_text` |
| Excess Arguments | params > 5 | args > 4 | partial | Misses at 5 arguments (`finding`, `resolve_py`) |
| Complex Conditional | max operators in one condition > 2 | `branches_warning` 2: fires at 2 operators | partial | Misses where we count 2. We also count 1 in `analyze` where CodeScene flags it. CodeScene folds nested functions into their parent (`scan_py_functions:240`); we report `scan_py_functions.is_protocol` |
| Deep, Nested Complexity | nesting > 3 | depth >= 4 (loops count) | yes | Same depth on every fixture (5, 5, 6); only the limit differs |
| Bumpy Road Ahead | bumps > 1 | bumps >= 2 at nesting 2 | partial | Same threshold, but we count fewer bumps: 1 vs 2 (`init`), 1 vs 4 (`scan_py_functions`), 2 vs 3 (`legacy_price`) |
| Large Method | nloc > 60 | LoC >= 70 | yes (corpus) | Our limit is lower, so we'd flag functions of 61-69 lines that CodeScene doesn't |
| Brain Method | none | rule exists | n/a | Neither `cs review` nor `cs delta` reports it, even on a function that is large, complex and deeply nested at once |
| Code Duplication | jscpd, flat penalty per finding | rule exists | n/a | Neither command reports it, even for 3 identical 25-line functions. We catch the fixture (9.0) |
| Primitive Obsession, String Heavy Args | none | file level, TS only | **miss** | Fires once about 15 functions have primitive arguments; never for Python |
| Overall Code Complexity | none | file mean cc >= 4 | **miss** | `quality_gate.py`, `backend_map.py` |
| Lines of Code in a Single File | file_nloc > 500 | 600 Python, 1000 TS | partial | Not in the function comparison. `backend_map.py` trips both |
| Cognitive complexity | cognitive > 15 | none | extra | 11 functions flagged for cognitive complexity alone; it isn't a CodeScene smell |

## What to change (Step 5)

In order of effect on the score gap:

1. **Rescale the score.** Swap the per-function worst metric (30 points per 100% over the limit)
   for a per-smell deduction near CodeScene's, which is about 0.2-0.6 per smell in these runs, and
   sum the deductions across a file. This closes the large fixture gaps and the gaps on the real files.
2. **Match the thresholds and the "reaches" rule.** Use ccn >= 9, params >= 5, conditional >= 2,
   nesting >= 4 and nloc >= 70, or keep our stricter limits but note in the README that they differ.
3. **Count bumps the way CodeScene does.** Every top-level block that contains nesting 2 deep is a bump.
   Ours undercounts on 3 of 3 real cases.
4. **Score nested functions with their parent** for Complex Conditional, as CodeScene does.
5. **Add the file-level rules** Overall Code Complexity (mean cc >= 4) and, for TS only, Primitive
   Obsession.
6. **Decide on cognitive complexity.** Keep it, since it's a useful signal, but leave it out of the
   parity claims, or weight it lower.

Can't be compared from the CLI: Brain Method and Code Duplication. Our duplication check stays as
it is, with no CodeScene number to compare against.
