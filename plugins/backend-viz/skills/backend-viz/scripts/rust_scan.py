"""
Rust support for backend_map.py: routes, dependency edges between project files, and #[traced] coverage.

Static and best effort, like the Python and Node scanners, with no dependencies:
  - routes: axum `.route("/path", get(h).post(h))` with `.nest("/prefix", module::router())` /
    `.merge(module::router())` one or two levels deep, and route tables written `route!(POST "/path" => Variant)`.
  - edges: `use` trees and inline paths (`crate::`, `super::`, `self::`, a child module, or another crate in
    the same workspace), resolved to the file that declares the module. `mod x;` lines are structure, not edges.
  - functions: `pub fn`s, `pub` methods of inherent impls and every method of a trait impl (except common std
    and framework traits), skipping trait definitions (ports), `#[cfg(test)]` and `#[test]`.
"""
import re
from pathlib import Path

HTTP = ("get", "post", "put", "patch", "delete")
SKIP_PARTS = {"target", "node_modules", ".git", ".backend-viz"}
COMMON_TRAITS = {
    "Default", "Display", "Debug", "From", "Into", "TryFrom", "TryInto", "Clone", "Copy", "PartialEq", "Eq",
    "PartialOrd", "Ord", "Hash", "Drop", "Error", "FromStr", "AsRef", "AsMut", "Deref", "DerefMut", "Iterator",
    "IntoIterator", "Serialize", "Deserialize", "IntoResponse", "FromRequest", "FromRequestParts", "Future",
    "Borrow", "Extend", "FromIterator", "Write", "Read", "Add", "Sub", "Mul", "Div", "Neg", "Not", "Index",
}

CHAR_LITERAL = re.compile(r"'(?:\\(?:x[0-9a-fA-F]{2}|u\{[0-9a-fA-F]{1,6}\}|.)|[^\\'\n])'")
RAW_STRING = re.compile(r'b?r(#*)"')
ROUTE_TABLE = re.compile(r'\broute!\s*\(\s*(GET|POST|PUT|PATCH|DELETE)\s+"(/[^"]*)"\s*=>\s*(\w+)')
AXUM_ROUTE = re.compile(r'\.route\(\s*"(/[^"]*)"\s*,')
AXUM_METHOD = re.compile(r"\b(?:routing::)?(get|post|put|patch|delete)\s*\(\s*([\w:]*)")
AXUM_MOUNT = re.compile(r'\.(nest|merge)\(\s*(?:"(/[^"]*)"\s*,\s*)?([A-Za-z_][\w:]*)\s*\(')
USE_TREE = re.compile(r"\buse\s+([^;]+);")
INLINE_PATH = re.compile(r"(?<![\w:])((?:[A-Za-z_]\w*)(?:::[A-Za-z_]\w*)+)")
TOKEN = re.compile(r"#!?\[|->|=>|::|[{};<>]|\w+|[^\s\w]")
TRACED_ATTR = re.compile(r"^\s*(?:[\w:]*::)?{name}\b")
TEST_MODULE = re.compile(r"#\[\s*cfg\s*\(\s*test\s*\)\s*\](?:\s*#\[[^\]]*\])*\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+\w+\s*\{")
CONSTRUCTORS = {"new"}  # like Python's __init__: not required to be traced


# ---------------------------------------------------------------- lexing
def blank(src: str):
    """(code, shape): comments blanked in both, string and char contents also blanked in shape.
    Same length and newlines as src, so offsets and line numbers still match."""
    code, shape = list(src), list(src)
    i, n = 0, len(src)

    def wipe(start, end, keep_code=False):
        for k in range(start, end):
            if src[k] != "\n":
                shape[k] = " "
                if not keep_code:
                    code[k] = " "

    while i < n:
        c = src[i]
        if src.startswith("//", i):
            end = src.find("\n", i)
            end = n if end < 0 else end
            wipe(i, end)
            i = end
        elif src.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if src.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif src.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            wipe(i, j)
            i = j
        elif c in "rb" and (i == 0 or not (src[i - 1].isalnum() or src[i - 1] == "_")) and RAW_STRING.match(src, i):
            m = RAW_STRING.match(src, i)
            close = '"' + m.group(1)
            end = src.find(close, m.end())
            end = n if end < 0 else end
            wipe(m.end(), end, keep_code=True)
            i = end + len(close)
        elif c == '"':
            j = i + 1
            while j < n and src[j] != '"':
                j += 2 if src[j] == "\\" else 1
            wipe(i + 1, min(j, n), keep_code=True)
            i = j + 1
        elif c == "'" and CHAR_LITERAL.match(src, i):
            end = CHAR_LITERAL.match(src, i).end()
            wipe(i + 1, end - 1, keep_code=True)
            i = end
        else:
            i += 1
    return "".join(code), "".join(shape)


