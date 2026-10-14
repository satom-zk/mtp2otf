"""Shared GSUB route manipulation used by the append producers."""
from fontTools.ttLib.tables import otTables as ot


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
    """Walk otTables, including Context/ChainContext/Extension descendants."""
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
    if (
        gs.LookupList.LookupCount != n
        or gs.FeatureList.FeatureCount != len(gs.FeatureList.FeatureRecord)
    ):
        raise ValueError('GSUB count mismatch')
    for lookup in gs.LookupList.Lookup:
        if (
            lookup.LookupType not in range(1, 9)
            or lookup.SubTableCount != len(lookup.SubTable)
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
        if (
            feature.Feature.LookupCount != len(feature.Feature.LookupListIndex)
            or any((not 0 <= i < n for i in feature.Feature.LookupListIndex))
        ):
            raise ValueError('feature lookup reference out of range')
    for record in references(gs):
        if not 0 <= record.LookupListIndex < n:
            raise ValueError('context lookup reference out of range')
    nf = len(gs.FeatureList.FeatureRecord)
    for lang in lang_systems(gs):
        if (
            lang.FeatureCount != len(lang.FeatureIndex)
            or any((not 0 <= i < nf for i in lang.FeatureIndex))
        ):
            raise ValueError('LangSys feature reference out of range')
        if (
            lang.ReqFeatureIndex != 65535
            and (not 0 <= lang.ReqFeatureIndex < nf)
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
    gs = font['GSUB'].table
    lookup_map = {
        i: i if i < index else i + 1 for i in range(len(gs.LookupList.Lookup))
    }
    remap_lookups(gs, lookup_map)
    grouped = {
        cp: {
            r['style']: r['output_glyph'] for r in rows
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
        'inserted_lookup_index': index, 'old_to_new_lookup_index': lookup_map,
        'old_to_new_feature_index': {
            i: feature_map[i] for i in range(len(old_features))
        },
        tag + '_feature_index': new_fi, tag + '_mapping': mapping,
        'ssty_added': new_ssty
    }


def ssty_mapping(font):
    gs = font['GSUB'].table
    features = [
        i for i, r in enumerate(gs.FeatureList.FeatureRecord)
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
    indices = (
        gs.FeatureList.FeatureRecord[feature_index].Feature.LookupListIndex
    )
    if len(indices) != 1:
        raise ValueError('one actual ssty lookup required')
    lk = gs.LookupList.Lookup[indices[0]]
    if lk.LookupType != 3 or len(lk.SubTable) != 1:
        raise ValueError('unsupported actual ssty lookup')
    return lk.SubTable[0].alternates
