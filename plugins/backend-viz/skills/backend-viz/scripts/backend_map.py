#!/usr/bin/env python3
"""
backend-viz: compare what you DESIGNED (API contract + layer rules) against what
was BUILT (FastAPI / Node routes + import graph), then render a visual dashboard.

Usage:
  backend_map.py [--root DIR]            analyze, write .backend-viz/report.json + dashboard.html
  backend_map.py --open                  ...and open the dashboard in a browser
  backend_map.py --init [fastapi|node]   scaffold design/ (contract + architecture rules)
  backend_map.py --hook                  Claude Code PostToolUse mode (reads hook JSON on stdin;
                                         exit 2 + stderr feedback when drift is found)
  backend_map.py --summary               print a one-line JSON summary (used by the live pane)
  backend_map.py --traces [n]            print the last n traces as trees (what actually ran)
  backend_map.py --serve [port]          live dashboard on http://localhost:8765, updates as requests run
  backend_map.py --init-tracing          copy the tracer into app/trace/
  backend_map.py --clear-traces          delete recorded spans

Static, best-effort analysis. No dependencies except PyYAML for .yaml files.
"""
import ast
import datetime
import fnmatch
import json
import os
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / "templates"

SKIP_DIRS = {"node_modules", ".git", "venv", ".venv", "env", "__pycache__", "dist", "build",
             ".backend-viz", ".next", "coverage", "site-packages", ".pytest_cache", ".mypy_cache"}
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
PY_EXT = {".py"}
JS_EXT = {".js", ".ts", ".mjs", ".cjs", ".jsx", ".tsx"}
WATCH_EXT = PY_EXT | JS_EXT | {".yaml", ".yml", ".json"}


