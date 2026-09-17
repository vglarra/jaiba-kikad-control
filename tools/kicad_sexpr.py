"""
Minimal KiCad S-expression reader/writer.

KiCad's .kicad_pcb / .kicad_mod files are S-expressions where the distinction
between a quoted string and a bare atom matters (a net name like "3V3" must be
written back quoted, a number like 1.27 must not). This parser preserves that
distinction by wrapping quoted strings in Quoted (a str subclass), so the
serializer can round-trip a parsed file faithfully.

Why this exists: the board generator normally runs inside KiCad's scripting
console against the `pcbnew` module. That module is not installed on every
machine (it ships with KiCad, not with Python), so this module lets the
project's layout plan be validated -- and a board emitted -- without KiCad.
"""


class Quoted(str):
    """A string that was quoted in the source file and must stay quoted."""


def _tokenize(text):
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c == "(" or c == ")":
            yield c
            i += 1
        elif c == '"':
            i += 1
            buf = []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    buf.append(text[i + 1])
                    i += 2
                else:
                    buf.append(text[i])
                    i += 1
            i += 1  # closing quote
            yield Quoted("".join(buf))
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '()':
                j += 1
            yield text[i:j]
            i = j


def parse(text):
    """Parse the first top-level S-expression in `text`."""
    stack = [[]]
    for tok in _tokenize(text):
        if tok == "(":
            new = []
            stack[-1].append(new)
            stack.append(new)
        elif tok == ")":
            stack.pop()
        else:
            stack[-1].append(tok)
    top = stack[0]
    if len(top) != 1:
        raise ValueError(f"expected exactly one top-level form, found {len(top)}")
    return top[0]


def parse_all(text):
    """Parse every top-level S-expression in `text`."""
    stack = [[]]
    for tok in _tokenize(text):
        if tok == "(":
            new = []
            stack[-1].append(new)
            stack.append(new)
        elif tok == ")":
            stack.pop()
        else:
            stack[-1].append(tok)
    return stack[0]


# --- accessors -------------------------------------------------------------

def children(node, key):
    """Direct child nodes whose head is `key`."""
    if not isinstance(node, list):
        return []
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def child(node, key):
    got = children(node, key)
    return got[0] if got else None


def value_of(node, key, default=None):
    c = child(node, key)
    return c[1] if c is not None and len(c) > 1 else default


# --- serializer ------------------------------------------------------------

def _fmt(v):
    if isinstance(v, Quoted):
        escaped = str(v).replace("\\", "\\\\").replace('"', '\\"')
        return '"' + escaped + '"'
    return str(v)


def dumps(node, level=0):
    """Serialize a node tree back to KiCad's on-disk formatting (tab indents)."""
    if not isinstance(node, list):
        return _fmt(node)
    if not node:
        return "()"
    head = _fmt(node[0])
    rest = node[1:]
    if not rest:
        return "(" + head + ")"
    if not any(isinstance(x, list) for x in rest):
        return "(" + head + " " + " ".join(_fmt(x) for x in rest) + ")"
    parts = ["(" + head]
    for x in rest:
        if isinstance(x, list):
            parts.append("\n" + "\t" * (level + 1) + dumps(x, level + 1))
        else:
            parts.append(" " + _fmt(x))
    parts.append("\n" + "\t" * level + ")")
    return "".join(parts)


def dump_file(root, path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(dumps(root) + "\n")
