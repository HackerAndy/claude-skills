"""Structure smells that lizard doesn't measure, read from tree-sitter syntax trees so Python, JavaScript,
TypeScript and Rust are scored by one definition. Modelled on CodeScene's smells of the same names:

  nesting      deepest chain of if / loop / switch inside one another; try and with don't count (Nested Complexity)
  conditional  most && / || (and / or) operators in any single condition (Complex Conditional)
  bumps        chunks of nested logic in the function, counted the way CodeScene counts them (Bumpy Road),
               fitted to its flags on 2,391 functions: each path of an if / switch / match that holds a
               nested branch or loop (or in Python, assigns a ternary; in Rust, has a match guard) is a bump, and
               in Rust a path holding bumps of its own counts those instead (`else { if }` is `else if`), and
               a match is one bump unless its arms hold bumps of their own; a loop is one bump if it holds branches, or else the bumps
               inside it plus one if it also has a plain conditional path; try and with are looked inside

It also gives `ccn`, cyclomatic complexity counted as CodeScene counts it (lizard's count misses decisions
in some JSX): each if / elif, loop, except / catch, case, `&&` / `||` (`and` / `or`), JS ternary and `?.`,
Python comprehension `for`, `raise` / `throw`, and a Python `else`; not a JS `else` or default, a Python
ternary, comprehension `if` or `finally`, nor `??`. In Rust: each if / if let / let-else, for / while / loop,
match (once, whatever its arms) and match guard, and `&&` / `||`; not an `else`, `?` or a panicking macro.
A Rust closure is code of the function it's written in (lizard doesn't list closures), and a nested `fn` folds.

And `similar`: whether the function has a near copy in the same file, standing in for CodeScene's Code
Duplication (similar functions within one file). CodeScene doesn't publish how it compares them; this
compares functions of SIMILAR_MIN_LINES lines or more (SIMILAR_MIN_LINES_RUST in Rust; nested ones folded in, as CodeScene folds them) by
the share of 5-token runs they have in common (Jaccard), with the threshold fitted to its flags on one
project. See docs/codescene-parity.md.

Runs on its own, `python qg_smells.py FILE...`, printing JSON {file: [{line, end, nesting, conditional,
bumps, ccn, loc, folded, similar}, ...]} with one entry per function; qg_checks.py runs it in-process when tree-sitter is
installed and through `uvx --with tree-sitter-language-pack` otherwise. Needs tree-sitter-language-pack."""
import json
import sys
from pathlib import Path

LANGUAGES = {".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
             ".cjs": "javascript", ".ts": "typescript", ".mts": "typescript", ".cts": "typescript",
             ".tsx": "tsx", ".rs": "rust"}
FUNCTIONS = {"function_definition", "function_declaration", "function_expression", "function",
             "generator_function_declaration", "generator_function", "method_definition", "arrow_function",
             "function_item"}
RUST_LOOPS = {"for_expression", "while_expression", "loop_expression"}
BRANCHES = {"if_statement", "for_statement", "for_in_statement", "while_statement", "do_statement",
            "try_statement", "switch_statement", "match_statement", "if_expression", "match_expression", *RUST_LOOPS}
CONDITION_OWNERS = {"if_statement", "elif_clause", "while_statement", "do_statement", "for_statement",
                    "if_expression", "while_expression"}  # a Rust match guard isn't a Complex Conditional for CodeScene
IFS = {"if_statement", "if_expression"}
# A JS / TS ternary's condition isn't a Complex Conditional for CodeScene; a Python one is (handled in conditions)
LOGICAL = {"&&", "||"}
LOOPS = {"for_statement", "for_in_statement", "while_statement", "do_statement", *RUST_LOOPS}
FORKS = {"if_statement", "switch_statement", "match_statement", "if_expression", "match_expression"}  # code that takes one of several paths
CONDITIONED = {"elif_clause", "case_clause", "switch_case"}  # a path with a condition of its own (a Rust match arm isn't, for CodeScene)
CLAUSES = {"elif_clause", "else_clause", "except_clause", "finally_clause", "case_clause", "switch_case",
           "switch_default", "catch_clause", "match_arm"}


def parser_for(path, parsers):
    lang = LANGUAGES.get(Path(path).suffix.lower())
    if lang and lang not in parsers:
        from tree_sitter_language_pack import get_parser
        parsers[lang] = get_parser(lang)
    return parsers.get(lang)


def is_function(node):
    return node.is_named and node.type in FUNCTIONS  # the `function` keyword is an unnamed token of that type


def own_children(node):
    """Children of node that belong to the same function: nested functions are measured on their own."""
    return [c for c in node.children if not is_function(c)]


