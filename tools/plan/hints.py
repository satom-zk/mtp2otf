"""Hinting dictionaries (design document, section 10)."""

LENGTHS = (
    "BlueValues", "OtherBlues", "FamilyBlues", "FamilyOtherBlues",
    "StdHW", "StdVW", "StemSnapH", "StemSnapV",
)
BLUES = ("BlueValues", "OtherBlues", "FamilyBlues", "FamilyOtherBlues")
# Lengths are kept to 0.01 unit, the precision of the outlines: LuaTeX
# cannot write longer reals when it embeds the font in a PDF.
PRECISION = 2
# Values a Type 1 font has when it does not state them.
DEFAULTS = {"BlueScale": 0.039625, "BlueShift": 7, "BlueFuzz": 1}


def dictionary(private, scale, rise):
    """The source's dictionary for glyphs scaled about the origin and
    then raised by `rise`: lengths follow the scale, and the alignment
    zones, which are heights, follow the glyph."""
    if scale == 1 and not rise:
        return dict(private)
    result = dict(private)
    for key in LENGTHS:
        if key in result:
            value = result[key]
            result[key] = (
                [x * scale for x in value] if isinstance(value, list)
                else value * scale)
    if scale != 1:
        result["BlueScale"] = (
            result.get("BlueScale", DEFAULTS["BlueScale"]) / scale)
        for key in ("BlueShift", "BlueFuzz"):
            result[key] = result.get(key, DEFAULTS[key]) * scale
    for key in BLUES:
        if key in result:
            result[key] = [x + rise for x in result[key]]
    for key in LENGTHS + ("BlueShift", "BlueFuzz"):
        if key in result:
            value = result[key]
            result[key] = (
                [_rounded(x) for x in value] if isinstance(value, list)
                else _rounded(value))
    return result


def _rounded(value):
    value = round(value, PRECISION)
    return int(value) if value == int(value) else value
