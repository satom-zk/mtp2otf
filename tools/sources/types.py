"""Plain data returned by the readers of the inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

# An outline is a tuple of contours; a contour is a tuple of segments.
# Segments are ("move", (x, y)), ("line", (x, y)) and
# ("curve", (x1, y1), (x2, y2), (x3, y3)).  Every contour is closed.
Outline = tuple


@dataclass(frozen=True)
class TfmChar:
    width: Fraction
    height: Fraction
    depth: Fraction
    italic: Fraction
    kerns: dict  # next character code -> Fraction
    next_larger: int | None
    extensible: tuple | None  # (top, mid, bot, rep), each a code or None


@dataclass(frozen=True)
class Tfm:
    """Dimensions are in design-size units (1 = the design size)."""

    checksum: int
    design_size: Fraction  # in points
    params: tuple  # params[0] is fontdimen 1
    chars: dict  # character code -> TfmChar

    def param(self, number: int) -> Fraction:
        """Return fontdimen `number` (1-based); the preflight has made
        sure it is there."""
        return self.params[number - 1]


@dataclass(frozen=True)
class Type1Glyph:
    name: str
    width: float
    program: tuple  # Type 2 charstring, hints included, width removed
    outline: Outline


@dataclass(frozen=True)
class Type1Font:
    font_name: str
    encoding: dict  # slot -> glyph name
    glyphs: dict  # glyph name -> Type1Glyph
    private: dict  # hinting dictionary (BlueValues, StdHW, ...)

    def slot(self, code: int) -> Type1Glyph | None:
        name = self.encoding.get(code)
        return self.glyphs.get(name) if name else None


@dataclass(frozen=True)
class MathAccent:
    family: str
    slot: int


@dataclass(frozen=True)
class FontShape:
    encoding: str
    family: str
    series: str
    shape: str
    sizes: tuple  # ((low, high), font name); None bounds are open
    skewchar: int | None


@dataclass(frozen=True)
class Package:
    script_ratio: Fraction
    scriptscript_ratio: Fraction
    family_skewchars: dict  # (encoding, family) -> slot
    shapes: tuple  # FontShape, in declaration order
    accents: tuple  # MathAccent, in declaration order
    # name -> (encoding, family, series, shape)
    symbol_fonts: dict = field(default_factory=dict)
    # \\command -> (file, scale) of fonts loaded by \\font
    commands: dict = field(default_factory=dict)
    vdots_step: Fraction | None = None      # points
    ddots_raises: tuple = ()                # points, left to right
    ddots_gaps: tuple = ()                  # mu, between the dots

    def files(self, declaration):
        """(text, script, scriptscript, scale) of a font shape
        "enc/family/series/shape" or a font command, or None.

        A shape with three size ranges gives the text font (the range
        open above), the scriptscript font (open below) and the script
        font (the other)."""
        if declaration in self.commands:
            name, scale = self.commands[declaration]
            return name, "", "", scale
        for shape in self.shapes:
            key = "/".join((shape.encoding, shape.family, shape.series,
                            shape.shape))
            if key != declaration:
                continue
            if len(shape.sizes) == 1:
                return shape.sizes[0][1], "", "", 1
            if len(shape.sizes) != 3:
                return None
            text = [n for (low, high), n in shape.sizes if high is None]
            small = [n for (low, high), n in shape.sizes if low is None]
            if len(text) != 1 or len(small) != 1:
                return None
            middle = [n for _, n in shape.sizes if n not in text + small]
            return text[0], middle[0], small[0], 1
        return None

    def skewchar(self, font_name: str) -> int | None:
        """Skew character in effect for a font file name."""
        for shape in self.shapes:
            if all(name != font_name for _, name in shape.sizes):
                continue
            # A shape's own declaration overrides its family's.
            if shape.skewchar is not None:
                return shape.skewchar
            key = (shape.encoding, shape.family)
            return self.family_skewchars.get(key)
        return None


@dataclass(frozen=True)
class DonorGlyph:
    name: str
    width: int
    outline: Outline
    program: tuple | None  # Type 2 charstring if the donor is CFF


@dataclass(frozen=True)
class Donor:
    units_per_em: int
    weight: int
    upright: bool
    fixed_pitch: bool
    cmap: dict  # code point -> glyph name
    glyphs: dict  # glyph name -> DonorGlyph
    private: dict | None  # CFF hinting dictionary, if any


@dataclass(frozen=True)
class Sources:
    fonts: dict  # source file name -> Type1Font
    metrics: dict  # source file name -> Tfm
    package: Package
    donor: Donor
