"""The plan's values as tab-separated tables, for checking a build
against the design document.  Each table has a header line."""

from fractions import Fraction

from fontTools.ttLib.tables.otData import otData

from emit.cff import dictionary_keys

MATH_CONSTANTS = next(
    [field[1] for field in fields] for name, fields in otData
    if name == "MathConstants")


def tables(plan):
    """File name -> text."""
    order = {glyph.name: index for index, glyph in enumerate(plan.glyphs)}
    keys = dictionary_keys(plan)
    return {
        "constants.tsv": _table(("constant", "value"), _constants(plan)),
        "glyphs.tsv": _table(GLYPH_COLUMNS, _glyphs(plan, keys)),
        "variants.tsv": _table(
            ("root", "axis", "step", "glyph", "measurement"),
            _variants(plan)),
        "parts.tsv": _table(
            ("root", "axis", "index", "glyph", "extender", "start", "end",
             "full"), _parts(plan)),
        "features.tsv": _table(
            ("feature", "input", "output"), _features(plan, order)),
        "kerns.tsv": _table(
            ("left", "right", "value"),
            [(left, right, value) for (left, right), value in sorted(
                plan.kerns.items(),
                key=lambda item: (order[item[0][0]], order[item[0][1]]))]),
        "dictionaries.tsv": _table(
            ("dictionary", "source", "scale", "dy", "key", "value"),
            _dictionaries(plan, keys)),
    }


def group(glyph):
    """The glyph's group (design document, section 3.2)."""
    if glyph.source is None:
        return "empty" if not glyph.outline else "constructed"
    if glyph.source[0] in ("donor", "constructed"):
        return glyph.source[0]
    scale, dx, dy = glyph.transform
    if dy:
        return "vshift"
    if dx:
        return "hshift"
    return "scale" if scale != 1 else "keep"


GLYPH_COLUMNS = (
    "glyph", "codepoints", "source", "group", "scale", "dx", "dy",
    "advance", "italic", "math_kern", "top_accent", "class", "extended",
    "dictionary")


def _glyphs(plan, keys):
    for glyph in plan.glyphs:
        scale, dx, dy = glyph.transform
        yield (
            glyph.name,
            " ".join("%04X" % c for c in sorted(glyph.codepoints)),
            _source(glyph.source), group(glyph),
            _ratio(scale), _number(dx), _number(dy),
            glyph.advance, glyph.italic or "", _blank(glyph.math_kern),
            _blank(glyph.top_accent),
            3 if glyph.name in plan.marks else 1,
            "yes" if glyph.name in plan.extended_shapes else "",
            keys.index(glyph.hints))


def _source(source):
    if source is None:
        return ""
    if source[0] == "donor":
        return "donor:U+%04X" % source[1]
    if source[0] == "constructed":
        return "constructed:%s" % source[1]
    return "%s:%d" % source


def _constants(plan):
    rows = [(name, plan.constants[name]) for name in MATH_CONSTANTS]
    rows.append(("MinConnectorOverlap", plan.min_connector_overlap))
    return rows


def _variants(plan):
    for c in plan.constructions:
        for step, (glyph, measurement) in enumerate(c.variants):
            yield c.root, c.axis, step, glyph, measurement


def _parts(plan):
    for c in plan.constructions:
        for index, part in enumerate(c.parts):
            yield (c.root, c.axis, index, part.glyph,
                   "yes" if part.extender else "", part.start, part.end,
                   part.full)


def _features(plan, order):
    for feature in plan.features:
        if feature.kind == "ligature":
            items = sorted(feature.mapping.items(), key=lambda item: [
                order[name] for name in item[0]])
            for inputs, output in items:
                yield feature.tag, " ".join(inputs), output
            continue
        for glyph, output in sorted(
                feature.mapping.items(), key=lambda item: order[item[0]]):
            if feature.kind == "alternate":
                output = " ".join(output)
            yield feature.tag, glyph, output


def _dictionaries(plan, keys):
    for number, key in enumerate(keys):
        if key is None:
            yield number, "", "", "", "", ""
            continue
        source, scale, dy = key
        for name, value in plan.hints[key].items():
            text = (" ".join(_number(v) for v in value)
                    if isinstance(value, list) else _number(value))
            yield number, source, _ratio(scale), _number(dy), name, text


def _ratio(value):
    """A scale as the ratio it was made from (10/7, not 1.428...)."""
    ratio = Fraction(value).limit_denominator(1000)
    if ratio.denominator == 1:
        return str(ratio.numerator)
    return "%d/%d" % (ratio.numerator, ratio.denominator)


def _number(value):
    """Whole numbers without a decimal point; others as the plan has
    them (the shortest form that reads back as the same value)."""
    if value == int(value):
        return str(int(value))
    return repr(float(value))


def _blank(value):
    return "" if value is None else value


def _table(columns, rows):
    lines = ["\t".join(columns)]
    lines += ["\t".join(str(value) for value in row) for row in rows]
    return "\n".join(lines) + "\n"