def nesting(node, depth=0):
    """Deepest chain of branches below node, counting `else if` as the same level as its `if`. As in
    CodeScene, a try is not a level: it doesn't choose a path. In Rust, CodeScene doesn't count an `else`
    block as inside its `if`: what's in it is at the if's own level."""
    best = depth
    for child in own_children(node):
        if child.type == "else_clause" and node.type == "if_expression":
            best = max(best, nesting(child, depth - 1))
            continue
        level = depth + (child.type in BRANCHES and child.type != "try_statement"
                         and not (child.type == "if_statement" and node.type == "else_clause"))
        best = max(best, nesting(child, level))
    return best


def operators(node):
    """&& / || (and / or) operators inside one condition."""
    n = 0
    for c in own_children(node):
        if c.type == "boolean_operator" or (c.type == "binary_expression" and
                                            (op := c.child_by_field_name("operator")) and op.type in LOGICAL):
            n += 1
        n += operators(c)
    return n


def unbraced_js_if(node):
    """A JS / TS `if (...) stmt` without braces whose condition CodeScene doesn't check: it does only when that
    statement, or the one after it, ends in a semicolon (semicolon-free code goes unchecked). Python's it does."""
    body = node.child_by_field_name("consequence")
    if node.type != "if_statement" or body is None or body.type in ("statement_block", "block"):
        return False
    after = node.next_named_sibling
    return not body.text.rstrip().endswith(b";") and not (after is not None and after.text.rstrip().endswith(b";"))


def conditions(node):
    """The condition expression of each branch inside the function."""
    out = []
    for c in own_children(node):
        cond = c.child_by_field_name("condition") if c.type in CONDITION_OWNERS and not unbraced_js_if(c) else None
        if c.type == "conditional_expression" and len(c.named_children) == 3:  # python ternary
            cond = c.named_children[1]
        if cond is not None:
            out.append(cond)
        out += conditions(c)
    return out


def lone_if(else_clause):
    """[the if] when a Rust else's block holds nothing but an if, which CodeScene reads as `else if`."""
    block = next((x for x in else_clause.named_children if x.type == "block"), None)
    body = statements(block) if block is not None else []
    return body if len(body) == 1 and body[0].type == "if_expression" else []


def path_block(path):
    """The block a Rust path runs: an if's or else's block, or a match arm's when it has one."""
    if path.type == "block":
        return path
    body = path.child_by_field_name("value") if path.type == "match_arm" else next(
        (x for x in path.named_children if x.type == "block"), None)
    return body if body is not None and body.type == "block" else None


def path_bumps(path):
    """A Rust path's bumps: the bumps inside it if it has any, else one if it holds logic at all."""
    block = path_block(path)
    inner = bumps(block) if block is not None else 0
    return inner or int(has_logic(path))


def has_logic(node):
    """Whether node is, or holds, a branch or loop of its own function. A ternary isn't one for CodeScene,
    except in Python where a statement assigns it straight to a name; a Rust match guard is one."""
    return (node.type in BRANCHES or assigns_ternary(node) or is_guard(node)
            or any(has_logic(c) for c in own_children(node)))


def is_guard(node):
    """Whether node is a Rust match arm's pattern with an `if` guard."""
    return node.type == "match_pattern" and node.child_by_field_name("condition") is not None


def assigns_ternary(node):
    """Whether node is a Python block with a statement like `x = a if c else b`."""
    if node.type != "block":  # Python's block; JS / TS have statement_block
        return False
    for st in node.named_children:
        e = st.named_children[0] if st.type == "expression_statement" and st.named_children else st  # a one-line block holds it bare
        right = e.child_by_field_name("right") if e.type in ("assignment", "augmented_assignment") else None
        if right is not None and right.type == "conditional_expression":
            return True
    return False


def paths(fork):
    """The code on each path of an if / elif / else, switch / match or try (clauses keep their condition)."""
    out = []
    for c in fork.named_children:
        if c in (fork.child_by_field_name("condition"), fork.child_by_field_name("subject"),
                 fork.child_by_field_name("value")):
            continue
        inner = [x for x in c.named_children if x.type in IFS] or lone_if(c)
        if c.type == "else_clause" and inner:  # `else if`, and in Rust `else { if ... }`: the next link of the chain
            out += paths(inner[0])
        elif c.type in ("switch_body", "match_block") or (fork.type == "match_statement" and c.type == "block"):
            out += [x for x in c.named_children if x.type in CLAUSES]
        else:
            out.append(c)
    return out


RUST_VALUE = {"let_declaration": "value", "assignment_expression": "right", "compound_assignment_expr": "right",
              "return_expression": None}


