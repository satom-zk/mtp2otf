"""Store final MATH values and source-measured constructions."""

import copy

import mapping as U
import substitution
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib.tables import otTables as ot


def copy_math_attributes(font, source, clone):
    gi = font["MATH"].table.MathGlyphInfo
    state = {}
    for attr, covfield, valuesfield, countfield in (
        (
            "MathItalicsCorrectionInfo",
            "Coverage",
            "ItalicsCorrection",
            "ItalicsCorrectionCount",
        ),
        (
            "MathTopAccentAttachment",
            "TopAccentCoverage",
            "TopAccentAttachment",
            "TopAccentAttachmentCount",
        ),
        (
            "MathKernInfo",
            "MathKernCoverage",
            "MathKernInfoRecords",
            "MathKernCount",
        ),
    ):
        table = getattr(gi, attr, None)
        cov = getattr(table, covfield, None) if table else None
        present = bool(cov and source in cov.glyphs)
        state[attr] = present
        if present:
            old = getattr(table, valuesfield)[cov.glyphs.index(source)]
            cov.glyphs.append(clone)
            getattr(table, valuesfield).append(copy.deepcopy(old))
            setattr(table, countfield, len(cov.glyphs))
            pairs = sorted(
                zip(cov.glyphs, getattr(table, valuesfield)),
                key=lambda pair: font.getGlyphID(pair[0]),
            )
            cov.glyphs = [name for name, _ in pairs]
            setattr(table, valuesfield, [value for _, value in pairs])
    ext = gi.ExtendedShapeCoverage
    present = bool(ext and source in ext.glyphs)
    state["ExtendedShapeCoverage"] = present
    if present:
        ext.glyphs.append(clone)
        ext.glyphs.sort(key=font.getGlyphID)
    gdef = font["GDEF"].table
    for attr in ("GlyphClassDef", "MarkAttachClassDef"):
        table = getattr(gdef, attr, None)
        classes = table.classDefs if table else {}
        state["GDEF." + attr] = classes.get(source)
        if source in classes:
            classes[clone] = classes[source]
    for attr, covfield, valfield, countfield in (
        ("AttachList", "Coverage", "AttachPoint", "GlyphCount"),
        ("LigCaretList", "Coverage", "LigGlyph", "LigGlyphCount"),
    ):
        table = getattr(gdef, attr, None)
        cov = getattr(table, covfield, None) if table else None
        present = bool(cov and source in cov.glyphs)
        state["GDEF." + attr] = present
        if present:
            value = getattr(table, valfield)[cov.glyphs.index(source)]
            cov.glyphs.append(clone)
            getattr(table, valfield).append(copy.deepcopy(value))
            setattr(table, countfield, len(cov.glyphs))
            pairs = sorted(
                zip(cov.glyphs, getattr(table, valfield)),
                key=lambda pair: font.getGlyphID(pair[0]),
            )
            cov.glyphs = [name for name, _ in pairs]
            setattr(table, valfield, [value for _, value in pairs])
    return state