def without_test_modules(code: str, shape: str):
    """Blank `#[cfg(test)] mod … { … }` bodies: tests aren't part of the map, and `super::` inside an inline
    module can't be resolved from the file alone."""
    code, shape = list(code), list(shape)
    text = "".join(shape)
    for m in TEST_MODULE.finditer(text):
        depth, k = 0, m.end() - 1
        while k < len(text):
            depth += {"{": 1, "}": -1}.get(text[k], 0)
            if depth == 0:
                break
            k += 1
        for i in range(m.start(), min(k + 1, len(text))):
            if text[i] != "\n":
                code[i] = shape[i] = " "
    return "".join(code), "".join(shape)


def line_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


# ---------------------------------------------------------------- crates and modules
def rust_crates(root: Path) -> dict:
    """{lib name: src folder} for every crate under root (a workspace, or one crate)."""
    crates = {}
    for toml in root.rglob("Cargo.toml"):
        if SKIP_PARTS & set(toml.relative_to(root).parts):
            continue
        text = toml.read_text(encoding="utf-8", errors="ignore")
        package = re.search(r'^\[package\][^\[]*?^name\s*=\s*"([^"]+)"', text, re.M | re.S)
        lib = re.search(r'^\[lib\][^\[]*?^name\s*=\s*"([^"]+)"', text, re.M | re.S)
        name = (lib or package).group(1) if (lib or package) else None
        if name and (toml.parent / "src").is_dir():
            crates[name.replace("-", "_")] = (toml.parent / "src").resolve()
    return crates


def crate_of(crates: dict, f: Path):
    """(crate name, src folder) holding f, the deepest match."""
    best = None
    for name, src in crates.items():
        if f.is_relative_to(src) and (best is None or len(src.parts) > len(best[1].parts)):
            best = (name, src)
    return best


def module_path(src: Path, f: Path) -> list:
    parts = list(f.relative_to(src).with_suffix("").parts)
    return parts[:-1] if parts and parts[-1] in ("lib", "main", "mod") else parts


def module_dir(src: Path, f: Path) -> Path:
    """The folder a file's child modules live in."""
    return f.parent if f.stem in ("lib", "main", "mod") else f.parent / f.stem


def crate_root(src: Path) -> Path:
    return src / "lib.rs" if (src / "lib.rs").is_file() else src / "main.rs"


def module_file(src: Path, parts: list) -> Path:
    """The deepest file declaring a prefix of `parts` (the rest are items or inline modules)."""
    best, folder = crate_root(src), src
    for part in parts:
        if (folder / f"{part}.rs").is_file():
            best = folder / f"{part}.rs"
        elif (folder / part / "mod.rs").is_file():
            best = folder / part / "mod.rs"
        else:
            break
        folder = folder / part
    return best


def expand_use(tree: str) -> list:
    """`a::{b, c::d as e, self}` -> [[a, b], [a, c, d], [a]]."""
    tree = re.sub(r"\s+as\s+\w+", "", tree)
    tree = re.sub(r"\s+", "", tree).lstrip(":")
    out = []

    def walk(prefix, text):
        depth, start, parts = 0, 0, []
        for k, ch in enumerate(text):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append(text[start:k])
                start = k + 1
        parts.append(text[start:])
        for part in filter(None, parts):
            if "{" in part:
                head, inner = part.split("{", 1)
                walk(prefix + [s for s in head.split("::") if s], inner.rsplit("}", 1)[0])
            else:
                segs = [s for s in part.split("::") if s and s != "*"]
                out.append(prefix + [s for s in segs if s != "self"] if segs else prefix)

    walk([], tree)
    return [p for p in out if p]


def resolve_path(segs: list, here: tuple, crates: dict):
    """The project file a path points into, or None for std and external crates."""
    name, src, f = here
    mod = module_path(src, f)
    head, rest = segs[0], segs[1:]
    if head == "crate":
        return module_file(src, rest)
    if head == "self":
        return module_file(src, mod + rest)
    if head == "super":
        ups = 0
        while ups < len(segs) and segs[ups] == "super":
            ups += 1
        return module_file(src, mod[: max(0, len(mod) - ups)] + segs[ups:])
    if head in crates and head != name:
        return module_file(crates[head], rest)
    child = module_dir(src, f)
    if (child / f"{head}.rs").is_file() or (child / head / "mod.rs").is_file():
        return module_file(src, mod + segs)
    return None


# ---------------------------------------------------------------- routes + imports
def router_stem(f: Path) -> str:
    return f.parent.name if f.stem in ("lib", "mod") else f.stem


def closing(text: str, open_at: int) -> int:
    depth = 0
    for k in range(open_at, len(text)):
        if text[k] == "(":
            depth += 1
        elif text[k] == ")":
            depth -= 1
            if depth == 0:
                return k
    return len(text)


def scan_routes(f_rel: str, stem: str, code: str):
    routes, includes = [], []
    for m in ROUTE_TABLE.finditer(code):
        routes.append({"method": m.group(1), "local_path": m.group(2), "router": (stem, None), "file": f_rel,
                       "line": line_at(code, m.start()), "handler": m.group(3), "absolute": True})
    for m in AXUM_ROUTE.finditer(code):
        call = code[m.end(): closing(code, m.end() - len(m.group(0)) + len(".route"))]
        for mm in AXUM_METHOD.finditer(call):
            routes.append({"method": mm.group(1).upper(), "local_path": m.group(1), "router": (stem, None),
                           "file": f_rel, "line": line_at(code, m.start()), "handler": mm.group(2) or mm.group(1)})
    for m in AXUM_MOUNT.finditer(code):
        segs = m.group(3).split("::")
        key = segs[-2] if len(segs) > 1 else stem
        includes.append({"key": (key, None), "prefix": m.group(2) or "", "parent": (stem, None)})
    return routes, includes


