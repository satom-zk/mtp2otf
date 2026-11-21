"""Vertical placement of glyphs (design document, section 3.2)."""

from collections import defaultdict

from outline import bounds


class Placement:
    """Decides how far a glyph without code points is raised; glyphs
    with code points stay where the source has them, except constructed
    roots of a series with a set bottom."""

    def __init__(self, design, axis_height):
        self.axis_height = axis_height
        slots = {
            codepoint: (glyph.role, glyph.slot)
            for glyph in design.slots for codepoint in glyph.codepoints}
        constructed = {
            codepoint: item.name for item in design.constructed.values()
            for codepoint in item.codepoints}

        def key(ref):
            """(role, slot) or the name of a constructed glyph."""
            if ref.kind == "codepoint":
                return slots.get(ref.value) or constructed.get(ref.value)
            return ref.value

        series = defaultdict(list)
        for item in design.stretch:
            # The root keeps its place; it is also the glyph in text.
            if item.kind == "variant" and item.glyph != item.root:
                series[item.root, item.axis].append(key(item.glyph))
        for root, axis in {(i.root, i.axis) for i in design.stretch}:
            series.setdefault((root, axis), [])
        self.centred = set()    # keys
        self.bottoms = {}       # key -> height of the ink bottom
        for (root, axis), keys in series.items():
            keys = [k for k in keys if k is not None]
            bottom = design.series.get(root) and design.series[root].bottom
            if bottom is not None:
                for k in keys + [key(root)]:
                    self.bottoms[k] = bottom
                continue
            if axis != "v":
                continue
            # The sizes of a big operator are set on the math axis, and
            # so are those of a delimiter series that mixes extension
            # fonts, which do not agree on where a glyph hangs.
            extension = [
                k for k in keys
                if isinstance(k, tuple) and not design.roles[k[0]].script]
            root_key = key(root)
            operator = (
                isinstance(root_key, tuple)
                and not design.roles[root_key[0]].script)
            if operator:
                self.centred.update(keys)
            elif len({role for role, _ in extension}) > 1:
                self.centred.update(extension)

    def rise(self, key, outline):
        box = bounds(outline)
        if box is None:
            return 0
        if key in self.bottoms:
            return round(self.bottoms[key] - box[1])
        if key in self.centred:
            # Less than a unit off the axis is left where it is.
            dy = self.axis_height - (box[1] + box[3]) / 2
            return round(dy) if abs(dy) >= 1 else 0
        return 0
