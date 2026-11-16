"""Native and serialized GSUB routes with shared lookup-reference
management.
"""

import mapping as U


def with_ssty(pairs, glyphs):
    """Extend substitution pairs with existing matching optical forms.
    """
    res = []
    for base, alt in pairs:
        if not base or not alt:
            continue
        res.append((base, alt))
        for level in (1, 2):
            b, a = f"{base}.ssty{level}", f"{alt}.ssty{level}"
            if b in glyphs and a in glyphs:
                res.append((b, a))
    return res


def lang_systems(gs):
    for record in gs.ScriptList.ScriptRecord:
        if record.Script.DefaultLangSys is not None:
            yield record.Script.DefaultLangSys
        for lang in record.Script.LangSysRecord:
            yield lang.LangSys


def ssty_index(gs):
    features = [
        r for r in gs.FeatureList.FeatureRecord if r.FeatureTag == "ssty"
    ]
    if len(features) != 1 or len(features[0].Feature.LookupListIndex) != 1:
        raise ValueError("expected one ssty feature with one lookup")
    index = features[0].Feature.LookupListIndex[0]
    if not 0 <= index < len(gs.LookupList.Lookup):
        raise ValueError("ssty lookup index out of range")
    lookup = gs.LookupList.Lookup[index]
    if (
        lookup.LookupType != 3
        or len(lookup.SubTable) != 1
        or (not hasattr(lookup.SubTable[0], "alternates"))
    ):
        raise ValueError(
            "unsupported ssty structure (requires one AlternateSubst subtable)"
        )
    if lookup.LookupFlag != 0:
        raise ValueError("unsupported ssty lookup flags")
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
    elif hasattr(node, "__dict__"):
        children = vars(node).values()
    else:
        raise ValueError("unknown GSUB object: " + type(node).__name__)
    for child in children:
        yield from references(child, seen)


def validate_gsub(gs):
    if getattr(gs, "FeatureVariations", None) is not None:
        raise ValueError(
            "FeatureVariations are not supported"
        )
    if gs.Version != 65536:
        raise ValueError("unsupported GSUB version")
    n = len(gs.LookupList.Lookup)
    if gs.LookupList.LookupCount != n or gs.FeatureList.FeatureCount != len(
        gs.FeatureList.FeatureRecord
    ):
        raise ValueError("GSUB count mismatch")
    for lookup in gs.LookupList.Lookup:
        if lookup.LookupType not in range(1, 9) or lookup.SubTableCount != len(
            lookup.SubTable
        ):
            raise ValueError("unsupported GSUB lookup type/count")
        if lookup.LookupType == 7:
            for sub in lookup.SubTable:
                if (
                    sub.ExtensionLookupType not in (1, 2, 3, 4, 5, 6, 8)
                    or sub.ExtSubTable is None
                ):
                    raise ValueError("unsupported GSUB extension structure")
    for feature in gs.FeatureList.FeatureRecord:
        if feature.Feature.LookupCount != len(
            feature.Feature.LookupListIndex
        ) or any((not 0 <= i < n for i in feature.Feature.LookupListIndex)):
            raise ValueError("feature lookup reference out of range")
    for record in references(gs):
        if not 0 <= record.LookupListIndex < n:
            raise ValueError("context lookup reference out of range")
    nf = len(gs.FeatureList.FeatureRecord)
    for lang in lang_systems(gs):
        if lang.FeatureCount != len(lang.FeatureIndex) or any(
            (not 0 <= i < nf for i in lang.FeatureIndex)
        ):
            raise ValueError("LangSys feature reference out of range")
        if lang.ReqFeatureIndex != 65535 and (
            not 0 <= lang.ReqFeatureIndex < nf
        ):
            raise ValueError("required feature reference out of range")


def remap_lookups(gs, mapping):
    for feature in gs.FeatureList.FeatureRecord:
        feature.Feature.LookupListIndex = [
            mapping[i] for i in feature.Feature.LookupListIndex
        ]
    for record in references(gs):
        record.LookupListIndex = mapping[record.LookupListIndex]


def insert_routes(font, rows, index, tag):
    from fontTools.ttLib.tables import otTables as ot

    gs = font["GSUB"].table
    lookup_map = {
        i: i if i < index else i + 1 for i in range(len(gs.LookupList.Lookup))
    }
    remap_lookups(gs, lookup_map)
    grouped = {
        cp: {
            r["style"]: r["output_glyph"]
            for r in rows
            if r["Unicode_input"] == cp
        }
        for cp in sorted({r["Unicode_input"] for r in rows})
    }
    mapping = {font.getBestCmap()[cp]: v["T"] for cp, v in grouped.items()}
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
    new_ssty = {v["T"]: [v["S"], v["SS"]] for v in grouped.values()}
    if set(new_ssty) & set(oldssty):
        raise ValueError("mbf ssty collision")
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
        "inserted_lookup_index": index,
        "old_to_new_lookup_index": lookup_map,
        "old_to_new_feature_index": {
            i: feature_map[i] for i in range(len(old_features))
        },
        tag + "_feature_index": new_fi,
        tag + "_mapping": mapping,
        "ssty_added": new_ssty,
    }


