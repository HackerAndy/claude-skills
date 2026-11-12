"""End-to-end tests on a copy of examples/demo. Run from the plugin folder:
    python3 -m unittest discover tests
Needs the tools the gate uses (installed, or uvx / npx to fetch them)."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
QG = PLUGIN / "skills" / "code-quality" / "scripts" / "quality_gate.py"

NEW_PY = '''

def shipping(order, cache={}):
    if order["id"] in cache:
        return cache[order["id"]]
    cost = 0
    for p in order["parcels"]:
        if p["weight"] > 10:
            if p["fragile"]:
                cost += 20
            elif p["oversize"]:
                cost += 15
            else:
                cost += 10
        elif p["weight"] > 5:
            if p["fragile"] and p["express"]:
                cost += 12
            else:
                cost += 6
        elif p["express"]:
            cost += 4
        else:
            cost += 2
    cache[order["id"]] = cost
    return cost
'''


def gate(cwd, *args, stdin=None):
    return subprocess.run([sys.executable, str(QG), *args], cwd=cwd, input=stdin,
                          capture_output=True, text=True, check=False)


class GateTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp()) / "demo"
        shutil.copytree(PLUGIN / "examples" / "demo", self.dir)
        self.assertEqual(gate(self.dir, "init", "--no-ci").returncode, 0)

    def tearDown(self):
        shutil.rmtree(self.dir.parent)

    def hook(self, file):
        return gate(self.dir, "--hook", stdin=json.dumps({"cwd": str(self.dir), "tool_input": {"file_path": file}}))

    def test_existing_code_is_baselined(self):
        entries = json.loads((self.dir / ".quality" / "baseline.json").read_text())["entries"]
        self.assertEqual(entries["app/orders.py::ccn::legacy_price"], 16)  # CodeScene's count: lizard's 13 + 3 elses
        self.assertEqual(gate(self.dir, "check", "--all").returncode, 0)

    def test_hook_reports_new_findings(self):
        with open(self.dir / "app" / "orders.py", "a") as f:
            f.write(NEW_PY)
        r = self.hook("app/orders.py")
        self.assertEqual(r.returncode, 2)
        # its costs leave 95%, but a function with findings stops at 94%
        self.assertIn("shipping (94%): 2 separate blocks of nested logic > 1, cyclomatic complexity 13 > 8, "
                      "cognitive complexity 17 > 15", r.stderr)
        self.assertIn("ruff B006", r.stderr)
        self.assertNotIn("legacy_price", r.stderr)

    def test_hook_ignores_projects_without_quality(self):
        shutil.rmtree(self.dir / ".quality")
        self.assertEqual(self.hook("app/orders.py").returncode, 0)

    def test_functions_are_scored(self):
        r = gate(self.dir, "check", "--all", "--json")
        scores = {fn["symbol"]: fn for fn in json.loads(r.stdout)["functions"]}
        # CodeScene's costs, multiplied: cc 16 (0.446), 6 parameters (0.32), 3 bumps (0.16);
        # cognitive isn't charged alongside cc. 100 * 0.9554 * 0.968 * 0.984 = 91 (CodeScene: 9.11 for the file)
        self.assertEqual(scores["legacy_price"]["score"], 91)
        self.assertEqual(scores["legacy_price"]["values"]["ccn"], 16)  # CodeScene: cc = 16
        self.assertEqual(scores["legacy_price"]["values"]["bumps"], 3)
        self.assertFalse(scores["legacy_price"]["approved"])
        self.assertTrue(scores["subtotal"]["approved"])

    def test_deep_nesting_is_a_finding(self):
        lines = ["def deep(a):", "    if a:", "        for x in a:", "            if x:",
                 "                while x:", "                    x -= 1", "    return a"]
        src = "\n".join(lines) + "\n"
        (self.dir / "app" / "deep.py").write_text(src)
        r = gate(self.dir, "check", "--all", "--json")
        fn = {f["symbol"]: f for f in json.loads(r.stdout)["functions"]}["deep"]
        self.assertEqual(fn["values"]["nesting"], 4)
        self.assertFalse(fn["approved"])  # limit 3: CodeScene's Deep, Nested Complexity at 4

    def test_conditions_and_bumps_are_measured_in_python_and_typescript(self):
        py_src = ["def f(a, b, c, d):", "    if a and b or c and d:", "        pass",
                  "    if a:", "        if b:", "            pass", "    if c:", "        if d:", "            pass"]
        ts_src = ["export function g(a: boolean, b: boolean, c: boolean, d: boolean) {",
                  "  if (a && b || c && d) { return 1 }",
                  "  if (a) { if (b) { return 2 } }",
                  "  if (c) { if (d) { return 3 } }",
                  "  return 0", "}"]
        (self.dir / "app" / "many.py").write_text("\n".join(py_src) + "\n")
        (self.dir / "web" / "many.ts").write_text("\n".join(ts_src) + "\n")
        r = gate(self.dir, "check", "--all", "--json")
        fns = {(f["file"], f["symbol"]): f["values"] for f in json.loads(r.stdout)["functions"]}
        for key in (("app/many.py", "f"), ("web/many.ts", "g")):
            self.assertEqual((fns[key]["conditional"], fns[key]["bumps"], fns[key]["nesting"]), (3, 2, 2), key)

    def test_bumps_are_counted_as_codescene_counts_them(self):
        # A loop around branches is one bump; each branch of an if chain holding nested logic is its own
        # bump, inside a loop too; a ternary counts as nested logic. CodeScene: 1, 3 and 2 bumps.
        src = ["def loop(xs):", "    for x in xs:", "        if x:", "            x += 1", "        if x > 2:",
               "            x -= 1", "    return xs",
               "", "def chain(xs, k):", "    for x in xs:", "        if k == 1:", "            if x:", "                x += 1",
               "        elif k == 2:", "            if x:", "                x -= 1", "        else:", "            x = 0",
               "    if k:", "        if xs:", "            k = 1", "    return k",
               "", "def tern(xs, k):", "    if not k:", "        k = 1 if xs else 2", "    for x in xs:",
               "        if x:", "            k += 1", "    return k"]
        (self.dir / "app" / "bumps.py").write_text("\n".join(src) + "\n")
        r = gate(self.dir, "check", "--all", "--json")
        bumps = {f["symbol"]: f["values"]["bumps"] for f in json.loads(r.stdout)["functions"] if f["file"] == "app/bumps.py"}
        self.assertEqual(bumps, {"loop": 1, "chain": 3, "tern": 2})

    def test_nested_functions_fold_into_their_parent(self):
        # CodeScene (cs 1.0.58) reports only outer: cc 15 (8 + 8 - 1) and 2 bumps (1 + 1); inner's 6 parameters don't count.
        src = ["def outer(x):", *[f"    if x == {i}:\n        x += 1" for i in range(5)],
               "    if x:", "        if x > 1:", "            x = 1",
               "    def inner(a, b, c, d, e, f):", *[f"        if a == {i}:\n            a += 1" for i in range(5)],
               "        if b:", "            if c:", "                b = c",
               "        return a", "    return inner(x, x, x, x, x, x)"]
        (self.dir / "app" / "nested.py").write_text("\n".join(src) + "\n")
        r = gate(self.dir, "check", "--all", "--json")
        fns = {f["symbol"]: f["values"] for f in json.loads(r.stdout)["functions"] if f["file"] == "app/nested.py"}
        self.assertEqual(list(fns), ["outer"])
        self.assertEqual((fns["outer"]["ccn"], fns["outer"]["bumps"], fns["outer"]["params"]), (15, 2, 1))

    def test_scores_match_codescene(self):
        # File scores CodeScene (cs 1.0.58) gives these files: one cc 15 function 9.58; two functions
        # with 6 parameters 9.68 (charged once per file); cc 15 plus 6 parameters 9.27.
        cc15 = "def f(code):\n" + "".join(f"    {'if' if i == 0 else 'elif'} code == {i}:\n        return {i}\n"
                                          for i in range(14)) + "    return -1\n"
        args6 = "\n\ndef g{n}(a, b, c, d, e, f):\n    return [a, b, c, d, e, f]\n"
        for name, src, want in (("one.py", cc15, 9.6), ("two.py", args6.format(n=1) + args6.format(n=2), 9.7),
                                ("both.py", cc15 + args6.format(n=1), 9.3)):
            (self.dir / "app" / name).write_text(src)
            r = gate(self.dir, "score", f"app/{name}", "--json")
            self.assertEqual(json.loads(r.stdout)["scores"]["health"], want, name)
            (self.dir / "app" / name).unlink()  # the next sample reuses this code, which would be a duplicate

    def test_copied_code_is_flagged_when_a_file_is_checked(self):
        src = (self.dir / "app" / "orders.py").read_text()
        (self.dir / "app" / "orders_copy.py").write_text(src)
        r = gate(self.dir, "check", "app/orders_copy.py", "--json")
        rules = [(f["file"], f["rule"]) for f in json.loads(r.stdout)["new"]]
        self.assertIn(("app/orders_copy.py", "duplicate"), rules)

    def test_minified_and_ignored_files_are_skipped(self):
        (self.dir / "web" / "bundle.js").write_text("function a(b){" + "if(b){b++}" * 200 + "}\n")
        r = gate(self.dir, "check", "--all", "--json")
        self.assertNotIn("web/bundle.js", json.loads(r.stdout)["scores"]["files"])

    def test_each_package_uses_its_own_config(self):
        # A sub-package whose ruff config selects the magic-number rule; the demo root doesn't.
        pkg = self.dir / "svc"
        pkg.mkdir()
        (pkg / "pyproject.toml").write_text('[tool.ruff.lint]\nselect = ["PLR2004"]\n')
        (pkg / "rates.py").write_text("def rate(x):\n    return x > 42\n")
        r = gate(self.dir, "check", "svc/rates.py")
        self.assertIn("ruff PLR2004", r.stdout)

    def test_baseline_lowers_as_code_improves(self):
        src = self.dir / "app" / "orders.py"
        src.write_text(src.read_text().replace("coupon, season, rush)", "coupon, season)")
                       .replace("    if rush:", "    if season == 'rush':"))
        self.assertEqual(gate(self.dir, "check", "app/orders.py").returncode, 0)
        entries = json.loads((self.dir / ".quality" / "baseline.json").read_text())["entries"]
        self.assertEqual(entries["app/orders.py::params::legacy_price"], 5)  # was 6; CodeScene flags 5 too

    def test_targets_lists_functions_below_95(self):
        r = gate(self.dir, "targets", "--json")
        rows = json.loads(r.stdout)
        self.assertEqual([row["symbol"] for row in rows], ["legacy_price"])
        self.assertIn("cognitive complexity 21 > 15", rows[0]["why"])
        self.assertEqual(json.loads(gate(self.dir, "targets", "web", "--json").stdout), [])

    def test_score_passes_only_when_the_function_is_approved(self):
        self.assertEqual(gate(self.dir, "score", "app/orders.py", "--symbol", "subtotal").returncode, 0)
        r = gate(self.dir, "score", "app/orders.py", "--symbol", "legacy_price")
        self.assertEqual(r.returncode, 1)
        self.assertIn("LOW  app/orders.py", r.stdout)

    def test_report_page_and_json_follow_each_check(self):
        page = self.dir / ".quality" / "report.html"
        self.assertTrue(page.is_file())
        self.assertNotIn("/*__REPORT__*/null", page.read_text(encoding="utf-8"))
        self.assertIn("__pycache__/", (self.dir / ".quality" / ".gitignore").read_text(encoding="utf-8").splitlines())
        with open(self.dir / "app" / "orders.py", "a") as f:
            f.write(NEW_PY)
        self.hook("app/orders.py")
        report = json.loads((self.dir / ".quality" / "report.json").read_text())
        self.assertEqual(report["summary"]["new"], 4)  # shipping's bumps, cc and cognitive, and ruff B006
        # cart.ts's reduce callback is folded into cartTotal, so 4 functions, not 5
        self.assertEqual(report["summary"]["bands"], {"green": 2, "yellow": 2, "red": 0})
        self.assertEqual(report["folders"][0]["path"], "app")
        self.assertEqual(report["targets"][0]["symbol"], "legacy_price")
        self.assertIn("web/cart.ts", report["files"])

    def test_report_explains_a_low_function_with_its_code(self):
        with open(self.dir / "app" / "orders.py", "a") as f:
            f.write(NEW_PY)
        self.hook("app/orders.py")
        report = json.loads((self.dir / ".quality" / "report.json").read_text())
        entry = report["files"]["app/orders.py"]
        legacy = next(fn for fn in entry["functions"] if fn["symbol"] == "legacy_price")
        # every place lizard counts a path is marked: one per decision, the function itself is the first
        self.assertEqual(len(legacy["code"]["branches"]), legacy["values"]["ccn"] - 1)
        self.assertTrue(legacy["code"]["lines"][0].startswith("def legacy_price"))
        b006 = next(f for f in entry["findings"] if f["rule"] == "ruff:B006")
        self.assertEqual(entry["functions"][-1]["code"]["lines"][0][b006["col"] - 1:b006["end_col"] - 1], "{}")
        self.assertIn("mutable", report["rules"]["ruff:B006"]["what"])
        self.assertIn("ccn", report["metrics"])


if __name__ == "__main__":
    unittest.main()
