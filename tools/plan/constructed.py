"""Constructed glyphs (design document, annex 2 L).

A constructed glyph is drawn by a rule from source glyphs; it has no
hints.  Each method returns the text form, and the script and
scriptscript forms where the rule gives them.
"""

from __future__ import annotations

import re
from fractions import Fraction

from design.types import Ref
from errors import Error
from outline import bounds, moved, rectangle, scaled
from plan.metrics import UNITS_PER_EM, units
from plan.types import Glyph
from sources.donor import dotless_j

SLOT = re.compile(r"([a-z]+):(\d+)")
# TeX puts a thin space (\thinmuskip) after punctuation such as the dots
# of \ldots and \cdots.
THIN_SPACE = 3


class ConstructedError(Error):
    pass


class ConstructedMaker:
    """Draws the constructed glyphs of the design.

    glyph_of: function from a design Ref to the text glyph it names,
    for rules built on other glyphs of the font; optical: text glyph
    name -> (script, scriptscript) names; glyphs: name -> Glyph.
    """

    def __init__(self, design, sources, maker, constants):
        self.design = design
        self.sources = sources
        self.maker = maker
        self.constants = constants
        self.glyph_of = None
        self.optical = {}
        self.glyphs = {}
        self._cache = {}

    def available(self, name, lite):
        """Whether a Lite or Full build has what the rule needs."""
        for word in self.design.constructed[name].arguments:
            match = SLOT.match(word)
            if match and lite and not self.design.roles[match[1]].lite:
                return False
            if word in self.design.constructed:
                if not self.available(word, lite):
                    return False
        return True

    def raw(self, name, size=0):
        """The glyph a rule draws, before it gets its name; None where
        the rule has no form of that size."""
        key = (name, size)
        if key not in self._cache:
            item = self.design.constructed[name]
            method = getattr(self, "_" + item.method)
            glyph = method(item, size, *item.arguments)
            if glyph is not None:
                glyph = _with(glyph, origin=("constructed",) + key,
                              source=("constructed",) + key,
                              transform=(1, 0, 0))
            self._cache[key] = glyph
        return self._cache[key]

    # Rules

    def _prime(self, item, size, slot, count):
        """Primes on the line: the script form scaled by the script
        ratio, raised to TeX's display superscript position (sup1).
        The smaller forms set the source's own primes side by side."""
        role, slot = self._slot(slot)
        count = int(count)
        if size > 0 and count == 1:
            return None     # the source's forms; see optical_sources
        source = _source_name(role, max(size, 1))
        glyph = self.maker.from_slot(source, slot, "")
        factor = self.sources.package.script_ratio if size == 0 else 1
        step = self._width(source, slot) * factor
        rise = units(self._symbols().param(13)) if size == 0 else 0
        outline = ()
        for k in range(count):
            outline += moved(
                scaled(glyph.outline, float(factor)), float(step * k), rise)
        top_accent = None
        if size == 0 and count == 1:
            char = self._char(source, slot)
            top_accent = units((char.width + char.italic) * factor / 2)
        return Glyph(
            "", (), round(step * count), outline, top_accent=top_accent)

    def optical_sources(self, name):
        """Source slots that give a constructed glyph its smaller
        forms: a single prime uses the script and scriptscript
        primes of its source."""
        item = self.design.constructed[name]
        if item.method == "prime" and item.arguments[1] == "1":
            role, slot = self._slot(item.arguments[0])
            return role, slot
        return None

    def _dotless(self, item, size):
        """The donor's dotless j (or its j without the dot), in the
        units of the font."""
        if size:
            return None
        donor = self.sources.donor
        outline, width = dotless_j(donor)
        factor = Fraction(UNITS_PER_EM, donor.units_per_em)
        if factor != 1:
            return Glyph("", (), round(width * factor),
                         scaled(outline, float(factor)))
        return Glyph("", (), width, outline)

    def _row(self, item, size, *pieces):
        """Pieces side by side, each at the end of the one before."""
        if size:
            return None
        outline, x = (), 0
        for piece in pieces:
            glyph = self._text_slot(*self._slot(piece))
            outline += moved(glyph.outline, x, 0)
            x += glyph.advance
        return Glyph("", (), x, outline)

    def _spaced(self, item, size, piece, count):
        """Copies of a punctuation glyph with a thin space after each
        but the last (\\ldots, \\cdots)."""
        if size:
            return None
        glyph = self._text_slot(*self._slot(piece))
        step = glyph.advance + self._mu(THIN_SPACE)
        count = int(count)
        outline = ()
        for k in range(count):
            outline += moved(glyph.outline, step * k, 0)
        return Glyph("", (), step * count - self._mu(THIN_SPACE), outline)

    def _vdots(self, item, size, piece):
        """Three dots \\baselineskip apart as mtpro2.sty's \\vdots sets
        them, centred on the math axis."""
        if size:
            return None
        glyph = self._text_slot(*self._slot(piece))
        step = self._points(self.sources.package.vdots_step)
        outline = ()
        for k in range(3):
            outline += moved(glyph.outline, 0, step * k)
        return Glyph("", (), glyph.advance, self._on_axis(outline))

    def _ddots(self, item, size, piece, order="down"):
        """Dots raised and kerned as mtpro2.sty's \\ddots sets them,
        centred on the math axis; order "up" reverses the raises."""
        if size:
            return None
        glyph = self._text_slot(*self._slot(piece))
        package = self.sources.package
        raises = [self._points(x) for x in package.ddots_raises]
        if order == "up":
            raises.reverse()
        outline, x = (), 0
        for k, rise in enumerate(raises):
            outline += moved(glyph.outline, x, rise)
            x += glyph.advance
            if k < len(package.ddots_gaps):
                x += self._mu(package.ddots_gaps[k])
        return Glyph("", (), x, self._on_axis(outline))

    def _moustache(self, item, size, lower, upper):
        """The lower piece of a moustache recipe with its ink bottom at
        0, and the upper piece on it, overlapping by the lower piece's
        reach above the baseline (at most the upper piece's height)."""
        if size:
            return None
        low = self._text_slot(*self._slot(lower))
        high = self._text_slot(*self._slot(upper))
        a, b = bounds(low.outline), bounds(high.outline)
        overlap = max(0, min(a[3], b[3] - b[1]))
        outline = moved(low.outline, 0, -a[1])
        outline += moved(high.outline, 0, a[3] - a[1] - overlap - b[1])
        return Glyph("", (), low.advance, outline)

    def _rule(self, item, size, piece, width):
        """A rectangle as tall as the TFM height of a piece."""
        if size:
            return None
        role, slot = self._slot(piece)
        char = self._char(role.text, slot)
        height = units(char.height * role.scale)
        width = int(width)
        return Glyph("", (), width, (rectangle(0, 0, width, height),))

    def _mirror(self, item, size, reference):
        """Left-right mirror.  A glyph with an accent attachment is
        mirrored about it; others about the middle of the box."""
        glyph = self._referred(reference, size)
        if glyph is None:
            return None
        axis = glyph.top_accent if glyph.top_accent is not None \
            and glyph.advance == 0 else glyph.advance / 2
        outline = tuple(
            tuple(
                (segment[0],) + tuple(
                    (2 * axis - x, y) for x, y in segment[1:])
                for segment in contour)
            for contour in glyph.outline)
        return Glyph(
            "", (), glyph.advance, outline, top_accent=glyph.top_accent)

    def _column(self, item, size, piece, step):
        """Rectangles as wide as the contours of an extension piece,
        reaching from the ink bottom to the ink top of `step`, the
        angle bracket of the same size."""
        if size:
            return None
        glyph = self._text_slot(*self._slot(piece))
        box = bounds(self._placed(step).outline)
        outline = tuple(
            rectangle(part[0], box[1], part[2], box[3])
            for part in (bounds((contour,)) for contour in glyph.outline))
        return Glyph("", (), glyph.advance, outline)

    def _interpolate(self, item, size, height):
        """A size between two steps of its series: the outlines of the
        neighbouring steps interpolated by height, centred on the math
        axis and rounded."""
        if size:
            return None
        height = int(height)
        steps = [
            self.glyph_of(ref) for ref in self._series_of(item.name)
            if ref.kind != "name"]
        boxes = [bounds(glyph.outline) for glyph in steps]
        sizes = [box[3] - box[1] for box in boxes]
        for i in range(len(steps) - 1):
            if sizes[i] < height < sizes[i + 1]:
                break
        else:
            raise ConstructedError("%s: no steps around it" % item.name)
        a, b = steps[i], steps[i + 1]
        ratio = Fraction(height) - Fraction(sizes[i])
        ratio /= Fraction(sizes[i + 1]) - Fraction(sizes[i])
        centre_a = (boxes[i][1] + boxes[i][3]) / 2
        centre_b = (boxes[i + 1][1] + boxes[i + 1][3]) / 2
        axis = self.constants["AxisHeight"]
        outline = []
        for contour_a, contour_b in zip(a.outline, b.outline):
            contour = []
            for segment_a, segment_b in zip(contour_a, contour_b):
                if segment_a[0] != segment_b[0]:
                    raise ConstructedError(
                        "%s: outlines do not correspond" % item.name)
                contour.append((segment_a[0],) + tuple(
                    (round(xa + ratio * (xb - xa)),
                     round(axis + ya - centre_a
                           + ratio * (yb - centre_b - ya + centre_a)))
                    for (xa, ya), (xb, yb)
                    in zip(segment_a[1:], segment_b[1:])))
            outline.append(tuple(contour))
        advance = round(a.advance + ratio * (b.advance - a.advance))
        return Glyph("", (), advance, tuple(outline))

    def _vector(self, item, size, part):
        """Parts of the stretched vector (design document, section 6),
        raised by AccentBaseHeight like the source's arrow."""
        rise = self.constants["AccentBaseHeight"]
        source = _source_name(self.design.roles["sy"], size)
        minus = self.maker.from_slot(source, 0, "")
        arrow = self.maker.from_slot(source, 33, "")
        minus_box = bounds(minus.outline)
        arrow_box = bounds(arrow.outline)
        b = minus_box[0]
        r = arrow.advance - arrow_box[2]
        shaft = min(
            _straight_part(arrow.outline, minus_box),
            minus_box[2] - minus_box[0])
        low, high = minus_box[1] + rise, minus_box[3] + rise
        if part == "start":
            return Glyph("", (), b + shaft, (
                rectangle(b, low, b + shaft, high),))
        if part == "shaft":
            return Glyph("", (), shaft, (rectangle(0, low, shaft, high),))
        return Glyph(
            "", (), arrow_box[2] - arrow_box[0] + r,
            moved(arrow.outline, -arrow_box[0], rise))

    def _overparen(self, item, size, template, part):
        """Pieces of the over-parenthesis assembly, cut from the end of
        its source chain at the middle and lengthened on the inner side
        by the connector length."""
        if size:
            return None
        role, slot = self._slot(template)
        contour = self._text_slot(role, slot).outline[0]
        kinds = [segment[0] for segment in contour]
        if kinds != ["move", "line", "curve", "curve", "line", "curve",
                     "curve"]:
            raise ConstructedError("%s: unexpected template" % item.name)
        start = contour[0][1]
        left_inner = contour[1][1]
        lower_left, lower_right = contour[2][1:], contour[3][1:]
        right_edge = contour[4][1]
        upper_right, upper_left = contour[5][1:], contour[6][1:]
        middle_low, middle_high = lower_left[-1], upper_right[-1]
        span = right_edge[0] - start[0]
        connector = round(span / 15)
        inner = middle_low[0] + connector
        shift = connector - middle_low[0]
        if part == "left":
            outline = (
                ("move", start), ("line", left_inner),
                ("curve",) + lower_left,
                ("line", (inner, middle_low[1])),
                ("line", (inner, middle_high[1])),
                ("line", middle_high), ("curve",) + upper_left)
            return Glyph("", (), inner - start[0], (outline,))
        if part == "ext":
            width = round(span / 6)
            return Glyph("", (), width, (rectangle(
                0, middle_low[1], width, middle_high[1]),))

        def right(point):
            return (point[0] + shift, point[1])

        outline = (
            ("move", (0, middle_low[1])),
            ("line", (connector, middle_low[1])),
            ("curve",) + tuple(right(p) for p in lower_right),
            ("line", right(right_edge)),
            ("curve",) + tuple(right(p) for p in upper_right),
            ("line", (0, middle_high[1])))
        return Glyph("", (), right_edge[0] + shift, (outline,))

    # Helpers

    def _slot(self, text):
        match = SLOT.fullmatch(text)
        if not match or match[1] not in self.design.roles:
            raise ConstructedError("bad slot %r" % text)
        return self.design.roles[match[1]], int(match[2])

    def _text_slot(self, role, slot):
        if isinstance(role, str):
            role = self.design.roles[role]
        return self.maker.from_slot(role.text, slot, "")

    def _placed(self, text):
        """A source slot or a constructed glyph where the font has it."""
        if SLOT.fullmatch(text):
            role, slot = self._slot(text)
            return self.maker.from_slot(role.text, slot, "", placed=True)
        glyph = self.raw(text)
        rise = self.maker.placement.rise(text, glyph.outline)
        return _with(glyph, outline=moved(glyph.outline, 0, rise))

    def _symbols(self):
        return self.sources.metrics[self.design.roles["sy"].text]

    def _mu(self, mu):
        """Math units (1/18 of the quad of the symbol font) in font
        units, rounded."""
        return round(units(self._symbols().param(6)) * Fraction(mu) / 18)

    def _points(self, points):
        """Points at the design size of the symbol font."""
        return round(Fraction(points) / self._symbols().design_size * 1000)

    def _on_axis(self, outline):
        box = bounds(outline)
        return moved(outline, 0, self.constants["AxisHeight"]
                     - (box[1] + box[3]) / 2)

    def _char(self, source, slot):
        return self.sources.metrics[source].chars[slot]

    def _width(self, source, slot):
        return Fraction(self._char(source, slot).width) * 1000

    def _referred(self, reference, size):
        if reference in self.design.constructed:
            return self.raw(reference, size)
        text = self.glyph_of(Ref("codepoint", int(reference[2:], 16)))
        if size == 0:
            return text
        sizes = self.optical.get(text.name)
        return self.glyphs[sizes[size - 1]] if sizes else None

    def _series_of(self, name):
        for item in self.design.stretch:
            if item.glyph.kind == "name" and item.glyph.value == name:
                root, axis = item.root, item.axis
                return [
                    other.glyph for other in self.design.stretch
                    if other.root == root and other.axis == axis
                    and other.kind == "variant"]
        raise ConstructedError("%s is in no series" % name)


def _source_name(role, size):
    return (role.text, role.script, role.scriptscript)[size]


def _with(glyph, **changes):
    fields = dict(glyph.__dict__)
    fields.update(changes)
    return Glyph(**fields)


def _straight_part(outline, band):
    """Length from the left of the ink to the first point outside the
    band of the minus sign (the straight shaft of an arrow)."""
    box = bounds(outline)
    outside = [
        x for contour in outline for segment in contour
        for x, y in segment[1:] if not band[1] <= y <= band[3]]
    return min(outside) - box[0]
