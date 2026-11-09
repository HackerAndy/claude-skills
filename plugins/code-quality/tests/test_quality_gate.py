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
        self.assertEqual(entries["app/orders.py::ccn::legacy_price"], 13)
        self.assertEqual(gate(self.dir, "check", "--all").returncode, 0)

    def test_hook_reports_new_findings(self):
        with open(self.dir / "app" / "orders.py", "a") as f:
            f.write(NEW_PY)
        r = self.hook("app/orders.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("shipping (86%): cognitive complexity 17 > 15", r.stderr)
        self.assertIn("ruff B006", r.stderr)
        self.assertNotIn("legacy_price", r.stderr)

    def test_hook_ignores_projects_without_quality(self):
        shutil.rmtree(self.dir / ".quality")
        self.assertEqual(self.hook("app/orders.py").returncode, 0)

    def test_functions_are_scored(self):
        r = gate(self.dir, "check", "--all", "--json")
        scores = {fn["symbol"]: fn for fn in json.loads(r.stdout)["functions"]}
        # two bumps against a limit of 1 is the worst metric: 95 - 30 * (2/1 - 1) = 65
        self.assertEqual(scores["legacy_price"]["score"], 65)
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
        self.assertFalse(fn["approved"])  # limit 3: 95 - 30 * (4/3 - 1) = 85

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
        self.assertNotIn("app/orders.py::params::legacy_price", entries)

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
        self.assertEqual(report["summary"]["new"], 2)
        self.assertEqual(report["summary"]["bands"], {"green": 3, "yellow": 1, "red": 1})
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