# ---------------------------------------------------------------- helpers
def load_struct(path: Path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    try:
        import yaml  # type: ignore
    except ImportError:
        raise SystemExit("backend-viz: PyYAML is needed to read YAML (pip install pyyaml), or use .json files")
    return yaml.safe_load(text) or {}


def first_existing(root: Path, names):
    for n in names:
        p = root / n
        if p.exists():
            return p
    return None


def norm_path(p: str) -> str:
    p = re.sub(r"\{[^}]+\}", "{}", p)                     # /items/{item_id}
    p = re.sub(r":[A-Za-z_][A-Za-z0-9_]*\??", "{}", p)    # /items/:id
    p = re.sub(r"/+", "/", p)
    if len(p) > 1:
        p = p.rstrip("/")
    return p or "/"


def join_paths(*parts):
    out = "/".join(s.strip("/") for s in parts if s and s.strip("/"))
    return "/" + out if out else "/"


def iter_source_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for f in filenames:
            p = Path(dirpath) / f
            if p.suffix in PY_EXT or (p.suffix in JS_EXT and not f.endswith(".d.ts")):
                yield p


def rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


# ---------------------------------------------------------------- design side
def load_design(root: Path):
    ddir = root / "design"
    contract_file = first_existing(ddir, ["openapi.yaml", "openapi.yml", "openapi.json"])
    arch_file = first_existing(ddir, ["architecture.yaml", "architecture.yml", "architecture.json"])
    endpoints, tag_order = [], []
    if contract_file:
        spec = load_struct(contract_file) or {}
        tag_order = [t.get("name") for t in (spec.get("tags") or []) if isinstance(t, dict)]
        for path, item in (spec.get("paths") or {}).items():
            for method, op in (item or {}).items():
                if method.lower() in HTTP_METHODS:
                    op = op or {}
                    endpoints.append({
                        "method": method.upper(), "path": path, "key": f"{method.upper()} {norm_path(path)}",
                        "summary": op.get("summary") or op.get("operationId") or "",
                        "tag": (op.get("tags") or [""])[0],
                    })
    arch = load_struct(arch_file) if arch_file else {}
    return {
        "contract_file": rel(root, contract_file) if contract_file else None,
        "arch_file": rel(root, arch_file) if arch_file else None,
        "endpoints": endpoints,
        "tag_order": tag_order,
        "layers": arch.get("layers") or [],
        "enforce": {"layer_violations": True, "undocumented_endpoints": True, **(arch.get("enforce") or {})},
        "ignore": arch.get("ignore") or ["tests/**", "test/**", "**/*.test.*", "**/*.spec.*"],
        "tracing": {"required_in": [], "decorator": "traced", **(arch.get("tracing") or {})},
    }


# ---------------------------------------------------------------- FastAPI routes + imports
def py_module_parts(root: Path, f: Path):
    return list(f.relative_to(root).with_suffix("").parts)


def resolve_py(root: Path, f: Path, module: str, level: int, name: str = None):
    """Return project files an import points at (empty if external)."""
    parts = module.split(".") if module else []
    if level:
        base = f.parent
        for _ in range(level - 1):
            base = base.parent
        bases = [base]
    else:
        bases = [root, root / "src"]
    found = []
    for b in bases:
        target = b.joinpath(*parts) if parts else b
        cands = []
        if name:
            cands += [target / f"{name}.py", target / name / "__init__.py"]
        cands += [target.with_suffix(".py") if parts else None, target / "__init__.py"]
        for c in cands:
            if c and c.is_file():
                found.append(c)
                break
        if found:
            break
    return found


def scan_python(root: Path, f: Path, src: str):
    routes, imports, includes, alias = [], [], [], {}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return routes, imports, includes
    stem = f.stem if f.stem != "__init__" else f.parent.name
    router_prefix, app_names = {}, set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports += resolve_py(root, f, a.name, 0)
                alias[a.asname or a.name.split(".")[0]] = (a.name.split(".")[-1], None)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for a in node.names:
                imports += resolve_py(root, f, mod, node.level, a.name)
                local = a.asname or a.name
                # `from app.routers import items` -> module alias; `from .items import router` -> (items, router)
                if resolve_py(root, f, mod, node.level, a.name) and \
                        any(p.stem == a.name or p.parent.name == a.name for p in resolve_py(root, f, mod, node.level, a.name)):
                    alias[local] = (a.name, None)
                else:
                    alias[local] = ((mod.split(".")[-1] if mod else stem), a.name)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            fname = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            for t in node.targets:
                if isinstance(t, ast.Name):
                    if fname == "APIRouter":
                        pref = next((k.value.value for k in node.value.keywords
                                     if k.arg == "prefix" and isinstance(k.value, ast.Constant)), "")
                        router_prefix[t.id] = pref
                    elif fname == "FastAPI":
                        app_names.add(t.id)
                        router_prefix[t.id] = ""

    def expr_key(e):
        if isinstance(e, ast.Attribute) and isinstance(e.value, ast.Name):
            mod = alias.get(e.value.id, (e.value.id, None))[0]
            return (mod, e.attr)
        if isinstance(e, ast.Name):
            return alias.get(e.id, (stem, e.id)) if e.id in alias else (stem, e.id)
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "include_router" and node.args:
            key = expr_key(node.args[0])
            pref = next((k.value.value for k in node.keywords if k.arg == "prefix" and isinstance(k.value, ast.Constant)), "")
            parent = node.func.value.id if isinstance(node.func.value, ast.Name) else None
            if key:
                includes.append({"key": key, "prefix": pref, "parent": (stem, parent)})
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.decorator_list:
                if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and isinstance(d.func.value, ast.Name)):
                    continue
                obj, attr = d.func.value.id, d.func.attr
                if obj not in router_prefix and obj not in {"app", "router"}:
                    continue
                path = d.args[0].value if d.args and isinstance(d.args[0], ast.Constant) else None
                if path is None:
                    path = next((k.value.value for k in d.keywords if k.arg == "path" and isinstance(k.value, ast.Constant)), None)
                if path is None:
                    continue
                methods = []
                if attr in HTTP_METHODS:
                    methods = [attr.upper()]
                elif attr == "api_route":
                    for k in d.keywords:
                        if k.arg == "methods" and isinstance(k.value, (ast.List, ast.Tuple)):
                            methods = [c.value.upper() for c in k.value.elts if isinstance(c, ast.Constant)]
                    methods = methods or ["GET"]
                for m in methods:
                    routes.append({"method": m, "local_path": join_paths(router_prefix.get(obj, ""), path),
                                   "router": (stem, obj), "file": rel(root, f), "line": node.lineno,
                                   "handler": node.name})
    return routes, imports, includes


def scan_py_functions(f_rel: str, src: str, decorator: str):
    """Public functions and methods, and whether each is traced (by decorator, or its class's)."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []

    def is_traced(decos):
        for d in decos:
            t = d.func if isinstance(d, ast.Call) else d
            if (isinstance(t, ast.Name) and t.id == decorator) or (isinstance(t, ast.Attribute) and t.attr == decorator):
                return True
        return False

    def is_protocol(cls):
        """A Protocol only declares a port; its adapters are what run, so there's nothing to trace."""
        for base in cls.bases:
            b = base.value if isinstance(base, ast.Subscript) else base
            if (isinstance(b, ast.Name) and b.id == "Protocol") or (isinstance(b, ast.Attribute) and b.attr == "Protocol"):
                return True
        return False

    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            out.append({"file": f_rel, "func": node.name, "line": node.lineno, "traced": is_traced(node.decorator_list)})
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_") and not is_protocol(node):
            cls_traced = is_traced(node.decorator_list)
            for m in node.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and not m.name.startswith("_"):
                    out.append({"file": f_rel, "func": f"{node.name}.{m.name}", "line": m.lineno,
                                "traced": cls_traced or is_traced(m.decorator_list)})
    return out


