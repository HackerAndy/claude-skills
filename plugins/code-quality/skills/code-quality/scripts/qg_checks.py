"""
The checks behind quality_gate.py: which files count, which tools run them, and the per-function scores.

A check run carries a context dict, `ctx`: {root, conf, cache (tool lookups), ran (tools that ran),
missing (tools that were needed but not found)}. Tools run per package, the nearest folder with the
package's own config (pyproject.toml, package.json, biome.json, tsconfig.json ...), so a monorepo's
backend and frontend each use their own settings, .venv and node_modules.
"""
import csv
import fnmatch
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

SKIP_DIRS = {"node_modules", ".git", "venv", ".venv", "env", "__pycache__", "dist", "build", ".next",
             "coverage", "site-packages", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".quality",
             ".tox", ".turbo", "out"}
PY_EXT = {".py"}
JS_EXT = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"}
SOURCE_EXT = PY_EXT | JS_EXT
# Config files only: a setup.py can just as well be an ordinary module.
PY_MARKERS = ("pyproject.toml", "setup.cfg", "ruff.toml", ".ruff.toml", "mypy.ini", "pyrightconfig.json")
JS_MARKERS = ("package.json", "biome.json", "biome.jsonc", "tsconfig.json")
MINIFIED_LINE = 1000  # a file with a line this long is generated or minified, not written by hand

METRICS = {  # rule -> how the message reads
    "ccn": "cyclomatic complexity {v} > {limit}",
    "cognitive": "cognitive complexity {v} > {limit}",
    "nloc": "{v} lines of code > {limit}",
    "params": "{v} parameters > {limit}",
    "nesting": "nested {v} levels deep > {limit}",
}
APPROVED = 95    # a function scoring at least this is approved: 9.5 on CodeScene's 1-10 Code Health scale,
                 # the level it recommends for code that AI agents will work in
SMELL_COST = 5   # points per lint finding inside the function
CHURN_DAYS = 180  # how far back a file's commits count toward refactoring priority


# ---------------------------------------------------------------- files and packages

def rel(root, path):
    return Path(os.path.relpath(Path(path).resolve(), root)).as_posix()


def looks_generated(path):
    try:
        with open(path, "rb") as f:
            head = f.read(65536)
    except OSError:
        return True
    return any(len(line) > MINIFIED_LINE for line in head.splitlines())


def in_scope(root, conf, path):
    r = rel(root, path)
    if r.startswith("../") or Path(r).suffix not in SOURCE_EXT:
        return False
    if any(part in SKIP_DIRS for part in Path(r).parts[:-1]):
        return False
    if any(fnmatch.fnmatch(r, pat) for pat in conf["scope"]["exclude"]):
        return False
    return not looks_generated(path)


def git(root, *args):
    r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=root, capture_output=True,
                       text=True, check=False)
    return r.stdout.splitlines() if r.returncode == 0 else None


def walk_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        yield from (Path(dirpath) / n for n in sorted(filenames))


def all_files(root, conf):
    """Source files in scope: what git tracks or would track (so .gitignore counts), else a walk."""
    listed = git(root, "ls-files", "--cached", "--others", "--exclude-standard")
    paths = (root / p for p in listed) if listed is not None else walk_files(root)
    return sorted(p for p in paths if p.is_file() and in_scope(root, conf, p))


def changed_files(root, conf, base=None):
    top = git(root, "rev-parse", "--show-toplevel")
    if not top:
        return all_files(root, conf)
    names = git(root, "diff", "--name-only", f"{base}...HEAD" if base else "HEAD") or []
    if not base:
        names += git(root, "ls-files", "--others", "--exclude-standard", "--full-name") or []
    files = {Path(top[0]) / n for n in names}
    return sorted(f for f in files if f.is_file() and in_scope(root, conf, f))


def package_of(root, path, markers):
    """The nearest folder at or above path holding one of markers, stopping at root."""
    for d in Path(path).resolve().parents:
        if d == root or not d.is_relative_to(root):
            return root
        if any((d / m).is_file() for m in markers):
            return d
    return root


def by_package(root, files, exts, markers):
    groups = {}
    for f in files:
        if f.suffix in exts:
            groups.setdefault(package_of(root, f, markers), []).append(f)
    return groups


# ---------------------------------------------------------------- tools

DOWNLOAD = {  # how to run a tool that isn't installed, at its pinned version
    "lizard": lambda v: ["uvx", f"lizard=={v}"],
    "ruff": lambda v: ["uvx", f"ruff=={v}"],
    "biome": lambda v: ["npx", "--yes", f"@biomejs/biome@{v}"],
    "pyright": lambda v: ["npx", "--yes", f"pyright@{v}"],
    "jscpd": lambda v: ["npx", "--yes", f"jscpd@{v}"],
}  # tsc and mypy are never downloaded: type checking must use the project's own version


