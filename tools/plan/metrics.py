"""Metrics (design document, section 4)."""

from dataclasses import dataclass
from fractions import Fraction

UNITS_PER_EM = 1000


@dataclass(frozen=True)
class Metrics:
    advance: int
    italic: int
    math_kern: int | None
    top_accent: int


def units(value):
    """Round a dimension in ems to font units; ties go to even."""
    return round(Fraction(value) * UNITS_PER_EM)


def tfm_char(design, sources, source, slot):
    """The TFM record that gives a slot its metrics, or None."""
    role = design.role_of(source)
    slot = design.metric_slots.get((role.name, slot), slot)
    return sources.metrics[source].chars.get(slot)


def source_metrics(design, sources, source, slot):
    """Metrics of a glyph that keeps the box of its source slot."""
    role = design.role_of(source)
    char = tfm_char(design, sources, source, slot)
    skew = sources.package.skewchar(source)
    kern = char.kerns.get(skew, 0)
    box = (char.width + char.italic) * role.scale
    correction = units(char.italic * role.scale)
    italic, math_kern = correction, None
    # Letters and symbols take scripts at the italic-corrected edge;
    # a bottom-right kern moves the subscript back.  The extension
    # fonts (no optical sizes) keep TeX's italic correction.
    if correction and role.script:
        italic, math_kern = 0, -correction
    return Metrics(
        advance=units(box),
        italic=italic,
        math_kern=math_kern,
        top_accent=units((box + 2 * kern * role.scale) / 2),
    )
