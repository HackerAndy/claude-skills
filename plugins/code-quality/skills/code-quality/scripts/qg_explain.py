"""What the report shows under a finding: the code around it, where in that code the problem is, and
what the rule means in plain words (from the tool's own rule docs, fetched once per rule)."""
import json
import re

import qg_checks as qc

CODE_CAP = 200   # most lines of a function's code the report keeps
CONTEXT = 3      # lines kept above and below a finding outside such a function

# The gate's own measures, in plain words. {v} and {limit} are filled in by the page.
METRIC_HELP = {
    "ccn": {
        "title": "Too many paths through it",
        "what": "Cyclomatic complexity counts the separate paths through the function: 1, plus 1 for each "
                "if, loop, case, catch, && / || and ?: it has.",
        "why": "Each path needs its own test, and with many of them it's hard to be sure a change "
               "doesn't break one you didn't think of.",
        "fix": "Return early instead of nesting, move each branch into a named helper, or replace an "
               "if/else chain with a lookup table.",
    },
    "cognitive": {
        "title": "Hard to follow",
        "what": "Cognitive complexity counts each branch and loop, plus 1 more for every level it is "
                "nested inside another, and each run of && / || operators.",
        "why": "Deep nesting makes a reader keep many conditions in mind at once; that's where bugs hide.",
        "fix": "Flatten it: handle the special cases first and return, then move the inner blocks into "
               "named helpers.",
    },
    "nloc": {
        "title": "Too long",
        "what": "The function has more lines of code than the limit (blank lines and comments don't count).",
        "why": "A long function usually does several jobs, which makes each one harder to find, test and change.",
        "fix": "Split it into steps with names that say what they do; in UI code, extract sub-components and hooks.",
    },
    "nesting": {
        "title": "Nested too deeply",
        "what": "The function puts an if, loop or try inside another one more levels deep than the limit "
                "(CodeScene's Nested Complexity).",
        "why": "Each level adds a condition the reader must hold in mind, and the inner code is the hardest "
               "to reach in a test.",
        "fix": "Use guard clauses (return or continue early), and move the inner block into a named helper.",
    },
    "conditional": {
        "title": "Complicated condition",
        "what": "One if / while / ternary condition combines more && / || operators than the limit "
                "(CodeScene's Complex Conditional).",
        "why": "To know when the branch runs, a reader must work out every combination of its parts, and "
               "a missed one is a bug.",
        "fix": "Name each part (a variable or a small function such as is_eligible(order)) and combine "
               "the names, or move the rule into one well-named predicate.",
    },
    "bumps": {
        "title": "Bumpy road",
        "what": "Several separate top-level branches of the function each contain more branches inside "
                "them (CodeScene's Bumpy Road).",
        "why": "Each bump is a chunk of logic that deserves a name; stacked together they make the function "
               "read as several jobs, and the bumps hide behavior from tests.",
        "fix": "Extract each bump into a helper named for what it does, leaving the function as a short "
               "sequence of steps.",
    },
    "params": {
        "title": "Too many parameters",
        "what": "The function takes more parameters than the limit.",
        "why": "Callers have to get the order right, and every new option makes every call longer.",
        "fix": "Group related parameters into one object (a dataclass or an options type).",
    },
    "file_nloc": {
        "title": "File too long",
        "what": "The file has more lines of code than the limit.",
        "why": "Big files mix concerns, so changes collide and it's hard to see what belongs together.",
        "fix": "Move a cohesive part (a component, a group of helpers) into its own module.",
    },
    "duplicate": {
        "title": "Duplicated code",
        "what": "The same block appears in two places.",
        "why": "A fix made in one copy is easily missed in the other.",
        "fix": "Move the shared code into one function both places call.",
    },
}

# What lizard counts toward cyclomatic complexity, found again so the page can mark it. Measured on
# lizard 1.25: in JS/TS `?.` doesn't count but `??` does, and so does each default value in the
# parameter list; in Python `finally`, comprehension `for`/`if` and f-string `if`s count, defaults don't.
BRANCHES = {
    "py": re.compile(r"\b(?:if|elif|for|while|except|finally|and|or|case)\b"),
    "js": re.compile(r"(?<!\.)\b(?:if|for|while|case|catch)\b|&&|\|\||\?\?|(?<![?.])\?(?![.?:])"),
}
QUOTED = re.compile(r"""(["'])(?:\\.|(?!\1).)*\1""")
TRIPLE = re.compile(r'("""|\'\'\')[\s\S]*?\1')
FSTRING = re.compile(r"""\b[fF][rR]?(["'])(?:\\.|(?!\1).)*\1""")
TEMPLATE = re.compile(r"`(?:\\.|[^`])*`")
COMMENT = {"py": re.compile(r"#.*"), "js": re.compile(r"//.*")}
BLOCK_COMMENT = re.compile(r"/\*[\s\S]*?\*/")