def scan_rust(root: Path, f: Path, src: str, crates: dict):
    """(routes, imported project files, router mounts) for one .rs file."""
    code, shape = without_test_modules(*blank(src))
    f_rel = f.relative_to(root).as_posix()
    routes, includes = scan_routes(f_rel, router_stem(f), code)
    here = crate_of(crates, f.resolve())
    if not here:
        return routes, [], includes
    here = (here[0], here[1], f.resolve())
    paths = []
    for m in USE_TREE.finditer(shape):
        paths += expand_use(m.group(1))
    for m in INLINE_PATH.finditer(shape):
        paths.append(m.group(1).split("::"))
    imports = set()
    for segs in paths:
        target = resolve_path(segs, here, crates)
        if target and target.resolve() != here[2]:
            imports.add(target.resolve())
    return routes, sorted(imports), includes


# ---------------------------------------------------------------- functions + #[traced]
def impl_names(header: list):
    """(type, trait or None) from the tokens after `impl`."""
    tokens, depth, k = header, 0, 0
    if tokens and tokens[0] == "<":
        for k, t in enumerate(tokens):
            depth += 1 if t == "<" else -1 if t == ">" else 0
            if depth == 0:
                break
        tokens = tokens[k + 1:]
    if "where" in tokens:
        tokens = tokens[: tokens.index("where")]

    def last_ident(part):
        level, name = 0, None
        for t in part:
            level += 1 if t == "<" else -1 if t == ">" else 0
            if level == 0 and re.fullmatch(r"[A-Za-z_]\w*", t) and t not in ("dyn", "for", "mut"):
                name = t
        return name

    if "for" in tokens:
        at = tokens.index("for")
        return last_ident(tokens[at + 1:]), last_ident(tokens[:at])
    return last_ident(tokens), None


def scan_rs_functions(f_rel: str, src: str, decorator: str = "traced"):
    """Public functions and methods in a .rs file, and whether each is traced (by its attribute or its impl's)."""
    _, shape = blank(src)
    traced_attr = re.compile(TRACED_ATTR.pattern.format(name=re.escape(decorator)))
    stack = [{"kind": "file", "skip": False}]
    header, at, attrs, out, pos = [], [], [], [], 0
    while True:
        m = TOKEN.search(shape, pos)
        if not m:
            break
        tok, pos = m.group(0), m.end()
        if tok in ("#[", "#!["):
            depth, k = 1, pos
            while k < len(shape) and depth:
                depth += {"[": 1, "]": -1}.get(shape[k], 0)
                k += 1
            attrs.append(shape[pos: k - 1])
            pos = k
        elif tok == "{":
            stack.append(open_context(stack[-1], (header, at, attrs), shape, traced_attr, out, f_rel))
            header, at, attrs = [], [], []
        elif tok == "}":
            if len(stack) > 1:
                stack.pop()
            header, at, attrs = [], [], []
        elif tok == ";":
            header, at, attrs = [], [], []
        else:
            header.append(tok)
            at.append(m.start())
    return out


def open_context(parent, item, shape, traced_attr, out, f_rel):
    """The context a `{` opens, recording the function it starts when that function counts.
    `item` is the tokens since the last item boundary, their offsets, and the attributes before them."""
    header, at, attrs = item
    skip = parent["skip"] or any(re.match(r"\s*cfg\s*\(\s*test", a) for a in attrs)
    is_traced = any(traced_attr.match(a) for a in attrs)
    if parent["kind"] in ("fn", "block", "trait"):
        return {"kind": "block", "skip": True}
    if "fn" in header:
        fn_at = header.index("fn")
        name = header[fn_at + 1] if fn_at + 1 < len(header) else "?"
        before = header[:fn_at]
        is_public = "pub" in before or parent.get("trait") is not None
        if parent["kind"] == "impl" and parent.get("trait") in COMMON_TRAITS:
            skip = True
        is_test = any(re.match(r"\s*(?:[\w:]*::)?test\b", a) for a in attrs)
        if not skip and is_public and not is_test and "const" not in before and name not in CONSTRUCTORS:
            func = f"{parent['type']}.{name}" if parent["kind"] == "impl" and parent.get("type") else name
            out.append({"file": f_rel, "func": func, "line": line_at(shape, at[fn_at]),
                        "traced": is_traced or parent.get("traced", False)})
        return {"kind": "fn", "skip": True}
    if "impl" in header:
        type_name, trait = impl_names(header[header.index("impl") + 1:])
        return {"kind": "impl", "skip": skip, "type": type_name, "trait": trait, "traced": is_traced}
    if "trait" in header:
        return {"kind": "trait", "skip": True}
    if "mod" in header:
        return {"kind": "mod", "skip": skip}
    return {"kind": "block", "skip": True}
