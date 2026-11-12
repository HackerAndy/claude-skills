"""Structure smells that lizard doesn't measure, read from tree-sitter syntax trees so Python, JavaScript
and TypeScript are scored by one definition. Modelled on CodeScene's smells of the same names:

  nesting      deepest chain of if / loop / switch inside one another; try and with don't count (Nested Complexity)
  conditional  most && / || (and / or) operators in any single condition (Complex Conditional)
  bumps        chunks of nested logic in the function, counted the way CodeScene counts them (Bumpy Road),
               fitted to its flags on 2,391 functions: each path of an if / switch / match that holds a
               nested branch or loop (or in Python, assigns a ternary) is a bump; a loop is one bump if it holds branches, or else the bumps
               inside it plus one if it also has a plain conditional path; try and with are looked inside

It also gives `ccn_fix`, what turns lizard's cyclomatic count into CodeScene's: CodeScene counts each
`raise` / `throw`, a Python `else` and a JS / TS `?.`, and not a Python ternary, comprehension `if` or
`finally`, nor a JS / TS `??` or default parameter value, all of which lizard counts the other way.

And `similar`: whether the function has a near copy in the same file, standing in for CodeScene's Code
Duplication (similar functions within one file). CodeScene doesn't publish how it compares them; this
compares functions of SIMILAR_MIN_LINES lines or more (nested ones folded in, as CodeScene folds them) by
the share of 5-token runs they have in common (Jaccard), with the threshold fitted to its flags on one
project. See docs/codescene-parity.md.

Runs on its own, `python qg_smells.py FILE...`, printing JSON {file: [{line, end, nesting, conditional,
bumps, ccn_fix, similar}, ...]} with one entry per function; qg_checks.py runs it in-process when tree-sitter is
installed and through `uvx --with tree-sitter-language-pack` otherwise. Needs tree-sitter-language-pack."""
import json
import sys
from pathlib import Path

LANGUAGES = {".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
             ".cjs": "javascript", ".ts": "typescript", ".mts": "typescript", ".cts": "typescript",
             ".tsx": "tsx"}
FUNCTIONS = {"function_definition", "function_declaration", "function_expression", "function",
             "generator_function_declaration", "generator_function", "method_definition", "arrow_function"}
BRANCHES = {"if_statement", "for_statement", "for_in_statement", "while_statement", "do_statement",
            "try_statement", "switch_statement", "match_statement"}
CONDITION_OWNERS = {"if_statement", "elif_clause", "while_statement", "do_statement", "for_statement"}
# A JS / TS ternary's condition isn't a Complex Conditional for CodeScene; a Python one is (handled in conditions)
LOGICAL = {"&&", "||"}
LOOPS = {"for_statement", "for_in_statement", "while_statement", "do_statement"}
FORKS = {"if_statement", "switch_statement", "match_statement"}  # code that takes one of several paths
CONDITIONED = {"elif_clause", "case_clause", "switch_case"}  # a path with a condition of its own
CLAUSES = {"elif_clause", "else_clause", "except_clause", "finally_clause", "case_clause", "switch_case",
           "switch_default", "catch_clause"}


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
    CodeScene, a try is not a level: it doesn't choose a path."""
    best = depth
    for child in own_children(node):
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


def has_logic(node):
    """Whether node is, or holds, a branch or loop of its own function. A ternary isn't one for CodeScene,
    except in Python where a statement assigns it straight to a name."""
    return node.type in BRANCHES or assigns_ternary(node) or any(has_logic(c) for c in own_children(node))


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
        if c == fork.child_by_field_name("condition") or c == fork.child_by_field_name("subject"):
            continue
        inner = [x for x in c.named_children if x.type == "if_statement"]
        if c.type == "else_clause" and inner:  # JS `else if`: the next link of the same chain
            out += paths(inner[0])
        elif c.type == "switch_body" or (fork.type == "match_statement" and c.type == "block"):
            out += [x for x in c.named_children if x.type in CLAUSES]
        else:
            out.append(c)
    return out


