"""Check the serialized product pair."""

import json

import donors
from config import FONT_REVISION, FONT_VERSION, identity
from fontTools.pens.basePen import NullPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot
from substitution import lang_systems, references
from windows_metrics import errors as windows_errors
from windows_metrics import read as read_windows


def average_width_errors(font):
    total = count = 0
    for name in font.getGlyphOrder():
        width = font["hmtx"][name][0]
        if width:
            total += width
            count += 1
    if not count:
        return ["xAvgCharWidth: no nonzero advances"]
    quotient, remainder = divmod(total, count)
    expected = quotient + int(2 * remainder >= count)
    if not 0 <= expected <= 32767 or font["OS/2"].xAvgCharWidth != expected:
        return [
            "xAvgCharWidth differs from the independently calculated average"
        ]
    return []


def windows_ansi_errors(font):
    cmap = font.getBestCmap() or {}
    names = set(font.getGlyphOrder())
    if any(
        cmap.get(cp) in (None, ".notdef") or cmap[cp] not in names
        for cp in range(0x20, 0x7F)
    ):
        return ["ASCII cmap missing valid glyphs"]
    if not font["OS/2"].ulCodePageRange1 & 1:
        return ["Windows ANSI bit 0 missing"]
    return []


def _glyph_references(node, names, seen=None):
    """Check references in the layout objects emitted by our generators.
    """
    if seen is None:
        seen = set()
    if node is None or isinstance(node, (str, int, float, bool, bytes)):
        return
    if id(node) in seen:
        return
    seen.add(id(node))
    used = []
    if isinstance(node, ot.Coverage):
        used.extend(node.glyphs)
    elif isinstance(node, ot.ClassDef):
        used.extend(node.classDefs)
    elif isinstance(node, ot.SingleSubst):
        used.extend(node.mapping)
        used.extend(node.mapping.values())
    elif isinstance(node, (ot.AlternateSubst, ot.MultipleSubst)):
        mapping = (
            node.alternates
            if isinstance(node, ot.AlternateSubst)
            else node.mapping
        )
        used.extend(mapping)
        used.extend(g for values in mapping.values() for g in values)
    elif isinstance(node, ot.LigatureSubst):
        used.extend(node.ligatures)
    elif isinstance(node, ot.Ligature):
        used.extend(node.Component)
        used.append(node.LigGlyph)
    elif isinstance(node, ot.PairValueRecord):
        used.append(node.SecondGlyph)
    elif isinstance(node, ot.GlyphPartRecord):
        used.append(node.glyph)
    elif isinstance(node, ot.MathGlyphVariantRecord):
        used.append(node.VariantGlyph)
    if any(name not in names for name in used):
        raise ValueError("layout references a missing glyph")
    if isinstance(node, dict):
        children = node.values()
    elif isinstance(node, (list, tuple)):
        children = node
    else:
        children = vars(node).values() if hasattr(node, "__dict__") else ()
    for child in children:
        _glyph_references(child, names, seen)


def _layout(font):
    names = set(font.getGlyphOrder())
    for tag in ("MATH", "GSUB", "GPOS", "GDEF"):
        table = font[tag].table
        _glyph_references(table, names)
        if tag not in ("GSUB", "GPOS"):
            continue
        lookups = table.LookupList.Lookup
        features = table.FeatureList.FeatureRecord
        if table.LookupList.LookupCount != len(
            lookups
        ) or table.FeatureList.FeatureCount != len(features):
            raise ValueError(tag + " count mismatch")
        for lookup in lookups:
            if lookup.SubTableCount != len(lookup.SubTable):
                raise ValueError(tag + " subtable count mismatch")
        for feature in features:
            indices = feature.Feature.LookupListIndex
            if feature.Feature.LookupCount != len(indices) or any(
                not 0 <= i < len(lookups) for i in indices
            ):
                raise ValueError(
                    tag + " feature lookup reference out of range"
                )
        for record in references(table):
            if not 0 <= record.LookupListIndex < len(lookups):
                raise ValueError(
                    tag + " context lookup reference out of range"
                )
        for lang in lang_systems(table):
            if lang.FeatureCount != len(lang.FeatureIndex) or any(
                not 0 <= i < len(features) for i in lang.FeatureIndex
            ):
                raise ValueError(
                    tag + " language feature reference out of range"
                )
            if (
                lang.ReqFeatureIndex != 65535
                and not 0 <= lang.ReqFeatureIndex < len(features)
            ):
                raise ValueError(
                    tag + " required feature reference out of range"
                )
    math = font["MATH"].table
    variants = math.MathVariants
    for axis in ("Vert", "Horiz"):
        coverage = getattr(variants, axis + "GlyphCoverage")
        constructions = getattr(variants, axis + "GlyphConstruction")
        if len(coverage.glyphs) != len(constructions) or getattr(
            variants, axis + "GlyphCount"
        ) != len(constructions):
            raise ValueError("MATH construction count mismatch")
        for construction in constructions:
            if construction.VariantCount != len(
                construction.MathGlyphVariantRecord
            ):
                raise ValueError("MATH variant count mismatch")
            assembly = construction.GlyphAssembly
            if assembly and assembly.PartCount != len(assembly.PartRecords):
                raise ValueError("MATH assembly count mismatch")