def ssty_mapping(font):
    gs = font["GSUB"].table
    features = [
        i
        for i, r in enumerate(gs.FeatureList.FeatureRecord)
        if r.FeatureTag == "ssty"
    ]
    if len(features) != 1:
        raise ValueError("one actual ssty feature required")
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
        raise ValueError("ssty feature unreachable from ScriptList")
    indices = gs.FeatureList.FeatureRecord[
        feature_index
    ].Feature.LookupListIndex
    if len(indices) != 1:
        raise ValueError("one actual ssty lookup required")
    lk = gs.LookupList.Lookup[indices[0]]
    if lk.LookupType != 3 or len(lk.SubTable) != 1:
        raise ValueError("unsupported actual ssty lookup")
    return lk.SubTable[0].alternates


def install_optical_routes(sources, ssty_map, alphabet):
    bold_dotless_i = alphabet.bold_dotless_i
    bold_dotless_j = alphabet.bold_dotless_j
    bold_it_latin = alphabet.bold_italic
    imported = sources.imported
    out = sources.font
    uni_owner = sources.uni_owner
    upright_dotless = alphabet.upright_dotless_i
    upright_dotless_j = alphabet.upright_dotless_j
    if ssty_map:
        out.addLookup(
            "ssty",
            "gsub_alternate",
            (),
            (
                (
                    "ssty",
                    (
                        ("DFLT", ("dflt",)),
                        ("latn", ("dflt",)),
                        ("math", ("dflt",)),
                    ),
                ),
            ),
        )
        out.addLookupSubtable("ssty", "ssty-1")
        for base, alts in ssty_map.items():
            try:
                out[base].addPosSub("ssty-1", tuple(alts))
            except Exception as exc:
                raise ValueError(f"ssty glyph {base}: {exc}") from exc

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
    if bold_it_latin.get("i") and bold_dotless_i:
        dtls_pairs.append((bold_it_latin["i"], bold_dotless_i))
    if bold_it_latin.get("j") and bold_dotless_j:
        dtls_pairs.append((bold_it_latin["j"], bold_dotless_j))
    if dtls_pairs:
        out.addLookup(
            "dtls",
            "gsub_single",
            (),
            (
                (
                    "dtls",
                    (
                        ("DFLT", ("dflt",)),
                        ("latn", ("dflt",)),
                        ("math", ("dflt",)),
                    ),
                ),
            ),
        )
        out.addLookupSubtable("dtls", "dtls-1")
        for base, sub in dtls_pairs:
            out[base].addPosSub("dtls-1", sub)

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
    # and ordinary GPOS stores the TFM pair kern alone. Exclude family
    # skewchar-right pairs from ordinary kerning.

    # cv17: slashed-zero and circular empty-set forms.
    if ("ams", 191) in imported and 0x2205 in uni_owner:
        out.addLookup(
            "cv17",
            "gsub_single",
            (),
            (
                (
                    "cv17",
                    (
                        ("DFLT", ("dflt",)),
                        ("latn", ("dflt",)),
                        ("math", ("dflt",)),
                    ),
                ),
            ),
        )
        out.addLookupSubtable("cv17", "cv17-1")
        for base, alt in with_ssty(
            [(uni_owner[0x2205], imported[("ams", 191)])], out
        ):
            try:
                out[base].addPosSub("cv17-1", alt)
            except Exception as exc:
                raise ValueError(f"cv17 glyph {base}: {exc}") from exc

    def add_cv(tag, pairs):
        """Register a single-substitution character-variant feature."""
        pairs = [
            (b, a) for b, a in with_ssty(pairs, out) if b in out and a in out
        ]
        if not pairs:
            return
        out.addLookup(
            tag,
            "gsub_single",
            (),
            (
                (
                    tag,
                    (
                        ("DFLT", ("dflt",)),
                        ("latn", ("dflt",)),
                        ("math", ("dflt",)),
                    ),
                ),
            ),
        )
        out.addLookupSubtable(tag, tag + "-1")
        for base, alt in pairs:
            try:
                out[base].addPosSub(tag + "-1", alt)
            except Exception as exc:
                raise ValueError(f"{tag} glyph {base}: {exc}") from exc

    # cv06: straight braces.
    add_cv(
        "cv06",
        [
            (uni_owner.get(0x007B), "braceleft.straight"),
            (uni_owner.get(0x007D), "braceright.straight"),
        ],
    )

    # cv14: AMS negated relations; defaults retain MTPro2 forms.
    add_cv(
        "cv14",
        [
            (uni_owner.get(u), imported.get(("ams", slot)))
            for u, slot in ((0x2241, 156),)
        ],
    )

    # cv10: variant subsetneq and supsetneq.
    add_cv(
        "cv10",
        [
            (uni_owner.get(u), imported.get(("ams", slot)))
            for u, slot in ((0x228A, 160), (0x228B, 161))
        ],
    )

    # cv04: hbar and hslash.
    add_cv("cv04", [(uni_owner.get(0x210F), imported.get(("syt", 175)))])

    # ss07: slanted large operators.
    suffixes = U.OPERATOR_SUFFIXES if sources.condition == "source" else ("",)
    operator_pairs = [
        (base + suffix, alt + suffix)
        for u, slot in ((0x2211, 160), (0x220F, 162), (0x2210, 164))
        for base, alt in [(uni_owner[u], imported[("exa", slot)])]
        for suffix in suffixes
    ]
    if (len(set(operator_pairs)) != 3 * len(suffixes)
            or any(a not in out or b not in out for a, b in operator_pairs)):
        raise ValueError("incomplete ss07 six-stage operator coverage")
    add_cv("ss07", operator_pairs)


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
    if getattr(gs, "FeatureVariations", None):
        for rec in gs.FeatureVariations.FeatureVariationRecord:
            for sub in rec.FeatureTableSubstitution.SubstitutionRecord:
                sub.FeatureIndex = remap[sub.FeatureIndex]
    gs.FeatureList.FeatureRecord = [old[i] for i in order]


