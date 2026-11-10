#!/usr/bin/env python3
"""
code-quality: a deterministic complexity and code-smell gate for AI agents, humans and CI.

Usage:
  quality_gate.py init [--root DIR] [--no-ci]  opt a project in: .quality/config.toml, a copy of the
                                               gate for CI, a GitHub workflow, and a baseline
  quality_gate.py check [FILES...]             function metrics + lint on FILES (default: files changed
                                               since git HEAD, plus untracked ones)
      --all                                    every source file in the project
      --base REF                               files changed since REF (CI: --base origin/main)
      --full                                   also type checking and duplication, project-wide (slower)
      --json                                   machine-readable output
  quality_gate.py baseline [--full]            accept today's findings; checks then report only new or
                                               worse ones, and lower the baseline as code improves
  quality_gate.py targets [PATHS...] [--limit N] [--json]
                                               functions below 95%, highest refactoring priority first:
                                               (100 - score) x (1 + commits to the file, last 180 days)
  quality_gate.py score FILE [--symbol NAME] [--json]
                                               every function's score in FILE, and new findings; exit 0
                                               when NAME (or every function) is approved and nothing is new
  quality_gate.py report [--full] [--open]     the visual report: .quality/report.html (one page: scores by
                                               folder, file and function) and report.json for the
                                               code-quality-live pane; each check then keeps it current
  quality_gate.py doctor                       which tools were found for each package, and how they run
  quality_gate.py --hook                       Claude Code PostToolUse mode (hook JSON on stdin;
                                               exit 2 + stderr feedback on new findings)

Exit codes: 0 clean, 1 new findings, 3 setup error.
Opt-in per project: nothing runs unless .quality/config.toml exists (found by walking up).
Python 3.11+ and no dependencies; the checks are in qg_checks.py next to this file, the report in qg_report.py.
"""
import json
import shutil
import sys
import tomllib
import webbrowser
from pathlib import Path

import qg_checks as qc
import qg_report as qr

HERE = Path(__file__).resolve()
TEMPLATES = HERE.parent.parent / "templates"

CONFIG = ".quality/config.toml"
BASELINE = ".quality/baseline.json"
FILE_SOURCES = {"lizard", "ruff", "biome"}  # the checks that run per file, on every check

DEFAULTS = {
    "limits": {"ccn": 10, "cognitive": 15, "nloc": 60, "params": 5, "file_nloc": 500},
    "scope": {"exclude": []},
    "lint": {"ruff_extend_select": ["B", "SIM", "C4", "UP"], "biome": True},
    "full": {"types": True, "duplication": True, "min_tokens": 70},
    "tools": {"download": True, "pins": {"lizard": "1.25.1", "ruff": "0.17.4", "biome": "2.6.6",
                                         "pyright": "1.1.414", "jscpd": "5.4.3"}},
}
FIX_HINT = ("Fix the code: extract helpers, return early, replace branch chains with lookup tables, "
            "group parameters into an object, move code into its own module. Don't silence findings "
            "with noqa / biome-ignore or by editing .quality/.")


# ---------------------------------------------------------------- config

def find_root(start):
    p = Path(start).resolve()
    for d in [p, *p.parents] if p.is_dir() else p.parents:
        if (d / CONFIG).is_file():
            return d
    return None


def load_config(root):
    conf = {k: dict(v) for k, v in DEFAULTS.items()}
    with open(root / CONFIG, "rb") as f:
        user = tomllib.load(f)
    for section, values in user.items():
        if isinstance(values, dict):
            conf.setdefault(section, {}).update(values)
    conf["tools"]["pins"] = {**DEFAULTS["tools"]["pins"], **conf["tools"].get("pins", {})}
    return conf


def new_context(root, conf):
    return {"root": root, "conf": conf, "cache": {}, "ran": set(), "missing": set()}


# ---------------------------------------------------------------- baseline

def key(f):
    """Metric findings are keyed per function and compared by value; everything else is counted
    per file and rule, since line numbers move."""
    return f"{f['file']}::{f['rule']}::{f['symbol']}" if f["symbol"] else f"{f['file']}::{f['rule']}"


def measure(findings):
    m = {}
    for f in findings:
        k = key(f)
        m[k] = max(m.get(k, 0), f["value"]) if f["symbol"] else m.get(k, 0) + 1
    return m


