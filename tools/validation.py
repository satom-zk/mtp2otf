"""Validate inputs, native provenance, and serialized products."""

import json
import math
from math import ceil

from fontTools.pens.basePen import NullPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot

import donors
import mapping as U
from config import FONT_REVISION, FONT_VERSION, identity
from substitution import (
    lang_systems,
    references,
    selector_mapping,
    ssty_mapping,
    validate_gsub,
)
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


def _horizontal_growth(font):
    """Require the adopted minimum and continuous arrow/vector growth.
    """
    variants = font["MATH"].table.MathVariants
    if variants.MinConnectorOverlap != 20:
        raise ValueError("final minimum connector overlap differs")
    cons = dict(zip(
        variants.HorizGlyphCoverage.glyphs,
        variants.HorizGlyphConstruction,
    ))
    cmap, optical = font.getBestCmap(), ssty_mapping(font)
    left, right = cmap[0x20D6], cmap[0x20D7]
    lefts = [left] + list(optical[left])
    rights = [right] + list(optical[right])
    if len(lefts) != 3 or len(rights) != 3:
        raise ValueError("vector requires three optical styles")
    for a, b in zip(lefts, rights):
        x, y = cons[a], cons[b]
        if x.VariantCount != 2 or [
            v.AdvanceMeasurement for v in x.MathGlyphVariantRecord
        ] != [v.AdvanceMeasurement for v in y.MathGlyphVariantRecord]:
            raise ValueError("left/right vector variant sizes differ")
        ep, sp = x.GlyphAssembly.PartRecords
        shaft, end = y.GlyphAssembly.PartRecords
        if (sp.__dict__ != shaft.__dict__ or ep.PartFlags != 0
                or ep.StartConnectorLength != 0
                or ep.EndConnectorLength != end.StartConnectorLength
                or ep.FullAdvance != end.FullAdvance):
            raise ValueError("left/right vector assembly differs")
    roots = [cmap[cp] for cp in (
        0x2190, 0x2192, 0x2194, 0x21D0, 0x21D2, 0x21D4,
    )] + lefts + rights
    for root in roots:
        c = cons[root]
        intervals = []
        for repeats in range(4):
            parts = [p for p in c.GlyphAssembly.PartRecords
                     for _ in range(repeats if p.PartFlags & 1 else 1)]
            caps = [min(a.EndConnectorLength, b.StartConnectorLength)
                    for a, b in zip(parts, parts[1:])]
            if any(cap < 20 for cap in caps):
                raise ValueError("horizontal joint below minimum overlap")
            total = sum(p.FullAdvance for p in parts)
            intervals.append((total - sum(caps), total - 20 * len(caps)))
        end = max(v.AdvanceMeasurement for v in c.MathGlyphVariantRecord)
        for lo, hi in sorted(intervals):
            if hi > end and lo > end:
                raise ValueError("uncovered horizontal growth interval")
            end = max(end, hi)
        # Extender self-overlap >= 20 makes later interval overlap grow.
        if intervals[-1][0] > intervals[-2][1]:
            raise ValueError("horizontal growth tail is not continuous")


def _delimiter_sizes(font):
    """Check the serialized common angle/bar series and retained growth.
    """
    variants = font["MATH"].table.MathVariants
    cons = dict(
        zip(variants.VertGlyphCoverage.glyphs, variants.VertGlyphConstruction)
    )
    cmap = font.getBestCmap()
    glyphs = font.getGlyphSet()

    def ink_bounds(records):
        bounds = []
        for record in records:
            pen = BoundsPen(glyphs)
            glyphs[record.VariantGlyph].draw(pen)
            if pen.bounds is None:
                raise ValueError("angle/bar variant has no outline")
            _, y_min, _, y_max = pen.bounds
            if record.AdvanceMeasurement != ceil(y_max - y_min) + 1:
                raise ValueError(
                    "angle/bar measurement differs from outline"
                )
            bounds.append((y_min, y_max))
        return bounds

    reference = cons[cmap[0x27E8]].MathGlyphVariantRecord
    expected = [r.AdvanceMeasurement for r in reference]
    if (
        len(expected) != 8
        or any(a >= b for a, b in zip(expected, expected[1:]))
        or expected[1:6:2] != [1101, 1451, 2101]
    ):
        raise ValueError("invalid interpolated angle sequence")
    expected_bounds = ink_bounds(reference)
    for cp in (0x27E8, 0x27E9, 0x007C, 0x2016, 0x2223, 0x2225):
        con = cons[cmap[cp]]
        records = con.MathGlyphVariantRecord
        if [r.AdvanceMeasurement for r in records] != expected:
            raise ValueError("angle/bar size sequence mismatch")
        # Equal heights alone do not guarantee equal selection at the
        # separately rounded height/depth boundaries in script sizes.
        if ink_bounds(records) != expected_bounds:
            raise ValueError("angle/bar ink bounds mismatch")
        if bool(con.GlyphAssembly) != (cp not in (0x27E8, 0x27E9)):
            raise ValueError("angle/bar assembly presence mismatch")
    for base, alias in ((0x007C, 0x2223), (0x2016, 0x2225)):
        if (
            [r.VariantGlyph
             for r in cons[cmap[base]].MathGlyphVariantRecord]
            != [r.VariantGlyph
                for r in cons[cmap[alias]].MathGlyphVariantRecord]
        ):
            raise ValueError("bar alias size mismatch")


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
    validate_public_selectors(font, edition)
    _delimiter_sizes(font)
    _horizontal_growth(font)


