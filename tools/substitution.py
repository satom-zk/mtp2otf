"""Manage native/serialized GSUB routes and shared lookup references."""

import mapping as U


def lang_systems(gs):
    for record in gs.ScriptList.ScriptRecord:
        if record.Script.DefaultLangSys is not None:
            yield record.Script.DefaultLangSys
        for lang in record.Script.LangSysRecord:
            yield lang.LangSys


def ssty_index(gs):
    features = [
        r for r in gs.FeatureList.FeatureRecord if r.FeatureTag == 'ssty'
    ]
    if len(features) != 1 or len(features[0].Feature.LookupListIndex) != 1:
        raise ValueError('expected one ssty feature with one lookup')
    index = features[0].Feature.LookupListIndex[0]
    if not 0 <= index < len(gs.LookupList.Lookup):
        raise ValueError('ssty lookup index out of range')
    lookup = gs.LookupList.Lookup[index]
    if (
        lookup.LookupType != 3
        or len(lookup.SubTable) != 1
        or (not hasattr(lookup.SubTable[0], 'alternates'))
    ):
        raise ValueError(
            'unsupported ssty structure (requires one AlternateSubst '
            'subtable)'
        )
    if lookup.LookupFlag != 0:
        raise ValueError('unsupported ssty lookup flags')
    return index


def references(node, seen=None):
    """Walk otTables, including Context/ChainContext/Extension
    descendants.
    """
    from fontTools.ttLib.tables import otTables as ot

    if seen is None:
        seen = set()
    if node is None or isinstance(node, (str, int, float, bool, bytes)):
        return
    if id(node) in seen:
        return
    seen.add(id(node))
    if isinstance(node, ot.SubstLookupRecord):
        yield node
    if isinstance(node, dict):
        children = node.values()
    elif isinstance(node, (list, tuple)):
        children = node
    elif hasattr(node, '__dict__'):
        children = vars(node).values()
    else:
        raise ValueError('unknown GSUB object: ' + type(node).__name__)
    for child in children:
        yield from references(child, seen)


def validate_gsub(gs):
    if getattr(gs, 'FeatureVariations', None) is not None:
        raise ValueError(
            'FeatureVariations not supported by mathematical bold stage'
        )
    if gs.Version != 65536:
        raise ValueError('unsupported GSUB version')
    n = len(gs.LookupList.Lookup)
    if gs.LookupList.LookupCount != n or gs.FeatureList.FeatureCount != len(
        gs.FeatureList.FeatureRecord
    ):
        raise ValueError('GSUB count mismatch')
    for lookup in gs.LookupList.Lookup:
        if lookup.LookupType not in range(1, 9) or lookup.SubTableCount != len(
            lookup.SubTable
        ):
            raise ValueError('unsupported GSUB lookup type/count')
        if lookup.LookupType == 7:
            for sub in lookup.SubTable:
                if (
                    sub.ExtensionLookupType not in (1, 2, 3, 4, 5, 6, 8)
                    or sub.ExtSubTable is None
                ):
                    raise ValueError('unsupported GSUB extension structure')
    for feature in gs.FeatureList.FeatureRecord:
        if feature.Feature.LookupCount != len(
            feature.Feature.LookupListIndex
        ) or any((not 0 <= i < n for i in feature.Feature.LookupListIndex)):
            raise ValueError('feature lookup reference out of range')
    for record in references(gs):
        if not 0 <= record.LookupListIndex < n:
            raise ValueError('context lookup reference out of range')
    nf = len(gs.FeatureList.FeatureRecord)
    for lang in lang_systems(gs):
        if lang.FeatureCount != len(lang.FeatureIndex) or any(
            (not 0 <= i < nf for i in lang.FeatureIndex)
        ):
            raise ValueError('LangSys feature reference out of range')
        if lang.ReqFeatureIndex != 65535 and (
            not 0 <= lang.ReqFeatureIndex < nf
        ):
            raise ValueError('required feature reference out of range')


def remap_lookups(gs, mapping):
    for feature in gs.FeatureList.FeatureRecord:
        feature.Feature.LookupListIndex = [
            mapping[i] for i in feature.Feature.LookupListIndex
        ]
    for record in references(gs):
        record.LookupListIndex = mapping[record.LookupListIndex]