def load_baseline(root):
    p = root / BASELINE
    return json.loads(p.read_text()).get("entries", {}) if p.is_file() else {}


def save_baseline(root, entries):
    p = root / BASELINE
    p.write_text(json.dumps({"version": 1, "entries": dict(sorted(entries.items()))}, indent=1) + "\n")


def compare(findings, baseline):
    """Split findings into new (or worse than the baseline) and baselined."""
    now = measure(findings)
    worse = {k for k, v in now.items() if v > baseline.get(k, 0)}
    new = [f for f in findings if key(f) in worse]
    return new, len(findings) - len(new)


def ratchet(baseline, findings, checked_files, sources):
    """Lower baseline entries for code that improved; never raise them."""
    now = measure(findings)
    out = {}
    for k, v in baseline.items():
        file, rule = k.split("::")[:2]
        if file not in checked_files or qc.source_of(rule) not in sources:
            out[k] = v
        elif now.get(k, 0) > 0:
            out[k] = min(v, now[k])
    return out


# ---------------------------------------------------------------- a check

def with_scores(findings, functions):
    scores = {(fn["file"], fn["symbol"]): fn["score"] for fn in functions}
    return [{**f, "score": scores[(f["file"], f["symbol"])]} if (f["file"], f["symbol"]) in scores else f
            for f in findings]


def check(root, files, full):
    ctx = new_context(root, load_config(root))
    findings, functions = qc.analyze(ctx, files, full)
    baseline = load_baseline(root)
    new, baselined = compare(findings, baseline)
    checked = {qc.rel(root, f) for f in files} | ({f["file"] for f in findings} if full else set())
    lowered = ratchet(baseline, findings, checked, ctx["ran"])
    if lowered != baseline:
        save_baseline(root, lowered)
    qr.update(ctx, {"files": files, "findings": findings, "functions": functions, "new": new}, full)
    return {"root": str(root), "files_checked": len(files), "new": with_scores(new, functions),
            "baselined": baselined, "scores": qc.score_summary(functions), "functions": functions,
            "missing_tools": sorted(ctx["missing"] - ctx["ran"])}


def file_report(file, new):
    """One line per function (its metrics joined) and one per other finding."""
    rows = {}
    for f in (f for f in new if f["file"] == file):
        if f["symbol"] and f["symbol"] != "<file>":
            label = f"{f['symbol']} ({f['score']}%)" if "score" in f else f["symbol"]
            rows.setdefault((f["line"], label), []).append(f["message"])
        else:
            rows.setdefault((f["line"], None), []).append(f"{f['rule'].replace(':', ' ', 1)}: {f['message']}")
    lines = [file]
    for (line, symbol), msgs in sorted(rows.items(), key=lambda kv: kv[0][0]):
        if symbol:
            lines.append(f"  {line:>5}  {symbol}: {', '.join(msgs)}")
        else:
            lines += [f"  {line:>5}  {m}" for m in msgs]
    return lines


def report_text(result):
    new = result["new"]
    files = sorted({f["file"] for f in new})
    if not new:
        lines = [f"code-quality: clean ({result['files_checked']} files, {result['baselined']} baselined)"]
    else:
        lines = [f"code-quality: {len(new)} new finding(s) in {len(files)} file(s) ({result['baselined']} baselined)"]
        lines += [line for file in files for line in file_report(file, new)] + [FIX_HINT]
    s = result["scores"]
    if s["functions"]:
        lines.append(f"scores: {s['approved']}/{s['functions']} functions approved (>= {qc.APPROVED}%),"
                     f" average {s['average']}%, Code Health {s['health']}/10")
    if result["missing_tools"]:
        lines.append(f"(not run, tool not found: {', '.join(result['missing_tools'])}; see `quality_gate.py doctor`)")
    return "\n".join(lines)


# ---------------------------------------------------------------- commands

