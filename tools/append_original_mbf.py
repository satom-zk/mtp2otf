"""Append original mathematical bold and its cv89/ssty routes."""
from pathlib import Path

from fontTools import t1Lib
from fontTools.tfmLib import TFM
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen

from finalize import update_average_width
from layout import validate_gsub, ssty_index, insert_routes
from finalize import math_add, aggregate_values

TAG = 'cv89'
STYLES = (
    ('T', 'bold', 'mt2mbt'), ('S', 'bold_s', 'mt2mbs'),
    ('SS', 'bold_ss', 'mt2mbf')
)
SLOTS = tuple(range(48, 58)) + tuple(range(65, 91)) + tuple(range(97, 123))
MATH_FIELDS = (
    (
        'MathItalicsCorrectionInfo', 'Coverage', 'ItalicsCorrection',
        'ItalicsCorrectionCount'
    ),
    (
        'MathTopAccentAttachment', 'TopAccentCoverage', 'TopAccentAttachment',
        'TopAccentAttachmentCount'
    )
)


def identities():
    rows = []
    for style, role, stem in STYLES:
        for slot in SLOTS:
            cp = (
                120782 + slot - 48 if slot < 58 else 119808 + slot - 65
                if slot < 91 else 119834 + slot - 97
            )
            rows.append(
                {
                    'source_id': f'SRC-{stem}-{slot:03d}', 'source_face': stem,
                    'source_role': role, 'style': style, 'Unicode_input': cp,
                    'source_slot': slot,
                    'output_glyph': f'original.mbf.u{cp:05X}.{style}'
                }
            )
    return rows


def precheck(font):
    if 'CFF ' not in font or font['head'].unitsPerEm != 1000:
        raise ValueError('mbf186 requires CFF1 OTF at 1000 UPM')
    top = font['CFF '].cff.topDictIndex[0]
    if tuple(top.FontMatrix) != (0.001, 0, 0, 0.001, 0, 0):
        raise ValueError('unsupported output CFF FontMatrix')
    if not top.CharStrings.charStringsAreIndexed or hasattr(top, 'FDArray'):
        raise ValueError('unsupported CFF charstring/CID structure')
    names = [r['output_glyph'] for r in identities()]
    existing = set(font.getGlyphOrder())
    overlap = sorted(existing & set(names))
    if overlap:
        raise ValueError(
            'mbf glyph collision/repeated append: ' + ', '.join(overlap[:3])
        )
    if any((n.startswith('original.mbf.') for n in existing)):
        raise ValueError('partial mbf glyph namespace collision')
    gs = font['GSUB'].table
    if any((r.FeatureTag == TAG for r in gs.FeatureList.FeatureRecord)):
        raise ValueError('cv89 feature collision/repeated append')
    validate_gsub(gs)
    index = ssty_index(gs)
    cmap = font.getBestCmap()
    cps = {r['Unicode_input'] for r in identities()}
    if not cps <= set(cmap) or len({cmap[c] for c in cps}) != 62:
        raise ValueError(
            '62 distinct existing mathematical bold cmap owners required'
        )
    gi = font['MATH'].table.MathGlyphInfo
    if any((getattr(gi, field) is None for field, _, _, _ in MATH_FIELDS)):
        raise ValueError('MATH IC/TopAccent tables required')
    return index


def load_sources(source_dir, mf, edition, policy):
    if edition not in ('full', 'lite') or mf.get('large_variants') != policy:
        raise ValueError('mbf edition/policy mismatch')
    source_dir = Path(source_dir)
    cache = {}
    for _, role, stem in STYLES:
        if (
            mf['source_font_by_tag'].get(role) != stem
            or mf['skewchar_by_tag'].get(role) != 32
        ):
            raise ValueError('mbf source/skewchar role mismatch')
        pf = t1Lib.T1Font(str(source_dir / (stem + '.pfb')))
        pf.parse()
        if tuple(pf['FontMatrix']) != (0.001, 0, 0, 0.001, 0, 0):
            raise ValueError('unsupported source FontMatrix: ' + stem)
        cache[stem] = (pf, TFM(str(source_dir / (stem + '.tfm'))))
    return cache


def edit(font, cache, mf, edition):
    index = precheck(font)
    expected_name = 'MTPro2Math' if edition == 'full' else 'MTPro2MathLite'
    if font['name'].getDebugName(6) != expected_name:
        raise ValueError('font edition mismatch')
    top = font['CFF '].cff.topDictIndex[0]
    rows = []
    for identity in identities():
        stem = identity['source_face']
        slot = identity['source_slot']
        role = identity['source_role']
        pf, tfm = cache[stem]
        if slot not in tfm.chars:
            raise ValueError('mbf TFM slot missing: ' + identity['source_id'])
        source_name = pf['Encoding'][slot]
        if source_name == '.notdef' or source_name not in pf.getGlyphSet():
            raise ValueError(
                'mbf PFB Encoding slot missing: ' + identity['source_id']
            )
        metrics = tfm.chars[slot]
        width = metrics['width']
        italic = metrics.get('italic', 0)
        skew = tfm.kerning.get(slot, {}).get(mf['skewchar_by_tag'][role], 0)
        if any(
            (
                float(v) * (1 << 20) != int(float(v) * (1 << 20))
                for v in (width, italic, skew)
            )
        ):
            raise ValueError(
                'binary TFM metric is not an exact fix_word fraction'
            )
        advance = round(1000 * width)
        ic = round(1000 * italic)
        accent = round(1000 * ((width + italic) / 2 + skew))
        glyphs = pf.getGlyphSet()
        glyph = glyphs[source_name]
        source_bounds = BoundsPen(glyphs)
        glyph.draw(source_bounds)
        if source_bounds.bounds is None:
            raise ValueError(
                'empty mbf source outline: ' + identity['source_id']
            )
        # T2 width operand is relative to the existing
        # Private nominalWidthX.
        pen = T2CharStringPen(advance - top.Private.nominalWidthX, glyphs)
        glyph.draw(pen)
        char = pen.getCharString(
            private=top.Private, globalSubrs=font['CFF '].cff.GlobalSubrs
        )
        name = identity['output_glyph']
        top.CharStrings.charStrings[name] = len(
            top.CharStrings.charStringsIndex.items
        )
        top.CharStrings.charStringsIndex.items.append(char)
        top.charset.append(name)
        font.setGlyphOrder(list(top.charset))
        bp = BoundsPen(font.getGlyphSet())
        char.draw(bp)
        if bp.bounds is None or char.width != advance:
            raise ValueError('new CFF outline/decoded width mismatch')
        font['hmtx'][name] = (advance, round(bp.bounds[0]))
        math_add(font, name, ic, accent)
        rows.append(identity)
    insert_routes(font, rows, index)
    font['maxp'].numGlyphs = len(font.getGlyphOrder())
    agg = aggregate_values(font)
    top.FontBBox = agg['FontBBox']
    for k, v in zip(('xMin', 'yMin', 'xMax', 'yMax'), agg['head_bbox']):
        setattr(font['head'], k, v)
    for k, v in agg['hhea'].items():
        setattr(font['hhea'], k, v)
    update_average_width(font)