def check_pair(
    otf_path, ttf_path, edition, windows_policy=None, input_manifest=None
):
    with TTFont(otf_path) as otf, TTFont(ttf_path) as ttf:
        if "CFF " not in otf or "glyf" not in ttf:
            raise ValueError("expected final CFF OTF and quadratic TTF")
        for font in (otf, ttf):
            _one(font, edition)
        validate_operator_growth(otf)
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
                # reverse index.
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


def compound_records(inventory):
    """Require construction-time provenance, including both halves."""
    expected = {
        (name, U.OPERATOR_STAGES[i]): refs
        for name, stages in U.operator_sources().items()
        for i, refs in enumerate(stages) if len(refs) > 1
    }
    records = inventory.get("compound_sources")
    if not isinstance(records, list):
        raise ValueError("missing compound_sources payload")
    imports = {(r["tag"], r["slot"]): r["glyph"]
               for r in inventory["imports"]}
    found = {}
    for record in records:
        if not isinstance(record, dict) or not {
            "glyph", "series", "stage", "parts", "advance", "bbox"
        } <= set(record):
            raise ValueError("incomplete compound source record")
        key = (record["series"], record["stage"])
        if key not in expected or key in found:
            raise ValueError("unexpected/duplicate compound source record")
        parts = record["parts"]
        if not isinstance(parts, list) or any(
            not isinstance(part, dict) or not {
                "tag", "slot", "glyph", "scale", "transform"
            } <= set(part) for part in parts
        ):
            raise ValueError("incomplete compound part record")
        if tuple((p["tag"], p["slot"]) for p in parts) != expected[key]:
            raise ValueError("compound source order/parts mismatch")
        for part in parts:
            ref = (part["tag"], part["slot"])
            transform = part["transform"]
            if (imports.get(ref) != part["glyph"]
                    or part["scale"] != (2 if part["tag"] == "xxxl" else 1)
                    or not isinstance(transform, list) or len(transform) != 6
                    or not all(isinstance(x, (int, float)) and math.isfinite(x)
                               for x in transform)
                    or transform[:4] != [1, 0, 0, 1]):
                raise ValueError("invalid compound part provenance")
        if (not isinstance(record["bbox"], list) or len(record["bbox"]) != 4
                or not all(isinstance(x, (int, float)) and math.isfinite(x)
                           for x in record["bbox"] + [record["advance"]])):
            raise ValueError("invalid compound result dimensions")
        found[key] = record
    if set(found) != set(expected):
        raise ValueError("missing required compound source record")
    return list(found.values())


def validate_compounds(font, records, *, require_parts):
    """Match construction records to native/final glyph geometry."""

    gs = font.getGlyphSet()
    for record in records:
        name = record["glyph"]
        if name not in gs or font["hmtx"][name][0] != record["advance"]:
            raise ValueError("compound output/advance mismatch")
        bounds_pen = BoundsPen(gs)
        gs[name].draw(bounds_pen)
        bounds = bounds_pen.bounds
        if bounds is None or any(
            abs(a - b) > 1 for a, b in zip(bounds, record["bbox"])
        ):
            raise ValueError("compound output bounds mismatch")
        if require_parts:
            pen = BoundsPen(gs)
            for part in record["parts"]:
                if part["glyph"] not in gs:
                    raise ValueError("missing imported compound part glyph")
                gs[part["glyph"]].draw(TransformPen(pen, part["transform"]))
            if pen.bounds is None or any(
                abs(a - b) > 1 for a, b in zip(pen.bounds, record["bbox"])
            ):
                raise ValueError("compound references/result mismatch")


