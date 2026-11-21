"""Which glyphs the font has (design document, sections 2, 3 and 7)."""

from __future__ import annotations

import unicodedata
from fractions import Fraction

from charstring import transformed
from design.types import Ref
from errors import Error
from outline import bounds, moved, rectangle, scaled
from plan import names
from plan.hints import dictionary
from plan.metrics import UNITS_PER_EM, source_metrics, units
from plan.placement import Placement
from plan.types import Glyph

DONOR_HINTS = ("donor", 1, 0)
ACCENT_ROLE = "sy"
ACCENT_FAMILY = "symbols"

NOTDEF = Glyph(
    name=".notdef",
    codepoints=(),
    advance=500,
    outline=(
        rectangle(50, 0, 450, 533),
        rectangle(100, 50, 400, 483, clockwise=True),
    ),
)


class PlanError(Error):
    pass


def source_names(design, lite):
    """The source files a build reads."""
    result = []
    for role in design.roles.values():
        if lite and not role.lite:
            continue
        result += [
            name for name in (role.text, role.script, role.scriptscript)
            if name]
    return result


class GlyphMaker:
    """Makes glyphs from the sources and collects their hint
    dictionaries."""

    def __init__(self, design, sources):
        self.design = design
        self.sources = sources
        self.hints = {}
        symbols = sources.metrics[design.roles["sy"].text]
        extension = sources.metrics[design.roles["exa"].text]
        axis = units(symbols.param(22))
        self.placement = Placement(design, axis)
        self.accent_base_height = units(symbols.param(5))
        # The attachment point of combining accents, in every size.
        self.attachment = -(axis + round(units(extension.param(8)) / 4))
        self.accent_source = design.roles[ACCENT_ROLE].text
        self.accents = {
            accent.slot for accent in sources.package.accents
            if accent.family == ACCENT_FAMILY}
        self.combining = {
            row.slot for row in design.slots
            if row.role == ACCENT_ROLE and row.slot in self.accents
            and any(unicodedata.category(chr(c)) == "Mn"
                    for c in row.codepoints)}

    def from_slot(self, source, slot, name, codepoints=(), placed=False):
        font = self.sources.fonts[source]
        glyph = font.slot(slot)
        if glyph is None or slot not in self.sources.metrics[source].chars:
            raise PlanError("%s has no slot %d" % (source, slot))
        role = self.design.role_of(source)
        outline = scaled(glyph.outline, role.scale)
        metrics = source_metrics(self.design, self.sources, source, slot)
        advance, italic = metrics.advance, metrics.italic
        math_kern, top_accent = metrics.math_kern, metrics.top_accent
        dx = 0
        dy = self.placement.rise(
            (role.name, slot), outline) if placed else 0
        if role.name == ACCENT_ROLE and slot in self.accents:
            dy += self._accent_drop(source)
            if slot in self.combining:
                # Centre the accent's TFM box on the attachment point.
                width = units(self.sources.metrics[source].chars[slot].width)
                dx = _exact(self.attachment - Fraction(width, 2))
                advance, italic, math_kern = 0, 0, None
                top_accent = self.attachment
        if top_accent is not None and not advance and slot not in \
                self.combining:
            # Zero-width marks such as the negation slash.
            box = bounds(outline)
            top_accent = round((box[0] + box[2]) / 2) if box else 0
        key = (source, role.scale, dy)
        self.hints.setdefault(
            key, dictionary(font.private, role.scale, dy))
        return Glyph(
            name, codepoints, advance, moved(outline, dx, dy),
            transformed(glyph.program, role.scale, dx, dy), key,
            (source, slot), italic, math_kern, top_accent,
            (source, slot), (role.scale, dx, dy))

    def _accent_drop(self, source):
        """Script accents sit on the script x-height; OpenType has one
        AccentBaseHeight, so they move down by the difference."""
        role = self.design.role_of(source)
        if source == role.text:
            return 0
        x_height = units(self.sources.metrics[source].param(5))
        return self.accent_base_height - x_height

    def derive(self, glyph, name, factor=1, dx=0, dy=0, advance=None):
        """A glyph made by scaling and moving another one made from a
        slot.  It keeps neither the source box nor its metrics."""
        outline = moved(scaled(glyph.outline, factor), dx, dy)
        if advance is None:
            advance = round(glyph.advance * factor + dx)
        scale, x, y = glyph.transform
        made = {"source": glyph.source, "transform": (
            scale * factor, x * factor + dx, y * factor + dy)}
        if glyph.hints is None:
            return Glyph(name, (), advance, outline, **made)
        source = glyph.hints[0]
        scale = glyph.hints[1] * factor
        rise = glyph.hints[2] * factor + dy
        key = (source, scale, rise)
        self.hints.setdefault(key, dictionary(
            self.sources.fonts[source].private, scale, rise))
        return Glyph(
            name, (), advance, outline,
            transformed(glyph.program, factor, dx, dy), key, **made)

    def optical_sizes(self, role, slot, name):
        """The script and scriptscript forms of a text glyph."""
        return tuple(
            self.from_slot(source, slot, name + suffix)
            for source, suffix in (
                (role.script, names.SCRIPT),
                (role.scriptscript, names.SCRIPTSCRIPT)))

    def from_donor(self, codepoints):
        donor = self.sources.donor
        # The first code point is the donor's character; the others
        # are aliases of the glyph.
        if codepoints[0] not in donor.cmap:
            raise PlanError("donor has no U+%04X" % codepoints[0])
        glyph = donor.glyphs[donor.cmap[codepoints[0]]]
        name = names.base_name(codepoints)
        source = ("donor", codepoints[0])
        if donor.units_per_em != UNITS_PER_EM:
            factor = UNITS_PER_EM / donor.units_per_em
            return Glyph(
                name, codepoints, round(glyph.width * factor),
                scaled(glyph.outline, factor), source=source,
                transform=(factor, 0, 0))
        if glyph.program is None:
            return Glyph(name, codepoints, glyph.width, glyph.outline,
                         source=source)
        self.hints.setdefault(DONOR_HINTS, donor.private)
        return Glyph(
            name, codepoints, glyph.width, glyph.outline,
            glyph.program, DONOR_HINTS, source=source)


def encoded_glyphs(design, maker, lite):
    """The glyphs with code points, in order.

    Returns (glyphs, slots): slots maps a glyph name to the (role,
    slot) it was made from.
    """
    glyphs, slots = [], {}
    for row in design.slots:
        role = design.roles[row.role]
        if lite and not role.lite:
            continue
        name = names.base_name(row.codepoints)
        glyphs.append(
            maker.from_slot(role.text, row.slot, name, row.codepoints))
        slots[name] = (row.role, row.slot)
    glyphs += [maker.from_donor(codepoints) for codepoints in design.donor]
    widths = {codepoint: glyph.advance
              for glyph in glyphs for codepoint in glyph.codepoints}
    glyphs += [
        Glyph(names.base_name((codepoint,)), (codepoint,),
              widths[advance.value] if isinstance(advance, Ref) else advance,
              ())
        for codepoint, advance in design.spaces.items()]
    glyphs.sort(key=lambda glyph: names.primary(glyph.codepoints))
    return glyphs, slots


def _exact(value):
    """An integer if the value is whole, else a float."""
    value = Fraction(value)
    return int(value) if value.denominator == 1 else float(value)