def blank(m):
    return re.sub(r"[^\n]", " ", m[0])


def keep_expressions(m):
    """A template literal or f-string with its text blanked and its {...} expressions kept."""
    out, depth = [], 0
    for c in m[0]:
        depth += (c == "{") - (c == "}" and depth > 0)
        out.append(c if depth or c in "}\n" else " ")
    return "".join(out).replace("}", " ")


def code_only(lines, lang):
    """The lines with string text and comments blanked, columns and line breaks kept."""
    text = "\n".join(lines)
    if lang == "js":
        text = TEMPLATE.sub(keep_expressions, BLOCK_COMMENT.sub(blank, text))
    else:
        text = FSTRING.sub(keep_expressions, TRIPLE.sub(blank, text))
    return [COMMENT[lang].sub(blank, QUOTED.sub(blank, line)) for line in text.split("\n")]


# A default value: `name = ...` or `name: Type = ...` right after `(` or `,`, or after `{` on the same
# line (a `{` ending its line opens a block of statements), so in a parameter list or a destructuring
# pattern. A type doesn't start with `<` (that's JSX) or cross a line.
DEFAULT = re.compile(r"(?:(?<=[(,])\s*|(?<=\{)[ \t]*)[\w$]+\s*(?::(?![ \t]*<)[^=;{}()\n]+?)?\s*=(?![=>])")


def defaults(code):
    """[line, start col, end col, "default"] of each default value in JS/TS: lizard counts each as a path."""
    text = "\n".join(code)
    out = []
    for m in DEFAULT.finditer(text):
        j = m.end() - 1
        line = text.count("\n", 0, j)
        col = j - (text.rfind("\n", 0, j) + 1) + 1
        out.append([line, col, col + 1, "default"])
    return out


def arrow_body(text):
    """(start, end) of a one-line arrow function's body: from its `=>` to the bracket that closes
    around it, or the end of the line."""
    start = text.find("=>")
    depth = 0
    for j in range(start, len(text)):
        depth += (text[j] in "([{") - (text[j] in ")]}")
        if depth < 0:
            return start, j
    return start, len(text)


def counted(i, col, nested, owned):
    """Whether a decision at line i, column col belongs to this function, not one nested in it."""
    if any(a < i <= b for a, b in nested):
        return False
    return not (i in owned and owned[i][0] < col < owned[i][1])


def branch_spans(lines, lang, nested=()):
    """[[line index, start col, end col, kind], ...] (1-based columns) of each decision point, skipping
    strings, comments and the lines of functions nested inside (lizard scores those on their own)."""
    code = code_only(lines, lang)
    owned = {a: arrow_body(code[a]) for a, b in nested if a == b and 0 <= a < len(code) and "=>" in code[a]}
    out = [[i, m.start() + 1, m.end() + 1, "branch"] for i, text in enumerate(code)
           for m in BRANCHES[lang].finditer(text) if counted(i, m.start(), nested, owned)]
    return sorted((defaults(code) if lang == "js" else []) + out)


def lang_of(name):
    return "py" if name.endswith(".py") else "js"


def function_code(fn, functions, lines, lang):
    """A function's code for the report: its lines (up to CODE_CAP), its decision points, and the
    line ranges of the functions nested in it (relative to its first line)."""
    body = lines[fn["line"] - 1:min(fn["end"], fn["line"] - 1 + CODE_CAP)]
    nested = [(g["line"] - fn["line"], g["end"] - fn["line"]) for g in functions
              if g is not fn and fn["line"] <= g["line"] <= g["end"] <= fn["end"]]
    return {"start": fn["line"], "lines": body, "more": max(0, fn["end"] - fn["line"] + 1 - len(body)),
            "branches": branch_spans(body, lang, nested), "nested": [[a, b] for a, b in nested if a < b]}


