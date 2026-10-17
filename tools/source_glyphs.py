"""Post-normalization original glyphs and their public/optical routes.
All source acquisition belongs to catalog/outlines/metrics, not this
module.
"""

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen

from font_geometry import update_average_width, math_add, aggregate_values
from substitution import (
    validate_gsub,
    ssty_index,
    insert_routes,
    ssty_mapping,
    feature,
    fraktur_mapping,
)
import declarations


AMS_SYMBOLS = ((10003, 88, 'checkmark'), (10016, 122, 'maltese'))


AMS_STYLES = (('T', 'mt2syat'), ('S', 'mt2syas'), ('SS', 'mt2syaf'))


def add_ams_glyphs(f, sources):
    original = list(f.getGlyphOrder())
    if 'CFF ' not in f:
        raise ValueError('append requires CFF OTF')
    names = [
        label + ('' if i == 0 else '.ssty' + str(i))
        for _, _, label in AMS_SYMBOLS
        for i in range(3)
    ]
    if set(names) & set(original):
        raise ValueError('appended glyph name collision')
    if any(
        (cp in st.cmap for st in f['cmap'].tables for cp, _, _ in AMS_SYMBOLS)
    ):
        raise ValueError('Unicode collision or repeated append')
    unicodes = [st for st in f['cmap'].tables if st.isUnicode()]
    if not unicodes or any((st.format not in (4, 12) for st in unicodes)):
        raise ValueError('unsupported Unicode cmap structure')
    ssty = ssty_mapping(f)
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
    for cp, slot, label in AMS_SYMBOLS:
        optical = []
        for i, (style, stem) in enumerate(AMS_STYLES):
            t1, tfm = sources[stem]
            if slot not in tfm.chars:
                raise ValueError('source slot missing')
            source_name = t1['Encoding'][slot]
            if source_name == '.notdef' or source_name not in t1.getGlyphSet():
                raise ValueError('AMS_SYMBOLS source Encoding slot missing')
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
                width,
                round(bounds.bounds[0] if bounds.bounds else 0),
            )
            f.setGlyphOrder(list(top.charset))
            math_add(f, name, ic, accent)
        ssty[optical[0]] = optical[1:]
        for st in unicodes:
            st.cmap[cp] = optical[0]
    f['maxp'].numGlyphs = len(f.getGlyphOrder())
    update_average_width(f)


ALTERNATE_STYLES = ('text', 'script', 'scriptscript')


