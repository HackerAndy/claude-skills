#!/usr/bin/env python3
"""Run quality-gate and CodeScene's `cs review` on the parity corpus and write results/parity.json.

    python3 tests/parity/run_parity.py [--cs PATH]

The corpus is copied into a temporary git repo (cs needs one) with its own .quality/, so this
repo stays untouched. Needs `cs` with CS_ACCESS_TOKEN set.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent.parent
GATE = PLUGIN / "skills" / "code-quality" / "scripts" / "quality_gate.py"
sys.path.insert(0, str(GATE.parent))
from quality_gate import DEFAULTS  # noqa: E402

REAL = {
    "real/orders.py": PLUGIN / "examples" / "demo" / "app" / "orders.py",
    "real/qg_checks.py": PLUGIN / "skills" / "code-quality" / "scripts" / "qg_checks.py",
    "real/quality_gate.py": GATE,
    "real/backend_map.py": PLUGIN.parent / "backend-viz" / "skills" / "backend-viz" / "scripts" / "backend_map.py",
}
# Our metric over its limit -> the CodeScene smell it stands for. cognitive has no CodeScene twin.
SMELL = {"ccn": "Complex Method", "nesting": "Deep, Nested Complexity", "conditional": "Complex Conditional",
         "bumps": "Bumpy Road Ahead", "params": "Excess Number of Function Arguments", "nloc": "Large Method",
         "cognitive": "(cognitive)"}


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def corpus(work):
    files = []
    for src in sorted((HERE / "fixtures").rglob("*")):
        if src.suffix in (".py", ".ts"):
            files.append(str(src.relative_to(HERE)))
            dest = work / files[-1]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dest)
    for name, src in REAL.items():
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, work / name)
        files.append(name)
    return files


def gate(work, name):
    out = json.loads(run([sys.executable, str(GATE), "score", name, "--json"], work).stdout)
    fns = {}
    for fn in out["functions"]:
        fns[fn["symbol"]] = {"score": fn["score"], "values": fn["values"], "smells": fn["smells"]}
    return {"health": out["scores"]["health"], "functions": fns}


def codescene(work, name, cs):
    out = json.loads(run([cs, "review", name, "--output-format", "json"], work).stdout)
    fns = {}
    for r in out["review"]:
        for fn in r.get("functions", []):
            fns.setdefault(fn["title"], []).append(f"{r['category']} ({fn.get('details', '')})")
        if not r.get("functions"):
            fns.setdefault("(file)", []).append(r["category"])
    return {"score": out["score"], "functions": fns}


def smells_over(limits, values):
    return sorted(SMELL[m] for m, v in values.items() if v > limits[m])


def main(argv):
    cs = argv[argv.index("--cs") + 1] if "--cs" in argv else shutil.which("cs") or str(Path.home() / ".local/bin/cs")
    limits = DEFAULTS["limits"]
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        files = corpus(work)
        run(["git", "init", "-q"], work)
        run([sys.executable, str(GATE), "init", "--no-ci"], work)
        rows = []
        for name in files:
            ours, theirs = gate(work, name), codescene(work, name, cs)
            for fn in ours["functions"].values():
                fn["smells_over_limit"] = smells_over(limits, fn["values"])
            rows.append({"file": name, "gate": ours, "codescene": theirs})
            print(f"{name:42} gate {ours['health']:>4}  cs {theirs['score']}")
    (HERE / "results" / "parity.json").write_text(json.dumps(rows, indent=1) + "\n")
    print(f"wrote {HERE / 'results' / 'parity.json'}")


if __name__ == "__main__":
    main(sys.argv[1:])
