"""Glyph names and glyph order (design document, section 11)."""

from collections import deque

PRIVATE_USE = range(0xE000, 0xF900)
SCRIPT = ".s"
SCRIPTSCRIPT = ".ss"


def primary(codepoints):
    """The code point a glyph is named after."""
    public = [c for c in codepoints if c not in PRIVATE_USE]
    return min(public or codepoints)


def base_name(codepoints):
    codepoint = primary(codepoints)
    return ("uni%04X" if codepoint <= 0xFFFF else "u%05X") % codepoint


PARTS = ("bot", "left", "ext", "mid", "top", "right")


def size_suffix(name):
    for suffix in (SCRIPTSCRIPT, SCRIPT):
        if name.endswith(suffix):
            return suffix
    return ""


def with_suffix(name, suffix):
    """Add a suffix before the optical size, which always comes last."""
    size = size_suffix(name)
    return name[:len(name) - len(size)] + suffix + size


def order_key(name):
    """Sort key of a glyph without code points: the code point it is
    named after, then forms, step, part and optical size."""
    base, *tokens = name.split(".")
    codepoint = int(base[3:] if base.startswith("uni") else base[1:], 16)
    size = (SCRIPT, SCRIPTSCRIPT).index(size_suffix(name)) + 1 \
        if size_suffix(name) else 0
    if size:
        tokens = tokens[:-1]
    forms, step, part = [], (), -1
    for token in tokens:
        if token in PARTS:
            part = PARTS.index(token)
        elif token[0] in "vh" and token[1:].isdigit():
            step = (token[0], int(token[1:]))
        else:
            forms.append(token)
    return codepoint, forms, step, part, size


def derived_names(encoded, edges):
    """Name the glyphs without code points after the glyphs they are
    reached from.

    encoded: key -> name of each glyph with code points, in the order
    of their primary code points.  edges: key -> list of (key, suffix
    kind, suffix); the kinds are "form" (a feature) and "step" (a
    stretch series).  Returns key -> name for the keys reached.
    """
    names = {}
    for start, base in encoded.items():
        # Breadth first: a glyph is named by its shortest path.
        pending = deque([(start, "", "")])
        while pending:
            key, forms, step = pending.popleft()
            for target, kind, suffix in sorted(edges.get(key, ())):
                if target in encoded or target in names:
                    continue
                new_forms = forms + (suffix if kind == "form" else "")
                new_step = step or (suffix if kind == "step" else "")
                names[target] = base + new_forms + new_step
                pending.append((target, new_forms, new_step))
    return names