def add_optical_alternates(f, cache, mf, ledger):
    if 'CFF ' not in f:
        raise ValueError('alternate append requires completed CFF OTF')
    original = list(f.getGlyphOrder())
    top = f['CFF '].cff.topDictIndex[0]
    # Decompile MATH before modifying the glyph set.
    f['MATH'].table.MathGlyphInfo
    gs = f['GSUB'].table
    tags = ('cv90', 'cv91', 'cv92', 'cv93', 'cv94', 'cv95')
    if any((r.FeatureTag in tags for r in gs.FeatureList.FeatureRecord)):
        raise ValueError('diagnostic CV collision')
    maps = {tag: {} for tag in tags}
    script_targets = {}
    for route in ledger:
        if (
            tuple((s['style'] for s in route['source_styles']))
            != ALTERNATE_STYLES
        ):
            raise ValueError('alternate style order differs')
        cp = int(route['base_unicode'][2:], 16)
        base = f.getBestCmap()[cp]
        for i, style in enumerate(route['source_styles']):
            alt = style['alternate']
            stem = alt['font']
            tag = alt['tag']
            slot = int(alt['slot'])
            if declarations.SOURCE_FONTS.get(tag) != stem:
                raise ValueError('alternate source family mismatch')
            pf, tf = cache[stem]
            sn = pf['Encoding'][slot]
            if (
                sn == '.notdef'
                or sn not in pf.getGlyphSet()
                or slot not in tf.chars
            ):
                raise ValueError('alternate Type1 slot mismatch')
            m = tf.chars[slot]
            skewchar = mf['skewchar_by_tag'][tag]
            skew = (
                tf.kerning.get(slot, {}).get(skewchar, 0)
                if skewchar is not None
                else 0
            )
            if alt['accent_calibration']['skewchar'] != skewchar:
                raise ValueError('alternate skew policy mismatch')
            width = round(1000 * m['width'])
            ic = round(1000 * m.get('italic', 0))
            accent = round(
                1000 * ((m['width'] + m.get('italic', 0)) / 2 + skew)
            )
            name = (
                'diagnostic.'
                + route['semantic_id'].replace('.', '_')
                + '.'
                + style['style']
            )
            if name in top.CharStrings.charStrings:
                raise ValueError('alternate identity collision')
            glyph = pf.getGlyphSet()[sn]
            pen = T2CharStringPen(
                width - top.Private.nominalWidthX, pf.getGlyphSet()
            )
            glyph.draw(pen)
            char = pen.getCharString(
                private=top.Private, globalSubrs=f['CFF '].cff.GlobalSubrs
            )
            top.CharStrings.charStrings[name] = len(
                top.CharStrings.charStringsIndex.items
            )
            top.CharStrings.charStringsIndex.items.append(char)
            top.charset.append(name)
            f.setGlyphOrder(list(top.charset))
            bp = BoundsPen(pf.getGlyphSet())
            glyph.draw(bp)
            f['hmtx'][name] = (width, round(bp.bounds[0]))
            math_add(f, name, ic, accent)
            mapping = maps[tags[i + 3 if route['group'] == 'Curly' else i]]
            standard = style['current_standard']['glyph']
            if standard not in original:
                raise ValueError('alternate standard route missing')
            mapping[base] = name
            mapping[standard] = name
            if route['group'] == 'Curly' and i:
                sibling = base + '.ssty' + str(i)
                if sibling in original:
                    mapping[sibling] = name
            if route['group'] == 'Script' and route['weight'] == 'regular':
                script_targets[cp, i] = name
    for route in ledger:
        if route['group'] == 'Curly':
            cp = int(route['base_unicode'][2:], 16)
            for i, s in enumerate(route['source_styles']):
                if (cp, i) in script_targets:
                    maps[tags[i]][s['current_standard']['glyph']] = (
                        script_targets[cp, i]
                    )
    for tag, entries in fraktur_mapping(f).items():
        if set(maps[tag]) & set(entries):
            raise ValueError('Fraktur reuse CV collision')
        maps[tag].update(entries)
    for tag in tags:
        feature(f, tag, maps[tag])
    f['maxp'].numGlyphs = len(f.getGlyphOrder())
    update_average_width(f)


AMS_ALTERNATE_TAG = 'cv96'


AMS_ALTERNATE_STYLES = (
    ('T', 'ams', 'mt2syat'),
    ('S', 'ams_s', 'mt2syas'),
    ('SS', 'ams_ss', 'mt2syaf'),
)


AMS_ALTERNATE_SYMBOLS = ((165, 85, 'yen'), (174, 114, 'registered'))


def ams_alternates_identities():
    return [
        dict(
            Unicode_input=cp,
            slot=slot,
            style=style,
            source=stem,
            source_role=role,
            output_glyph='original.ams.' + label + '.' + style,
        )
        for cp, slot, label in AMS_ALTERNATE_SYMBOLS
        for style, role, stem in AMS_ALTERNATE_STYLES
    ]


def ams_alternates_precheck(font):
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
    if any(
        (
            r.FeatureTag == AMS_ALTERNATE_TAG
            for r in gs.FeatureList.FeatureRecord
        )
    ):
        raise ValueError('cv96 feature collision/repeated append')
    validate_gsub(gs)
    index = ssty_index(gs)
    cmap = font.getBestCmap()
    if (
        any((cp not in cmap for cp, _, _ in AMS_ALTERNATE_SYMBOLS))
        or cmap[165] == cmap[174]
    ):
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


def ams_alternates_add_routes(font, rows, index):
    return insert_routes(font, rows, index, tag=AMS_ALTERNATE_TAG)


