"""Append explicitly scoped source glyphs after completed core
serialization.
"""
from pathlib import Path

from fontTools import t1Lib
from fontTools.tfmLib import TFM
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen

from finalize import update_average_width, math_add

AMS = ((10003, 88, 'checkmark'), (10016, 122, 'maltese'))
STYLES = (('T', 'mt2syat'), ('S', 'mt2syas'), ('SS', 'mt2syaf'))


def resolve_ssty(font):
    gs = font['GSUB'].table
    indices = {
        i for r in gs.FeatureList.FeatureRecord if r.FeatureTag == 'ssty'
        for i in r.Feature.LookupListIndex
    }
    if len(indices) != 1:
        raise ValueError('expected one explicit ssty lookup')
    lookup = gs.LookupList.Lookup[next(iter(indices))]
    if (
        lookup.LookupType != 3
        or len(lookup.SubTable) != 1
        or (not hasattr(lookup.SubTable[0], 'alternates'))
    ):
        raise ValueError('unsupported ssty structure')
    return lookup.SubTable[0].alternates


def load_sources(source, manifest, edition, policy):
    if edition != 'full':
        raise ValueError('AMS append is Full-only')
    source = Path(source)
    if manifest.get('large_variants') != policy:
        raise ValueError('input manifest policy differs')
    sources = {}
    for _, stem in STYLES:
        t1 = t1Lib.T1Font(str(source / (stem + '.pfb')))
        t1.parse()
        if tuple(t1['FontMatrix']) != (0.001, 0, 0, 0.001, 0, 0):
            raise ValueError('unsupported AMS FontMatrix')
        sources[stem] = (t1, TFM(str(source / (stem + '.tfm'))))
    return sources


def edit(f, sources):
    original = list(f.getGlyphOrder())
    if 'CFF ' not in f:
        raise ValueError('append requires CFF OTF')
    names = [
        label + ('' if i == 0 else '.ssty' + str(i)) for _, _, label in AMS
        for i in range(3)
    ]
    if set(names) & set(original):
        raise ValueError('appended glyph name collision')
    if any((cp in st.cmap for st in f['cmap'].tables for cp, _, _ in AMS)):
        raise ValueError('Unicode collision or repeated append')
    unicodes = [st for st in f['cmap'].tables if st.isUnicode()]
    if not unicodes or any((st.format not in (4, 12) for st in unicodes)):
        raise ValueError('unsupported Unicode cmap structure')
    ssty = resolve_ssty(f)
    gi = f['MATH'].table.MathGlyphInfo
    for name in names:
        if name in ssty:
            raise ValueError('ssty collision')
    if (
        gi.MathItalicsCorrectionInfo is None
        or gi.MathTopAccentAttachment is None
    ):
        raise ValueError('MATH value tables missing')
    top = f['CFF '].cff.topDictIndex[0]
    for cp, slot, label in AMS:
        optical = []
        for i, (style, stem) in enumerate(STYLES):
            t1, tfm = sources[stem]
            if slot not in tfm.chars:
                raise ValueError('source slot missing')
            source_name = t1['Encoding'][slot]
            if source_name == '.notdef' or source_name not in t1.getGlyphSet():
                raise ValueError('AMS source Encoding slot missing')
            glyph = t1.getGlyphSet()[source_name]
            m = tfm.chars[slot]
            width = round(1000 * m['width'])
            ic = round(1000 * m.get('italic', 0))
            accent = round((width + ic) / 2)
            name = label + ('' if i == 0 else '.ssty' + str(i))
            optical.append(name)
            pen = T2CharStringPen(
                width - top.Private.nominalWidthX, t1.getGlyphSet()
            )
            glyph.draw(pen)
            char = pen.getCharString(
                private=top.Private, globalSubrs=f['CFF '].cff.GlobalSubrs
            )
            top.CharStrings.charStrings[name] = len(
                top.CharStrings.charStringsIndex
            )
            top.CharStrings.charStringsIndex.items.append(char)
            top.charset.append(name)
            bounds = BoundsPen(t1.getGlyphSet())
            glyph.draw(bounds)
            f['hmtx'].metrics[name] = (
                width, round(bounds.bounds[0] if bounds.bounds else 0)
            )
            f.setGlyphOrder(list(top.charset))
            math_add(f, name, ic, accent)
        ssty[optical[0]] = optical[1:]
        for st in unicodes:
            st.cmap[cp] = optical[0]
    f['maxp'].numGlyphs = len(f.getGlyphOrder())
    update_average_width(f)