def feature(font, tag, mapping):
    from fontTools.ttLib.tables import otTables as ot

    gs = font["GSUB"].table
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


def alternate_feature(font, tag, choices):
    """Install an ordered final choice list without provisional
    features.
    """
    from fontTools.ttLib.tables import otTables as ot

    feature(font, tag, {})
    gs = font["GSUB"].table
    record = next(
        r for r in gs.FeatureList.FeatureRecord if r.FeatureTag == tag
    )
    lookup = gs.LookupList.Lookup[record.Feature.LookupListIndex[0]]
    lookup.LookupType = 3
    sub = ot.AlternateSubst()
    sub.alternates = {a: list(bs) for a, bs in choices.items()}
    lookup.SubTable = [sub]
    validate_gsub(gs)


def selector_mapping(lookup, parameters):
    """Read disjoint simple subtables without changing lookup semantics.
    """
    kind = 3 if parameters else 1
    if lookup.LookupType != kind or lookup.LookupFlag != 0:
        raise ValueError("unsupported selector lookup type/flags")
    mapping = {}
    for sub in lookup.SubTable:
        entries = sub.alternates if parameters else sub.mapping
        if mapping.keys() & entries.keys():
            raise ValueError("overlapping selector subtables")
        if parameters and any(len(v) != parameters for v in entries.values()):
            raise ValueError("selector alternate count differs")
        mapping.update(entries)
    if not mapping:
        raise ValueError("empty selector lookup")
    return mapping


def selector_metadata(font, spec, stylistic):
    from fontTools.ttLib.tables import otTables as ot

    name = font["name"]
    characters = sorted(
        cp for cp in spec["characters"] if cp in font.getBestCmap())
    values = [spec["label"]]
    if not stylistic:
        if not characters:
            raise ValueError("character variant has no UI sample characters")
        values += [spec["tooltip"],
                   "".join(map(chr, characters)), *spec["parameters"]]
    start = max(255, *(n.nameID for n in name.names)) + 1
    if start + len(values) - 1 > 32767:
        raise ValueError("feature name ID space exhausted")
    for offset, value in enumerate(values):
        name.setName(value, start + offset, 3, 1, 0x409)
    if stylistic:
        params = ot.FeatureParamsStylisticSet()
        params.Version = 0
        params.UINameID = start
    else:
        params = ot.FeatureParamsCharacterVariants()
        params.Format = 0
        params.FeatUILabelNameID = start
        params.FeatUITooltipTextNameID = start + 1
        params.SampleTextNameID = start + 2
        params.NumNamedParameters = len(spec["parameters"])
        params.FirstParamUILabelNameID = start + 3 if spec["parameters"] else 0
        params.Character = characters
        params.CharCount = len(characters)
    return params