def installed(name, pkg, root):
    """The package's own install of a tool: its .venv / node_modules, or a parent's up to root."""
    dirs = [pkg, *(p for p in pkg.parents if p.is_relative_to(root))]
    found = (d / sub / name for d in dirs for sub in (".venv/bin", "node_modules/.bin"))
    return next(([str(p)] for p in found if p.is_file()), None)


def locate(name, pkg, root, conf):
    """The package's own install first, then PATH, then a pinned download."""
    if cmd := installed(name, pkg, root):
        return cmd
    if shutil.which(name):
        return [name]
    if name == "lizard" and run([sys.executable, "-c", "import lizard"], root).returncode == 0:
        return [sys.executable, "-m", "lizard"]
    if name in DOWNLOAD and conf["tools"]["download"]:
        cmd = DOWNLOAD[name](conf["tools"]["pins"][name])
        if shutil.which(cmd[0]):
            return cmd
    return None


def tool(ctx, name, pkg=None):
    """The command for a tool in a package, noting in ctx whether it ran or was missing."""
    k = (name, pkg or ctx["root"])
    if k not in ctx["cache"]:
        ctx["cache"][k] = locate(name, pkg or ctx["root"], ctx["root"], ctx["conf"])
    ctx["ran" if ctx["cache"][k] else "missing"].add(name)
    return ctx["cache"][k]


def run(cmd, cwd, timeout=600):
    cmd = [shutil.which(cmd[0]) or cmd[0], *cmd[1:]]  # Windows: npx is npx.cmd, which subprocess can't find by name
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)


def run_json(cmd, cwd, default):
    try:
        return json.loads(run(cmd, cwd).stdout or "null") or default
    except json.JSONDecodeError:
        return default


def finding(file, line, rule, message, **metric):
    """metric: symbol, value and limit, for per-function and per-file measurements."""
    return {"file": file, "line": line, "rule": rule, "message": message,
            "symbol": None, "value": None, "limit": None, **metric}


# ---------------------------------------------------------------- per-file checks

def code_lines(path):
    return sum(1 for ln in path.read_text(errors="replace").splitlines()
               if ln.strip() and not ln.strip().startswith(("#", "//")))


def check_file_size(ctx, files):
    limit = ctx["conf"]["limits"]["file_nloc"]
    sizes = {f: code_lines(f) for f in files}
    return [finding(rel(ctx["root"], f), 1, "file_nloc", f"file has {n} lines of code > {limit}; split the module",
                    symbol="<file>", value=n, limit=limit)
            for f, n in sizes.items() if n > limit]


def lizard_functions(ctx, files):
    """One {file, symbol, line, end, values} per function, from lizard's CSV output."""
    cmd = tool(ctx, "lizard") if files else None
    if not cmd:
        return []
    r = run([*cmd, "--csv", "-Ecognitive", "-ENS", *map(str, files)], ctx["root"])
    seen, out = {}, []
    for row in csv.reader(io.StringIO(r.stdout)):
        if len(row) < 12:
            continue
        # nloc, ccn, tokens, params, length, location, file, name, long name, start, end, cognitive, nesting
        file, name = rel(ctx["root"], row[6]), row[7]
        seen[(file, name)] = seen.get((file, name), 0) + 1
        symbol = name if seen[(file, name)] == 1 else f"{name}#{seen[(file, name)]}"
        values = {"ccn": int(row[1]), "cognitive": int(row[11]), "nloc": int(row[0]), "params": int(row[3]),
                  "nesting": int(row[12]) if len(row) > 12 else 0}
        out.append({"file": file, "symbol": symbol, "line": int(row[9]), "end": int(row[10]), "values": values})
    return out


def check_functions(conf, functions):
    limits = conf["limits"]
    return [finding(fn["file"], fn["line"], metric, METRICS[metric].format(v=v, limit=limits[metric]),
                    symbol=fn["symbol"], value=v, limit=limits[metric])
            for fn in functions for metric, v in fn["values"].items() if v > limits[metric]]


def check_ruff(ctx, files):
    out = []
    extend = ctx["conf"]["lint"]["ruff_extend_select"]
    for pkg, group in by_package(ctx["root"], files, PY_EXT, PY_MARKERS).items():
        cmd = tool(ctx, "ruff", pkg)
        if not cmd:
            continue
        cmd = [*cmd, "check", "--output-format", "json", "--no-fix", "--force-exclude", "--quiet"]
        cmd += ["--extend-select", ",".join(extend)] if extend else []
        out += [finding(rel(ctx["root"], i["filename"]), i["location"]["row"], f"ruff:{i['code'] or 'syntax'}",
                        i["message"], **span(i["location"], i.get("end_location"), "row"))
                for i in run_json([*cmd, *map(str, group)], pkg, [])]
    return out