def finalize_measured_growth(font):
    """Apply the approved source-reachable sets without changing any AM.
    """
    M = font["MATH"].table.MathVariants
    cmap = font.getBestCmap()
    cp_by_root = {}
    for cp, n in sorted(cmap.items()):
        if not 0xE000 <= cp <= 0xF8FF:
            cp_by_root.setdefault(n, cp)
    records = []
    for direction in ["Vert", "Horiz"]:
        cov = getattr(M, direction + "GlyphCoverage").glyphs
        cons = getattr(M, direction + "GlyphConstruction")
        for root, c in zip(cov, cons):
            cp = cp_by_root.get(root)
            if direction != "Horiz" or cp not in U.NORMAL_HORIZONTAL:
                continue
            old = list(c.MathGlyphVariantRecord)
            kept = list(old)
            collapsed = []
            if cp in U.NORMAL_HORIZONTAL:
                gs = font.getGlyphSet()
                ta = font["MATH"].table.MathGlyphInfo.MathTopAccentAttachment
                tac = dict(
                    zip(
                        ta.TopAccentCoverage.glyphs,
                        [x.Value for x in ta.TopAccentAttachment],
                    )
                )
                unique, seen = [], {}
                for v in kept:
                    n = v.VariantGlyph
                    p = DecomposingRecordingPen(gs)
                    gs[n].draw(p)
                    # Full absolute path, not only bounding box
                    # equality.
                    key = (
                        repr(p.value),
                        font["hmtx"][n],
                        tac.get(n),
                        v.AdvanceMeasurement,
                    )
                    if key in seen:
                        collapsed.append(dict(excluded=n, retained=seen[key]))
                    else:
                        seen[key] = n
                        unique.append(v)
                kept = unique
                expected = {0x302: 37, 0x303: 37, 0x30C: 35, 0x23DC: 24}[cp]
                if len(kept) != expected:
                    raise ValueError("C05 horizontal set differs")
            if not kept:
                raise ValueError("C05 empty normal ready-made series")
            c.MathGlyphVariantRecord = kept
            c.VariantCount = len(kept)
            records.append(
                dict(
                    direction=direction,
                    root=root,
                    Unicode=cp,
                    before=[
                        dict(glyph=v.VariantGlyph, AM=v.AdvanceMeasurement)
                        for v in old
                    ],
                    after=[
                        dict(glyph=v.VariantGlyph, AM=v.AdvanceMeasurement)
                        for v in kept
                    ],
                    excluded=[v.VariantGlyph for v in old if v not in kept],
                    collapsed=collapsed,
                    assembly_unchanged=True,
                )
            )
    return records


def install_brace_choices(font, inventory):
    """Bind ordinary/Plain/Curly roots directly to final cv24 choices.
    """
    imports = {(r["tag"], r["slot"]): r["glyph"] for r in inventory["imports"]}
    variants = font["MATH"].table.MathVariants
    constructions = dict(
        zip(
            variants.HorizGlyphCoverage.glyphs, variants.HorizGlyphConstruction
        )
    )
    choices = {}
    for cp, slot, label in ((0x23DE, 176, "over"), (0x23DF, 144, "under")):
        ordinary = f"uni{cp:04X}"
        curly = imports["exe", slot]
        source = constructions[curly]
        if font.getBestCmap()[cp] != curly or source.VariantCount != 35:
            raise ValueError("source curly brace root/series differs")
        if not source.GlyphAssembly or source.GlyphAssembly.PartCount != 5:
            raise ValueError("source curly brace assembly differs")
        constructions[ordinary].MathGlyphVariantRecord = []
        constructions[ordinary].VariantCount = 0
        for table in font["cmap"].tables:
            if table.isUnicode() and cp in table.cmap:
                table.cmap[cp] = ordinary
        choices[ordinary] = ["brace.plain." + label, curly]
    substitution.alternate_feature(font, "cv24", choices)
    return dict(choices=choices)


