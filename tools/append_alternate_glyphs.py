"""Append the Full 31x3 optical alternates without moving existing glyphs."""
from pathlib import Path

from fontTools import t1Lib
from fontTools.tfmLib import TFM
from fontTools.ttLib.tables import otTables as ot
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen

from finalize import update_average_width, math_add
import source_policy
from layout import ssty_mapping

STYLES = ('text', 'script', 'scriptscript')


def sort_features(gs):
    old = list(gs.FeatureList.FeatureRecord)
    order = sorted(range(len(old)), key=lambda i: (old[i].FeatureTag, i))
    remap = {a: b for b, a in enumerate(order)}
    for sr in gs.ScriptList.ScriptRecord:
        for lang in (
            [sr.Script.DefaultLangSys]
            + [r.LangSys for r in sr.Script.LangSysRecord]
        ):
            if lang:
                lang.FeatureIndex = sorted(
                    (remap[i] for i in lang.FeatureIndex)
                )
                if lang.ReqFeatureIndex != 65535:
                    lang.ReqFeatureIndex = remap[lang.ReqFeatureIndex]
    if getattr(gs, 'FeatureVariations', None):
        for rec in gs.FeatureVariations.FeatureVariationRecord:
            for sub in rec.FeatureTableSubstitution.SubstitutionRecord:
                sub.FeatureIndex = remap[sub.FeatureIndex]
    gs.FeatureList.FeatureRecord = [old[i] for i in order]


def feature(font, tag, mapping):
    gs = font['GSUB'].table
    st = ot.SingleSubst()
    st.mapping = dict(mapping)
    lk = ot.Lookup()
    lk.LookupType = 1
    lk.LookupFlag = 0
    lk.SubTable = [st]
    lk.SubTableCount = 1
    idx = len(gs.LookupList.Lookup)
    gs.LookupList.Lookup.append(lk)
    gs.LookupList.LookupCount += 1
    feat = ot.Feature()
    feat.FeatureParams = None
    feat.LookupListIndex = [idx]
    feat.LookupCount = 1
    rec = ot.FeatureRecord()
    rec.FeatureTag = tag
    rec.Feature = feat
    fi = len(gs.FeatureList.FeatureRecord)
    gs.FeatureList.FeatureRecord.append(rec)
    gs.FeatureList.FeatureCount += 1
    for sr in gs.ScriptList.ScriptRecord:
        for lang in (
            [sr.Script.DefaultLangSys]
            + [r.LangSys for r in sr.Script.LangSysRecord]
        ):
            if lang:
                lang.FeatureIndex.append(fi)
                lang.FeatureCount += 1
    sort_features(gs)


def fraktur_mapping(font):
    """Reuse ordinary Fraktur I/R through actual reachable ssty inputs."""
    ssty = ssty_mapping(font)
    cmap = font.getBestCmap()
    names = set(font.getGlyphOrder())
    maps = {tag: {} for tag in ('cv90', 'cv91', 'cv92')}
    for cp, letter in ((8465, 'I'), (8476, 'R')):
        base = f'uni{cp:04X}'
        if cmap.get(cp) != base:
            raise ValueError('Fraktur reserved Unicode owner changed')
        styles = ssty.get(base)
        if not styles or len(styles) != 2 or len(set([base, *styles])) != 3:
            raise ValueError('Fraktur requires actual S/SS ssty inputs')
        for i, tag in enumerate(maps):
            target = letter + '.frak' + ('', '.ssty1', '.ssty2')[i]
            if target not in names:
                raise ValueError('Fraktur target missing')
            for name in [base] if i == 0 else [base, styles[i - 1]]:
                if name not in names or name in maps[tag]:
                    raise ValueError('Fraktur route collision/missing input')
                maps[tag][name] = target
    return maps


def load_sources(source, mf, ledger):
    source = Path(source)
    if len(ledger) != 31 or len({r['semantic_id'] for r in ledger}) != 31:
        raise ValueError('31 unique alternate routes required')
    cache = {}
    for route in ledger:
        if tuple(s['style'] for s in route['source_styles']) != STYLES:
            raise ValueError('alternate style order differs')
        for style in route['source_styles']:
            alt = style['alternate']
            stem, tag = alt['font'], alt['tag']
            if source_policy.SOURCE_FONTS.get(tag) != stem:
                raise ValueError('alternate source family mismatch')
            if stem not in cache:
                pf = t1Lib.T1Font(str(source / (stem + '.pfb')))
                pf.parse()
                if tuple(pf['FontMatrix']) != (0.001, 0, 0, 0.001, 0, 0):
                    raise ValueError('unsupported alternate FontMatrix')
                cache[stem] = (pf, TFM(str(source / (stem + '.tfm'))))
    return cache


def edit(f, cache, mf, ledger):
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
        if tuple((s['style'] for s in route['source_styles'])) != STYLES:
            raise ValueError('alternate style order differs')
        cp = int(route['base_unicode'][2:], 16)
        base = f.getBestCmap()[cp]
        for i, style in enumerate(route['source_styles']):
            alt = style['alternate']
            stem = alt['font']
            tag = alt['tag']
            slot = int(alt['slot'])
            if source_policy.SOURCE_FONTS.get(tag) != stem:
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
                if skewchar is not None else 0
            )
            if alt['accent_calibration']['skewchar'] != skewchar:
                raise ValueError('alternate skew policy mismatch')
            width = round(1000 * m['width'])
            ic = round(1000 * m.get('italic', 0))
            accent = round(
                1000 * ((m['width'] + m.get('italic', 0)) / 2 + skew)
            )
            name = (
                'diagnostic.' + route['semantic_id'].replace('.', '_')
                + '.' + style['style']
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
