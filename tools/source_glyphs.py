"""Post-normalization original glyphs and their public/optical routes.
All
source acquisition belongs to catalog/outlines/metrics, not this module.
"""

from collections import defaultdict
from copy import deepcopy

import declarations
import mapping as U
import metrics
import substitution
from config import identity as font_identity
from font_geometry import (
    _copy_shift,
    _set_charstring,
    aggregate_values,
    math_add,
    update_average_width,
)
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib.tables.otBase import ValueRecord
from mapping import bold_identities
from math_tables import copy_math_attributes
from positioning import append_pairs
from substitution import (
    insert_routes,
    ssty_index,
    ssty_mapping,
    validate_gsub,
)

AMS_SYMBOLS = ((10003, 88, "checkmark"), (10016, 122, "maltese"))


AMS_STYLES = (("T", "mt2syat"), ("S", "mt2syas"), ("SS", "mt2syaf"))


def add_ams_glyphs(f, sources):
    original = list(f.getGlyphOrder())
    if "CFF " not in f:
        raise ValueError("append requires CFF OTF")
    names = [
        label + ("" if i == 0 else ".ssty" + str(i))
        for _, _, label in AMS_SYMBOLS
        for i in range(3)
    ]
    if set(names) & set(original):
        raise ValueError("appended glyph name collision")
    if any(
        (cp in st.cmap for st in f["cmap"].tables for cp, _, _ in AMS_SYMBOLS)
    ):
        raise ValueError("Unicode collision or repeated append")
    unicodes = [st for st in f["cmap"].tables if st.isUnicode()]
    if not unicodes or any((st.format not in (4, 12) for st in unicodes)):
        raise ValueError("unsupported Unicode cmap structure")
    ssty = ssty_mapping(f)
    gi = f["MATH"].table.MathGlyphInfo
    for name in names:
        if name in ssty:
            raise ValueError("ssty collision")
    if (
        gi.MathItalicsCorrectionInfo is None
        or gi.MathTopAccentAttachment is None
    ):
        raise ValueError("MATH value tables missing")
    top = f["CFF "].cff.topDictIndex[0]
    for cp, slot, label in AMS_SYMBOLS:
        optical = []
        for i, (style, stem) in enumerate(AMS_STYLES):
            t1, tfm = sources[stem]
            if slot not in tfm.chars:
                raise ValueError("source slot missing")
            source_name = t1["Encoding"][slot]
            if source_name == ".notdef" or source_name not in t1.getGlyphSet():
                raise ValueError("AMS_SYMBOLS source Encoding slot missing")
            glyph = t1.getGlyphSet()[source_name]
            m = tfm.chars[slot]
            width = round(1000 * m["width"])
            ic = round(1000 * m.get("italic", 0))
            accent = round((width + ic) / 2)
            name = label + ("" if i == 0 else ".ssty" + str(i))
            optical.append(name)
            pen = T2CharStringPen(
                width - top.Private.nominalWidthX, t1.getGlyphSet()
            )
            glyph.draw(pen)
            char = pen.getCharString(
                private=top.Private, globalSubrs=f["CFF "].cff.GlobalSubrs
            )
            top.CharStrings.charStrings[name] = len(
                top.CharStrings.charStringsIndex
            )
            top.CharStrings.charStringsIndex.items.append(char)
            top.charset.append(name)
            bounds = BoundsPen(t1.getGlyphSet())
            glyph.draw(bounds)
            f["hmtx"].metrics[name] = (
                width,
                round(bounds.bounds[0] if bounds.bounds else 0),
            )
            f.setGlyphOrder(list(top.charset))
            math_add(f, name, ic, accent)
        ssty[optical[0]] = optical[1:]
        for st in unicodes:
            st.cmap[cp] = optical[0]
    f["maxp"].numGlyphs = len(f.getGlyphOrder())
    update_average_width(f)


ALTERNATE_STYLES = ("text", "script", "scriptscript")