def finish(font, edition):
    """Order final public lookups and attach their UI metadata."""
    gs = font["GSUB"].table
    validate_gsub(gs)
    specs = U.public_selectors(edition)
    records = gs.FeatureList.FeatureRecord
    by_tag = {r.FeatureTag: r for r in records}
    if (len(by_tag) != len(records)
            or set(by_tag) - {"dtls", "ssty", "ccmp"} != set(specs)):
        raise ValueError("final selector inventory differs")
    tags = [tag for tag in U.SUBSTITUTION_ORDER if tag in by_tag]
    order = []
    for tag in tags:
        indices = by_tag[tag].Feature.LookupListIndex
        if len(indices) != 1:
            raise ValueError("one final lookup expected: " + tag)
        order.extend(indices)
    if len(set(order)) != len(order):
        raise ValueError("unexpected shared final lookup")
    lookups = gs.LookupList.Lookup
    if any(True for i in order for _ in references(lookups[i])):
        raise ValueError("contextual lookup requires an explicit order rule")
    for tag in tags:
        if tag in specs:
            spec = specs[tag]
            record = by_tag[tag].Feature
            selector_mapping(lookups[record.LookupListIndex[0]],
                             len(spec["parameters"]))
            record.FeatureParams = selector_metadata(
                font, spec, tag.startswith("ss")
            )
    remap_lookups(gs, {old: new for new, old in enumerate(order)})
    gs.LookupList.Lookup = [lookups[i] for i in order]
    gs.LookupList.LookupCount = len(order)
    sort_features(gs)
    return dict(features=sorted(by_tag), lookup_order=tags)


def install_maps(font, maps, new_tags=()):
    from fontTools.ttLib.tables import otTables as ot

    gs = font["GSUB"].table
    validate_gsub(gs)
    by_tag = {r.FeatureTag: r for r in gs.FeatureList.FeatureRecord}
    if set(new_tags) & set(by_tag):
        raise ValueError("new relation CV already installed")
    # Extend native proper-inclusion routes with their optical forms.
    if "cv10" in maps:
        rec = by_tag["cv10"]
        if len(rec.Feature.LookupListIndex) != 1:
            raise ValueError("unsupported cv10 structure")
        st = gs.LookupList.Lookup[rec.Feature.LookupListIndex[0]].SubTable[0]
        for a, b in maps["cv10"].items():
            if a in st.mapping and st.mapping[a] != b:
                raise ValueError("cv10 prior route changed")
            st.mapping[a] = b
    tags = [tag for tag in new_tags if maps.get(tag)]
    shift = len(tags)
    remap_lookups(gs, {i: i + shift for i in range(len(gs.LookupList.Lookup))})
    new_lookups, new_records = [], []
    old_records = list(gs.FeatureList.FeatureRecord)
    for i, tag in enumerate(tags):
        st = ot.SingleSubst()
        st.mapping = maps[tag]
        lookup = ot.Lookup()
        lookup.LookupType = 1
        lookup.LookupFlag = 0
        lookup.SubTable = [st]
        lookup.SubTableCount = 1
        lookup.MarkFilteringSet = None
        new_lookups.append(lookup)
        rec = ot.FeatureRecord()
        rec.FeatureTag = tag
        rec.Feature = ot.Feature()
        rec.Feature.FeatureParams = None
        rec.Feature.LookupListIndex = [i]
        rec.Feature.LookupCount = 1
        new_records.append(rec)
    gs.LookupList.Lookup = new_lookups + gs.LookupList.Lookup
    gs.LookupList.LookupCount = len(gs.LookupList.Lookup)
    records = old_records + new_records
    order = sorted(range(len(records)), key=lambda i: records[i].FeatureTag)
    feature_map = {old: new for new, old in enumerate(order)}
    for lang in lang_systems(gs):
        lang.FeatureIndex = sorted(
            [feature_map[i] for i in lang.FeatureIndex]
            + [feature_map[i] for i in range(len(old_records), len(records))]
        )
        lang.FeatureCount = len(lang.FeatureIndex)
        if lang.ReqFeatureIndex != 65535:
            lang.ReqFeatureIndex = feature_map[lang.ReqFeatureIndex]
    gs.FeatureList.FeatureRecord = [records[i] for i in order]
    gs.FeatureList.FeatureCount = len(records)
    validate_gsub(gs)


