"""Structure smells that lizard doesn't measure, read from tree-sitter syntax trees so Python, JavaScript
and TypeScript are scored by one definition. Modelled on CodeScene's smells of the same names:

  nesting      deepest chain of if / loop / try / switch inside one another (Nested Complexity)
  conditional  most && / || (and / or) operators in any single condition (Complex Conditional)
  bumps        top-level branches of the function that themselves contain nested branches (Bumpy Road)

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


def measure_function(fn):
    body = fn.child_by_field_name("body")
    top = [c for c in body.named_children if c.type in BRANCHES] if body is not None and body.type in {
        "block", "statement_block"} else []
    conds = conditions(fn)
    return {"line": fn.start_point[0] + 1, "end": fn.end_point[0] + 1, "nesting": nesting(fn),
            "conditional": max((operators(c) + _self(c) for c in conds), default=0),
            "bumps": sum(nesting(b, 1) >= 2 for b in top)}


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