def add_code(root, name, entry, approved):
    """Attach the code a reader needs: a low-scoring function's whole body with its branches marked,
    and a few lines around each finding that isn't inside such a function."""
    try:
        lines = (root / name).read_text(errors="replace").splitlines()
    except OSError:
        return entry
    shown = []
    for fn in (fn for fn in entry["functions"] if fn["score"] < approved):
        fn["code"] = function_code(fn, entry["functions"], lines, lang_of(name))
        shown.append((fn["line"], fn["line"] + len(fn["code"]["lines"]) - 1))
    for f in entry["findings"]:
        if f["symbol"] != "<file>" and not any(a <= f["line"] <= b for a, b in shown):
            start = max(1, f["line"] - CONTEXT)
            f["context"] = {"start": start, "lines": lines[start - 1:(f.get("end_line") or f["line"]) + CONTEXT]}
    return entry


# ---------------------------------------------------------------- rule docs, from the tools

def sections(markdown):
    """{heading: text} of a markdown document's ## sections."""
    out, head = {}, None
    for line in markdown.splitlines():
        if line.startswith("## "):
            head = line[3:].strip()
            out[head] = ""
        elif head:
            out[head] += line + "\n"
    return out


def paragraph(text, n=1):
    """The first n paragraphs, outside code blocks, each joined onto one line."""
    paras = [" ".join(p.split()) for p in re.sub(r"```.*?```", "", text, flags=re.DOTALL).split("\n\n")]
    return " ".join([p for p in paras if p][:n])


FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


def first_block(text):
    """The first fenced code block in text, dedented and cut to 12 lines."""
    m = FENCE.search(text)
    if not m:
        return None
    lines = m[1].rstrip().splitlines()
    pad = min((len(x) - len(x.lstrip()) for x in lines if x.strip()), default=0)
    return "\n".join(x[pad:] for x in lines[:12])


def ruff_help(ctx, code, pkg):
    cmd = qc.tool(ctx, "ruff", pkg)
    data = qc.run_json([*cmd, "rule", code, "--output-format", "json"], pkg, {}) if cmd else {}
    if not data:
        return None
    s = sections(data.get("explanation", ""))
    example = s.get("Example", "")
    bad, _, good = example.partition("Use instead")
    return {"title": data.get("summary") or data.get("name"), "name": data.get("name"),
            "what": paragraph(s.get("What it does", "")), "why": paragraph(s.get("Why is this bad?", ""), 2),
            "bad": first_block(bad), "good": first_block(good),
            "url": f"https://docs.astral.sh/ruff/rules/{data.get('name')}/"}


def biome_help(ctx, name, pkg):
    cmd = qc.tool(ctx, "biome", pkg)
    text = qc.run([*cmd, "explain", name], pkg).stdout if cmd else ""
    if "\nDescription" not in text:
        return None
    desc, _, examples = text.split("\nDescription", 1)[1].partition("\nExamples")
    paras = [" ".join(p.split()) for p in FENCE.sub("", desc).strip().split("\n\n") if p.strip()]
    if not paras:
        return None
    bad, _, good = examples.partition("\nValid")
    kebab = re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()
    return {"title": paras[0].rstrip("."), "name": name, "what": paras[0], "why": " ".join(paras[1:3]),
            "bad": first_block(bad), "good": first_block(good),
            "url": f"https://biomejs.dev/linter/rules/{kebab}/"}


def rule_help(ctx, rule, file):
    tool_name, _, code = rule.partition(":")
    try:
        if tool_name == "ruff":
            return ruff_help(ctx, code, qc.package_of(ctx["root"], ctx["root"] / file, qc.PY_MARKERS))
        if tool_name == "biome":
            return biome_help(ctx, code.split("/")[-1], qc.package_of(ctx["root"], ctx["root"] / file, qc.JS_MARKERS))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return None


def rules(ctx, files, known):
    """{rule: help} for every lint rule in files, reusing what an earlier report fetched."""
    out = {}
    for name, entry in files.items():
        for f in entry["findings"]:
            r = f["rule"]
            if r in out or qc.source_of(r) not in ("ruff", "biome"):
                continue
            out[r] = known.get(r) or rule_help(ctx, r, name)
    return {r: h for r, h in out.items() if h}
