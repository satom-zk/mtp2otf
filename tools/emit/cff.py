"""The CFF table: CID-keyed, one hinting dictionary per source."""

from fontTools.cffLib import (
    CFFFontSet,
    CharStrings,
    FDArrayIndex,
    FDSelect,
    FontDict,
    GlobalSubrsIndex,
    IndexedStrings,
    PrivateDict,
    TopDict,
    TopDictIndex,
)
from fontTools.misc.psCharStrings import T2CharString
from fontTools.pens.t2CharStringPen import T2CharStringPen

from outline import draw


def build_cff(plan, glyph_names):
    """Return a CFFFontSet; glyph_names are the names in glyph order."""
    fontset = CFFFontSet()
    fontset.major, fontset.minor = 1, 0
    fontset.hdrSize, fontset.offSize = 4, 4
    fontset.fontNames = [plan.postscript_name]
    fontset.strings = strings = IndexedStrings()
    fontset.GlobalSubrs = subrs = GlobalSubrsIndex()
    fontset.topDictIndex = TopDictIndex()

    # Widths are written in full, so every dictionary can use 0 for
    # both width defaults.
    keys = dictionary_keys(plan)
    privates = []
    for key in keys:
        private = PrivateDict(strings=strings)
        private.rawDict = dict(plan.hints[key]) if key else {}
        private.rawDict.update(defaultWidthX=0, nominalWidthX=0)
        privates.append(private)

    selector = FDSelect()
    selector.format = 3
    selector.gidArray = [keys.index(glyph.hints) for glyph in plan.glyphs]
    fonts = FDArrayIndex()
    fonts.strings = strings
    for private in privates:
        font = FontDict(strings=strings)
        font.rawDict = {}
        font.Private = private
        fonts.append(font)

    top = TopDict(strings=strings, GlobalSubrs=subrs)
    top.ROS = ("Adobe", "Identity", 0)
    top.CIDCount = len(plan.glyphs)
    top.FullName = top.FamilyName = plan.family
    top.charset = list(glyph_names)
    top.FDSelect = selector
    top.FDArray = fonts
    charstrings = CharStrings(
        None, top.charset, subrs, None, selector, fonts)
    for name, glyph, index in zip(
            glyph_names, plan.glyphs, selector.gidArray):
        charstrings[name] = _charstring(glyph, privates[index], subrs)
    top.CharStrings = charstrings
    fontset.topDictIndex.append(top)
    return fontset


def dictionary_keys(plan):
    """The font dictionaries in order: the first is for glyphs without
    hints."""
    return [None] + sorted(plan.hints)


def _charstring(glyph, private, subrs):
    if glyph.program is None:
        pen = T2CharStringPen(glyph.advance, None, roundTolerance=0)
        draw(glyph.outline, pen)
        program = pen.getCharString().program
    else:
        program = [glyph.advance] + list(glyph.program)
    return T2CharString(program=program, private=private, globalSubrs=subrs)