# ---------------------------------------------------------------- runtime traces
def load_traces(root: Path, layer_of, max_traces: int = 60, max_spans: int = 400):
    """Read .backend-viz/traces/spans.jsonl: recent traces + per-function call stats."""
    path = root / ".backend-viz" / "traces" / "spans.jsonl"
    empty = {"traces": [], "calls": {}, "endpoint_calls": {}, "runtime_edges": [], "span_count": 0}
    if not path.exists():
        return empty
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 8 * 1024 * 1024))
            lines = fh.read().decode("utf-8", "ignore").splitlines()
    except OSError:
        return empty
    spans = []
    for ln in lines:
        try:
            spans.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    by_trace, calls, ep_calls, redges = {}, {}, {}, {}
    by_id = {sp["span"]: sp for sp in spans if "span" in sp}
    for sp in spans:
        sp["layer"] = layer_of(sp.get("file") or "") if sp.get("file") else ("api" if sp.get("attrs", {}).get("kind") == "request" else None)
        by_trace.setdefault(sp.get("trace"), []).append(sp)
        if sp.get("file"):
            k = f"{sp['file']}::{sp['func']}"
            c = calls.setdefault(k, {"count": 0, "errors": 0, "ms": 0.0, "last": 0})
            c["count"] += 1
            c["errors"] += 0 if sp.get("ok") else 1
            c["ms"] += sp.get("ms") or 0
            c["last"] = max(c["last"], sp.get("start") or 0)
            par = by_id.get(sp.get("parent"))
            if par and par.get("file") and par["file"] != sp["file"]:
                ek = (par["file"], sp["file"])
                redges[ek] = redges.get(ek, 0) + 1
        route = (sp.get("attrs") or {}).get("route")
        if route and not sp.get("parent"):
            key = f"{sp['attrs'].get('method', '').upper()} {norm_path(route)}"
            e = ep_calls.setdefault(key, {"count": 0, "errors": 0, "last_trace": None, "last": 0})
            e["count"] += 1
            e["errors"] += 0 if sp.get("ok") and (sp["attrs"].get("status") or 200) < 500 else 1
            if (sp.get("start") or 0) >= e["last"]:
                e["last"], e["last_trace"] = sp.get("start") or 0, sp.get("trace")
    traces = []
    for tid, sps in by_trace.items():
        sps.sort(key=lambda x: x.get("start") or 0)
        roots = [x for x in sps if not x.get("parent") or x["parent"] not in {y["span"] for y in sps}]
        root_sp = roots[0] if roots else sps[0]
        start = min(x.get("start") or 0 for x in sps)
        end = max((x.get("start") or 0) + (x.get("ms") or 0) for x in sps)
        traces.append({"id": tid, "name": root_sp.get("name"), "start": start, "ms": round(end - start, 3),
                       "ok": all(x.get("ok") for x in sps), "status": (root_sp.get("attrs") or {}).get("status"),
                       "count": len(sps), "spans": sps[:max_spans]})
    traces.sort(key=lambda t: t["start"], reverse=True)
    return {"traces": traces[:max_traces], "calls": calls, "endpoint_calls": ep_calls,
            "runtime_edges": [{"from": a, "to": b, "count": n} for (a, b), n in redges.items()],
            "span_count": len(spans)}