def statements(block):
    """block's statements, each Rust statement read as the expression it holds: `x;`, and the value of
    `let x = ...`, `x = ...` and `return ...`, so `let x = if ... { ... }` is the if."""
    out = []
    for st in block.named_children:
        if st.type == "expression_statement" and st.named_children:
            st = st.named_children[0]
        if st.type in RUST_VALUE:
            field = RUST_VALUE[st.type]
            value = st.child_by_field_name(field) if field else (st.named_children or [None])[0]
            st = value if value is not None else st
        out.append(st)
    return out


def closures_in(node):
    """The Rust closures written in node, outermost only."""
    for c in node.named_children:
        if c.type == "closure_expression":
            yield c
        else:
            yield from closures_in(c)


def plain_path(block):
    """Whether block has an if / elif / case path with a condition and no nested logic in it."""
    for st in statements(block):
        if st.type in FORKS:
            for p in paths(st):
                if (p.type in CONDITIONED or p == st.child_by_field_name("consequence")) and not has_logic(p):
                    return True
    return False


def blocks_of(st):
    """The blocks of a try (body, except / catch, else, finally), a with, or a bare block."""
    if st.type in ("statement_block", "block"):
        return [st]
    out = []
    for c in st.named_children:
        if c.type in ("block", "statement_block"):
            out.append(c)
        else:
            out += [x for x in c.named_children if x.type in ("block", "statement_block")]
    return out


def bumps(block):
    """Chunks of nested logic among block's statements (see the module docstring)."""
    n = 0
    for st in statements(block):
        body = st.child_by_field_name("body")
        if st.type == "if_expression":
            n += sum(path_bumps(p) for p in paths(st))
        elif st.type == "match_expression":  # one bump for the whole match, unless its arms hold bumps of their own
            arms = paths(st)
            n += sum(bumps(b) for p in arms if (b := path_block(p)) is not None) or int(any(map(has_logic, arms)))
        elif st.type in FORKS:
            n += sum(has_logic(p) for p in paths(st))
        elif st.type in LOOPS and body is not None:
            inner = bumps(body)
            n += inner + plain_path(body) if inner else int(has_logic(body))
        elif st.type in ("try_statement", "with_statement", "statement_block", "block", "unsafe_block"):  # no choice of path: look inside
            n += sum(bumps(b) for b in blocks_of(st))
        else:  # a Rust closure's body counts as code of the function, as a nested function's would
            n += sum(bumps(body) for c in closures_in(st)
                     if (body := c.child_by_field_name("body")) is not None and body.type == "block")
    return n


DECISIONS = {"if_statement", "elif_clause", "for_statement", "for_in_statement", "while_statement", "do_statement",
             "except_clause", "catch_clause", "switch_case", "case_clause", "ternary_expression", "optional_chain",
             "raise_statement", "throw_statement", "for_in_clause", "boolean_operator",
             "if_expression", "match_expression", *RUST_LOOPS}


def ccn(fn):
    """Cyclomatic complexity of fn's own code, counted as CodeScene counts it (see the module docstring)."""
    n = 1
    for node in own_nodes(fn):
        if node.type in DECISIONS:
            n += 1
        elif node.type == "else_clause" and node.parent is not None and node.parent.type == "if_statement":
            n += fn.type == "function_definition"  # a Python else counts; a JS else doesn't
        elif node.type == "binary_expression" and (op := node.child_by_field_name("operator")) and op.type in LOGICAL:
            n += 1
        elif is_guard(node) or (node.type == "let_declaration" and node.child_by_field_name("alternative")):
            n += 1  # a Rust match guard, or let-else
    return n


def own_nodes(node):
    """Every node inside node that belongs to its own function, not to a nested one."""
    for c in own_children(node):
        yield c
        yield from own_nodes(c)


def measure_function(fn):
    body = fn.child_by_field_name("body")
    conds = conditions(fn)
    return {"line": fn.start_point[0] + 1, "end": fn.end_point[0] + 1, "nesting": nesting(fn),
            "conditional": max((operators(c) + _self(c) for c in conds), default=0),
            "bumps": bumps(body) if body is not None and body.type in {"block", "statement_block"} else 0,
            "ccn": ccn(fn), "loc": loc(fn), "folded": is_folded(fn), "name": name_of(fn)}


def _self(cond):
    """A condition that is itself a logical operator counts that operator too."""
    op = cond.child_by_field_name("operator")
    return int(cond.type == "boolean_operator" or (cond.type == "binary_expression" and op is not None
                                                  and op.type in LOGICAL))


def functions_in(node):
    for c in node.children:
        if is_function(c):
            yield c
        yield from functions_in(c)


SIMILAR_MIN_LINES = 10  # CodeScene's function_duplication_min_lines_of_code_for_check
SIMILAR_MIN_LINES_RUST = 9  # fitted on 402 Rust files: fewer missed and fewer extra flags than 10
SIMILAR_SHARE = 0.5     # fitted on 1,800 files to favour stricter over missed: CodeScene says 75%, but measures differently
SHINGLE = 5             # tokens per run compared
OWN_FUNCTION_LINES = 25  # a nested JS / TS function this long is a function of its own for CodeScene