def span(start, end, row):
    """Where on its lines a finding is: 1-based columns, the end one past the last character."""
    end = end or {}
    return {"col": start.get("column"), "end_line": end.get(row), "end_col": end.get("column")}


def biome_finding(root, pkg, d):
    loc = d.get("location") or {}
    if d.get("severity") not in ("error", "warning") or not loc.get("path"):
        return None
    return finding(rel(root, pkg / loc["path"]), loc["start"]["line"],
                   f"biome:{d['category'].removeprefix('lint/')}", d["message"],
                   **span(loc["start"], loc.get("end"), "line"))


def check_biome(ctx, files):
    if not ctx["conf"]["lint"]["biome"]:
        return []
    out = []
    for pkg, group in by_package(ctx["root"], files, JS_EXT, JS_MARKERS).items():
        cmd = tool(ctx, "biome", pkg)
        if not cmd:
            continue
        cmd = [*cmd, "lint", "--reporter=json", "--no-errors-on-unmatched", "--max-diagnostics=500"]
        diags = run_json([*cmd, *map(str, group)], pkg, {}).get("diagnostics", [])
        out += [f for f in (biome_finding(ctx["root"], pkg, d) for d in diags) if f]
    return out


# ---------------------------------------------------------------- project-wide checks (--full)

def uses_mypy(pkg):
    if (pkg / "mypy.ini").is_file() or (pkg / ".mypy.ini").is_file():
        return True
    py = pkg / "pyproject.toml"
    return py.is_file() and "mypy" in tomllib.loads(py.read_text()).get("tool", {})


def check_mypy(ctx, pkg):
    cmd = tool(ctx, "mypy", pkg)
    if not cmd:
        return []
    conf = tomllib.loads((pkg / "pyproject.toml").read_text()) if (pkg / "pyproject.toml").is_file() else {}
    targets = [] if conf.get("tool", {}).get("mypy", {}).get("files") else ["."]
    r = run([*cmd, "--output", "json", "--no-error-summary", *targets], pkg)
    out = []
    for line in r.stdout.splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("severity") == "error" and in_scope(ctx["root"], ctx["conf"], pkg / d["file"]):
            out.append(finding(rel(ctx["root"], pkg / d["file"]), d["line"], f"mypy:{d.get('code') or 'error'}",
                               d["message"]))
    return out


def check_pyright(ctx, pkg):
    cmd = tool(ctx, "pyright", pkg)
    if not cmd:
        return []
    venv_python = pkg / ".venv" / "bin" / "python"
    extra = ["--pythonpath", str(venv_python)] if venv_python.is_file() else []
    diags = run_json([*cmd, "--outputjson", *extra], pkg, {}).get("generalDiagnostics", [])
    return [finding(rel(ctx["root"], d["file"]), d["range"]["start"]["line"] + 1,
                    f"pyright:{d.get('rule', 'error')}", d["message"].splitlines()[0])
            for d in diags if d.get("severity") == "error" and in_scope(ctx["root"], ctx["conf"], d["file"])]


TSC_LINE = re.compile(r"^(.+?)\((\d+),(\d+)\): error (TS\d+): (.*)$")


def check_tsc(ctx, pkg):
    cmd = tool(ctx, "tsc", pkg)
    if not cmd:
        return []
    r = run([*cmd, "--noEmit", "--pretty", "false", "-p", "tsconfig.json"], pkg)
    matches = (TSC_LINE.match(line) for line in r.stdout.splitlines())
    return [finding(rel(ctx["root"], pkg / m[1]), int(m[2]), f"tsc:{m[4]}", m[5], col=int(m[3]))
            for m in matches if m and in_scope(ctx["root"], ctx["conf"], pkg / m[1])]


def check_types(ctx, files):
    """Each Python package with mypy configured runs mypy, others pyright; each tsconfig.json runs tsc."""
    root = ctx["root"]
    out = []
    for pkg in by_package(root, files, PY_EXT, PY_MARKERS):
        out += check_mypy(ctx, pkg) if uses_mypy(pkg) else check_pyright(ctx, pkg)
    for pkg in by_package(root, files, JS_EXT, ("tsconfig.json",)):
        out += check_tsc(ctx, pkg) if (pkg / "tsconfig.json").is_file() else []
    return out