def plain_path(block):
    """Whether block has an if / elif / case path with a condition and no nested logic in it."""
    for st in block.named_children:
        if st.type in FORKS:
            for p in paths(st):
                if (p.type in CONDITIONED or p == st.child_by_field_name("consequence")) and not has_logic(p):
                    return True
    return False


def blocks_of(st):
    """The blocks of a try (body, except / catch, else, finally), a with, or a bare block."""
    if st.type == "statement_block":
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
    for st in block.named_children:
        body = st.child_by_field_name("body")
        if st.type in FORKS:
            n += sum(has_logic(p) for p in paths(st))
        elif st.type in LOOPS and body is not None:
            inner = bumps(body)
            n += inner + plain_path(body) if inner else int(has_logic(body))
        elif st.type in ("try_statement", "with_statement", "statement_block"):  # no choice of path: look inside
            n += sum(bumps(b) for b in blocks_of(st))
    return n


def ccn_fix(fn):
    """CodeScene's cyclomatic count less lizard's, for this function's own code (see the module docstring)."""
    fix = 0
    for node in own_nodes(fn):
        if node.type == "else_clause" and node.parent is not None and node.parent.type == "if_statement" \
                and fn.type == "function_definition":  # Python; a JS else isn't counted by either
            fix += 1
        elif node.type in ("optional_chain", "raise_statement", "throw_statement"):
            fix += 1
        elif node.type in ("conditional_expression", "if_clause", "finally_clause"):
            fix -= 1
        elif node.type == "binary_expression" and (op := node.child_by_field_name("operator")) and op.type == "??":
            fix -= 1
    params = fn.child_by_field_name("parameters")
    if params is not None and fn.type != "function_definition":  # JS / TS default values; lizard skips Python's
        fix -= sum(1 for p in params.named_children
                   if p.type == "assignment_pattern" or p.child_by_field_name("value") is not None)
    return fix


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
            "ccn_fix": ccn_fix(fn)}


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
SIMILAR_SHARE = 0.6     # fitted: CodeScene's own setting says 75%, but its measure isn't this one
SHINGLE = 5             # tokens per run compared
OWN_FUNCTION_LINES = 25  # a nested JS / TS function this long is a function of its own for CodeScene


def is_folded(fn):
    """Whether CodeScene counts fn as part of the function around it."""
    p = fn.parent
    while p is not None and not is_function(p):
        p = p.parent
    return p is not None and (fn.type == "function_definition" or source_lines(fn) < OWN_FUNCTION_LINES)


def code_leaves(node, markup=False):
    """(line, text) of each leaf below node that is code: comments and JSX left out. CodeScene doesn't count
    two components as duplicates for alike markup, nor a function of mostly markup as long enough to check."""
    markup = markup or node.type.startswith("jsx_")
    if node.child_count == 0 and not markup and "comment" not in node.type:
        yield node.start_point[0], node.text
    for c in node.children:
        yield from code_leaves(c, markup)


def source_lines(node):
    """Lines of node that hold anything but comments, JSX included: lizard's count."""
    lines = set()

    def walk(n):
        if n.child_count == 0 and "comment" not in n.type:
            lines.add(n.start_point[0])
        for c in n.children:
            walk(c)
    walk(node)
    return len(lines)


def similar(fns):
    """The indexes of functions with a near copy among fns (see the module docstring)."""
    runs = {}
    for i, fn in enumerate(fns):
        leaves = list(code_leaves(fn))
        if not is_folded(fn) and len({line for line, _ in leaves}) >= SIMILAR_MIN_LINES:
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
            near = similar(fns)
            out[str(path)] = [measure_function(fn) | {"similar": i in near} for i, fn in enumerate(fns)]
    return out


if __name__ == "__main__":
    json.dump(measure(sys.argv[1:]), sys.stdout)
