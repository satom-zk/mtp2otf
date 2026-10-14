"""Append Full original yen/registered six glyphs and cv96 before ssty."""
from pathlib import Path

from fontTools import t1Lib
from fontTools.tfmLib import TFM
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen

from finalize import update_average_width, math_add, aggregate_values
from layout import validate_gsub, ssty_index, insert_routes

TAG = 'cv96'
STYLES = (
    ('T', 'ams', 'mt2syat'), ('S', 'ams_s', 'mt2syas'),
    ('SS', 'ams_ss', 'mt2syaf')
)
SYMBOLS = ((165, 85, 'yen'), (174, 114, 'registered'))


def identities():
    return [
        dict(
            Unicode_input=cp, slot=slot, style=style, source=stem,
            source_role=role,
            output_glyph='original.ams.' + label + '.' + style
        )
        for cp, slot, label in SYMBOLS for style, role, stem in STYLES
    ]


def precheck(font):
    if (
        'CFF ' not in font
        or font['head'].unitsPerEm != 1000
        or font['name'].getDebugName(6) != 'MTPro2Math'
    ):
        raise ValueError('AMS alternates require Full 1000-UPM CFF OTF')
    if any(
        (
            n.startswith(('original.ams.yen.', 'original.ams.registered.'))
            for n in font.getGlyphOrder()
        )
    ):
        raise ValueError('AMS alternate namespace collision/repeated append')
    gs = font['GSUB'].table
    if any((r.FeatureTag == TAG for r in gs.FeatureList.FeatureRecord)):
        raise ValueError('cv96 feature collision/repeated append')
    validate_gsub(gs)
    index = ssty_index(gs)
    cmap = font.getBestCmap()
    if any((cp not in cmap for cp, _, _ in SYMBOLS)) or cmap[165] == cmap[174]:
        raise ValueError(
            'two distinct existing yen/registered cmap owners required'
        )
    info = font['MATH'].table.MathGlyphInfo
    if (
        info.MathItalicsCorrectionInfo is None
        or info.MathTopAccentAttachment is None
    ):
        raise ValueError('AMS alternate MATH IC/TopAccent tables required')
    return index


def add_routes(font, rows, index):
    return insert_routes(font, rows, index, tag=TAG)


def load_sources(source, mf, edition, policy):
    if edition != 'full':
        raise ValueError('AMS alternates are Full-only')
    if mf.get('large_variants') != policy:
        raise ValueError('AMS alternate policy mismatch')
    cache = {}
    for stem in ('mt2syat', 'mt2syas', 'mt2syaf'):
        pf = t1Lib.T1Font(str(Path(source) / (stem + '.pfb')))
        pf.parse()
        if tuple(pf['FontMatrix']) != (0.001, 0, 0, 0.001, 0, 0):
            raise ValueError('unsupported AMS alternate FontMatrix')
        cache[stem] = (pf, TFM(str(Path(source) / (stem + '.tfm'))))
    return cache


def edit(f, cache):
    index = precheck(f)
    top = f['CFF '].cff.topDictIndex[0]
    rows = []
    for identity in identities():
        pf, tf = cache[identity['source']]
        slot = identity['slot']
        sn = pf['Encoding'][slot]
        if (
            slot not in tf.chars
            or sn == '.notdef'
            or sn not in pf.getGlyphSet()
        ):
            raise ValueError('AMS alternate original slot missing')
        m = tf.chars[slot]
        width = round(1000 * m['width'])
        corr = round(1000 * m.get('italic', 0))
        accent = round((width + corr) / 2)
        bp = BoundsPen(pf.getGlyphSet())
        pf.getGlyphSet()[sn].draw(bp)
        if bp.bounds is None:
            raise ValueError('empty AMS alternate original outline')
        name = identity['output_glyph']
        pen = T2CharStringPen(
            width - top.Private.nominalWidthX, pf.getGlyphSet()
        )
        pf.getGlyphSet()[sn].draw(pen)
        char = pen.getCharString(
            private=top.Private, globalSubrs=f['CFF '].cff.GlobalSubrs
        )
        top.CharStrings.charStrings[name] = len(
            top.CharStrings.charStringsIndex.items
        )
        top.CharStrings.charStringsIndex.items.append(char)
        top.charset.append(name)
        f.setGlyphOrder(list(top.charset))
        f['hmtx'][name] = (width, round(bp.bounds[0]))
        math_add(f, name, corr, accent)
        rows.append(identity)
    add_routes(f, rows, index)
    f['maxp'].numGlyphs = len(f.getGlyphOrder())
    agg = aggregate_values(f)
    top.FontBBox = agg['FontBBox']
    for k, v in zip(('xMin', 'yMin', 'xMax', 'yMax'), agg['head_bbox']):
        setattr(f['head'], k, v)
    for k, v in agg['hhea'].items():
        setattr(f['hhea'], k, v)
    update_average_width(f)
