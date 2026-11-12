"""The visual report: .quality/report.json (read by the code-quality-live pane) and report.html,
one self-contained page built from templates/report.html. `report` writes both from a full
analysis; every check after that refreshes the entries of the files it checked."""
import json
import os
from datetime import datetime
from pathlib import Path

import qg_checks as qc
import qg_explain as qx

HERE = Path(__file__).resolve()
TEMPLATE = HERE.parent.parent / "templates" / "report.html"
REPORT_JSON = ".quality/report.json"
REPORT_HTML = ".quality/report.html"
YELLOW = 70  # APPROVED (95) and up is green, 70-94 yellow, below 70 red
TARGETS = 10


def band(score):
    if score is None or score >= qc.APPROVED:
        return "green"
    return "yellow" if score >= YELLOW else "red"


def file_entries(root, conf, run):
    """{file: {functions, findings}} for the files a run checked; findings carry whether they're new.
    run: {files, findings, functions, new}, as a check found them."""
    fresh = {id(f) for f in run["new"]}
    out = {qc.rel(root, f): {"functions": [], "findings": []} for f in run["files"]}
    for fn in run["functions"]:
        out.setdefault(fn["file"], {"functions": [], "findings": []})["functions"].append(
            {k: fn[k] for k in ("symbol", "line", "end", "score", "values", "smells", "costs")}
            | {"why": qc.reasons(conf, fn)})
    for entry in out.values():
        entry["health"] = qc.health(entry["functions"])
        entry["nloc"] = sum(fn["values"].get("nloc", 0) for fn in entry["functions"])
    for f in run["findings"]:
        out.setdefault(f["file"], {"functions": [], "findings": []})["findings"].append(
            {k: f[k] for k in ("line", "rule", "message", "symbol")} | {"new": id(f) in fresh}
            | {k: f[k] for k in ("col", "end_line", "end_col") if f.get(k)})
    return {name: qx.add_code(root, name, entry, qc.APPROVED) for name, entry in out.items()}


def merge(old, entries, full, sources):
    """old report files with the checked files replaced. Without --full, a checked file keeps its
    type and duplication findings from the last full run, and files that no longer exist drop out."""
    files = dict(old)
    for name, entry in entries.items():
        kept = [] if full else [f for f in files.get(name, {}).get("findings", [])
                                if qc.source_of(f["rule"]) not in sources]
        files[name] = {**entry, "findings": entry["findings"] + kept}
    return files


def tally(fns):
    scores = [fn["score"] for fn in fns]
    bands = {b: sum(band(s) == b for s in scores) for b in ("green", "yellow", "red")}
    return {"functions": len(scores), "approved": bands["green"], "bands": bands,
            "average": qc.mean(scores), "worst": min(scores, default=None)}


def code_health(root, files):
    """CodeScene-style Code Health on a 1-10 scale. Per file: qc.health, its smells' costs
    multiplied. Overall: files weighted by lines of code; the hotspot figure counts only files
    changed in the last CHURN_DAYS days; the worst file is the lowest single score."""
    rows = [(name, e["health"], max(e["nloc"], 1)) for name, e in files.items() if e["health"] is not None]
    commits = qc.churn(root)

    def weighted(rs):
        return qc.ten(sum(h * w for _, h, w in rs) / sum(w for _, _, w in rs)) if rs else None
    worst = min(rows, key=lambda r: r[1], default=None)
    return {"average": weighted(rows), "hotspot": weighted([r for r in rows if commits.get(r[0])]),
            "worst": {"file": worst[0], "score": qc.ten(worst[1])} if worst else None,
            "files": {name: qc.ten(h) for name, h, _ in rows}}


def folders(files):
    groups = {}
    for name, entry in files.items():
        groups.setdefault(os.path.dirname(name) or ".", []).append(entry)
    rows = [{"path": path, "files": len(group), "findings": sum(len(e["findings"]) for e in group),
             "new": sum(f["new"] for e in group for f in e["findings"]),
             **tally([fn for e in group for fn in e["functions"]])}
            for path, group in groups.items()]
    return sorted(rows, key=lambda r: (r["worst"] if r["worst"] is not None else 101, r["path"]))


def targets(root, files):
    commits = qc.churn(root)
    rows = [{"file": name, **fn, "churn": commits.get(name, 0),
             "priority": (100 - fn["score"]) * (1 + commits.get(name, 0))}
            for name, entry in files.items() for fn in entry["functions"] if fn["score"] < qc.APPROVED]
    return sorted(rows, key=lambda r: (-r["priority"], r["file"], r["line"]))[:TARGETS]


def build(root, conf, files, full, rules):
    fns = [fn for e in files.values() for fn in e["functions"]]
    findings = [f for e in files.values() for f in e["findings"]]
    return {"version": 1, "generated": datetime.now().isoformat(timespec="seconds"),
            "project": root.name, "full": full,
            "thresholds": {"green": qc.APPROVED, "yellow": YELLOW}, "limits": conf["limits"],
            "health": code_health(root, files),
            "summary": {**tally(fns), "files": len(files), "findings": len(findings),
                        "new": sum(f["new"] for f in findings)},
            "folders": folders(files), "targets": targets(root, files),
            "metrics": qx.METRIC_HELP, "rules": rules,
            "files": dict(sorted(files.items()))}


def load(root):
    p = root / REPORT_JSON
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def write(root, report):
    (root / REPORT_JSON).write_text(json.dumps(report, indent=1) + "\n")
    if TEMPLATE.is_file():  # CI's copy in .quality/ has no template, and needs no page
        data = json.dumps(report).replace("</", "<\\/")
        page = TEMPLATE.read_text(encoding="utf-8").replace("/*__REPORT__*/null", data)
        (root / REPORT_HTML).write_text(page, encoding="utf-8")
    ignore_generated(root)
    return root / REPORT_HTML


def ignore_generated(root):
    """Keep .quality/'s generated files out of git: the report, and Python's cache of the gate's copy."""
    ignore = root / ".quality" / ".gitignore"
    have = (ignore.read_text(encoding="utf-8").splitlines() if ignore.exists()
            else ["# generated by `quality_gate.py report`, refreshed by each check"])
    missing = [p for p in ("report.json", "report.html", "__pycache__/") if p not in have]
    if missing:
        ignore.write_text("\n".join([*have, *missing]) + "\n", encoding="utf-8")


def update(ctx, run, full, fresh=False):
    """Refresh the report for the files just checked; a check only does so once `report` made one."""
    root, conf = ctx["root"], ctx["conf"]
    old = load(root)
    if old is None and not fresh:
        return None
    before = {} if fresh else old  # a fresh report keeps only the rule docs fetched before
    merged = merge(before.get("files", {}), file_entries(root, conf, run), full, qc.file_sources(conf))
    merged = {name: e for name, e in merged.items() if (root / name).is_file()}
    was_full = full or before.get("full", False)
    rules = qx.rules(ctx, merged, (old or {}).get("rules", {}))
    return write(root, build(root, conf, merged, was_full, rules))