def cmd_init(root, opts):
    q = root / ".quality"
    q.mkdir(exist_ok=True)
    if not (root / CONFIG).exists():
        shutil.copy(TEMPLATES / "config.toml", root / CONFIG)
        print(f"wrote {CONFIG}")
    for script in (HERE, HERE.parent / "qg_checks.py", HERE.parent / "qg_report.py",
                   HERE.parent / "qg_explain.py"):  # CI runs these copies; re-run init to update them
        shutil.copy(script, q / script.name)
    print("wrote .quality/quality_gate.py and its modules (CI's copy of the gate)")
    wf = root / ".github" / "workflows" / "code-quality.yml"
    if "--no-ci" not in opts["flags"] and not wf.exists():
        wf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(TEMPLATES / "code-quality.yml", wf)
        print(f"wrote {qc.rel(root, wf)}")
    return cmd_baseline(root, {"flags": {"--full"}})


def cmd_baseline(root, opts):
    full = "--full" in opts["flags"]
    ctx = new_context(root, load_config(root))
    files = qc.all_files(root, ctx["conf"])
    findings, functions = qc.analyze(ctx, files, full)
    # Without --full, keep what the project-wide checks recorded last time.
    kept = {} if full else {k: v for k, v in load_baseline(root).items()
                            if qc.source_of(k.split("::")[1]) not in FILE_SOURCES}
    save_baseline(root, {**kept, **measure(findings)})
    print(f"baseline: {len(findings)} existing finding(s) accepted in {BASELINE}")
    page = qr.update(ctx, {"files": files, "findings": findings, "functions": functions, "new": []}, full,
                     fresh=True)
    print(f"report: {qc.rel(root, page)}")
    missing = sorted(ctx["missing"] - ctx["ran"])
    if missing:
        print(f"(not run, tool not found: {', '.join(missing)})")
    return 0


def cmd_report(root, opts):
    full = "--full" in opts["flags"]
    ctx = new_context(root, load_config(root))
    files = qc.all_files(root, ctx["conf"])
    findings, functions = qc.analyze(ctx, files, full)
    new, _ = compare(findings, load_baseline(root))
    page = qr.update(ctx, {"files": files, "findings": findings, "functions": functions, "new": new}, full,
                     fresh=True)
    s = qc.score_summary(functions)
    print(f"report: {page}\n{s['approved']}/{s['functions']} functions approved (>= {qc.APPROVED}%),"
          f" average {s['average']}%, Code Health {s['health']}/10, {len(new)} new finding(s)")
    if "--open" in opts["flags"]:
        webbrowser.open(page.as_uri())
    return 0


def tool_line(ctx, name, pkg=None, indent="  "):
    cmd = qc.tool(ctx, name, pkg)
    return f"{indent}{name:8} {' '.join(cmd) if cmd else 'NOT FOUND'}"


def cmd_doctor(root, _opts):
    print(f"python {sys.version.split()[0]}  project: {root or '(none: no .quality/config.toml above here)'}")
    if not root:
        return 0
    ctx = new_context(root, load_config(root))
    files = qc.all_files(root, ctx["conf"])
    kinds = ((qc.PY_EXT, qc.PY_MARKERS, ("ruff", "mypy", "pyright")), (qc.JS_EXT, qc.JS_MARKERS, ("biome", "tsc")))
    for exts, markers, names in kinds:
        for pkg, group in qc.by_package(root, files, exts, markers).items():
            print(f"{qc.rel(root, pkg) if pkg != root else '.'}/  ({len(group)} files)")
            print("\n".join(tool_line(ctx, name, pkg) for name in names))
    print("\n".join(tool_line(ctx, name, indent="") for name in ("lizard", "jscpd")))
    return 0


def cmd_check(root, opts):
    conf = load_config(root)
    if opts["files"]:
        files = [Path(a).resolve() for a in opts["files"] if qc.in_scope(root, conf, Path(a))]
    elif "--all" in opts["flags"]:
        files = qc.all_files(root, conf)
    else:
        files = qc.changed_files(root, conf, opts["base"])
    result = check(root, files, full="--full" in opts["flags"])
    print(json.dumps(result, indent=1) if "--json" in opts["flags"] else report_text(result))
    return 1 if result["new"] else 0


def under(root, files, paths):
    """files within any of paths (files or folders, relative to the working directory)."""
    wanted = [qc.rel(root, Path(p)) for p in paths]
    return [f for f in files if any(w == "." or qc.rel(root, f) == w or qc.rel(root, f).startswith(w + "/")
                                    for w in wanted)]