def check_duplication(ctx):
    cmd = tool(ctx, "jscpd")
    if not cmd:
        return []
    root, conf = ctx["root"], ctx["conf"]
    ignore = ",".join([f"**/{d}/**" for d in sorted(SKIP_DIRS)] + conf["scope"]["exclude"])
    with tempfile.TemporaryDirectory() as tmp:
        run([*cmd, "--reporters", "json", "--output", tmp, "--silent", "--min-tokens", str(conf["full"]["min_tokens"]),
             "--ignore", ignore, "--format", "python,javascript,typescript,jsx,tsx", "."], root)
        report = Path(tmp) / "jscpd-report.json"
        dups = json.loads(report.read_text()).get("duplicates", []) if report.is_file() else []
    return [finding(rel(root, root / d["firstFile"]["name"]), d["firstFile"]["start"], "duplicate",
                    f"{d['lines']} lines duplicated in {rel(root, root / d['secondFile']['name'])}"
                    f":{d['secondFile']['start']}-{d['secondFile']['end']}")
            for d in dups if in_scope(root, conf, root / d["firstFile"]["name"])]


# ---------------------------------------------------------------- scores

def metric_score(value, limit):
    """100 at zero, APPROVED exactly at the limit, then 30 points lost per 100% over it."""
    r = value / limit
    return 100 - (100 - APPROVED) * r if r <= 1 else APPROVED - 30 * (r - 1)


def innermost(functions, f):
    """The smallest function whose lines contain finding f, if any."""
    around = [fn for fn in functions if fn["file"] == f["file"] and fn["line"] <= f["line"] <= fn["end"]]
    return min(around, key=lambda fn: fn["end"] - fn["line"], default=None)


def source_of(rule):
    return rule.split(":")[0] if ":" in rule else ("jscpd" if rule == "duplicate" else "lizard")


def score_functions(conf, functions, findings):
    """Score each function 0-100: its worst metric against the limits, less SMELL_COST per lint
    finding inside it. Averages over files are for reading only; approval is per function."""
    smells = {}
    for f in findings:
        fn = innermost(functions, f) if source_of(f["rule"]) in ("ruff", "biome") else None
        if fn:
            smells[id(fn)] = smells.get(id(fn), 0) + 1
    limits = conf["limits"]
    for fn in functions:
        worst = min(metric_score(v, limits[m]) for m, v in fn["values"].items())
        fn["smells"] = smells.get(id(fn), 0)
        fn["score"] = max(0, round(worst - SMELL_COST * fn["smells"]))
        fn["approved"] = fn["score"] >= APPROVED
    return functions


def reasons(conf, fn):
    """Why a function scores what it does: its metrics over the limits, and lint findings in it."""
    limits = conf["limits"]
    out = [METRICS[m].format(v=v, limit=limits[m]) for m, v in fn["values"].items() if v > limits[m]]
    return [*out, f"{fn['smells']} lint finding(s)"] if fn["smells"] else out


def churn(root):
    """Commits touching each file (relative to root) in the last CHURN_DAYS days."""
    counts = {}
    for name in git(root, "log", f"--since={CHURN_DAYS}.days", "--format=", "--name-only", "--relative") or []:
        if name:
            counts[name] = counts.get(name, 0) + 1
    return counts


def mean(xs):
    return round(sum(xs) / len(xs)) if xs else None


def health(fns):
    """Code Health of a set of functions: their scores averaged, weighted by lines of code, so one
    large bad function outweighs many small good ones (as CodeScene weights files)."""
    weights = [max(fn["values"].get("nloc", 1), 1) for fn in fns]
    return round(sum(w * fn["score"] for w, fn in zip(weights, fns)) / sum(weights), 1) if fns else None


def ten(score):
    """A 0-100 score on CodeScene's 1-10 scale, one decimal."""
    return None if score is None else max(1.0, round(score / 10, 1))


def score_summary(functions):
    files = {}
    for fn in functions:
        files.setdefault(fn["file"], []).append(fn)
    by_file = {file: health(fns) for file, fns in sorted(files.items())}
    worst = min(by_file, key=by_file.get, default=None)
    return {"approved": sum(fn["approved"] for fn in functions), "functions": len(functions),
            "average": mean([fn["score"] for fn in functions]),
            "health": ten(health(functions)), "worst_file": worst,
            "worst_file_health": ten(by_file[worst]) if worst else None,
            "files": {file: mean([fn["score"] for fn in fns]) for file, fns in sorted(files.items())}}


# ---------------------------------------------------------------- a run

def analyze(ctx, files, full):
    """All findings and the scored functions for files; --full adds the project-wide checks."""
    functions = lizard_functions(ctx, files)
    findings = (check_file_size(ctx, files) + check_functions(ctx["conf"], functions)
                + check_ruff(ctx, files) + check_biome(ctx, files))
    if full:
        everything = all_files(ctx["root"], ctx["conf"])
        findings += check_types(ctx, everything) if ctx["conf"]["full"]["types"] else []
        findings += check_duplication(ctx) if ctx["conf"]["full"]["duplication"] else []
    findings.sort(key=lambda f: (f["file"], f["line"], f["rule"]))
    return findings, score_functions(ctx["conf"], functions, findings)