def validate_operator_growth(font):
    """Require complete ordered operator series after subsetting."""
    m = font["MATH"].table
    variants = dict(zip(m.MathVariants.VertGlyphCoverage.glyphs,
                        m.MathVariants.VertGlyphConstruction))
    extended = set(m.MathGlyphInfo.ExtendedShapeCoverage.glyphs)
    cmap = font.getBestCmap()
    approved = U.operator_sources()
    for _, (cp, name, _) in U.EXA_OPS.items():
        if name not in approved:
            continue
        root = cmap[cp] if cp is not None else name
        if root not in variants:
            raise ValueError("missing final operator construction: " + name)
        c = variants[root]
        glyphs = [r.VariantGlyph for r in c.MathGlyphVariantRecord]
        measurements = [r.AdvanceMeasurement for r in c.MathGlyphVariantRecord]
        if (glyphs != [root + s for s in U.OPERATOR_SUFFIXES]
                or c.GlyphAssembly
                or any(a >= b for a, b in zip(measurements, measurements[1:]))
                or not set(glyphs[2:]) <= extended):
            raise ValueError("invalid final six-stage operator: " + name)
    control = variants[cmap[0x2A03]]
    if len(control.MathGlyphVariantRecord) != 2 or control.GlyphAssembly:
        raise ValueError("bigcupdot ordinary growth changed")


def validate_public_selectors(font, edition):
    """Check final selectors, lookup order, and UI name references."""
    gs = font["GSUB"].table
    validate_gsub(gs)
    specs = U.public_selectors(edition)
    records = gs.FeatureList.FeatureRecord
    by_tag = {r.FeatureTag: r for r in records}
    if [r.FeatureTag for r in records] != sorted(by_tag):
        raise ValueError("duplicate or unsorted public features")
    if set(by_tag) - {"dtls", "ssty", "ccmp"} != set(specs):
        raise ValueError("final selector inventory differs")
    order = [tag for tag in U.SUBSTITUTION_ORDER if tag in by_tag]
    if len(gs.LookupList.Lookup) != len(order):
        raise ValueError("final lookup inventory differs")
    for index, tag in enumerate(order):
        if by_tag[tag].Feature.LookupListIndex != [index]:
            raise ValueError("final lookup order differs: " + tag)
    used_names = set()
    for tag, spec in specs.items():
        feature = by_tag[tag].Feature
        selector_mapping(gs.LookupList.Lookup[feature.LookupListIndex[0]],
                         len(spec["parameters"]))
        params = feature.FeatureParams
        if tag.startswith("ss"):
            if (not isinstance(params, ot.FeatureParamsStylisticSet)
                    or params.Version):
                raise ValueError("invalid stylistic-set metadata: " + tag)
            names = [(params.UINameID, spec["label"])]
        else:
            if (not isinstance(params, ot.FeatureParamsCharacterVariants)
                    or params.Format):
                raise ValueError("invalid character-variant metadata: " + tag)
            chars = sorted(
                cp for cp in spec["characters"] if cp in font.getBestCmap())
            if params.Character != chars or params.CharCount != len(chars):
                raise ValueError(
                    "character-variant UI character list differs: " + tag)
            if params.NumNamedParameters != len(spec["parameters"]):
                raise ValueError(
                    "character-variant parameter count differs: " + tag)
            if not spec["parameters"] and params.FirstParamUILabelNameID != 0:
                raise ValueError(
                    "unexpected character-variant parameter names")
            names = [(params.FeatUILabelNameID, spec["label"]),
                     (params.FeatUITooltipTextNameID, spec["tooltip"]),
                     (params.SampleTextNameID, "".join(map(chr, chars)))]
            names += [(params.FirstParamUILabelNameID + i, text)
                      for i, text in enumerate(spec["parameters"])]
        for name_id, expected in names:
            record = font["name"].getName(name_id, 3, 1, 0x409)
            if (not 256 <= name_id <= 32767 or name_id in used_names
                    or record is None or record.toUnicode() != expected):
                raise ValueError("invalid feature name reference: " + tag)
            used_names.add(name_id)