def target_rows(root, conf, functions):
    commits = qc.churn(root)
    rows = [{**fn, "churn": commits.get(fn["file"], 0), "why": qc.reasons(conf, fn),
             "priority": (100 - fn["score"]) * (1 + commits.get(fn["file"], 0))}
            for fn in functions if not fn["approved"]]
    return sorted(rows, key=lambda r: (-r["priority"], r["file"], r["line"]))


def cmd_targets(root, opts):
    ctx = new_context(root, load_config(root))
    files = qc.all_files(root, ctx["conf"])
    _, functions = qc.analyze(ctx, under(root, files, opts["files"]) if opts["files"] else files, False)
    rows = target_rows(root, ctx["conf"], functions)[:int(opts["limit"]) if opts["limit"] else None]
    if "--json" in opts["flags"]:
        print(json.dumps(rows, indent=1))
        return 0
    for r in rows:
        print(f"{r['score']:>4}%  {r['file']}:{r['line']}  {r['symbol']}  (churn {r['churn']})  {', '.join(r['why'])}")
    print(f"{len(rows)} function(s) below {qc.APPROVED}%" if rows else f"every function is at {qc.APPROVED}% or more")
    return 0


def score_passes(result, symbol):
    if result["new"]:
        return False
    if symbol:
        return any(fn["symbol"] == symbol and fn["approved"] for fn in result["functions"])
    return all(fn["approved"] for fn in result["functions"])


def score_text(conf, result, symbol):
    lines = [f"{fn['score']:>4}%  {'ok ' if fn['approved'] else 'LOW'}  {fn['file']}:{fn['line']}  {fn['symbol']}  "
             f"{', '.join(qc.reasons(conf, fn))}"
             for fn in sorted(result["functions"], key=lambda fn: (fn["file"], fn["line"]))]
    if symbol and not any(fn["symbol"] == symbol for fn in result["functions"]):
        lines.append(f"(no function named {symbol} in the file)")
    if result["new"]:
        lines.append(report_text(result))
    return "\n".join(lines)


def cmd_score(root, opts):
    conf = load_config(root)
    files = [Path(a).resolve() for a in opts["files"] if qc.in_scope(root, conf, Path(a))]
    if not files:
        print("code-quality: score needs a source file in scope", file=sys.stderr)
        return 3
    result = check(root, files, full=False)
    if "--json" in opts["flags"]:
        print(json.dumps(result, indent=1))
    else:
        print(score_text(conf, result, opts["symbol"]))
    return 0 if score_passes(result, opts["symbol"]) else 1


def cmd_hook():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    edited = (data.get("tool_input") or {}).get("file_path")
    if not isinstance(edited, str):
        return 0
    path = Path(data.get("cwd") or ".", edited).resolve()
    root = find_root(path)
    if not root or not path.is_file() or not qc.in_scope(root, load_config(root), path):
        return 0
    result = check(root, [path], full=False)
    if not result["new"]:
        return 0
    print(report_text(result), file=sys.stderr)
    return 2


def parse_args(argv):
    """{command, files, flags, root, base, limit, symbol}; the last four take a value."""
    opts = {"files": [], "flags": set(), "root": ".", "base": None, "limit": None, "symbol": None}
    it = iter(argv)
    for a in it:
        if a in ("--root", "--base", "--limit", "--symbol"):
            opts[a[2:]] = next(it, opts[a[2:]])
        elif a.startswith("--"):
            opts["flags"].add(a)
        else:
            opts["files"].append(a)
    opts["command"] = opts["files"].pop(0) if opts["files"] else "check"
    return opts


COMMANDS = {"check": cmd_check, "baseline": cmd_baseline, "doctor": cmd_doctor, "targets": cmd_targets,
            "score": cmd_score, "report": cmd_report}


def main(argv):
    if "--hook" in argv:
        return cmd_hook()
    opts = parse_args(argv)
    start = Path(opts["root"] or ".").resolve()
    if opts["command"] == "init":
        return cmd_init(start, opts)
    if opts["command"] not in COMMANDS:
        print(__doc__, file=sys.stderr)
        return 3
    root = find_root(start)
    if not root and opts["command"] != "doctor":
        print("code-quality: no .quality/config.toml here or above. Run `quality_gate.py init` to opt in.",
              file=sys.stderr)
        return 3
    return COMMANDS[opts["command"]](root, opts)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