# ---------------------------------------------------------------- Node routes + imports
JS_IMPORT_RES = [
    re.compile(r"""(?:import\s+(?:[\w*{}\s,]+?\s+from\s+)?|export\s+[\w*{}\s,]+?\s+from\s+)['"]([^'"]+)['"]"""),
    re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""import\(\s*['"]([^'"]+)['"]\s*\)"""),
]
JS_BIND_RES = [
    re.compile(r"""(?:const|let|var)\s+(\w+)\s*=\s*require\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""import\s+(\w+)(?:\s*,\s*\{[^}]*\})?\s+from\s+['"]([^'"]+)['"]"""),
]
JS_ROUTER_DECL = re.compile(r"""(?:const|let|var)\s+(\w+)\s*=\s*(?:express\.)?(?:Router|express|fastify|Fastify|new\s+Hono|Hono)\s*\(""")
JS_ROUTE = re.compile(r"""\b(\w+)\s*\.\s*(get|post|put|patch|delete|all)\s*\(\s*['"`](/[^'"`]*)['"`]""")
JS_USE = re.compile(r"""\b(\w+)\s*\.\s*(?:use|route|register)\s*\(\s*['"`](/[^'"`]*)['"`]\s*,\s*(\w+)""")
JS_EXTS_TRY = ["", ".ts", ".js", ".tsx", ".jsx", ".mjs", ".cjs", "/index.ts", "/index.js"]


def resolve_js(f: Path, spec: str):
    if not spec.startswith("."):
        return None
    base = (f.parent / spec)
    for ext in JS_EXTS_TRY:
        c = Path(str(base) + ext)
        if c.is_file():
            return c.resolve()
    # TS projects often import "./x.js" that is really x.ts
    if base.suffix == ".js":
        c = base.with_suffix(".ts")
        if c.is_file():
            return c.resolve()
    return None


def scan_js(root: Path, f: Path, src: str):
    routes, imports, includes = [], [], []
    stem = f.stem if f.stem != "index" else f.parent.name
    src_nc = re.sub(r"//[^\n]*|/\*.*?\*/", "", src, flags=re.S)
    for rx in JS_IMPORT_RES:
        for m in rx.finditer(src_nc):
            t = resolve_js(f, m.group(1))
            if t:
                imports.append(t)
    binds = {}
    for rx in JS_BIND_RES:
        for m in rx.finditer(src_nc):
            t = resolve_js(f, m.group(2))
            if t:
                binds[m.group(1)] = (t.stem if t.stem != "index" else t.parent.name)
    declared = set(JS_ROUTER_DECL.findall(src_nc)) | {"app", "router", "server", "fastify", "api"}
    declared |= {n for n in re.findall(r"\b(\w*[Rr]outer)\b", src_nc)}
    for m in JS_USE.finditer(src_nc):
        parent, pref, var = m.groups()
        if var in binds:
            includes.append({"key": (binds[var], None), "prefix": pref, "parent": (stem, parent)})
    lines = src.splitlines()
    for m in JS_ROUTE.finditer(src_nc):
        obj, meth, path = m.groups()
        if obj not in declared:
            continue
        snippet = m.group(0)
        line = next((i + 1 for i, l in enumerate(lines) if snippet.split("(")[0].replace(" ", "") in l.replace(" ", "")
                     and path in l), 0)
        methods = list(HTTP_METHODS - {"head", "options"}) if meth == "all" else [meth]
        for mm in methods:
            routes.append({"method": mm.upper(), "local_path": join_paths(path), "router": (stem, None),
                           "file": rel(root, f), "line": line, "handler": f"{obj}.{meth}"})
    return routes, imports, includes


# ---------------------------------------------------------------- analysis
def analyze(root: Path):
    design = load_design(root)
    ignore = design["ignore"]
    files, edges, all_routes, all_includes, funcs = [], [], [], [], []
    for f in iter_source_files(root):
        r = rel(root, f)
        if any(fnmatch.fnmatch(r, g) for g in ignore):
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if f.name == "__init__.py" and not src.strip():
            continue  # empty package markers are noise on the map
        files.append(r)
        routes, imps, incs = (scan_python if f.suffix in PY_EXT else scan_js)(root, f, src)
        if f.suffix in PY_EXT:
            funcs += scan_py_functions(r, src, design["tracing"]["decorator"])
        all_routes += routes
        all_includes += incs
        for t in imps:
            try:
                tr = rel(root, Path(t).resolve())
            except ValueError:
                continue
            if tr != r:
                edges.append((r, tr))
    edges = sorted(set(edges))
    fileset = set(files)
    edges = [e for e in edges if e[1] in fileset]

    # resolve mount prefixes (one or two levels of nesting)
    def mount_prefix(key, depth=0):
        if depth > 4:
            return ""
        for inc in all_includes:
            k = inc["key"]
            if k == key or (k[1] is None and k[0] == key[0]):
                return join_paths(mount_prefix(inc["parent"], depth + 1), inc["prefix"])
        return ""

    built = []
    for rt in all_routes:
        full = join_paths(mount_prefix(rt["router"]), rt["local_path"])
        built.append({"method": rt["method"], "path": full, "key": f"{rt['method']} {norm_path(full)}",
                      "file": rt["file"], "line": rt["line"], "handler": rt["handler"]})

    # endpoints: designed vs built
    dmap = {e["key"]: e for e in design["endpoints"]}
    bmap = {}
    for b in built:
        bmap.setdefault(b["key"], b)
    rows = []
    for k, d in dmap.items():
        b = bmap.get(k)
        rows.append({"method": d["method"], "path": d["path"], "summary": d["summary"], "tag": d["tag"],
                     "status": "built" if b else "missing",
                     "file": b["file"] if b else None, "line": b["line"] if b else None,
                     "handler": b["handler"] if b else None})
    for k, b in bmap.items():
        if k not in dmap:
            rows.append({"method": b["method"], "path": b["path"], "summary": "", "tag": "",
                         "status": "undocumented", "file": b["file"], "line": b["line"], "handler": b["handler"]})
    order = {"undocumented": 0, "missing": 1, "built": 2}
    rows.sort(key=lambda r: (r["path"], r["method"]))

    # layers
    layers = design["layers"]

    def layer_of(path):
        for L in layers:
            if any(fnmatch.fnmatch(path, g) for g in (L.get("paths") or [])):
                return L["name"]
        return None

    file_layer = {f: layer_of(f) for f in files}
    allowed = {L["name"]: set(L.get("may_depend_on") or []) for L in layers}
    edge_rows, violations = [], []
    for a, b in edges:
        la, lb = file_layer.get(a), file_layer.get(b)
        bad = bool(la and lb and la != lb and lb not in allowed.get(la, set()))
        edge_rows.append({"from": a, "to": b, "from_layer": la, "to_layer": lb, "violation": bad})
        if bad:
            violations.append({"from": a, "to": b, "from_layer": la, "to_layer": lb,
                               "rule": f"'{la}' may depend on: {', '.join(sorted(allowed.get(la, []))) or 'nothing'}"})

    # tracing: static coverage + runtime calls
    required = set(design["tracing"]["required_in"] or [])
    rt = load_traces(root, layer_of)
    funcs = [fn for fn in funcs if "/trace/" not in f"/{fn['file']}"]  # the tracer itself
    for fn in funcs:
        fn["layer"] = file_layer.get(fn["file"])
        fn["required"] = fn["layer"] in required
        c = rt["calls"].get(f"{fn['file']}::{fn['func']}")
        fn["calls"] = c["count"] if c else 0
        fn["errors"] = c["errors"] if c else 0
        fn["avg_ms"] = round(c["ms"] / c["count"], 2) if c else None
    for r in rows:
        e = rt["endpoint_calls"].get(f"{r['method']} {norm_path(r['path'])}")
        r["calls"] = e["count"] if e else 0
        r["errors"] = e["errors"] if e else 0
        r["last_trace"] = e["last_trace"] if e else None
    must = [fn for fn in funcs if fn["required"]]
    untraced = [fn for fn in must if not fn["traced"]]

    counts = {s: sum(1 for r in rows if r["status"] == s) for s in order}
    n_designed = len(dmap)
    return {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "project": root.name,
        "design": {k: design[k] for k in ("contract_file", "arch_file", "enforce")},
        "tag_order": design["tag_order"],
        "summary": {
            "designed": n_designed, "built": counts["built"], "missing": counts["missing"],
            "undocumented": counts["undocumented"], "violations": len(violations),
            "coverage": round(100 * counts["built"] / n_designed) if n_designed else None,
            "files": len(files), "unlayered": sum(1 for f in files if not file_layer[f]),
            "functions": len(funcs), "must_trace": len(must), "untraced": len(untraced),
            "called": sum(1 for fn in funcs if fn["calls"]), "spans": rt["span_count"],
            "traces": len(rt["traces"]), "trace_errors": sum(1 for t in rt["traces"] if not t["ok"]),
        },
        "tracing": design["tracing"],
        "functions": funcs,
        "untraced": untraced,
        "traces": rt["traces"],
        "runtime_edges": rt["runtime_edges"],
        "endpoints": rows,
        "layers": [{"name": L["name"], "may_depend_on": L.get("may_depend_on") or [],
                    "description": L.get("description", ""),
                    "files": [f for f in files if file_layer[f] == L["name"]]} for L in layers],
        "unlayered": [f for f in files if not file_layer[f]],
        "edges": edge_rows,
        "violations": violations,
    }


# ---------------------------------------------------------------- output
def write_outputs(root: Path, report: dict):
    out = root / ".backend-viz"
    out.mkdir(exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    tpl = (TEMPLATES / "dashboard.html").read_text(encoding="utf-8")
    data = json.dumps(report).replace("</", "<\\/")
    (out / "dashboard.html").write_text(tpl.replace("/*__REPORT__*/null", data), encoding="utf-8")
    gi = out / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n")
    return out / "dashboard.html"


def feedback(report: dict) -> str:
    """Compact drift message fed back to Claude by the hook."""
    enf = report["design"]["enforce"]
    lines = []
    if enf.get("layer_violations") and report["violations"]:
        lines.append("Layer violations (fix the import, or move the code to the right layer):")
        for v in report["violations"][:10]:
            lines.append(f"  - {v['from']} [{v['from_layer']}] -> {v['to']} [{v['to_layer']}]; {v['rule']}")
    und = [r for r in report["endpoints"] if r["status"] == "undocumented"]
    if enf.get("undocumented_endpoints") and und and report["design"]["contract_file"]:
        lines.append(f"Endpoints not in the contract ({report['design']['contract_file']}). "
                     "Contract-first: add them to the spec (ask the user if the design is unclear) or remove them:")
        for r in und[:10]:
            lines.append(f"  - {r['method']} {r['path']}  ({r['file']}:{r['line']})")
    unt = report.get("untraced") or []
    if unt:
        dec = report["tracing"]["decorator"]
        lines.append(f"Functions without tracing in {', '.join(report['tracing']['required_in'])} "
                     f"(decorate with @{dec} from app.trace, or the whole class, so calls show up on the map):")
        for fn in unt[:12]:
            lines.append(f"  - {fn['file']}:{fn['line']} {fn['func']}")
        if len(unt) > 12:
            lines.append(f"  … and {len(unt) - 12} more")
    if lines:
        lines.insert(0, "backend-viz drift check:")
    return "\n".join(lines)


def traces_text(report: dict, n: int = 5) -> str:
    """Readable trace trees, for Claude to verify what actually ran."""
    out = []
    for t in report["traces"][:n]:
        when = datetime.datetime.fromtimestamp(t["start"] / 1000).strftime("%H:%M:%S")
        out.append(f"{when}  {t['name']}  {t['ms']:.1f} ms  {'ok' if t['ok'] else 'ERROR'}  trace={t['id']}")
        kids = {}
        for sp in t["spans"]:
            kids.setdefault(sp.get("parent"), []).append(sp)
        ids = {sp["span"] for sp in t["spans"]}

        def walk(sp, depth):
            data = ", ".join(d["id"] for d in sp.get("data") or [])
            err = f"  !! {sp['error']}" if sp.get("error") else ""
            out.append(f"{'  ' * depth}- [{sp.get('layer') or '?'}] {sp.get('func') or sp['name']}  "
                       f"{sp.get('ms', 0):.1f} ms" + (f"  data: {data}" if data else "") + err)
            for lk in sp.get("links") or []:
                out.append(f"{'  ' * depth}    link {lk['from']} -> {lk['to']} {lk.get('how', '')}")
            for k in kids.get(sp["span"], []):
                walk(k, depth + 1)

        for r in [sp for sp in t["spans"] if not sp.get("parent") or sp["parent"] not in ids]:
            walk(r, 1)
    return "\n".join(out) or "No traces yet. Run the app and make a request."


def serve(root: Path, port: int):
    """Live dashboard: re-analyzes on each poll so new traces and edits appear within seconds."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.startswith("/data.json"):
                body = json.dumps(analyze(root)).encode()
                ctype = "application/json"
            elif self.path in ("/", "/index.html"):
                rep = analyze(root)
                tpl = (TEMPLATES / "dashboard.html").read_text(encoding="utf-8")
                body = tpl.replace("/*__REPORT__*/null", json.dumps(rep).replace("</", "<\\/")).encode()
                ctype = "text/html; charset=utf-8"
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    print(f"backend-viz live dashboard: http://localhost:{port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()



def detect_stack(root: Path) -> str:
    if list(root.glob("requirements*.txt")) or (root / "pyproject.toml").exists() or list(root.glob("*/main.py")) or (root / "main.py").exists():
        return "fastapi"
    return "node" if (root / "package.json").exists() else "fastapi"


def find_fastapi_main(root: Path):
    for f in sorted(iter_source_files(root)):
        if f.suffix == ".py":
            try:
                src = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if re.search(r"^\s*\w+\s*=\s*FastAPI\(", src, re.M):
                return f
    return None


def setup(root: Path) -> list:
    """Idempotent: make a project fully backend-viz ready. Returns what it did."""
    did = []
    stack = detect_stack(root)
    if not (root / "design").is_dir():
        init(root, stack, quiet=True)
        did.append(f"created design/ ({stack}): openapi.yaml + architecture.yaml")
    if stack == "fastapi":
        main_py = find_fastapi_main(root)
        pkg = main_py.parent if main_py else root / "app"
        trace_dir = pkg / "trace"
        if not (trace_dir / "__init__.py").exists():
            trace_dir.mkdir(parents=True, exist_ok=True)
            for name in ("__init__.py", "fastapi.py"):
                shutil.copy(TEMPLATES / "trace" / name, trace_dir / name)
            did.append(f"added tracer: {rel(root, trace_dir)}/")
        if main_py:
            src = main_py.read_text(encoding="utf-8")
            if "TraceMiddleware" not in src:
                mod = ".".join(rel(root, pkg).split("/")) or "app"
                m = re.search(r"^(\s*)(\w+)\s*=\s*FastAPI\(.*?\)\s*$", src, re.M | re.S)
                if m:
                    var = m.group(2)
                    end = m.end()
                    src = src[:end] + f"\n{var}.add_middleware(TraceMiddleware)  # backend-viz: one trace per request" + src[end:]
                    # import after the last top-level import
                    imports = list(re.finditer(r"^(from\s+\S+\s+import\s+.+|import\s+.+)$", src, re.M))
                    at = imports[-1].end() if imports else 0
                    src = src[:at] + f"\nfrom {mod}.trace.fastapi import TraceMiddleware" + src[at:]
                    main_py.write_text(src, encoding="utf-8")
                    did.append(f"wired TraceMiddleware into {rel(root, main_py)}")
        arch = first_existing(root / "design", ["architecture.yaml", "architecture.yml"])
        if arch:
            a = arch.read_text(encoding="utf-8")
            if not re.search(r"^\s*-\s*name:\s*trace\s*$", a, re.M):
                tpath = rel(root, trace_dir) + "/*"
                a = re.sub(r"(may_depend_on:\s*\[)([^\]]*)\]",
                           lambda m: m.group(0) if "trace" in m.group(2) else f"{m.group(1)}{m.group(2)}{', ' if m.group(2).strip() else ''}trace]", a)
                a = a.replace("layers:\n", f"layers:\n  - name: trace\n    description: backend-viz runtime tracing (@traced, data, link). Everyone may use it.\n    paths: [\"{tpath}\"]\n    may_depend_on: []\n", 1)
                did.append("added the trace layer to design/architecture.yaml")
            if not re.search(r"^tracing:", a, re.M):
                names = re.findall(r"^\s*-\s*name:\s*(\S+)", a, re.M)
                skip = {"trace", "routes", "api", "schemas", "models", "config", "core"}
                req = [n for n in names if n not in skip] or ["services"]
                a = a.rstrip() + f"\n\n# every public function in these layers must be @traced (the drift hook lists the ones that aren't)\ntracing:\n  required_in: [{', '.join(req)}]\n  decorator: traced\n"
                did.append(f"tracing required in: {', '.join(req)}")
            arch.write_text(a, encoding="utf-8")
    # decorate untraced public functions/classes in the layers that require tracing
    if stack == "fastapi" and (root / "design").is_dir():
        rep = analyze(root)
        mod = None
        main_py = find_fastapi_main(root)
        pkg = main_py.parent if main_py else root / "app"
        mod = ".".join(rel(root, pkg).split("/")) or "app"
        by_file = {}
        for fn in rep.get("untraced") or []:
            by_file.setdefault(fn["file"], []).append(fn)
        n = 0
        for f_rel, fns in by_file.items():
            path = root / f_rel
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            try:
                tree = ast.parse("".join(lines))
            except SyntaxError:
                continue
            targets = set()
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(x["func"] == node.name for x in fns):
                    targets.add(node)
                elif isinstance(node, ast.ClassDef) and any(x["func"].startswith(node.name + ".") for x in fns):
                    targets.add(node)  # one @traced on the class covers its methods
            for node in sorted(targets, key=lambda t: -t.lineno):
                first = min([d.lineno for d in node.decorator_list] + [node.lineno]) - 1
                indent = re.match(r"\s*", lines[first]).group(0)
                lines.insert(first, f"{indent}@traced\n")
                n += 1
            text = "".join(lines)
            if not re.search(r"^from\s+\S*trace\s+import\s+.*\btraced\b", text, re.M):
                imports = list(re.finditer(r"^(from\s+\S+\s+import\s+.+|import\s+.+)$", text, re.M))
                at = imports[-1].end() if imports else 0
                text = text[:at] + ("\n" if at else "") + f"from {mod}.trace import traced" + ("" if at else "\n\n\n") + text[at:]
            path.write_text(text, encoding="utf-8")
        if n:
            did.append(f"added @traced to {n} functions/classes in {len(by_file)} files")

    # monorepo convenience: subprojects' Claude skills usable from this folder
    links = 0
    for sk in root.glob("*/.claude/skills/*/"):
        dst = root / ".claude" / "skills" / sk.name
        if not dst.exists() and sk.parent.parent.parent != root and not sk.name.startswith("backend-viz"):
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                dst.symlink_to(os.path.relpath(sk, dst.parent))
                links += 1
            except OSError:
                pass
    if links:
        did.append(f"linked {links} skills from subfolders into .claude/skills")
    try:
        import yaml  # noqa: F401
    except ImportError:
        did.append("!! install PyYAML once: pip3 install pyyaml")
    return did


def init(root: Path, stack: str, quiet: bool = False):
    d = root / "design"
    d.mkdir(exist_ok=True)
    if not stack:
        stack = "node" if (root / "package.json").exists() and not list(root.glob("**/*.py"))[:1] else "fastapi"
    created = []
    for src, dst in [(f"architecture.{stack}.yaml", "architecture.yaml"), ("openapi.yaml", "openapi.yaml")]:
        if not (d / dst).exists():
            shutil.copy(TEMPLATES / src, d / dst)
            created.append(f"design/{dst}")
    if not quiet:
        print(json.dumps({"stack": stack, "created": created}))


def main():
    args = sys.argv[1:]
    alias = {"live": "--serve", "serve": "--serve", "traces": "--traces", "setup": "--setup", "open": "--open",
             "clear": "--clear-traces", "init": "--init"}
    if args and args[0] in alias:
        args[0] = alias[args[0]]
    if not args:
        args = ["--setup"]  # plain `backend-viz`: set up whatever is missing, then show the summary
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    if "--root" in args:
        root = Path(args[args.index("--root") + 1])
    hook = "--hook" in args
    if hook:
        try:
            data = json.loads(sys.stdin.read() or "{}")
        except json.JSONDecodeError:
            data = {}
        root = Path(data.get("cwd") or root)
        fp = (data.get("tool_input") or {}).get("file_path") or ""
        if fp and Path(fp).suffix not in WATCH_EXT:
            return 0
        # monorepo: the project is the nearest folder above the edited file that has design/
        if fp:
            p = Path(fp).resolve().parent
            for cand in [p, *p.parents]:
                if (cand / "design").is_dir() and any((cand / "design" / n).exists() for n in
                        ("architecture.yaml", "architecture.yml", "architecture.json", "openapi.yaml", "openapi.yml", "openapi.json")):
                    root = cand
                    break
    root = root.resolve()

    if "--init" in args:
        i = args.index("--init")
        stack = args[i + 1] if i + 1 < len(args) and not args[i + 1].startswith("-") else ""
        init(root, stack)
        return 0

    if not (root / "design").is_dir() and not hook:
        kids = [c for c in root.iterdir() if c.is_dir() and (c / "design").is_dir()] if root.is_dir() else []
        if len(kids) == 1:
            top, root = root, kids[0]
            if "--setup" in args:  # link sub-folder skills at the top too
                for line in [d for d in setup(top) if "linked" in d]:
                    print("backend-viz setup: " + line)
    if "--setup" in args:
        did = setup(root)
        print("backend-viz setup: " + ("; ".join(did) if did else "already set up, nothing to do"))
    if not (root / "design").is_dir():
        if hook:
            return 0  # project hasn't opted in
        print("backend-viz: no design/ folder here. Run with --init to scaffold one.", file=sys.stderr)
        return 1

    if "--clear-traces" in args:
        for p in (root / ".backend-viz" / "traces").glob("spans.jsonl*"):
            p.unlink()
        print("backend-viz: traces cleared")
        return 0
    if "--init-tracing" in args:
        dst = root / "app" / "trace"
        dst.mkdir(parents=True, exist_ok=True)
        made = []
        for name in ("__init__.py", "fastapi.py"):
            if not (dst / name).exists():
                shutil.copy(TEMPLATES / "trace" / name, dst / name)
                made.append(f"app/trace/{name}")
        print(json.dumps({"created": made}))
        return 0
    if "--serve" in args:
        i = args.index("--serve")
        port = int(args[i + 1]) if i + 1 < len(args) and args[i + 1].isdigit() else 8765
        serve(root, port)
        return 0

    report = analyze(root)
    dash = write_outputs(root, report)
    if "--traces" in args:
        i = args.index("--traces")
        n = int(args[i + 1]) if i + 1 < len(args) and args[i + 1].isdigit() else 5
        print(traces_text(report, n))
        return 0
    if "--summary" in args:
        print(json.dumps({**report["summary"], "dashboard": str(dash),
                          "violations": report["violations"][:20],
                          "endpoints": report["endpoints"]}))
        return 0
    if hook:
        msg = feedback(report)
        if msg:
            print(msg, file=sys.stderr)
            return 2
        return 0
    s = report["summary"]
    print(f"backend-viz: {s['built']}/{s['designed']} designed endpoints built, "
          f"{s['undocumented']} undocumented, {s['violations']} layer violations, "
          f"{s['unlayered']} unlayered files\n"
          f"tracing: {s['must_trace'] - s['untraced']}/{s['must_trace']} required functions traced, "
          f"{s['called']}/{s['functions']} functions seen running, {s['traces']} recent traces"
          f"{' (' + str(s['trace_errors']) + ' with errors)' if s['trace_errors'] else ''}\nDashboard: {dash}")
    if "--open" in args:
        import webbrowser
        webbrowser.open(dash.resolve().as_uri())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:  # output piped to head etc.
        sys.exit(0)
