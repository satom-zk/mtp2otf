"""Serialize original TFM kerns, excluding family skewchar-right pairs.
"""

import mapping


def install_source_kerns(sources):
    out, fonts, imported = sources.font, sources.faces, sources.imported
    SOURCE_SKEW = dict(sources.rules.skewchar_by_tag)
    # Serialize TFM pair kern without an added italic-correction term.
    out.addLookup(
        "kernL",
        "gpos_pair",
        (),
        (
            (
                "kern",
                (
                    ("DFLT", ("dflt",)),
                    ("latn", ("dflt",)),
                    ("math", ("dflt",)),
                ),
            ),
        ),
    )
    out.addLookupSubtable("kernL", "kern-1")
    _source_tfm_pairs = {}

    def _remember_source_tfm_pair(gl, gr, xadvance):
        key = (gl, gr)
        previous = _source_tfm_pairs.get(key)
        if previous is not None:
            if previous != xadvance:
                raise RuntimeError(
                    "conflicting source TFM kern %s/%s: %+d vs %+d"
                    % (gl, gr, previous, xadvance)
                )
            return
        _source_tfm_pairs[key] = xadvance
        out[gl].addPosSub("kern-1", gr, 0, 0, xadvance, 0, 0, 0, 0, 0)

    for _tag in tuple(SOURCE_SKEW):
        if _tag not in fonts:
            continue
        _tfm = fonts[_tag][1]
        _sk = SOURCE_SKEW[_tag]
        for (_l, _r), _v in sorted(_tfm.kerns.items()):
            if _sk is not None and _r == _sk:
                continue
            _gl = imported.get((_tag, _l))
            _gr = imported.get((_tag, _r))
            if not _gl or not _gr or _gl not in out or _gr not in out:
                continue
            _k = round((_v or 0.0) * 1000)
            if not _k:
                continue
            _remember_source_tfm_pair(_gl, _gr, int(_k))


def append_pairs(font, pairs):
    """Append an explicit source-derived pair lookup to the kern
    feature.
    """
    from fontTools.otlLib.builder import buildPairPosGlyphsSubtable
    from fontTools.ttLib.tables import otTables as ot

    if not pairs:
        return
    gp = font["GPOS"].table
    lookup = ot.Lookup()
    lookup.LookupType = 2
    lookup.LookupFlag = 0
    lookup.SubTable = [
        buildPairPosGlyphsSubtable(pairs, font.getReverseGlyphMap())
    ]
    lookup.SubTableCount = 1
    lookup.MarkFilteringSet = None
    index = len(gp.LookupList.Lookup)
    gp.LookupList.Lookup.append(lookup)
    gp.LookupList.LookupCount += 1
    kern = [r for r in gp.FeatureList.FeatureRecord if r.FeatureTag == "kern"]
    if len(kern) != 1:
        raise ValueError("one kern feature required")
    kern[0].Feature.LookupListIndex.append(index)
    kern[0].Feature.LookupCount += 1


def install_alphabet_kerns(font, catalog, sourceglyph, spec):
    """Serialize source swash pairs, independently of
    generation/reporting.
    """
    from fontTools.ttLib.tables.otBase import ValueRecord
    from math_metrics import kern_advance

    pairs, rows = {}, []
    for role, cp, ordinary, swash in spec["swash"]:
        if role != "bmit":
            continue
        for suffix in mapping.ALPHABET_SUFFIX:
            tag = role + suffix
            skew = catalog.declarations.skewchar_by_tag[tag]
            for (left, right), fix in catalog.faces[tag].kerns().items():
                if swash not in (left, right) or right == skew:
                    continue
                if (tag, left) not in sourceglyph or (
                    tag,
                    right,
                ) not in sourceglyph:
                    continue
                value = kern_advance(fix)
                if not value:
                    continue
                a, b = sourceglyph[tag, left], sourceglyph[tag, right]
                val = ValueRecord()
                val.XAdvance = value
                pairs[a, b] = (val, None)
                rows.append(
                    dict(
                        role=tag,
                        left_slot=left,
                        right_slot=right,
                        left_glyph=a,
                        right_glyph=b,
                        xadvance=value,
                        source_fix20=fix,
                    )
                )
    if catalog.edition == "full":
        append_pairs(font, pairs)
    return rows
