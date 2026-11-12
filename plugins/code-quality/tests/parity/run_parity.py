#!/usr/bin/env python3
"""Run quality-gate and CodeScene's `cs review` on the same files and compare them.

    python3 tests/parity/run_parity.py [--root DIR] [--out FILE] [--cs PATH]
    python3 tests/parity/run_parity.py --resummarise FILE   # recompute a results file's summary

Without --root it compares the parity corpus (fixtures/ plus a few real files) and writes
results/parity.json. With --root it compares every source file git tracks in that repo; give
--out somewhere outside this repo for code that isn't public. Either way the files are copied into
a temporary git repo (cs needs one) with its own .quality/, so the source stays untouched.
Needs `cs` with CS_ACCESS_TOKEN set.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent.parent
GATE = PLUGIN / "skills" / "code-quality" / "scripts" / "quality_gate.py"
sys.path.insert(0, str(GATE.parent))
import qg_checks as qc  # noqa: E402
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


def copy(sources, work):
    """sources: {name in the copy: path}. Returns the names."""
    for name, src in sources.items():
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, work / name)
    return sorted(sources)


def corpus():
    fixtures = {str(p.relative_to(HERE)): p for p in (HERE / "fixtures").rglob("*") if p.suffix in (".py", ".ts")}
    return fixtures | REAL


def tracked(root):
    """Every source file git tracks under root (or, outside git, every one the gate would walk), minified and
    generated ones left out."""
    listed = run(["git", "ls-files"], root)
    names = listed.stdout.splitlines() if listed.returncode == 0 else [qc.rel(root, p) for p in qc.walk_files(root)]
    return {n: root / n for n in names
            if Path(n).suffix in qc.SOURCE_EXT and (root / n).is_file() and not qc.looks_generated(root / n)}


def gate(work):
    """{file: {health, functions}} from one check of the whole copy."""
    out = json.loads(run([sys.executable, str(GATE), "check", "--all", "--json"], work).stdout)
    files = {}
    for fn in out["functions"]:
        files.setdefault(fn["file"], []).append(fn)
    return {f: {"health": qc.ten(qc.health(fns)),
                "functions": {fn["symbol"]: {"score": fn["score"], "values": fn["values"], "smells": fn["smells"]}
                              for fn in fns}}
            for f, fns in files.items()}


def codescene(work, name, cs):
    try:
        out = json.loads(run([cs, "review", name, "--output-format", "json"], work).stdout)
    except json.JSONDecodeError:
        return {"score": None, "functions": {}}
    fns = {}
    for r in out.get("review", []):
        for fn in r.get("functions", []):
            fns.setdefault(fn["title"], []).append(f"{r['category']} ({fn.get('details', '')})")
        if not r.get("functions"):
            fns.setdefault("(file)", []).append(r["category"])
    return {"score": out.get("score"), "functions": fns}


def smells_over(limits, values, file):
    limits = qc.limits_for(limits, file)
    return sorted(SMELL[m] for m, v in values.items() if v > limits[m])


def rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out, i = [0.0] * len(xs), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2
        i = j + 1
    return out


def spearman(a, b):
    ra, rb = rank(a), rank(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    var = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return cov / var if var else None


def short(name):
    """A function's own name: CodeScene says Class.method, lizard says method, and
    lizard names a second function of the same name f#2."""
    return re.sub(r"#\d+$", "", name).split(".")[-1]


def smell_sets(row):
    ours = {(short(fn), s) for fn, d in row["gate"]["functions"].items()
            for s in d["smells_over_limit"] if s != "(cognitive)"}
    theirs = {(short(re.sub(r":\d+$", "", k)), re.sub(r" \(.*", "", c))
              for k, v in row["codescene"]["functions"].items() for c in v}
    return ours, theirs


def summary(rows):
    scored = [r for r in rows if r["codescene"]["score"] is not None and r["gate"]["health"] is not None]
    a, b = [r["gate"]["health"] for r in scored], [r["codescene"]["score"] for r in scored]
    gaps = sorted(((x - y, r["file"]) for r, x, y in zip(scored, a, b)), key=lambda g: -abs(g[0]))
    by = {}
    for r in rows:
        ours, theirs = smell_sets(r)
        for kind, items in (("hit", ours & theirs), ("miss", theirs - ours), ("extra", ours - theirs)):
            for _, smell in items:
                by.setdefault(smell, {"hit": 0, "miss": 0, "extra": 0})[kind] += 1
    sp = spearman(a, b) if len(a) > 1 else None
    return {"files": len(rows), "scored": len(scored),
            "mean_abs_gap": round(sum(abs(g) for g, _ in gaps) / len(gaps), 2) if gaps else None,
            "within_0_5": sum(abs(g) <= 0.5 for g, _ in gaps), "spearman": round(sp, 2) if sp is not None else None,
            "smells": dict(sorted(by.items())), "worst": [{"file": f, "gap": round(g, 2)} for g, f in gaps[:15]]}


def resummarise(path):
    """Recompute the summary of a results file, after a change to how smells are matched."""
    result = json.loads(Path(path).read_text())
    result["summary"] = summary(result["files"])
    Path(path).write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result["summary"], indent=1))


def main(argv):
    cs = argv[argv.index("--cs") + 1] if "--cs" in argv else shutil.which("cs") or str(Path.home() / ".local/bin/cs")
    root = Path(argv[argv.index("--root") + 1]).resolve() if "--root" in argv else None
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else HERE / "results" / "parity.json"
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        files = copy(tracked(root) if root else corpus(), work)
        run(["git", "init", "-q"], work)
        run([sys.executable, str(GATE), "init", "--no-ci"], work)
        ours_all = gate(work)
        rows = []
        for name in files:
            ours = ours_all.get(name, {"health": None, "functions": {}})
            theirs = codescene(work, name, cs)
            for fn in ours["functions"].values():
                fn["smells_over_limit"] = smells_over(DEFAULTS["limits"], fn["values"], name)
            rows.append({"file": name, "gate": ours, "codescene": theirs})
            print(f"{name:60} gate {ours['health']}  cs {theirs['score']}")
    result = {"source": root.name if root else "parity corpus", "summary": summary(rows), "files": rows}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result["summary"], indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    if "--resummarise" in sys.argv:
        resummarise(sys.argv[sys.argv.index("--resummarise") + 1])
    else:
        main(sys.argv[1:])