def add_optical_alternates(f, cache, mf, ledger):
    if "CFF " not in f:
        raise ValueError("alternate append requires completed CFF OTF")
    top = f["CFF "].cff.topDictIndex[0]
    # Decompile MATH before modifying the glyph set.
    f["MATH"].table.MathGlyphInfo
    for route in ledger:
        if (
            tuple((s["style"] for s in route["source_styles"]))
            != ALTERNATE_STYLES
        ):
            raise ValueError("alternate style order differs")
        for i, style in enumerate(route["source_styles"]):
            alt = style["alternate"]
            stem = alt["font"]
            tag = alt["tag"]
            slot = int(alt["slot"])
            if declarations.SOURCE_FONTS.get(tag) != stem:
                raise ValueError("alternate source family mismatch")
            pf, tf = cache[stem]
            sn = pf["Encoding"][slot]
            if (
                sn == ".notdef"
                or sn not in pf.getGlyphSet()
                or slot not in tf.chars
            ):
                raise ValueError("alternate Type1 slot mismatch")
            m = tf.chars[slot]
            skewchar = mf["skewchar_by_tag"][tag]
            skew = (
                tf.kerning.get(slot, {}).get(skewchar, 0)
                if skewchar is not None
                else 0
            )
            if alt["accent_calibration"]["skewchar"] != skewchar:
                raise ValueError("alternate skew policy mismatch")
            width = round(1000 * m["width"])
            ic = round(1000 * m.get("italic", 0))
            accent = round(
                1000 * ((m["width"] + m.get("italic", 0)) / 2 + skew)
            )
            name = (
                "diagnostic."
                + route["semantic_id"].replace(".", "_")
                + "."
                + style["style"]
            )
            if name in top.CharStrings.charStrings:
                raise ValueError("alternate identity collision")
            glyph = pf.getGlyphSet()[sn]
            pen = T2CharStringPen(
                width - top.Private.nominalWidthX, pf.getGlyphSet()
            )
            glyph.draw(pen)
            char = pen.getCharString(
                private=top.Private, globalSubrs=f["CFF "].cff.GlobalSubrs
            )
            top.CharStrings.charStrings[name] = len(
                top.CharStrings.charStringsIndex.items
            )
            top.CharStrings.charStringsIndex.items.append(char)
            top.charset.append(name)
            f.setGlyphOrder(list(top.charset))
            bp = BoundsPen(pf.getGlyphSet())
            glyph.draw(bp)
            f["hmtx"][name] = (width, round(bp.bounds[0]))
            math_add(f, name, ic, accent)
    f["maxp"].numGlyphs = len(f.getGlyphOrder())
    update_average_width(f)


AMS_ALTERNATE_TAG = "cv53"


AMS_ALTERNATE_STYLES = (
    ("T", "ams", "mt2syat"),
    ("S", "ams_s", "mt2syas"),
    ("SS", "ams_ss", "mt2syaf"),
)


AMS_ALTERNATE_SYMBOLS = ((165, 85, "yen"), (174, 114, "registered"))


def ams_alternates_identities():
    return [
        dict(
            Unicode_input=cp,
            slot=slot,
            style=style,
            source=stem,
            source_role=role,
            output_glyph="original.ams." + label + "." + style,
        )
        for cp, slot, label in AMS_ALTERNATE_SYMBOLS
        for style, role, stem in AMS_ALTERNATE_STYLES
    ]