def add_ams_alternates(f, cache):
    index = ams_alternates_precheck(f)
    top = f['CFF '].cff.topDictIndex[0]
    rows = []
    for identity in ams_alternates_identities():
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
    ams_alternates_add_routes(f, rows, index)
    f['maxp'].numGlyphs = len(f.getGlyphOrder())
    agg = aggregate_values(f)
    top.FontBBox = agg['FontBBox']
    for k, v in zip(('xMin', 'yMin', 'xMax', 'yMax'), agg['head_bbox']):
        setattr(f['head'], k, v)
    for k, v in agg['hhea'].items():
        setattr(f['hhea'], k, v)
    update_average_width(f)


BOLD_TAG = 'cv89'


BOLD_STYLES = (
    ('T', 'bold', 'mt2mbt'),
    ('S', 'bold_s', 'mt2mbs'),
    ('SS', 'bold_ss', 'mt2mbf'),
)


BOLD_SLOTS = (
    tuple(range(48, 58)) + tuple(range(65, 91)) + tuple(range(97, 123))
)


BOLD_MATH_FIELDS = (
    (
        'MathItalicsCorrectionInfo',
        'Coverage',
        'ItalicsCorrection',
        'ItalicsCorrectionCount',
    ),
    (
        'MathTopAccentAttachment',
        'TopAccentCoverage',
        'TopAccentAttachment',
        'TopAccentAttachmentCount',
    ),
)


def bold_identities():
    rows = []
    for style, role, stem in BOLD_STYLES:
        for slot in BOLD_SLOTS:
            cp = (
                120782 + slot - 48
                if slot < 58
                else 119808 + slot - 65 if slot < 91 else 119834 + slot - 97
            )
            rows.append(
                {
                    'source_id': f'SRC-{stem}-{slot:03d}',
                    'source_face': stem,
                    'source_role': role,
                    'style': style,
                    'Unicode_input': cp,
                    'source_slot': slot,
                    'output_glyph': f'original.mbf.u{cp:05X}.{style}',
                }
            )
    return rows


def mbf_precheck(font):
    if 'CFF ' not in font or font['head'].unitsPerEm != 1000:
        raise ValueError('mbf186 requires CFF1 OTF at 1000 UPM')
    top = font['CFF '].cff.topDictIndex[0]
    if tuple(top.FontMatrix) != (0.001, 0, 0, 0.001, 0, 0):
        raise ValueError('unsupported output CFF FontMatrix')
    if not top.CharStrings.charStringsAreIndexed or hasattr(top, 'FDArray'):
        raise ValueError('unsupported CFF charstring/CID structure')
    names = [r['output_glyph'] for r in bold_identities()]
    existing = set(font.getGlyphOrder())
    overlap = sorted(existing & set(names))
    if overlap:
        raise ValueError(
            'mbf glyph collision/repeated append: ' + ', '.join(overlap[:3])
        )
    if any((n.startswith('original.mbf.') for n in existing)):
        raise ValueError('partial mbf glyph namespace collision')
    gs = font['GSUB'].table
    if any((r.FeatureTag == BOLD_TAG for r in gs.FeatureList.FeatureRecord)):
        raise ValueError('cv89 feature collision/repeated append')
    validate_gsub(gs)
    index = ssty_index(gs)
    cmap = font.getBestCmap()
    cps = {r['Unicode_input'] for r in bold_identities()}
    if not cps <= set(cmap) or len({cmap[c] for c in cps}) != 62:
        raise ValueError(
            '62 distinct existing mathematical bold cmap owners required'
        )
    gi = font['MATH'].table.MathGlyphInfo
    if any(
        (getattr(gi, field) is None for field, _, _, _ in BOLD_MATH_FIELDS)
    ):
        raise ValueError('MATH IC/TopAccent tables required')
    return index


def add_original_bold(font, cache, mf, edition):
    index = mbf_precheck(font)
    expected_name = 'MTPro2Math' if edition == 'full' else 'MTPro2MathLite'
    if font['name'].getDebugName(6) != expected_name:
        raise ValueError('font edition mismatch')
    top = font['CFF '].cff.topDictIndex[0]
    rows = []
    for identity in bold_identities():
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
