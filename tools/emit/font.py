"""Write the OpenType font (CFF outlines) and the TrueType font."""

import math
import os
import subprocess
import tempfile
import time
from pathlib import Path

from fontTools.fontBuilder import FontBuilder, buildCmapSubTable
from fontTools.otlLib.maxContextCalc import maxCtxFont
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables.O_S_2f_2 import Panose

from emit.cff import build_cff
from errors import Error
from emit.layout import build_gpos, build_gsub
from emit.math import build_math
from outline import bounds, draw
from plan import product
from plan.metrics import UNITS_PER_EM

# Quadratic curves may stray this far from the cubic ones.
TRUETYPE_TOLERANCE = 0.6

# Values FontForge gave v1.6; Word has worked with them.
SUBSCRIPT = dict(
    ySubscriptXSize=650, ySubscriptYSize=700, ySubscriptXOffset=0,
    ySubscriptYOffset=140)
SUPERSCRIPT = dict(
    ySuperscriptXSize=650, ySuperscriptYSize=700, ySuperscriptXOffset=0,
    ySuperscriptYOffset=480)
STRIKEOUT = dict(yStrikeoutSize=49, yStrikeoutPosition=258)
PANOSE = dict(bFamilyType=2, bWeight=5, bProportion=3)
UNDERLINE = dict(underlinePosition=-75, underlineThickness=50)
# By TrueType or not.  For TrueType, fontTools sets bit 1 on saving when
# every left side bearing is the glyph's xMin, as it is here (0x0B).
HEAD_FLAGS = {False: 0x0B, True: 0x09}

# Seconds from 1904-01-01 (OpenType) to 1970-01-01 (Unix).
EPOCH_DIFFERENCE = 2082844800

GLYPH_CLASS_BASE = 1
GLYPH_CLASS_MARK = 3


# Private dictionary entries tx +S may rewrite: the subroutines and
# the width encoding are its own; every other value is put back.
TX_PRIVATE = ("Subrs", "defaultWidthX", "nominalWidthX")


class EmitError(Error):
    pass


def write_otf(plan, path):
    # tx +S makes shared pieces of the charstrings into subroutines;
    # the outlines, hints and widths stay the same.
    font = _build(plan, truetype=False)
    with tempfile.TemporaryDirectory() as directory:
        flat = Path(directory) / "flat.otf"
        packed = Path(directory) / "packed.cff"
        font.save(flat)
        run = subprocess.run(
            ["tx", "-cff", "+S", "+b", str(flat), str(packed)],
            capture_output=True, text=True)
        if run.returncode != 0 or not packed.exists():
            raise EmitError("tx +S failed: %s" % run.stderr.strip())
        font = TTFont(flat)
        table = newTable("CFF ")
        table.decompile(packed.read_bytes(), font)
        _restore_private(font["CFF "].cff.topDictIndex[0],
                         table.cff.topDictIndex[0])
        # tx writes FDSelect format 4 (CFF2 only) when there are more
        # than 256 ranges; CFF allows only formats 0 and 3.
        table.cff.topDictIndex[0].FDSelect.format = 3
        font["CFF "] = table
        font.save(path)


def _restore_private(before, after):
    """Put back the values tx +S rewrote (it may reorder stem widths)."""
    if list(before.charset) != list(after.charset) or [
            before.CharStrings.getItemAndSelector(name)[1]
            for name in before.charset] != [
            after.CharStrings.getItemAndSelector(name)[1]
            for name in after.charset]:
        raise EmitError("tx +S changed the glyphs or their dictionaries")
    for old, new in zip(before.FDArray, after.FDArray):
        values = {key: value for key, value in old.Private.rawDict.items()
                  if key not in TX_PRIVATE}
        for key in list(new.Private.rawDict):
            if key not in TX_PRIVATE and key not in values:
                del new.Private.rawDict[key]
                delattr(new.Private, key)
        for key, value in values.items():
            new.Private.rawDict[key] = value
            setattr(new.Private, key, value)


def write_ttf(plan, path):
    _build(plan, truetype=True).save(path)


