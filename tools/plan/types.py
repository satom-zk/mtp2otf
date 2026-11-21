"""The font plan."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Glyph:
    name: str
    codepoints: tuple
    advance: int
    outline: tuple          # see sources.types.Outline
    # Type 2 charstring with the source's hints and no width;
    # None for a glyph without hints.
    program: tuple | None = None
    hints: object = None        # key of Plan.hints
    # (source file, slot) of a glyph that keeps the slot's box (and so
    # its kerns); None for glyphs scaled or moved from it.
    origin: tuple | None = None
    italic: int = 0             # MATH italics correction
    math_kern: int | None = None    # bottom-right MathKern, one value
    top_accent: int | None = None
    # What the outline was made from, for the build's tables:
    # (source file, slot), ("donor", code point) or ("constructed",
    # rule, size); and the scale and then the move applied to it.
    source: tuple | None = None
    transform: tuple = (1, 0, 0)    # (scale, dx, dy)


@dataclass(frozen=True)
class Feature:
    """One GSUB feature; the form of `mapping` depends on `kind`.

    "single": glyph -> glyph.
    "alternate": glyph -> tuple of glyphs, in the order of selection.
    "ligature": tuple of glyphs -> glyph.
    """

    tag: str
    kind: str
    mapping: dict
    name: str = ""              # user-interface strings (cv and ss)
    description: str = ""
    options: tuple = ()
    characters: tuple = ()      # code points the feature applies to


@dataclass(frozen=True)
class Part:
    glyph: str
    extender: bool
    start: int              # connector lengths
    end: int
    full: int               # full advance


@dataclass(frozen=True)
class Construction:
    """How a glyph grows along one axis."""

    root: str
    axis: str               # "v" or "h"
    variants: tuple         # of (glyph, advance measurement), small first
    parts: tuple            # of Part, bottom or left first; may be empty


@dataclass(frozen=True)
class Plan:
    family: str
    postscript_name: str
    version: str
    glyphs: tuple           # of Glyph, in glyph order
    hints: dict             # key -> hinting dictionary
    features: tuple         # of Feature, in order of application
    kerns: dict             # (left glyph, right glyph) -> adjustment
    constructions: tuple    # of Construction
    extended_shapes: frozenset
    constants: dict         # MATH constant -> value
    marks: frozenset        # glyphs of GDEF class 3; the others are 1
    x_height: int
    cap_height: int
    min_connector_overlap: int