def ams_alternates_precheck(font):
    if (
        "CFF " not in font
        or font["head"].unitsPerEm != 1000
        or font["name"].getDebugName(6) != font_identity("full")[1]
    ):
        raise ValueError("AMS alternates require Full 1000-UPM CFF OTF")
    if any(
        (
            n.startswith(("original.ams.yen.", "original.ams.registered."))
            for n in font.getGlyphOrder()
        )
    ):
        raise ValueError("AMS alternate namespace collision/repeated append")
    gs = font["GSUB"].table
    if any(
        (
            r.FeatureTag == AMS_ALTERNATE_TAG
            for r in gs.FeatureList.FeatureRecord
        )
    ):
        raise ValueError("cv53 feature collision/repeated append")
    validate_gsub(gs)
    index = ssty_index(gs)
    cmap = font.getBestCmap()
    if (
        any((cp not in cmap for cp, _, _ in AMS_ALTERNATE_SYMBOLS))
        or cmap[165] == cmap[174]
    ):
        raise ValueError(
            "two distinct existing yen/registered cmap owners required"
        )
    info = font["MATH"].table.MathGlyphInfo
    if (
        info.MathItalicsCorrectionInfo is None
        or info.MathTopAccentAttachment is None
    ):
        raise ValueError("AMS alternate MATH IC/TopAccent tables required")
    return index


def ams_alternates_add_routes(font, rows, index):
    return insert_routes(font, rows, index, tag=AMS_ALTERNATE_TAG)


def add_ams_alternates(f, cache):
    index = ams_alternates_precheck(f)
    top = f["CFF "].cff.topDictIndex[0]
    rows = []
    for identity in ams_alternates_identities():
        pf, tf = cache[identity["source"]]
        slot = identity["slot"]
        sn = pf["Encoding"][slot]
        if (
            slot not in tf.chars
            or sn == ".notdef"
            or sn not in pf.getGlyphSet()
        ):
            raise ValueError("AMS alternate original slot missing")
        m = tf.chars[slot]
        width = round(1000 * m["width"])
        corr = round(1000 * m.get("italic", 0))
        accent = round((width + corr) / 2)
        bp = BoundsPen(pf.getGlyphSet())
        pf.getGlyphSet()[sn].draw(bp)
        if bp.bounds is None:
            raise ValueError("empty AMS alternate original outline")
        name = identity["output_glyph"]
        pen = T2CharStringPen(
            width - top.Private.nominalWidthX, pf.getGlyphSet()
        )
        pf.getGlyphSet()[sn].draw(pen)
        char = pen.getCharString(
            private=top.Private, globalSubrs=f["CFF "].cff.GlobalSubrs
        )
        top.CharStrings.charStrings[name] = len(
            top.CharStrings.charStringsIndex.items
        )
        top.CharStrings.charStringsIndex.items.append(char)
        top.charset.append(name)
        f.setGlyphOrder(list(top.charset))
        f["hmtx"][name] = (width, round(bp.bounds[0]))
        math_add(f, name, corr, accent)
        rows.append(identity)
    ams_alternates_add_routes(f, rows, index)
    f["maxp"].numGlyphs = len(f.getGlyphOrder())
    agg = aggregate_values(f)
    top.FontBBox = agg["FontBBox"]
    for k, v in zip(("xMin", "yMin", "xMax", "yMax"), agg["head_bbox"]):
        setattr(f["head"], k, v)
    for k, v in agg["hhea"].items():
        setattr(f["hhea"], k, v)
    update_average_width(f)