DECLARING = {"variable_declarator", "assignment_expression", "pair", "public_field_definition"}
STATEMENTS = {"expression_statement", "return_statement", "lexical_declaration", "variable_declaration",
              "statement_block", "program", "if_statement", "for_statement", "for_in_statement", "while_statement"}


def name_of(fn):
    """The name CodeScene gives a function: its own, or that of the variable, property or assignment whose value
    it is (`const rows = list.map(r => ...)` is rows). None for an inline callback."""
    own = fn.child_by_field_name("name")
    if own is not None:
        return own.text.decode(errors="replace")
    p = fn.parent
    while p is not None and p.type not in STATEMENTS and not is_function(p):
        if p.type in DECLARING:
            target = p.child_by_field_name("name") or p.child_by_field_name("left") or p.child_by_field_name("key")
            return target.text.decode(errors="replace").split(".")[-1] if target is not None else None
        p = p.parent
    return None


def js_named(fn):
    """Whether CodeScene can name a JS / TS function (see name_of). An inline callback can't."""
    return name_of(fn) is not None


def is_folded(fn):
    """Whether CodeScene counts fn as part of the function around it: always in Python and Rust; in JS / TS unless it's
    OWN_FUNCTION_LINES lines or more and has a name (js_named)."""
    p = fn.parent
    while p is not None and not is_function(p):
        p = p.parent
    if p is None:
        return False
    return fn.type in ("function_definition", "function_item") or source_lines(fn) < OWN_FUNCTION_LINES or not js_named(fn)


def code_leaves(node, markup=False):
    """(line, text) of each leaf below node that is code: comments and JSX left out. CodeScene doesn't count
    two components as duplicates for alike markup, nor a function of mostly markup as long enough to check."""
    if "comment" in node.type:
        return
    markup = markup or node.type.startswith("jsx_")
    if node.child_count == 0 and not markup:
        yield node.start_point[0], node.text
    for c in node.children:
        yield from code_leaves(c, markup)


def loc(fn):
    """Lines of code as CodeScene counts them: every line a non-comment token touches, so a docstring, a
    multi-line string and each line of JSX count, and blank or comment-only lines don't. A nested function
    that stays a function of its own (see is_folded) is left out; one folded in counts."""
    lines = set()

    def walk(n):
        if (n is not fn and is_function(n) and not is_folded(n)) or "comment" in n.type:
            return
        if n.child_count == 0:
            lines.update(range(n.start_point[0], n.end_point[0] + 1))
        for c in n.children:
            walk(c)
    walk(fn)
    return len(lines)


def source_lines(node):
    """Lines of node that hold anything but comments, JSX included: lizard's count."""
    lines = set()

    def walk(n):
        if "comment" in n.type:
            return
        if n.child_count == 0:
            lines.add(n.start_point[0])
        for c in n.children:
            walk(c)
    walk(node)
    return len(lines)


def similar(fns, min_lines=SIMILAR_MIN_LINES):
    """The indexes of functions with a near copy among fns (see the module docstring)."""
    runs = {}
    for i, fn in enumerate(fns):
        leaves = list(code_leaves(fn))
        if not is_folded(fn) and len({line for line, _ in leaves}) >= min_lines:
            t = [text for _, text in leaves]
            runs[i] = {tuple(t[k:k + SHINGLE]) for k in range(max(1, len(t) - SHINGLE + 1))}
    out = set()
    keys = sorted(runs)
    for a, i in enumerate(keys):
        for j in keys[a + 1:]:
            if fns[i].start_byte <= fns[j].start_byte and fns[j].end_byte <= fns[i].end_byte:
                continue  # j is nested in i, not a copy of it
            if len(runs[i] & runs[j]) >= SIMILAR_SHARE * len(runs[i] | runs[j]):
                out |= {i, j}
    return out


def measure(paths):
    """{path: [per-function measures]} for the source files that tree-sitter can read."""
    parsers, out = {}, {}
    for path in paths:
        parser = parser_for(path, parsers)
        if parser:
            tree = parser.parse(Path(path).read_bytes())
            fns = list(functions_in(tree.root_node))
            near = similar(fns, SIMILAR_MIN_LINES_RUST if Path(path).suffix.lower() == ".rs" else SIMILAR_MIN_LINES)
            out[str(path)] = [measure_function(fn) | {"similar": i in near} for i, fn in enumerate(fns)]
    return out


if __name__ == "__main__":
    json.dump(measure(sys.argv[1:]), sys.stdout)