def _build(plan, truetype):
    # The fonts carry no glyph names (post format 3; CID-keyed CFF).
    order = [".notdef"] + [
        "cid%05d" % gid for gid in range(1, len(plan.glyphs))]
    font_name = dict(zip((glyph.name for glyph in plan.glyphs), order))

    builder = FontBuilder(UNITS_PER_EM, isTTF=truetype)
    builder.setupGlyphOrder(order)
    font = builder.font
    font["cmap"] = _cmap({
        codepoint: font_name[glyph.name]
        for glyph in plan.glyphs for codepoint in glyph.codepoints})
    if truetype:
        builder.setupGlyf({
            font_name[glyph.name]: _truetype_glyph(glyph)
            for glyph in plan.glyphs})
        glyf = font["glyf"]
        metrics = {
            font_name[glyph.name]: (
                glyph.advance, getattr(glyf[font_name[glyph.name]],
                                       "xMin", 0))
            for glyph in plan.glyphs}
    else:
        font.sfntVersion = "OTTO"
        font["CFF "] = newTable("CFF ")
        font["CFF "].cff = build_cff(plan, order)
        metrics = {
            font_name[glyph.name]: (glyph.advance, _left_bearing(glyph))
            for glyph in plan.glyphs}
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(
        ascent=product.TYPO_ASCENDER, descent=product.TYPO_DESCENDER,
        lineGap=product.TYPO_LINE_GAP)
    builder.setupNameTable({
        "copyright": product.COPYRIGHT,
        "familyName": plan.family,
        "styleName": "Regular",
        "uniqueFontIdentifier": "%s;%s" % (
            product.VENDOR, plan.postscript_name),
        "fullName": plan.family,
        "version": "Version " + plan.version,
        "psName": plan.postscript_name,
        "trademark": product.TRADEMARK,
        "typographicFamily": plan.family,
        "typographicSubfamily": "Regular",
    })
    builder.setupPost(keepGlyphNames=False, **UNDERLINE)
    if truetype:
        builder.setupMaxp()
        font["maxp"].maxZones = 1     # no instructions
    font["GSUB"] = build_gsub(plan, font_name, font["name"])
    font["GPOS"] = build_gpos(plan, font_name, font.getReverseGlyphMap())
    font["GDEF"] = _gdef(plan, font_name)
    build_math(font, plan, font_name)
    _head(font, plan, truetype)
    _os2(builder, plan, truetype)
    return font


def _truetype_glyph(glyph):
    pen = TTGlyphPen(None)
    # TrueType outlines run the other way round.
    draw(glyph.outline, Cu2QuPen(
        pen, TRUETYPE_TOLERANCE, reverse_direction=True))
    return pen.glyph()


def _cmap(mapping):
    """BMP and full-range subtables for the Unicode and Windows platforms."""
    bmp = {c: name for c, name in mapping.items() if c <= 0xFFFF}
    cmap = newTable("cmap")
    cmap.tableVersion = 0
    cmap.tables = [
        buildCmapSubTable(bmp, 4, 0, 3),
        buildCmapSubTable(mapping, 12, 0, 4),
        buildCmapSubTable(bmp, 4, 3, 1),
        buildCmapSubTable(mapping, 12, 3, 10),
    ]
    return cmap


def _left_bearing(glyph):
    box = bounds(glyph.outline)
    return math.floor(box[0]) if box else 0


def _gdef(plan, font_name):
    table = otTables.GDEF()
    table.Version = 0x00010000
    table.GlyphClassDef = otTables.GlyphClassDef()
    table.GlyphClassDef.classDefs = {
        font_name[glyph.name]: (
            GLYPH_CLASS_MARK if glyph.name in plan.marks
            else GLYPH_CLASS_BASE)
        for glyph in plan.glyphs}
    table.AttachList = table.LigCaretList = None
    table.MarkAttachClassDef = None
    gdef = newTable("GDEF")
    gdef.table = table
    return gdef


def _head(font, plan, truetype):
    head = font["head"]
    major, _, minor = plan.version.partition(".")
    head.fontRevision = int(major) + int(minor or 0) / 10 ** len(minor)
    head.flags = HEAD_FLAGS[truetype]
    head.lowestRecPPEM = 8
    # A reproducible build may fix the time stamps.
    stamp = int(os.environ.get("SOURCE_DATE_EPOCH", time.time()))
    head.created = head.modified = stamp + EPOCH_DIFFERENCE


def _os2(builder, plan, truetype):
    if truetype:
        win = (product.TRUETYPE_WIN_ASCENT, product.TRUETYPE_WIN_DESCENT)
    else:
        boxes = [bounds(g.outline) for g in plan.glyphs if g.outline]
        win = (
            round(max(box[3] for box in boxes)),
            -round(min(box[1] for box in boxes)))
    builder.setupOS2(
        version=4, usWeightClass=400, usWidthClass=5, fsType=8,
        achVendID=product.VENDOR, fsSelection=0x00C0,
        sTypoAscender=product.TYPO_ASCENDER,
        sTypoDescender=product.TYPO_DESCENDER,
        sTypoLineGap=product.TYPO_LINE_GAP,
        usWinAscent=win[0], usWinDescent=win[1],
        sxHeight=plan.x_height, sCapHeight=plan.cap_height,
        usDefaultChar=32, usBreakChar=32, panose=_panose(),
        **SUBSCRIPT, **SUPERSCRIPT, **STRIKEOUT)
    font = builder.font
    os2 = font["OS/2"]
    os2.recalcUnicodeRanges(font)
    os2.recalcCodePageRanges(font)
    os2.recalcAvgCharWidth(font)
    os2.usMaxContext = maxCtxFont(font)


def _panose():
    panose = Panose()
    for key in vars(panose):
        setattr(panose, key, PANOSE.get(key, 0))
    return panose