def _one(font, edition):
    required = (
        "head",
        "maxp",
        "hmtx",
        "hhea",
        "OS/2",
        "name",
        "cmap",
        "MATH",
        "GSUB",
        "GPOS",
        "GDEF",
    )
    missing = set(required) - set(font.keys())
    if missing:
        raise ValueError("missing final tables: " + ", ".join(sorted(missing)))
    order = font.getGlyphOrder()
    if (
        not order
        or len(order) != len(set(order))
        or font["maxp"].numGlyphs != len(order)
    ):
        raise ValueError("final glyph count/order mismatch")
    if set(font["hmtx"].metrics) != set(order):
        raise ValueError("hmtx glyph set mismatch")
    names = set(order)
    for subtable in font["cmap"].tables:
        if any(
            name not in names or name == ".notdef"
            for name in subtable.cmap.values()
        ):
            raise ValueError("invalid final cmap reference")
    cmap = font.getBestCmap() or {}
    required_chars = (0x20, 0x2061, 0x2062, 0x2063, 0x221A, 0x222B)
    if any(cp not in cmap for cp in required_chars):
        raise ValueError("required product character missing")
    failures = windows_ansi_errors(font) + average_width_errors(font)
    if failures:
        raise ValueError("; ".join(failures))
    family, basename, unique = identity(edition)
    expected_names = {
        1: family,
        2: "Regular",
        3: unique,
        4: family,
        5: FONT_VERSION,
        6: basename,
        16: family,
        17: "Regular",
    }
    for key, expected in expected_names.items():
        values = {n.toUnicode() for n in font["name"].names if n.nameID == key}
        if values != {expected}:
            raise ValueError("final name/edition mismatch: " + str(key))
    if (
        font["head"].fontRevision != FONT_REVISION
        or font["head"].unitsPerEm != 1000
    ):
        raise ValueError("final revision/UPM mismatch")
    os2, hhea = font["OS/2"], font["hhea"]
    typo = [os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap]
    horizontal_header = [hhea.ascent, hhea.descent, hhea.lineGap]
    if typo != [806, -194, 200] or horizontal_header != [806, -194, 200]:
        raise ValueError("final vertical metrics mismatch")
    _layout(font)


def check_pair(
    otf_path, ttf_path, edition, windows_policy=None, input_manifest=None
):
    with TTFont(otf_path) as otf, TTFont(ttf_path) as ttf:
        if "CFF " not in otf or "glyf" not in ttf:
            raise ValueError("expected final CFF OTF and quadratic TTF")
        for font in (otf, ttf):
            _one(font, edition)
        a, b = otf.getGlyphOrder(), ttf.getGlyphOrder()
        if len(a) != len(b):
            raise ValueError("OTF/TTF glyph count mismatch")

        def cmap_gids(font):
            return [
                (
                    t.platformID,
                    t.platEncID,
                    t.language,
                    t.format,
                    {cp: font.getGlyphID(name) for cp, name in t.cmap.items()},
                )
                for t in font["cmap"].tables
            ]

        if cmap_gids(otf) != cmap_gids(ttf):
            raise ValueError("OTF/TTF cmap GID mismatch")
        if [otf["hmtx"][n] for n in a] != [ttf["hmtx"][n] for n in b]:
            raise ValueError("OTF/TTF GID-ordered hmtx mismatch")
        for tag in ("MATH", "GSUB", "GPOS", "GDEF"):
            if otf.reader[tag] != ttf.reader[tag]:
                raise ValueError("OTF/TTF layout bytes differ: " + tag)
        cff = otf["CFF "].cff
        if len(cff.topDictIndex) != 1:
            raise ValueError("requires singleton CFF1")
        top = cff.topDictIndex[0]
        if list(top.charset) != a or len(top.CharStrings.charStrings) != len(
            a
        ):
            raise ValueError("CFF GID/charstring count mismatch")
        for name in a:
            char = top.CharStrings[name]
            char.draw(NullPen())
            if char.width != otf["hmtx"][name][0]:
                raise ValueError(
                    "decoded CFF width differs from hmtx: " + name
                )
        if windows_policy:
            obj = read_windows(windows_policy)
            failures = windows_errors(
                ttf,
                obj,
                "source",
                font_path=ttf_path,
                edition=edition,
                manifest=input_manifest,
                source_path=otf_path,
            )
            if failures:
                raise ValueError("; ".join(failures))
        elif [ttf["OS/2"].usWinAscent, ttf["OS/2"].usWinDescent] != [
            otf["OS/2"].usWinAscent,
            otf["OS/2"].usWinDescent,
        ]:
            raise ValueError("legacy OTF/TTF Windows metrics mismatch")