def insert_routes(font, rows, index, tag='cv89'):
    from fontTools.ttLib.tables import otTables as ot

    gs = font['GSUB'].table
    lookup_map = {
        i: i if i < index else i + 1 for i in range(len(gs.LookupList.Lookup))
    }
    remap_lookups(gs, lookup_map)
    grouped = {
        cp: {
            r['style']: r['output_glyph']
            for r in rows
            if r['Unicode_input'] == cp
        }
        for cp in sorted({r['Unicode_input'] for r in rows})
    }
    mapping = {font.getBestCmap()[cp]: v['T'] for cp, v in grouped.items()}
    sub = ot.SingleSubst()
    sub.mapping = mapping
    lookup = ot.Lookup()
    lookup.LookupType = 1
    lookup.LookupFlag = 0
    lookup.SubTable = [sub]
    lookup.SubTableCount = 1
    gs.LookupList.Lookup.insert(index, lookup)
    gs.LookupList.LookupCount += 1
    oldssty = gs.LookupList.Lookup[index + 1].SubTable[0].alternates
    new_ssty = {v['T']: [v['S'], v['SS']] for v in grouped.values()}
    if set(new_ssty) & set(oldssty):
        raise ValueError('mbf ssty collision')
    oldssty.update(new_ssty)
    feature = ot.Feature()
    feature.FeatureParams = None
    feature.LookupListIndex = [index]
    feature.LookupCount = 1
    record = ot.FeatureRecord()
    record.FeatureTag = tag
    record.Feature = feature
    old_features = list(gs.FeatureList.FeatureRecord)
    records = old_features + [record]
    order = sorted(
        range(len(records)), key=lambda i: (records[i].FeatureTag, i)
    )
    feature_map = {old: new for new, old in enumerate(order)}
    new_fi = feature_map[len(old_features)]
    for lang in lang_systems(gs):
        lang.FeatureIndex = sorted(
            [feature_map[i] for i in lang.FeatureIndex] + [new_fi]
        )
        lang.FeatureCount = len(lang.FeatureIndex)
        if lang.ReqFeatureIndex != 65535:
            lang.ReqFeatureIndex = feature_map[lang.ReqFeatureIndex]
    gs.FeatureList.FeatureRecord = [records[i] for i in order]
    gs.FeatureList.FeatureCount = len(records)
    validate_gsub(gs)
    return {
        'inserted_lookup_index': index,
        'old_to_new_lookup_index': lookup_map,
        'old_to_new_feature_index': {
            i: feature_map[i] for i in range(len(old_features))
        },
        tag + '_feature_index': new_fi,
        tag + '_mapping': mapping,
        'ssty_added': new_ssty,
    }


def ssty_mapping(font):
    gs = font['GSUB'].table
    features = [
        i
        for i, r in enumerate(gs.FeatureList.FeatureRecord)
        if r.FeatureTag == 'ssty'
    ]
    if len(features) != 1:
        raise ValueError('one actual ssty feature required')
    feature_index = features[0]
    reachable = False
    for script in gs.ScriptList.ScriptRecord:
        languages = [script.Script.DefaultLangSys] + [
            r.LangSys for r in script.Script.LangSysRecord
        ]
        reachable |= any(
            (
                lang
                and (
                    feature_index in lang.FeatureIndex
                    or lang.ReqFeatureIndex == feature_index
                )
                for lang in languages
            )
        )
    if not reachable:
        raise ValueError('ssty feature unreachable from ScriptList')
    indices = gs.FeatureList.FeatureRecord[
        feature_index
    ].Feature.LookupListIndex
    if len(indices) != 1:
        raise ValueError('one actual ssty lookup required')
    lk = gs.LookupList.Lookup[indices[0]]
    if lk.LookupType != 3 or len(lk.SubTable) != 1:
        raise ValueError('unsupported actual ssty lookup')
    return lk.SubTable[0].alternates


