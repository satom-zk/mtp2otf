"""Read the Roman donor font."""

from __future__ import annotations

from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont, TTLibError

from errors import Error
from outline import bounds
from sources.type1 import PRIVATE_KEYS, charstring_parts, outline_from_pen
from sources.types import Donor, DonorGlyph


class DonorError(Error):
    pass


class _CubicPen(BasePen):
    """Records the outline with quadratic segments made cubic (the shape
    is unchanged) and components drawn in place."""

    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.value = []

    def _moveTo(self, point):
        self.value.append(("moveTo", (point,)))

    def _lineTo(self, point):
        self.value.append(("lineTo", (point,)))

    def _curveToOne(self, point1, point2, point3):
        self.value.append(("curveTo", (point1, point2, point3)))

    def _closePath(self):
        self.value.append(("closePath", ()))

    def _endPath(self):
        self.value.append(("endPath", ()))


DOTLESS_J, J = 0x0237, 0x006A


def dotless_j(donor: Donor):
    """The donor's own dotless j, or its j without the dot: the j must
    have two contours, a body across the baseline and a dot above it.
    Returns (outline, advance) in the donor's units."""
    if DOTLESS_J in donor.cmap:
        glyph = donor.glyphs[donor.cmap[DOTLESS_J]]
        return glyph.outline, glyph.width
    if J not in donor.cmap:
        raise DonorError("donor: neither U+0237 nor U+006A")
    glyph = donor.glyphs[donor.cmap[J]]
    if len(glyph.outline) != 2:
        raise DonorError("donor: U+006A does not have two contours")
    boxes = [bounds((contour,)) for contour in glyph.outline]
    bodies = [i for i, box in enumerate(boxes) if box[1] < 0 < box[3]]
    if len(bodies) != 1:
        raise DonorError("donor: U+006A has no single body across the "
                         "baseline")
    body = bodies[0]
    if boxes[1 - body][1] <= boxes[body][3]:
        raise DonorError("donor: the dot of U+006A is not above its body")
    return (glyph.outline[body],), glyph.width


REQUIRED_TABLES = ("head", "hmtx", "cmap", "OS/2", "post")
ITALIC, OBLIQUE = 0x01, 0x200  # OS/2 fsSelection
MAC_ITALIC = 0x02  # head macStyle


def read_donor(path: str | Path) -> Donor:
    try:
        font = TTFont(str(path), lazy=False)
    except (TTLibError, OSError) as error:
        raise DonorError(f"{path}: not an OpenType font ({error})")
    missing = [tag for tag in REQUIRED_TABLES if tag not in font]
    if missing:
        raise DonorError(f"{path}: no {', '.join(missing)} table")
    units_per_em = font["head"].unitsPerEm
    if not 16 <= units_per_em <= 16384:
        raise DonorError(f"{path}: unitsPerEm {units_per_em} is not "
                         "16 to 16384")
    if "fvar" in font:
        raise DonorError(f"{path}: variable fonts are not supported")
    cmap = font.getBestCmap()
    if not cmap:
        raise DonorError(f"{path}: no Unicode cmap")

    private, strings, hints = None, None, None
    if "CFF " in font:
        cff = font["CFF "].cff
        top = cff.topDictIndex[0]
        if hasattr(top, "FDArray"):
            raise DonorError(f"{path}: CID-keyed donors are not supported")
        cff.desubroutinize()
        private, strings = top.Private, top.CharStrings
        hints = {
            key: private.rawDict[key]
            for key in PRIVATE_KEYS
            if key in private.rawDict
        }

    glyph_set = font.getGlyphSet()
    glyphs = {}
    for name in font.getGlyphOrder():
        pen = _CubicPen(glyph_set)
        glyph_set[name].draw(pen)
        program = None
        if strings is not None:
            _, program = charstring_parts(strings[name], private)
        glyphs[name] = DonorGlyph(
            name=name,
            width=font["hmtx"][name][0],
            outline=outline_from_pen(pen.value),
            program=program,
        )
    return Donor(
        units_per_em=units_per_em,
        weight=font["OS/2"].usWeightClass,
        upright=(abs(font["post"].italicAngle) <= 0.01
                 and not font["OS/2"].fsSelection & (ITALIC | OBLIQUE)
                 and not font["head"].macStyle & MAC_ITALIC),
        fixed_pitch=bool(font["post"].isFixedPitch),
        cmap=dict(cmap),
        glyphs=glyphs,
        private=hints,
    )