def source_status(face, slot, chars):
    """Presence only, using dictionaries/metrics already read for this
    phase.
    """
    encoding = face.font["Encoding"]
    name = encoding[slot] if 0 <= slot < len(encoding) else None
    present = name is not None and name in face.font["CharStrings"]
    return dict(
        encoding_name=name,
        charstring_present=present,
        pfb_usable=bool(name and name != ".notdef" and present),
        tfm_valid=slot in chars,
    )


def check_sources(catalog, generation, coverage, *, log=None):
    missing = []
    for phase, table in [
        ("native", generation.native),
        ("original additions", generation.originals),
    ]:
        for role, slots in table.items():
            face = catalog.faces[role]
            if phase == "original additions":
                if tuple(face.font["FontMatrix"]) != (
                    0.001,
                    0,
                    0,
                    0.001,
                    0,
                    0,
                ):
                    raise ValueError(
                        f"preflight {face.pfb_path.name} role={role}: "
                        "unsupported FontMatrix"
                    )
                chars = face.raw_metrics().chars
            else:
                chars = face.tfm.chars
            for slot in sorted(slots):
                status = source_status(face, slot, chars)
                if status["pfb_usable"] and status["tfm_valid"]:
                    continue
                record = dict(
                    phase=phase,
                    role=role,
                    pfb_file=str(face.pfb_path),
                    tfm_file=str(face.tfm_path),
                    slot=slot,
                    slot_hex=f"0x{slot:02X}",
                    **status,
                )
                # Reuse the small ledger already read by create; no
                # reverse
                # index.
                for row in generation.alternate_rows:
                    for style in row["source_styles"]:
                        alt = style["alternate"]
                        if alt["tag"] == role and alt["slot"] == slot:
                            record.setdefault("semantic_sources", []).append(
                                dict(
                                    semantic_id=row["semantic_id"],
                                    style=style["style"],
                                )
                            )
                missing.append(record)
                if log is not None:
                    log.write(
                        "required source missing: " + json.dumps(record) + "\n"
                    )
                    log.flush()
    if missing:
        first = missing[0]
        raise ValueError(
            f"{len(missing)} required source reference(s) missing; first: "
            f"{first['phase']} role={first['role']} "
            f"slot={first['slot']} ({first['slot_hex']})"
        )
    for role in ["bold", "bold_s", "bold_ss"]:
        if catalog.declarations.skewchar_by_tag.get(role) != 32:
            raise ValueError(
                f"preflight role={role}: mbf source/skewchar role mismatch"
            )
    import math

    for role, indices in generation.numeric["fontdimens"].items():
        face = catalog.faces[role]
        dimensions = getattr(face.tfm, "fontdimen", {})
        for index in indices:
            value = dimensions.get(index)
            if value is None or not math.isfinite(float(value)):
                raise ValueError(
                    f"preflight numeric role={role} "
                    f"fontdimen={index}: missing/nonfinite"
                )
    for role in generation.numeric["design_size"]:
        value = getattr(catalog.faces[role].tfm, "design_size", None)
        if value is None or not math.isfinite(float(value)) or value <= 0:
            raise ValueError(
                f"preflight numeric role={role} DESIGNSIZE invalid"
            )
    donors.check_supply(catalog.donors, coverage)