def install_optical_routes(sources, ssty_map, alphabet):
    bold_dotless_i = alphabet.bold_dotless_i
    bold_dotless_j = alphabet.bold_dotless_j
    bold_it_latin = alphabet.bold_italic
    fonts = sources.faces
    import_glyph = sources.import_glyph
    imported = sources.imported
    out = sources.font
    uni_owner = sources.uni_owner
    upright_dotless = alphabet.upright_dotless_i
    upright_dotless_j = alphabet.upright_dotless_j
    if ssty_map:
        out.addLookup(
            'ssty',
            'gsub_alternate',
            (),
            (
                (
                    'ssty',
                    (
                        ('DFLT', ('dflt',)),
                        ('latn', ('dflt',)),
                        ('math', ('dflt',)),
                    ),
                ),
            ),
        )
        out.addLookupSubtable('ssty', 'ssty-1')
        for base, alts in ssty_map.items():
            try:
                out[base].addPosSub('ssty-1', tuple(alts))
            except Exception as exc:
                raise ValueError(f'ssty glyph {base}: {exc}') from exc

    # Dotless substitutions for italic i/j and upright i/j.
    dtls_pairs = []
    if 0x1D456 in uni_owner and 0x1D6A4 in uni_owner:
        dtls_pairs.append((uni_owner[0x1D456], uni_owner[0x1D6A4]))
    if 0x1D457 in uni_owner and 0x1D6A5 in uni_owner:
        dtls_pairs.append((uni_owner[0x1D457], uni_owner[0x1D6A5]))
    if 0x0069 in uni_owner and upright_dotless:
        dtls_pairs.append((uni_owner[0x0069], upright_dotless))
    if 0x006A in uni_owner:
        dtls_pairs.append((uni_owner[0x006A], upright_dotless_j))
    if bold_it_latin.get('i') and bold_dotless_i:
        dtls_pairs.append((bold_it_latin['i'], bold_dotless_i))
    if bold_it_latin.get('j') and bold_dotless_j:
        dtls_pairs.append((bold_it_latin['j'], bold_dotless_j))
    if dtls_pairs:
        out.addLookup(
            'dtls',
            'gsub_single',
            (),
            (
                (
                    'dtls',
                    (
                        ('DFLT', ('dflt',)),
                        ('latn', ('dflt',)),
                        ('math', ('dflt',)),
                    ),
                ),
            ),
        )
        out.addLookupSubtable('dtls', 'dtls-1')
        for base, sub in dtls_pairs:
            out[base].addPosSub('dtls-1', sub)

    # Calligraphic salt maps Script to Curly.
    curly_pairs = []
    for slot, (u, name) in U.alpha_map('curly').items():
        key = ('curly', slot)
        if key in imported and ('script', slot) in imported:
            curly_pairs.append((imported[('script', slot)], imported[key]))
    # Keep varnothing in cv02 so calligraphic salt cannot change it.
    if curly_pairs:
        out.addLookup(
            'salt',
            'gsub_alternate',
            (),
            (
                (
                    'salt',
                    (
                        ('DFLT', ('dflt',)),
                        ('latn', ('dflt',)),
                        ('math', ('dflt',)),
                    ),
                ),
            ),
        )
        out.addLookupSubtable('salt', 'salt-1')
        for base, alt in curly_pairs:
            try:
                out[base].addPosSub('salt-1', (alt,))
            except Exception as exc:
                raise ValueError(f'salt glyph {base}: {exc}') from exc

    # Expose alternate codepoints for the same glyph.
    for base_u, extra_u in [
        (0x007C, 0x2223),
        (0x2016, 0x2225),
        (0x1D715, 0x2202),
    ]:
        if base_u in uni_owner and extra_u not in uni_owner:
            g = out[uni_owner[base_u]]
            g.altuni = (g.altuni or ()) + ((extra_u, -1, 0),)
            uni_owner[extra_u] = g.glyphname

    # After all alphabet imports, hmtx keeps CHARWD, MATH keeps CHARIC,
    # and ordinary GPOS stores the TFM pair kern alone.
    # Exclude family skewchar-right pairs from ordinary kerning.

    # cv01: swash z.
    zalt_pairs = []
    if ('mit', 180) in imported and 0x1D467 in uni_owner:
        zalt_pairs.append((uni_owner[0x1D467], imported[('mit', 180)]))
        for lvl, t in ((1, 'mit_s'), (2, 'mit_ss')):
            if t in fonts and 180 in fonts[t][1].chars:
                alt = import_glyph(t, 180, name=f'z.alt.ssty{lvl}')
                basek = (t, 0x7A)
                if alt and basek in imported:
                    zalt_pairs.append((imported[basek], alt))
    # cv03..cv07: blackboard and holey alphabet options.
    for cvn, tag in (
        ('cv03', 'bbd'),
        ('cv04', 'bbi'),
        ('cv05', 'hrb'),
        ('cv06', 'hrbd'),
        ('cv07', 'hbi'),
    ):
        if tag not in fonts:
            continue
        pairs = []
        for slot, (u, nm) in U.alpha_map('bb').items():
            alt = import_glyph(tag, slot, name=f'{nm}.{tag}')
            if alt and u in uni_owner:
                base = uni_owner[u]
                pairs.append((base, alt))
                # Add script-form pairs for either shaping order: ssty
                # then cv, or cv then ssty.
                for lvl in (1, 2):
                    bb, aa = f'{base}.ssty{lvl}', f'{alt}.ssty{lvl}'
                    if bb in out and aa in out:
                        pairs.append((bb, aa))
        if not pairs:
            continue
        out.addLookup(
            cvn,
            'gsub_single',
            (),
            (
                (
                    cvn,
                    (
                        ('DFLT', ('dflt',)),
                        ('latn', ('dflt',)),
                        ('math', ('dflt',)),
                    ),
                ),
            ),
        )
        out.addLookupSubtable(cvn, cvn + '-1')
        for base, alt in pairs:
            try:
                out[base].addPosSub(cvn + '-1', alt)
            except Exception as exc:
                raise ValueError(f'{cvn} glyph {base}: {exc}') from exc

    # cv02: slashed-zero and circular empty-set forms.
    if ('ams', 191) in imported and 0x2205 in uni_owner:
        out.addLookup(
            'cv02',
            'gsub_single',
            (),
            (
                (
                    'cv02',
                    (
                        ('DFLT', ('dflt',)),
                        ('latn', ('dflt',)),
                        ('math', ('dflt',)),
                    ),
                ),
            ),
        )
        out.addLookupSubtable('cv02', 'cv02-1')
        try:
            out[uni_owner[0x2205]].addPosSub('cv02-1', imported[('ams', 191)])
        except Exception as exc:
            raise ValueError(f'cv02 glyph {uni_owner[0x2205]}: {exc}') from exc

    if zalt_pairs:
        out.addLookup(
            'cv01',
            'gsub_single',
            (),
            (
                (
                    'cv01',
                    (
                        ('DFLT', ('dflt',)),
                        ('latn', ('dflt',)),
                        ('math', ('dflt',)),
                    ),
                ),
            ),
        )
        out.addLookupSubtable('cv01', 'cv01-1')
        for base, alt in zalt_pairs:
            try:
                out[base].addPosSub('cv01-1', alt)
            except Exception as exc:
                raise ValueError(f'cv01 glyph {base}: {exc}') from exc

    def with_ssty(pairs):
        """Extend substitution pairs with matching optical script forms.
        """
        res = []
        for b, a in pairs:
            if not b or not a:
                continue
            res.append((b, a))
            for lvl in (1, 2):
                bb, aa = f'{b}.ssty{lvl}', f'{a}.ssty{lvl}'
                if bb in out and aa in out:
                    res.append((bb, aa))
        return res

    def add_cv(tag, pairs):
        """Register a single-substitution character-variant feature."""
        pairs = [(b, a) for b, a in with_ssty(pairs) if b in out and a in out]
        if not pairs:
            return
        out.addLookup(
            tag,
            'gsub_single',
            (),
            (
                (
                    tag,
                    (
                        ('DFLT', ('dflt',)),
                        ('latn', ('dflt',)),
                        ('math', ('dflt',)),
                    ),
                ),
            ),
        )
        out.addLookupSubtable(tag, tag + '-1')
        for base, alt in pairs:
            try:
                out[base].addPosSub(tag + '-1', alt)
            except Exception as exc:
                raise ValueError(f'{tag} glyph {base}: {exc}') from exc

    # cv08: straight braces.
    add_cv(
        'cv08',
        [
            (uni_owner.get(0x007B), 'braceleft.straight'),
            (uni_owner.get(0x007D), 'braceright.straight'),
        ],
    )

    # cv09: AMS negated relations; defaults retain MTPro2 forms.
    add_cv(
        'cv09',
        [
            (uni_owner.get(u), imported.get(('ams', slot)))
            for u, slot in ((0x2241, 156), (0x2288, 170), (0x2289, 171))
        ],
    )

    # cv10: variant subsetneq and supsetneq.
    add_cv(
        'cv10',
        [
            (uni_owner.get(u), imported.get(('ams', slot)))
            for u, slot in ((0x228A, 160), (0x228B, 161))
        ],
    )

    # cv11: hbar and hslash.
    add_cv('cv11', [(uni_owner.get(0x210F), imported.get(('syt', 175)))])

    # cv12: slanted large operators.
    add_cv(
        'cv12',
        [
            (uni_owner.get(u), imported.get(('exa', slot)))
            for u, slot in ((0x2211, 160), (0x220F, 162), (0x2210, 164))
        ],
    )


def sort_features(gs):
    old = list(gs.FeatureList.FeatureRecord)
    order = sorted(range(len(old)), key=lambda i: (old[i].FeatureTag, i))
    remap = {a: b for b, a in enumerate(order)}
    for sr in gs.ScriptList.ScriptRecord:
        for lang in [sr.Script.DefaultLangSys] + [
            r.LangSys for r in sr.Script.LangSysRecord
        ]:
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
    from fontTools.ttLib.tables import otTables as ot

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
        for lang in [sr.Script.DefaultLangSys] + [
            r.LangSys for r in sr.Script.LangSysRecord
        ]:
            if lang:
                lang.FeatureIndex.append(fi)
                lang.FeatureCount += 1
    sort_features(gs)


def fraktur_mapping(font):
    """Reuse ordinary Fraktur I/R through actual reachable ssty inputs.
    """
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
