"""Structure smells that lizard doesn't measure, read from tree-sitter syntax trees so Python, JavaScript
and TypeScript are scored by one definition. Modelled on CodeScene's smells of the same names:

  nesting      deepest chain of if / loop / try / switch inside one another (Nested Complexity)
  conditional  most && / || (and / or) operators in any single condition (Complex Conditional)
  bumps        chunks of nested logic in the function, counted the way CodeScene counts them (Bumpy Road):
               each branch of a top-level if / switch / match / try that holds a nested branch, loop or
               ternary is a bump; a top-level loop is one bump if it holds branches, or the bumps inside it

Runs on its own, `python qg_smells.py FILE...`, printing JSON {file: [{line, end, nesting, conditional,
bumps}, ...]} with one entry per function; qg_checks.py runs it in-process when tree-sitter is
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
CONDITION_OWNERS = {"if_statement", "elif_clause", "while_statement", "do_statement", "for_statement",
                    "ternary_expression"}
LOGICAL = {"&&", "||"}
LOOPS = {"for_statement", "for_in_statement", "while_statement", "do_statement"}
FORKS = {"if_statement", "switch_statement", "match_statement", "try_statement"}  # code that takes one of several paths
TERNARIES = {"conditional_expression", "ternary_expression"}
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
    """Deepest chain of branches below node, counting `else if` as the same level as its `if`."""
    best = depth
    for child in own_children(node):
        level = depth + (child.type in BRANCHES and not (child.type == "if_statement" and node.type == "else_clause"))
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


def conditions(node):
    """The condition expression of each branch inside the function."""
    out = []
    for c in own_children(node):
        cond = c.child_by_field_name("condition") if c.type in CONDITION_OWNERS else None
        if c.type == "conditional_expression" and len(c.named_children) == 3:  # python ternary
            cond = c.named_children[1]
        if cond is not None:
            out.append(cond)
        out += conditions(c)
    return out


def has_logic(node):
    """Whether node is, or holds, a branch, loop or ternary of its own function."""
    return node.type in BRANCHES or node.type in TERNARIES or any(has_logic(c) for c in own_children(node))


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


def bumps(block):
    """Chunks of nested logic among block's statements (see the module docstring)."""
    n = 0
    for st in block.named_children:
        body = st.child_by_field_name("body")
        if st.type in FORKS:
            n += sum(has_logic(p) for p in paths(st))
        elif st.type in LOOPS and body is not None:
            n += bumps(body) or int(has_logic(body))
        elif st.type in ("with_statement", "statement_block"):  # no choice of path: look inside
            n += bumps(body if body is not None else st)
    return n


def measure_function(fn):
    body = fn.child_by_field_name("body")
    conds = conditions(fn)
    return {"line": fn.start_point[0] + 1, "end": fn.end_point[0] + 1, "nesting": nesting(fn),
            "conditional": max((operators(c) + _self(c) for c in conds), default=0),
            "bumps": bumps(body) if body is not None and body.type in {"block", "statement_block"} else 0}


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


def measure(paths):
    """{path: [per-function measures]} for the source files that tree-sitter can read."""
    parsers, out = {}, {}
    for path in paths:
        parser = parser_for(path, parsers)
        if parser:
            tree = parser.parse(Path(path).read_bytes())
            out[str(path)] = [measure_function(fn) for fn in functions_in(tree.root_node)]
    return out


if __name__ == "__main__":
    json.dump(measure(sys.argv[1:]), sys.stdout)