def install_logical_and(font):
    """Select existing logical-and alternatives, including size-grown
    input.

    Map all six matching large stages, plus the three small optical
    forms, so either selection order works.
    """
    c = font.getBestCmap()
    ss = ssty_mapping(font)
    small = [c[0x2227], *ss[c[0x2227]]]
    alternate = ["varland", *ss["varland"]]
    m = font["MATH"].table.MathVariants
    constructions = dict(
        zip(m.VertGlyphCoverage.glyphs, m.VertGlyphConstruction)
    )
    base = constructions[c[0x22C0]]
    target = constructions["varland.big"]
    old_large = [r.VariantGlyph for r in base.MathGlyphVariantRecord]
    new_large = [r.VariantGlyph for r in target.MathGlyphVariantRecord]
    if old_large != [c[0x22C0] + s for s in U.OPERATOR_SUFFIXES]:
        raise ValueError("unexpected standard bigwedge construction")
    if new_large != ["varland.big" + s for s in U.OPERATOR_SUFFIXES]:
        raise ValueError("unexpected alternate bigwedge construction")
    if base.GlyphAssembly or target.GlyphAssembly:
        raise ValueError("unexpected bigwedge assembly")
    mapping = dict(zip(small + old_large, alternate + new_large))
    if len(mapping) != 9:
        raise ValueError("incomplete conjunction input coverage")
    install_maps(font, {"cv05": mapping}, new_tags=("cv05",))
    return dict(
        tag="cv05",
        mapping=mapping,
        base_large_source_slots=[86, 94],
        alternate_large_source_slots=[166, 167],
        MATH_constructions_changed=False,
        GPOS_changed=False,
        new_glyphs=0,
        physical_deletion=False,
    )


def install_negative_choices(font, edition):
    if edition == "lite":
        return dict(
            edition=edition,
            routes=[],
            removed=[],
            removed_cmap={},
            physical_deletion=False,
        )
    if edition != "full":
        raise ValueError("unknown edition")
    cmap = font.getBestCmap()
    ss = ssty_mapping(font)
    choices = {}
    routes = []
    for tag, cp, first, second in U.NEGATIVE_CHOICES:
        forms = [cmap[cp], *ss[cmap[cp]]]
        left = [first, *ss[first]]
        right = [second, *ss[second]]
        for level, (a, b, c) in enumerate(zip(forms, left, right)):
            choices.setdefault(tag, {})[a] = [b, c]
            routes.append(
                dict(
                    tag=tag,
                    Unicode=f"U+{cp:04X}",
                    level=level,
                    input=a,
                    choices=[b, c],
                )
            )
    for tag, entries in choices.items():
        alternate_feature(font, tag, entries)
    return dict(
        edition=edition,
        routes=routes,
        choice_order="slanted/AMS first; double relation second",
    )


def install_alphabet_routes(font, maps, ss):
    from fontTools.ttLib.tables import otTables as ot

    gs = font["GSUB"].table
    replaced = set(maps) | {"ssty"}
    keep = [
        r for r in gs.FeatureList.FeatureRecord if r.FeatureTag not in replaced
    ]
    newlook = []
    newrecords = []
    for tag, entries in [*maps.items(), ("ssty", ss)]:
        if not entries:
            continue
        lookup = ot.Lookup()
        lookup.LookupType = 3 if tag == "ssty" else 1
        lookup.LookupFlag = 0
        lookup.SubTableCount = 1
        st = ot.AlternateSubst() if tag == "ssty" else ot.SingleSubst()
        if tag == "ssty":
            st.alternates = {k: list(v) for k, v in entries.items()}
        else:
            st.mapping = entries
        lookup.SubTable = [st]
        lookup.MarkFilteringSet = None
        newlook.append(lookup)
        rec = ot.FeatureRecord()
        rec.FeatureTag = tag
        rec.Feature = ot.Feature()
        rec.Feature.FeatureParams = None
        rec.Feature.LookupListIndex = [len(newlook) - 1]
        rec.Feature.LookupCount = 1
        newrecords.append(rec)
    shift = len(newlook)
    for rec in keep:
        rec.Feature.LookupListIndex = [
            n + shift for n in rec.Feature.LookupListIndex
        ]
    for rec in references(gs.LookupList):
        rec.LookupListIndex += shift
    gs.LookupList.Lookup = newlook + gs.LookupList.Lookup
    gs.LookupList.LookupCount = len(gs.LookupList.Lookup)
    gs.FeatureList.FeatureRecord = sorted(
        keep + newrecords, key=lambda r: r.FeatureTag
    )
    gs.FeatureList.FeatureCount = len(gs.FeatureList.FeatureRecord)
    for lang in lang_systems(gs):
        lang.ReqFeatureIndex = 65535
        lang.FeatureIndex = list(range(gs.FeatureList.FeatureCount))
        lang.FeatureCount = len(lang.FeatureIndex)