def install_vertical_choices(font):
    """Finish native series with optical roots and ordered CV entrances.
    """
    from font_geometry import clone_glyph

    variants = font["MATH"].table.MathVariants
    constructions = dict(
        zip(variants.VertGlyphCoverage.glyphs, variants.VertGlyphConstruction)
    )

    def entry_measurement(font, name):
        from math import ceil

        from fontTools.pens.boundsPen import BoundsPen

        gs = font.getGlyphSet()
        pen = BoundsPen(gs)
        gs[name].draw(pen)
        return ceil(pen.bounds[3] - pen.bounds[1]) + 1

    ss = substitution.ssty_mapping(font)
    maps = {"cv22": {}, "cv23": {}}
    cv21 = {}
    for root, choice in U.vertical_choices().items():
        base = f"uni{choice['cp']:04X}"
        copy_math_attributes(font, base, root)
        # Native geometry supplies AM, connectors and shared parts.
        # Optical
        # roots keep this selected series while using their source
        # entry.
        alts = []
        for level, source in enumerate(ss[base], 1):
            clone = clone_glyph(font, source, f"{root}.ssty{level}")
            alts.append(clone)
            constructions[clone] = copy.deepcopy(constructions[root])
            record = constructions[clone].MathGlyphVariantRecord[0]
            record.VariantGlyph = clone
            # Match the accepted native vertical AM rule: ceil(ink
            # height)+1.
            record.AdvanceMeasurement = entry_measurement(font, clone)
        ss[root] = alts
        for source, target in zip([base, *ss[base]], [root, *alts]):
            maps[choice["tag"]][source] = target
        if choice["cp"] in (123, 125):
            straight = (
                "braceleft" if choice["cp"] == 123 else "braceright"
            ) + ".straight"
            for source, target in zip(
                [root, *alts], [straight, *ss[straight]]
            ):
                cv21[source] = target
    # Bind ordinary and straight optical entries to their existing
    # native
    # constructions too. No path falls back to the ordinary series after
    # ssty.
    for base in (
        "uni0028",
        "uni0029",
        "uni007B",
        "uni007D",
        "braceleft.straight",
        "braceright.straight",
    ):
        for optical in ss[base]:
            constructions[optical] = copy.deepcopy(constructions[base])
            entry = constructions[optical].MathGlyphVariantRecord[0]
            entry.VariantGlyph = optical
            entry.AdvanceMeasurement = entry_measurement(font, optical)
    names = sorted(constructions, key=font.getGlyphID)
    variants.VertGlyphCoverage.glyphs = names
    variants.VertGlyphConstruction = [constructions[n] for n in names]
    variants.VertGlyphCount = len(names)
    substitution.install_maps(font, maps, new_tags=("cv22", "cv23"))
    gs = font["GSUB"].table
    rec = next(
        r for r in gs.FeatureList.FeatureRecord if r.FeatureTag == "cv21"
    )
    gs.LookupList.Lookup[rec.Feature.LookupListIndex[0]].SubTable[
        0
    ].mapping.update(cv21)
    return dict(
        choices=U.vertical_choices(), precedence="cv23 then cv21", new_PUA=0
    )


MATH_FIELDS = (
    (
        "MathItalicsCorrectionInfo",
        "Coverage",
        "ItalicsCorrection",
        "ItalicsCorrectionCount",
    ),
    (
        "MathTopAccentAttachment",
        "TopAccentCoverage",
        "TopAccentAttachment",
        "TopAccentAttachmentCount",
    ),
)


def math_add(font, name, ic, accent):
    gi = font["MATH"].table.MathGlyphInfo
    for value, (field, cov, array, count) in zip((ic, accent), MATH_FIELDS):
        table = getattr(gi, field)
        pairs = dict(zip(getattr(table, cov).glyphs, getattr(table, array)))
        if name in pairs:
            raise ValueError("MATH mbf identity collision")
        record = ot.MathValueRecord()
        record.Value = value
        record.DeviceTable = None
        pairs[name] = record
        names = sorted(pairs, key=font.getGlyphID)
        getattr(table, cov).glyphs = names
        setattr(table, array, [pairs[n] for n in names])
        setattr(table, count, len(names))


def metrics_values(f):
    gi = f["MATH"].table.MathGlyphInfo
    ans = []
    for field, cov, arr in [
        ("MathItalicsCorrectionInfo", "Coverage", "ItalicsCorrection"),
        (
            "MathTopAccentAttachment",
            "TopAccentCoverage",
            "TopAccentAttachment",
        ),
    ]:
        t = getattr(gi, field)
        ans.append(
            {
                n: v.Value
                for n, v in zip(getattr(t, cov).glyphs, getattr(t, arr))
            }
        )
    return ans
