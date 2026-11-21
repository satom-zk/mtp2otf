"""Data model of the design tables."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ref:
    """A reference to a glyph of the text size.

    kind "codepoint": the glyph that has the code point (value: int).
    kind "slot": the glyph without code points made from a source slot
    (value: (role, slot)); it exists because it is referred to.
    kind "name": a constructed glyph (value: str).
    """

    kind: str
    value: object

    def __str__(self):
        if self.kind == "codepoint":
            return "U+%04X" % self.value
        if self.kind == "slot":
            return "%s:%d" % self.value
        return self.value


@dataclass(frozen=True)
class Role:
    """A family of source fonts, as mtpro2.sty or an .fd file declares
    it; the files and the scale come from that declaration."""

    name: str
    declaration: str        # "enc/family/series/shape" or "\\fontcommand"
    lite: bool
    text: str = ""
    script: str = ""        # "" if the role has a single size
    scriptscript: str = ""
    scale: int = 1


@dataclass(frozen=True)
class SlotGlyph:
    role: str
    slot: int
    codepoints: tuple


@dataclass(frozen=True)
class Substitution:
    feature: str
    input: tuple            # of Ref; more than one: a ligature
    output: Ref


@dataclass(frozen=True)
class StretchItem:
    root: Ref
    axis: str               # "v" or "h"
    kind: str               # "variant", "part" or "extender"
    glyph: Ref


@dataclass(frozen=True)
class Constructed:
    """A glyph made by a rule (design document, annex 2 L)."""

    name: str
    codepoints: tuple
    method: str
    arguments: tuple


@dataclass(frozen=True)
class Series:
    bottom: int | None      # height of the ink bottom, if set
    # Inner connectors no longer than the extender is thick, less the
    # tolerance of the connector measure.
    connector_cap: bool
    # AdvanceMeasurement is the ink extent rounded up, not the extent
    # rounded down plus one.
    ceil_measure: bool = False


@dataclass(frozen=True)
class FeatureName:
    feature: str
    name: str
    description: str
    options: tuple


@dataclass(frozen=True)
class Design:
    roles: dict             # name -> Role
    slots: tuple            # of SlotGlyph
    # (role, slot) -> slot whose TFM record replaces a broken one
    metric_slots: dict
    donor: tuple            # of code point tuples, one per glyph
    spaces: dict            # code point -> advance, or Ref to a glyph
    constructed: dict       # name -> Constructed
    features: tuple         # of Substitution, in order of application
    stretch: tuple          # of StretchItem, in order within each root
    feature_names: dict     # feature -> FeatureName
    series: dict            # root of a stretch series -> Series

    def role_of(self, source):
        """The role a source file belongs to."""
        for role in self.roles.values():
            if source in (role.text, role.script, role.scriptscript):
                return role
        raise KeyError(source)