BOLD_MATH_FIELDS = (
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


def mbf_precheck(font):
    if "CFF " not in font or font["head"].unitsPerEm != 1000:
        raise ValueError("mbf186 requires CFF1 OTF at 1000 UPM")
    top = font["CFF "].cff.topDictIndex[0]
    if tuple(top.FontMatrix) != (0.001, 0, 0, 0.001, 0, 0):
        raise ValueError("unsupported output CFF FontMatrix")
    if not top.CharStrings.charStringsAreIndexed or hasattr(top, "FDArray"):
        raise ValueError("unsupported CFF charstring/CID structure")
    names = [r["output_glyph"] for r in bold_identities()]
    existing = set(font.getGlyphOrder())
    overlap = sorted(existing & set(names))
    if overlap:
        raise ValueError(
            "mbf glyph collision/repeated append: " + ", ".join(overlap[:3])
        )
    if any((n.startswith("original.mbf.") for n in existing)):
        raise ValueError("partial mbf glyph namespace collision")
    gs = font["GSUB"].table
    validate_gsub(gs)
    index = ssty_index(gs)
    cmap = font.getBestCmap()
    cps = {r["Unicode_input"] for r in bold_identities()}
    if not cps <= set(cmap) or len({cmap[c] for c in cps}) != 62:
        raise ValueError(
            "62 distinct existing mathematical bold cmap owners required"
        )
    gi = font["MATH"].table.MathGlyphInfo
    if any(
        (getattr(gi, field) is None for field, _, _, _ in BOLD_MATH_FIELDS)
    ):
        raise ValueError("MATH IC/TopAccent tables required")
    return index


def add_original_bold(font, cache, mf, edition):
    mbf_precheck(font)
    expected_name = font_identity(edition)[1]
    if font["name"].getDebugName(6) != expected_name:
        raise ValueError("font edition mismatch")
    top = font["CFF "].cff.topDictIndex[0]
    rows = []
    for identity in bold_identities():
        stem = identity["source_face"]
        slot = identity["source_slot"]
        role = identity["source_role"]
        pf, tfm = cache[stem]
        if slot not in tfm.chars:
            raise ValueError("mbf TFM slot missing: " + identity["source_id"])
        source_name = pf["Encoding"][slot]
        if source_name == ".notdef" or source_name not in pf.getGlyphSet():
            raise ValueError(
                "mbf PFB Encoding slot missing: " + identity["source_id"]
            )
        metrics = tfm.chars[slot]
        width = metrics["width"]
        italic = metrics.get("italic", 0)
        skew = tfm.kerning.get(slot, {}).get(mf["skewchar_by_tag"][role], 0)
        if any(
            (
                float(v) * (1 << 20) != int(float(v) * (1 << 20))
                for v in (width, italic, skew)
            )
        ):
            raise ValueError(
                "binary TFM metric is not an exact fix_word fraction"
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
                "empty mbf source outline: " + identity["source_id"]
            )
        # T2 width operand is relative to the existing
        # Private nominalWidthX.
        pen = T2CharStringPen(advance - top.Private.nominalWidthX, glyphs)
        glyph.draw(pen)
        char = pen.getCharString(
            private=top.Private, globalSubrs=font["CFF "].cff.GlobalSubrs
        )
        name = identity["output_glyph"]
        top.CharStrings.charStrings[name] = len(
            top.CharStrings.charStringsIndex.items
        )
        top.CharStrings.charStringsIndex.items.append(char)
        top.charset.append(name)
        font.setGlyphOrder(list(top.charset))
        bp = BoundsPen(font.getGlyphSet())
        char.draw(bp)
        if bp.bounds is None or char.width != advance:
            raise ValueError("new CFF outline/decoded width mismatch")
        font["hmtx"][name] = (advance, round(bp.bounds[0]))
        math_add(font, name, ic, accent)
        rows.append(identity)
    grouped = {}
    for row in rows:
        grouped.setdefault(row["Unicode_input"], {})[row["style"]] = row[
            "output_glyph"
        ]
    optical = ssty_mapping(font)
    optical.update({v["T"]: [v["S"], v["SS"]] for v in grouped.values()})
    font["maxp"].numGlyphs = len(font.getGlyphOrder())
    agg = aggregate_values(font)
    top.FontBBox = agg["FontBBox"]
    for k, v in zip(("xMin", "yMin", "xMax", "yMax"), agg["head_bbox"]):
        setattr(font["head"], k, v)
    for k, v in agg["hhea"].items():
        setattr(font["hhea"], k, v)
    update_average_width(font)


def source_info(face, slot, skew):
    p, tf = face.font, face.raw_metrics()
    name = p["Encoding"][slot]
    m = tf.chars.get(slot)
    present = name != ".notdef" and name in p["CharStrings"] and m is not None
    fix = metrics.read_kerns_fix20(face.tfm_path)
    return dict(
        role=face.role,
        slot=slot,
        pfb=face.pfb_path.name,
        tfm=face.tfm_path.name,
        encoding_name=name,
        present=present,
        width=round(1000 * m["width"]) if m else None,
        IC=round(1000 * m.get("italic", 0)) if m else None,
        skewchar=skew,
        skew_fix20=fix.get((slot, skew), 0),
        TopAccent=round(
            1000
            * (
                (m["width"] + m.get("italic", 0)) / 2
                + fix.get((slot, skew), 0) / (1 << 20)
            )
        )
        if m
        else None,
    )


def split_bars(font, ss):
    cmap = font.getBestCmap()
    aliases, clones, records = {}, {}, []
    for oldcp, newcp in [(0x007C, 0x2223), (0x2016, 0x2225)]:
        source = cmap[oldcp]
        if cmap[newcp] != source:
            raise ValueError("relation bars already split; do not apply twice")
        forms = [source, *ss[source]]
        new = [f"uni{newcp:04X}" + s for s in ("", ".ssty1", ".ssty2")]
        aliases[source] = [
            f"U+{cp:04X}" for cp, n in cmap.items() if n == source
        ]
        for a, b in zip(forms, new):
            _copy_shift(font, a, b)
            font["hmtx"][b] = font["hmtx"][a]
            copy_math_attributes(font, a, b)
            clones[a] = b
        ss[new[0]] = new[1:]
        mv = font["MATH"].table.MathVariants
        for direction in ("Vert", "Horiz"):
            cov = getattr(mv, direction + "GlyphCoverage")
            cs = getattr(mv, direction + "GlyphConstruction")
            for a, b in zip(forms, new):
                if a in cov.glyphs:
                    cs.append(deepcopy(cs[cov.glyphs.index(a)]))
                    cov.glyphs.append(b)
            setattr(mv, direction + "GlyphCount", len(cov.glyphs))
        for table in font["cmap"].tables:
            if table.isUnicode() and newcp in table.cmap:
                table.cmap[newcp] = new[0]
        records.append(
            dict(
                Unicode=f"U+{newcp:04X}",
                old=forms,
                new=new,
                original_aliases=aliases[source],
                growth="copied constructions; existing internal glyphs shared",
            )
        )
    pairs = {}
    for lookup in font["GPOS"].table.LookupList.Lookup:
        for sub in lookup.SubTable:
            st = getattr(sub, "ExtSubTable", sub)
            if not hasattr(st, "PairSet"):
                raise ValueError("unsupported GPOS during bar split")
            for a, ps in zip(st.Coverage.glyphs, st.PairSet):
                for pv in ps.PairValueRecord:
                    b = pv.SecondGlyph
                    for na in [a] + ([clones[a]] if a in clones else []):
                        for nb in [b] + ([clones[b]] if b in clones else []):
                            if (na, nb) != (a, b):
                                pairs[na, nb] = (
                                    deepcopy(pv.Value1),
                                    deepcopy(pv.Value2),
                                )
    append_pairs(font, pairs)
    return records, len(pairs)


def build_relations(font, catalog, snapshot, ab_report):
    edition = catalog.edition
    source_map = {
        (r["role"], r["slot"]): r["glyph"]
        for r in ab_report["source_glyphs"]
        if r["glyph"] in font.getGlyphOrder()
    }
    ss = substitution.ssty_mapping(font)
    bars, cloned_pairs = split_bars(font, ss)
    cmap = font.getBestCmap()
    maps = defaultdict(dict)
    routes, sources, imported = [], [], []
    new_names = set()

    def source(role, slot, glyph):
        face = catalog.faces[role]
        info = source_info(face, slot, snapshot["skewchar_by_tag"].get(role))
        if not info["present"]:
            raise ValueError(
                "adopted source slot missing: " + role + ":" + str(slot)
            )
        sources.append(dict(info, glyph=glyph))
        return info

    def import_source(role, slot):
        if (role, slot) in source_map:
            return source_map[role, slot]
        # Keep the historical glyph identifier stable across public CV
        # renumbering.
        n = f"cv22.{U.SOURCE_FONTS[role]}.s{slot:03d}"
        info = source(role, slot, n)
        face = catalog.faces[role]
        glyphs = face.font.getGlyphSet()
        _set_charstring(
            font, n, glyphs[info["encoding_name"]].draw, info["width"]
        )
        math_add(font, n, info["IC"], info["TopAccent"])
        source_map[role, slot] = n
        new_names.add(n)
        imported.append(dict(info, glyph=n))
        return n

    for group, cp, target, role, slot, boldcp in U.RELATION_ROWS:
        if role == "ams" and edition == "lite":
            continue
        if cp not in cmap or target not in font.getGlyphOrder():
            raise ValueError("adopted base input/target absent")
        inputs = [cmap[cp], *ss[cmap[cp]]]
        targets = [target, *ss[target]]
        for level, (a, b) in enumerate(zip(inputs, targets)):
            maps[U.RELATION_TAGS[group]][a] = b
            info = source(role + U.RELATION_SUFFIX[level], slot, b)
            source_map[role + U.RELATION_SUFFIX[level], slot] = b
            routes.append(
                dict(
                    group=group,
                    tag=U.RELATION_TAGS[group],
                    Unicode=f"U+{cp:04X}",
                    level=level,
                    input=a,
                    output=b,
                    bold=False,
                    role=info["role"],
                    slot=slot,
                )
            )
        if boldcp is not None and edition == "full":
            targets = [
                import_source("bmit" + s, slot) for s in U.RELATION_SUFFIX
            ]
            ss[targets[0]] = targets[1:]
            inputs = [cmap[boldcp], *ss[cmap[boldcp]]]
            for level, (a, b) in enumerate(zip(inputs, targets)):
                maps[U.RELATION_TAGS[group]][a] = b
                routes.append(
                    dict(
                        group=group,
                        tag=U.RELATION_TAGS[group],
                        Unicode=f"U+{boldcp:04X}",
                        level=level,
                        input=a,
                        output=b,
                        bold=True,
                        role="bmit" + U.RELATION_SUFFIX[level],
                        slot=slot,
                    )
                )
    pair_values, new_kerns = {}, []
    for role in (
        ["bmit" + s for s in U.RELATION_SUFFIX] if edition == "full" else []
    ):
        skew = snapshot["skewchar_by_tag"][role]
        face = catalog.faces[role]
        for (left, right), fix in metrics.read_kerns_fix20(
            face.tfm_path
        ).items():
            if (
                right == skew
                or (role, left) not in source_map
                or (role, right) not in source_map
            ):
                continue
            a, b = source_map[role, left], source_map[role, right]
            value = round(1000 * fix / (1 << 20))
            if not value or not ({a, b} & new_names):
                continue
            val = ValueRecord()
            val.XAdvance = value
            pair_values[a, b] = (val, None)
            new_kerns.append(
                dict(
                    role=role,
                    left_slot=left,
                    right_slot=right,
                    left_glyph=a,
                    right_glyph=b,
                    xadvance=value,
                    source_fix20=fix,
                )
            )
    append_pairs(font, pair_values)
    substitution.install_maps(font, maps, new_tags=U.NEW_RELATION_TAGS)
    font["maxp"].numGlyphs = len(font.getGlyphOrder())
    return dict(
        edition=edition,
        feature_tags=U.RELATION_TAGS,
        split_bars=bars,
        cloned_bar_pairs=cloned_pairs,
        routes=routes,
        sources=sources,
        imported=imported,
        new_source_kerns=new_kerns,
        physical_deletion=False,
        bold_cards=(
            "bsyt slots129/131 exist; no distinct standard "
            "bold Unicode input; not imported"
        ),
        AMS_bold=(
            "mt2bsya/mt2hsya exist; no distinct standard "
            "bold/heavy Unicode inputs for these "
            "relations; not imported"
        ),
    )


def bind_unicode(font, catalog):
    edition = catalog.edition
    if edition not in ("full", "lite"):
        raise ValueError("unknown edition")
    ss = substitution.ssty_mapping(font)
    report = []
    for cp, command, glyph, role, slot in U.STANDARD_UNICODE_ROUTES:
        if edition == "lite" and role == "ams":
            continue
        forms = [glyph, *ss.get(glyph, ())]
        if len(forms) != 3 or any(
            n not in font.getGlyphOrder() for n in forms
        ):
            raise ValueError("existing T/S/SS family missing: " + glyph)
        tables = [t for t in font["cmap"].tables if t.isUnicode()]
        if not tables or any(t.format not in (4, 12) for t in tables):
            raise ValueError("unsupported Unicode cmap structure")
        if any(cp in t.cmap for t in tables):
            raise ValueError(
                "standard entrance already present; refuse overwrite"
            )
        for table in tables:
            table.cmap[cp] = glyph
        report.append(
            dict(
                Unicode=f"U+{cp:04X}",
                command="\\" + command,
                glyph=glyph,
                forms=forms,
                role=role,
                slot=slot,
                Unicode_subtables=len(tables),
                new_glyphs=0,
            )
        )

    # LuaTeX aligns nucleus and overlay TopAccentAttachment values. The
    # original zero-width slash has positive x coordinates: retain its
    # outline and advance, and attach at the geometric ink center.
    root = font.getBestCmap()[0x0338]
    forms = [root, *ss[root]]
    if len(forms) != 3:
        raise ValueError("overlay T/S/SS source family missing")
    table = font["MATH"].table.MathGlyphInfo.MathTopAccentAttachment
    attachments = dict(
        zip(table.TopAccentCoverage.glyphs, table.TopAccentAttachment)
    )
    glyphs = font.getGlyphSet()
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    overlay = []
    for name in forms:
        pen = BoundsPen(glyphs)
        glyphs[name].draw(pen)
        x0, y0, x1, y1 = pen.bounds
        if font["hmtx"][name][0] != 0:
            raise ValueError("original overlay advance must remain zero")
        value = round((x0 + x1) / 2)
        before = attachments[name].Value
        attachments[name].Value = value
        classes[name] = 3
        overlay.append(
            dict(
                glyph=name,
                bbox=pen.bounds,
                attachment_before=before,
                attachment=value,
            )
        )

    tie = font.getBestCmap()[0x0361]
    tie_forms = [tie, *ss[tie]]
    if len(tie_forms) != 3:
        raise ValueError("tie T/S/SS source family missing")
    tie_metrics = []
    for name, role in zip(tie_forms, ("syt", "syt_s", "syt_ss")):
        face = catalog.faces[role]
        raw = face.raw_metrics().chars[65]
        skew = catalog.declarations.skewchar_by_tag.get(role)
        kern = metrics.read_kerns_fix20(face.tfm_path).get((65, skew), 0)
        # Keep C02's raw source arithmetic even though the new Unicode
        # combining classification now makes the root a protected mark.
        value = round(
            1000 * (raw.get("width", 0) + raw.get("italic", 0)) / 2
            + 1000 * kern / (1 << 20)
        )
        attachments[name].Value = value
        classes[name] = 3
        tie_metrics.append(
            dict(
                glyph=name,
                source=role,
                slot=65,
                advance=font["hmtx"][name][0],
                attachment=value,
            )
        )

    return dict(
        edition=edition,
        additions=report,
        overlay=overlay,
        tie_source_metrics_preserved=tie_metrics,
        physical_deletion=False,
        outlines_unchanged=True,
        advances_unchanged=True,
        GPOS_unchanged=True,
    )
