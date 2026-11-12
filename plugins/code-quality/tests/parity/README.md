# CodeScene parity corpus

Small files, one code smell each, used to compare `quality-gate` with CodeScene's Code Health
(see `docs/plans/code-quality-codescene-parity.md` at the repo root). There's no `.quality/` folder
here or above, so the gate's edit hook leaves these deliberately bad files alone, and
`unittest discover` skips them because no file name starts with `test`.

- `fixtures/py/`, `fixtures/ts/`: the fixtures. The TS files mirror the Python ones.
- `results/codescene-thresholds-*.json`: CodeScene's default thresholds, from
  `cs rules-config list-thresholds --language <Python|TypeScript> --format json` (cs 1.0.58).
- Real files compared too: `../../examples/demo/app/orders.py` (`legacy_price`),
  `../../skills/code-quality/scripts/qg_checks.py`, `../../skills/code-quality/scripts/quality_gate.py`,
  `../../../backend-viz/skills/backend-viz/scripts/backend_map.py`.

## Fixtures and what `cs review` reports (cs 1.0.58, 2026-11-12)

| Fixture (py / ts) | Target smell | CodeScene score | CodeScene findings |
|---|---|---|---|
| `nested_complexity` / `nestedComplexity` | Nested Complexity | 9.38 / 9.38 | Deep, Nested Complexity (depth 5; loops count) |
| `complex_conditional` / `complexConditional` | Complex Conditional | 9.53 / 9.53 | Complex Conditional |
| `bumpy_road` / `bumpyRoad` | Bumpy Road | 9.84 / 9.84 | Bumpy Road Ahead (3 bumps) |
| `complex_method` / `complexMethod` | Complex Method | 9.6 / 9.6 | Complex Method (cc 14) |
| `large_method` | Large Method | 9.55 | Large Method (79 LoC) |
| `brain_method` | Brain Method | 7.97 | Bumpy Road, Nested, Complex Method, Large Method; **no Brain Method** |
| `dry_violation` | Code Duplication | 10.0 | **none**: `cs review` never reported duplication, even for 3 identical 25-line functions |
| `primitive_obsession` / `primitiveObsession` | Primitive Obsession | 10.0 / 9.38 | TS: Primitive Obsession + String Heavy Function Arguments. **Python: none**, even with type hints |
| `excess_arguments` / `excessArguments` | Excess Function Arguments | 9.68 / 9.68 | Excess Number of Function Arguments (6) |
| `clean` / `clean` | none (control) | 10.0 / 10.0 | none |

Notes:
- Primitive Obsession needs a minimum function count before its 30% rule applies. Five all-primitive
  functions scored 10.0; fifteen fired it.
- Duplication and Brain Method may need `cs delta` or a full CodeScene project analysis instead of
  `cs review`. Step 4 checks.
- `cs` runs git, so run it inside a git work tree.
