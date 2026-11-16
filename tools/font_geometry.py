"""Normalize CFF assemblies, aliases, and metadata with fontTools.

Restore source-dependent scalars from the local build snapshot.
"""

from __future__ import annotations

import math
from copy import deepcopy
from fractions import Fraction
from math import ceil

from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib.tables import otTables as ot

from config import FONT_REVISION, FONT_VERSION, identity
from math_tables import copy_math_attributes, math_add
from substitution import ssty_mapping


def _mvr(v):
    r = ot.MathValueRecord()
    r.Value = int(v)
    r.DeviceTable = None
    return r


def _cmap(font):
    return font.getBestCmap()


def _bbox(font, gname):
    gs = font.getGlyphSet()
    pen = BoundsPen(gs)
    gs[gname].draw(pen)
    return pen.bounds or (0, 0, 0, 0)


def _sync_cff_sidebearing(font, name):
    """Keep advance and outline intact; derive LSB from the CFF outline.
    """
    width, _ = font["hmtx"][name]
    font["hmtx"][name] = (width, int(round(_bbox(font, name)[0])))


def _set_charstring(font, name, draw_fn, width):
    """Create/replace one CFF1 glyph; ``draw_fn`` receives a pen."""
    top = font["CFF "].cff.topDictIndex[0]
    gs = font.getGlyphSet()
    pen = T2CharStringPen(width - top.Private.nominalWidthX, gs)
    draw_fn(pen)
    cs = pen.getCharString(private=top.Private, globalSubrs=top.GlobalSubrs)
    chars = top.CharStrings
    if name in chars.charStrings:
        idx = chars.charStrings[name]
        if chars.charStringsAreIndexed:
            chars.charStringsIndex.items[idx] = cs
        else:
            chars.charStrings[name] = cs
    else:
        if not chars.charStringsAreIndexed:
            chars.charStrings[name] = cs
        else:
            idx = len(chars.charStringsIndex.items)
            chars.charStringsIndex.items.append(cs)
            chars.charStrings[name] = idx
        order = font.getGlyphOrder() + [name]
        top.charset = order
        font.setGlyphOrder(order)
        font["maxp"].numGlyphs = len(order)
    font["hmtx"].metrics[name] = (int(round(width)), 0)
    _sync_cff_sidebearing(font, name)


def clone_glyph(font, source, clone):
    """Copy a CFF glyph exactly, including its local hints and metrics.
    """
    top = font["CFF "].cff.topDictIndex[0]
    chars = top.CharStrings
    if clone in chars.charStrings:
        raise ValueError("glyph clone already exists: " + clone)
    cs = deepcopy(chars[source])
    # Private and global subroutines belong to the same font, not a new
    # owner.
    cs.private, cs.globalSubrs = top.Private, top.GlobalSubrs
    if chars.charStringsAreIndexed:
        chars.charStrings[clone] = len(chars.charStringsIndex.items)
        chars.charStringsIndex.items.append(cs)
    else:
        chars.charStrings[clone] = cs
    order = font.getGlyphOrder() + [clone]
    top.charset = order
    font.setGlyphOrder(order)
    font["maxp"].numGlyphs = len(order)
    font["hmtx"][clone] = font["hmtx"][source]
    copy_math_attributes(font, source, clone)
    return clone


def _copy_shift(font, src, dst, dy=0, dx=0):
    gs = font.getGlyphSet()
    width, _ = font["hmtx"][src]

    def draw(pen):
        gs[src].draw(TransformPen(pen, Transform(1, 0, 0, 1, dx, dy)))

    _set_charstring(font, dst, draw, width)
    return dst


def _merge_two(font, left, right, dst, dy=0):
    gs = font.getGlyphSet()
    wl, _ = font["hmtx"][left]
    wr, _ = font["hmtx"][right]

    def draw(pen):
        gs[left].draw(TransformPen(pen, Transform(1, 0, 0, 1, 0, dy)))
        gs[right].draw(TransformPen(pen, Transform(1, 0, 0, 1, wl, dy)))

    _set_charstring(font, dst, draw, wl + wr)
    return dst


def _glyph_part(glyph, start, end, full, flags):
    p = ot.GlyphPartRecord()
    p.glyph = glyph
    p.StartConnectorLength = int(start)
    p.EndConnectorLength = int(end)
    p.FullAdvance = int(full)
    p.PartFlags = int(flags)
    return p


def _copy_assembly_geometry(font, template, glyphs):
    """Rebuild an assembly while retaining its source-measured connector
    lengths.
    """
    if template is None:
        raise ValueError("missing pre-font_geometry brace assembly template")
    records = list(template.PartRecords or ())
    if len(records) != len(glyphs):
        raise ValueError("brace assembly template length changed unexpectedly")
    ga = ot.GlyphAssembly()
    ga.ItalicsCorrection = _mvr(
        getattr(getattr(template, "ItalicsCorrection", None), "Value", 0)
    )
    ga.PartRecords = [
        _glyph_part(
            glyph,
            old.StartConnectorLength,
            old.EndConnectorLength,
            font["hmtx"][glyph][0],
            old.PartFlags,
        )
        for old, glyph in zip(records, glyphs)
    ]
    ga.PartCount = len(ga.PartRecords)
    return ga


def _assembly_ymin(font, assembly):
    if assembly is None or not assembly.PartRecords:
        raise ValueError("missing pre-font_geometry overbrace assembly")
    return min(_bbox(font, rec.glyph)[1] for rec in assembly.PartRecords)


def _fix_braces(font):
    """Normalize brace cusp glyphs without re-encoding source
    measurements.
    """
    m = font["MATH"].table
    cmap = _cmap(font)
    og = cmap.get(0x23DE)
    ug = cmap.get(0x23DF)
    if not og or not ug:
        return
    for req in ("braceld", "braceru", "bracelu", "bracerd", "brace.hext"):
        if req not in font.getGlyphOrder():
            return

    hmap = dict(
        zip(
            m.MathVariants.HorizGlyphCoverage.glyphs,
            m.MathVariants.HorizGlyphConstruction,
        )
    )
    ocn = hmap.get(og)
    ucn = hmap.get(ug)
    if ocn is None or ucn is None:
        raise ValueError(
            "brace construction missing from pre-font_geometry font"
        )
    old_over = ocn.GlyphAssembly
    old_under = ucn.GlyphAssembly
    over_target_ymin = _assembly_ymin(font, old_over)

    # TeX brace fill concatenates the two cusp halves directly.  Merge
    # each pair into one fixed non-extender; connector lengths stay
    # those measured from the local source and already stored in the
    # pre-font_geometry assembly.
    oc = "brace.over.center.v18"
    uc = "brace.under.center.v18"
    _merge_two(font, "braceru", "bracelu", oc)
    _merge_two(font, "bracerd", "braceld", uc)

    raw_ymin = min(
        _bbox(font, g)[1] for g in ("braceld", "bracerd", oc, "brace.hext")
    )
    dy = int(round(over_target_ymin - raw_ymin))
    ol = _copy_shift(font, "braceld", "brace.over.left.v18", dy)
    oe = _copy_shift(font, "brace.hext", "brace.over.ext.v18", dy)
    oc2 = _copy_shift(font, oc, "brace.over.center.shift.v18", dy)
    or_ = _copy_shift(font, "bracerd", "brace.over.right.v18", dy)

    ocn.GlyphAssembly = _copy_assembly_geometry(
        font, old_over, [ol, oe, oc2, oe, or_]
    )
    ucn.GlyphAssembly = _copy_assembly_geometry(
        font, old_under, ["bracelu", "brace.hext", uc, "brace.hext", "braceru"]
    )
    # Source braces re-use a dedicated glyph at the Unicode entrance.
    # Retain the former fallback construction with the same finalized
    # assembly too.
    for cp, base, con in ((0x23DE, og, ocn), (0x23DF, ug, ucn)):
        fallback = hmap.get(f"uni{cp:04X}")
        if cp == 0x23DF and base != f"uni{cp:04X}" and fallback is not None:
            fallback.GlyphAssembly = deepcopy(con.GlyphAssembly)
    # Retain the minimum overlap supplied by the native stage.


def _add_cmap_alias(font, cp, glyph):
    for t in font["cmap"].tables:
        if not t.isUnicode():
            continue
        if cp > 0xFFFF and t.format not in (12, 13):
            continue
        t.cmap.setdefault(cp, glyph)


def local_math_values(data):
    values = data.get("constants")
    if not isinstance(values, dict):
        raise ValueError("local MATH snapshot has no constants object")
    return {str(k): int(v) for k, v in values.items()}


def _restore_roundtrip_sensitive_constants(math_table, local_values):
    """Restore scalars FontForge may rewrite, using only the local
    snapshot.
    """
    c = math_table.MathConstants
    for name in ("ScriptPercentScaleDown", "ScriptScriptPercentScaleDown"):
        if name not in local_values:
            raise ValueError(f"local MATH snapshot missing {name}")
        setattr(c, name, int(local_values[name]))
    if "SpaceAfterScript" not in local_values:
        raise ValueError("local MATH snapshot missing SpaceAfterScript")
    c.SpaceAfterScript.Value = int(local_values["SpaceAfterScript"])


def preserve_windows_ansi_compatibility(font):
    """Preserve Windows ANSI font selection for this converter's math
    face.
    """
    cmap = font.getBestCmap() or {}
    names = set(font.getGlyphOrder())
    missing = [
        cp
        for cp in range(0x20, 0x7F)
        if cmap.get(cp) == ".notdef" or cmap.get(cp) not in names
    ]
    if missing:
        raise ValueError(
            "ASCII cmap missing valid glyphs: "
            + ", ".join(f"U+{cp:04X}" for cp in missing)
        )
    font["OS/2"].ulCodePageRange1 |= 1


def update_average_width(font):
    """Derive average advance from each nonzero-width GID once."""
    widths = [
        font["hmtx"][name][0]
        for name in font.getGlyphOrder()
        if font["hmtx"][name][0] != 0
    ]
    if not widths:
        raise ValueError("xAvgCharWidth: no nonzero advances")
    average = (2 * sum(widths) + len(widths)) // (2 * len(widths))
    if not 0 <= average <= 32767:
        raise ValueError("xAvgCharWidth: average outside FWORD range")
    font["OS/2"].xAvgCharWidth = average


def edit(f, *, edition, local_values):
    if "MATH" not in f or "CFF " not in f:
        raise ValueError("expected CFF OpenType MATH font")
    m = f["MATH"].table
    _restore_roundtrip_sensitive_constants(m, local_values)

    m.MathGlyphInfo.MathKernInfo = None

    cmap = _cmap(f)
    nabla = cmap.get(0x2207)
    if nabla:
        _add_cmap_alias(f, 0x1D6FB, nabla)

    # Base integrals are ExtendedShape so the OpenType math engine uses
    # large-operator script/limit placement.
    cov = m.MathGlyphInfo.ExtendedShapeCoverage
    glyphs = set(cov.glyphs if cov else [])
    for cp in range(0x222B, 0x2234):
        g = cmap.get(cp)
        if g:
            glyphs.add(g)
    if cov:
        cov.glyphs = sorted(glyphs, key=f.getGlyphID)

    _fix_braces(f)
    _sync_cff_sidebearing(f, ".notdef")

    # Canonical single-face install identity.
    family, psname, unique_id = identity(edition)

    # Fixed technical metadata for Windows compatibility.
    preserve_windows_ansi_compatibility(f)
    update_average_width(f)
    f["head"].fontRevision = FONT_REVISION
    f["name"].names = [n for n in f["name"].names if n.nameID not in (3, 5)]
    replacements = {
        1: family,
        2: "Regular",
        4: family,
        6: psname,
        16: family,
        17: "Regular",
    }
    for n in f["name"].names:
        repl = replacements.get(n.nameID)
        if repl is not None:
            try:
                n.string = repl.encode(n.getEncoding(), errors="replace")
            except Exception:
                pass
    for platformID, platEncID, langID in ((1, 0, 0), (3, 1, 0x0409)):
        f["name"].setName(unique_id, 3, platformID, platEncID, langID)
        f["name"].setName(FONT_VERSION, 5, platformID, platEncID, langID)
    top = f["CFF "].cff.topDictIndex[0]
    f["CFF "].cff.fontNames = [psname]
    top.FontName = psname
    top.FullName = family
    top.FamilyName = family
    top.Weight = "Regular"
    try:
        del top.version
    except Exception:
        pass
    top.rawDict.pop("version", None)


def aggregate_values(font):
    """Derive specified CFF/head/hhea aggregates from every actual
    glyph.
    """
    gs = font.getGlyphSet()
    bounds = {}
    combined = None
    for name in font.getGlyphOrder():
        pen = BoundsPen(gs)
        gs[name].draw(pen)
        if pen.bounds is not None:
            bounds[name] = pen.bounds
            x0, y0, x1, y1 = pen.bounds
            combined = (
                (x0, y0, x1, y1)
                if combined is None
                else (
                    min(combined[0], x0),
                    min(combined[1], y0),
                    max(combined[2], x1),
                    max(combined[3], y1),
                )
            )
    box = [
        math.floor(combined[0]),
        math.floor(combined[1]),
        math.ceil(combined[2]),
        math.ceil(combined[3]),
    ]
    widths = {n: math.ceil(b[2]) - math.floor(b[0]) for n, b in bounds.items()}
    metrics = font["hmtx"].metrics
    hhea = {
        "advanceWidthMax": max(v[0] for v in metrics.values()),
        "minLeftSideBearing": min(metrics[n][1] for n in widths),
        "minRightSideBearing": min(
            metrics[n][0] - metrics[n][1] - w for n, w in widths.items()
        ),
        "xMaxExtent": max(metrics[n][1] + w for n, w in widths.items()),
    }
    return {"FontBBox": box, "head_bbox": box, "hhea": hhea}


def construction_map(font, direction):
    variants = font["MATH"].table.MathVariants
    return dict(
        zip(
            getattr(variants, direction + "GlyphCoverage").glyphs,
            getattr(variants, direction + "GlyphConstruction"),
        )
    )


def build_horizontal_arrow_connectors(font):
    """Use the straight shaft outside each arrowhead's curve hull."""
    horizontal = construction_map(font, "Horiz")
    minimum = font["MATH"].table.MathVariants.MinConnectorOverlap
    records = []
    for cp in (0x2190, 0x2192, 0x2194, 0x21D0, 0x21D2, 0x21D4):
        root = font.getBestCmap()[cp]
        for part in horizontal[root].GlyphAssembly.PartRecords:
            pen = RecordingPen()
            font.getGlyphSet()[part.glyph].draw(pen)
            curve_x = [
                p[0] for op, points in pen.value
                if op in ("curveTo", "qCurveTo") for p in points
            ]
            xmin, _, xmax, _ = _bbox(font, part.glyph)
            for start, field in (
                (True, "StartConnectorLength"),
                (False, "EndConnectorLength"),
            ):
                old = getattr(part, field)
                if not old:
                    continue
                if not curve_x:
                    length = int(xmax - xmin)
                elif start:
                    length = int(min(curve_x) - xmin)
                else:
                    length = int(xmax - max(curve_x))
                if not minimum <= length <= part.FullAdvance:
                    raise ValueError("arrow shaft cannot accommodate overlap")
                setattr(part, field, length)
                records.append(dict(
                    root=root, glyph=part.glyph, field=field,
                    before=old, after=length,
                ))
    return records


def build_left_vector(font):
    """Mirror the final right-vector growth and optical styles."""
    from math_tables import metrics_values

    variants = font["MATH"].table.MathVariants
    info = font["MATH"].table.MathGlyphInfo
    horizontal = construction_map(font, "Horiz")
    optical = ssty_mapping(font)
    left = font.getBestCmap()[0x20D6]
    right = font.getBestCmap()[0x20D7]
    if left in optical:
        raise ValueError("left vector optical route already present")
    _, anchors = metrics_values(font)
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    extended = info.ExtendedShapeCoverage.glyphs

    def mirror(source, name, center_sum, width):
        glyphs = font.getGlyphSet()
        _set_charstring(
            font, name,
            lambda pen: glyphs[source].draw(TransformPen(
                pen, Transform(-1, 0, 0, 1, center_sum, 0)
            )), width,
        )
        math_add(font, name, 0, round(center_sum - anchors[source]))
        if source in classes:
            classes[name] = classes[source]
        extended.append(name)

    roots = []
    records = []
    for i, (style, source) in enumerate(zip(
        ("T", "S", "SS"), [right] + list(optical[right])
    )):
        root = left + (".ssty" + str(i) if i else "")
        roots.append(root)
        if i:
            bounds = _bbox(font, source)
            mirror(source, root, bounds[0] + bounds[2], 0)
        old = horizontal[source]
        shaft, end = old.GlyphAssembly.PartRecords
        if not shaft.PartFlags & 1 or end.PartFlags & 1:
            raise ValueError("unexpected right vector assembly order")
        name = "standard.leftvector.end." + style
        mirror(end.glyph, name, end.FullAdvance, end.FullAdvance)
        new = deepcopy(old)
        endpoint = deepcopy(end)
        endpoint.glyph = name
        endpoint.StartConnectorLength = 0
        endpoint.EndConnectorLength = end.StartConnectorLength
        new.GlyphAssembly.PartRecords = [endpoint, deepcopy(shaft)]
        new.MathGlyphVariantRecord[0].VariantGlyph = root
        new.MathGlyphVariantRecord[1].VariantGlyph = name
        horizontal[root] = new
        records.append(dict(
            style=style, root=root, source=source, end=name,
            AM=[v.AdvanceMeasurement for v in new.MathGlyphVariantRecord],
            connector=endpoint.EndConnectorLength,
        ))
    optical[left] = roots[1:]
    extended.sort(key=font.getGlyphID)
    pairs = sorted(horizontal.items(), key=lambda p: font.getGlyphID(p[0]))
    variants.HorizGlyphCoverage.glyphs = [n for n, c in pairs]
    variants.HorizGlyphConstruction = [c for n, c in pairs]
    variants.HorizGlyphCount = len(pairs)
    return dict(styles=records, fixed_left_root_unchanged=True)


def build_overbrace(font, inventory):
    """Construct final ordinary/Plain recipes at 569; Curly stays at
    539.
    """
    horizontal = construction_map(font, "Horiz")
    imports = {(r["tag"], r["slot"]): r["glyph"] for r in inventory["imports"]}
    ordinary = font.getBestCmap()[0x23DE]
    curly = imports["exe", 176]
    records = []
    for root, template in (
        (ordinary, horizontal[curly].GlyphAssembly),
        ("brace.plain.over", horizontal["brace.plain.over"].GlyphAssembly),
    ):
        final = deepcopy(template)
        clones = {}
        for part in final.PartRecords:
            if part.glyph not in clones:
                clone = part.glyph + ".c07"
                _copy_shift(font, part.glyph, clone, 30)
                copy_math_attributes(font, part.glyph, clone)
                clones[part.glyph] = clone
            part.glyph = clones[part.glyph]
        horizontal[root].GlyphAssembly = final
        if root == ordinary:
            fixed = [p.glyph for p in final.PartRecords if not p.PartFlags & 1]
            if len(fixed) != 3:
                raise ValueError(
                    "ordinary overbrace requires three fixed parts"
                )
            glyphs = font.getGlyphSet()
            widths = [font["hmtx"][n][0] for n in fixed]

            def draw(pen):
                x = 0
                for name, width in zip(fixed, widths):
                    glyphs[name].draw(
                        TransformPen(pen, Transform(1, 0, 0, 1, x, 0))
                    )
                    x += width

            _set_charstring(font, root, draw, sum(widths))
        else:
            _copy_shift(font, root, root, 30)
        records.append(
            dict(
                root=root,
                parts=clones,
                baseline=569,
                fallback_width=font["hmtx"][root][0],
            )
        )
    return dict(constructions=records, curly_baseline=539)


def build_groups(font, inventory):
    """Original small group designs with independently owned MID-free
    recipes.
    """
    native = {(r["tag"], r["slot"]): r["glyph"] for r in inventory["imports"]}
    vertical = construction_map(font, "Vert")
    variants = font["MATH"].table.MathVariants
    ssty = ssty_mapping(font)
    output = []
    for cp, paren, brace, small, top, bot, rep in [
        (0x27EE, 0x28, 0x7B, 46, 56, 58, 136),
        (0x27EF, 0x29, 0x7D, 47, 57, 59, 62),
    ]:
        parent = font.getBestCmap()[paren]
        root = f"uni{cp:04X}"
        _copy_shift(font, parent, root)
        copy_math_attributes(font, parent, root)
        # Preserve corresponding optical small designs without sharing
        # the complete parenthesis MATH root or growing through its
        # variants.
        styled = []
        for level, n in enumerate(ssty.get(parent, ()), 1):
            name = root + ".ssty" + str(level)
            _copy_shift(font, n, name)
            copy_math_attributes(font, n, name)
            styled.append(name)
        if styled:
            ssty[root] = styled
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[cp] = root
        old = vertical[font.getBestCmap()[brace]].GlyphAssembly
        parts = {}
        for p in old.PartRecords:
            for slot in (top, bot, rep):
                if p.glyph == native["exa", slot] + ".vn":
                    parts[slot] = p
        if set(parts) != {top, bot, rep}:
            raise ValueError("missing original normalized group parts")
        ga = deepcopy(old)
        ga.PartRecords = [deepcopy(parts[s]) for s in [bot, rep, top]]
        ga.PartCount = 3
        # Outer ends need no connector, same as the already measured
        # parts.
        if (
            ga.PartRecords[0].StartConnectorLength != 0
            or ga.PartRecords[-1].EndConnectorLength != 0
        ):
            raise ValueError("group outer connector mismatch")
        c = ot.MathGlyphConstruction()
        c.GlyphAssembly = ga
        v = ot.MathGlyphVariantRecord()
        v.VariantGlyph = root
        bb = _bbox(font, root)
        v.AdvanceMeasurement = math.ceil(bb[3] - bb[1]) + 1
        c.MathGlyphVariantRecord = [v]
        c.VariantCount = 1
        variants.VertGlyphCoverage.glyphs.append(root)
        variants.VertGlyphConstruction.append(c)
        variants.VertGlyphCount += 1
        output.append(
            dict(
                Unicode=cp,
                root=root,
                source_small=("mit", small),
                source_recipe=dict(TOP=top, BOT=bot, REP=rep),
                small_AM=v.AdvanceMeasurement,
                parts=[
                    dict(
                        glyph=p.glyph,
                        start=p.StartConnectorLength,
                        end=p.EndConnectorLength,
                        full=p.FullAdvance,
                        flags=p.PartFlags,
                    )
                    for p in ga.PartRecords
                ],
                no_MID=True,
                small_styles=styled,
            )
        )
    # Coverage must be in glyph-ID order for serialization and engine
    # lookup.
    pairs = sorted(
        zip(variants.VertGlyphCoverage.glyphs, variants.VertGlyphConstruction),
        key=lambda p: font.getGlyphID(p[0]),
    )
    variants.VertGlyphCoverage.glyphs = [p[0] for p in pairs]
    variants.VertGlyphConstruction = [p[1] for p in pairs]
    return output


def _check_bar_rectangles(path, bounds, count):
    """Require one or two disjoint, axis-aligned rectangular contours.
    """
    operations = ["moveTo", "lineTo", "lineTo", "lineTo", "closePath"]
    if [op for op, _ in path] != operations * count:
        raise ValueError("bar part has unexpected rectangular contours")
    intervals = []
    for offset in range(0, len(path), 5):
        contour = path[offset:offset + 5]
        if any(len(pts) != 1 for _, pts in contour[:-1]) or contour[-1][1]:
            raise ValueError("bar part has invalid contour operands")
        points = [pts[0] for _, pts in contour[:-1]]
        x0, x1 = min(x for x, _ in points), max(x for x, _ in points)
        y0, y1 = bounds[1], bounds[3]
        if x0 >= x1 or y0 >= y1 or set(points) != {
            (x0, y0), (x0, y1), (x1, y0), (x1, y1)
        }:
            raise ValueError("bar part is not a full-height rectangle")
        for (xa, ya), (xb, yb) in zip(points, points[1:] + points[:1]):
            if (xa == xb) == (ya == yb):
                raise ValueError("bar part has a diagonal or zero-length edge")
        intervals.append((x0, x1))
    intervals.sort()
    if any(a[1] >= b[0] for a, b in zip(intervals, intervals[1:])):
        raise ValueError("bar part rectangles are not separated")


def build_angle_bar_sizes(font):
    """Fill the adopted angle-bracket gaps and match vertical bar sizes.

    Keep the source outlines/metrics intact. Interpolate
    corresponding vertices and advance widths between adjacent source
    angles, after aligning their ink centers. Bars retain the
    extension part's x coordinates and advance. Assembly records are
    not changed here.
    """
    variants = font["MATH"].table.MathVariants
    cmap = font.getBestCmap()
    constructions = construction_map(font, "Vert")
    axis = font["MATH"].table.MathConstants.AxisHeight.Value
    upm = font["head"].unitsPerEm
    targets = [round(Fraction(n, 100) * upm) for n in (110, 145, 210)]
    added, report = [], {}

    def path(name):
        pen = RecordingPen()
        font.getGlyphSet()[name].draw(pen)
        return pen.value

    def record(name):
        r = ot.MathGlyphVariantRecord()
        r.VariantGlyph = name
        b = _bbox(font, name)
        r.AdvanceMeasurement = ceil(b[3] - b[1]) + 1
        return r

    reference_bounds = None
    for cp in (0x27E8, 0x27E9):
        root = cmap[cp]
        con = constructions[root]
        original = list(con.MathGlyphVariantRecord)
        if len(original) != 5 or con.GlyphAssembly:
            raise ValueError("expected five source angle sizes")
        names = [r.VariantGlyph for r in original]
        boxes = [_bbox(font, name) for name in names]
        sizes = [b[3] - b[1] for b in boxes]
        records, derivation = list(original), []
        for height in targets:
            i = next(
                (i for i in range(4) if sizes[i] < height < sizes[i + 1]),
                None,
            )
            if i is None:
                raise ValueError("angle interpolation target not bracketed")
            a, b = names[i:i + 2]
            pa, pb = path(a), path(b)
            if (
                [op for op, _ in pa] != [op for op, _ in pb]
                or [op for op, _ in pa]
                != ["moveTo", *(["lineTo"] * 5), "closePath"]
            ):
                raise ValueError("source angle contours do not correspond")
            ratio = Fraction(height - sizes[i], sizes[i + 1] - sizes[i])
            ca = Fraction(boxes[i][1] + boxes[i][3], 2)
            cb = Fraction(boxes[i + 1][1] + boxes[i + 1][3], 2)
            points = []
            for (op, aa), (_, bb) in zip(pa, pb):
                coords = tuple(
                    (
                        round(xa + ratio * (xb - xa)),
                        round(axis + ya - ca + ratio * (yb - cb - ya + ca)),
                    )
                    for (xa, ya), (xb, yb) in zip(aa, bb)
                )
                points.append((op, coords))
            name = f"{root}.interpolated{height}"
            width = round(
                font["hmtx"][a][0]
                + ratio * (font["hmtx"][b][0] - font["hmtx"][a][0])
            )

            def draw(pen):
                for op, coords in points:
                    getattr(pen, op)(*coords)

            _set_charstring(font, name, draw, width)
            records.append(record(name))
            added.append(name)
            derivation.append(
                dict(
                    glyph=name, sources=[a, b], ratio=str(ratio),
                    height=height, advance=width,
                )
            )
        records.sort(key=lambda r: r.AdvanceMeasurement)
        con.MathGlyphVariantRecord = records
        con.VariantCount = len(records)
        angle_boxes = [_bbox(font, r.VariantGlyph) for r in records]
        current_bounds = [(b[1], b[3]) for b in angle_boxes]
        if reference_bounds is None:
            reference_bounds = current_bounds
        elif reference_bounds != current_bounds:
            raise ValueError("left/right angle ink bounds differ")
        report[root] = derivation

    for cp, alias, count in ((0x007C, 0x2223, 1), (0x2016, 0x2225, 2)):
        root = cmap[cp]
        con = constructions[root]
        if len(con.MathGlyphVariantRecord) != 1 or not con.GlyphAssembly:
            raise ValueError("expected source bar with repeat-only assembly")
        parts = con.GlyphAssembly.PartRecords
        sources = {p.glyph for p in parts}
        if len(sources) != 1:
            raise ValueError("bar assembly uses distinct parts")
        source = next(iter(sources))
        source_path = path(source)
        box = _bbox(font, source)
        _check_bar_rectangles(source_path, box, count)
        records, derivation = list(con.MathGlyphVariantRecord), []
        for y_min, y_max in reference_bounds[1:]:
            height = y_max - y_min
            name = f"{root}.sized{height}"

            def draw(pen):
                for op, pts in source_path:
                    # Match both ink bounds, not only their difference:
                    # LuaTeX rounds height and depth separately at S/SS.
                    coords = tuple(
                        (x, y_max if y == box[3] else y_min)
                        for x, y in pts
                    )
                    getattr(pen, op)(*coords)

            _set_charstring(font, name, draw, font["hmtx"][source][0])
            records.append(record(name))
            added.append(name)
            derivation.append(dict(glyph=name, source=source, height=height))
        for name in (root, cmap[alias]):
            constructions[name].MathGlyphVariantRecord = deepcopy(records)
            constructions[name].VariantCount = len(records)
        report[root] = derivation

    cov = font["MATH"].table.MathGlyphInfo.ExtendedShapeCoverage
    cov.glyphs = sorted(set(cov.glyphs) | set(added), key=font.getGlyphID)
    return dict(
        added=added, sources=report, assembly_unchanged=True,
        min_overlap=variants.MinConnectorOverlap,
    )


def source_glyph(face, slot):
    glyphs = face.font.getGlyphSet()
    name = face.font["Encoding"][slot]
    if name == ".notdef" or slot not in face.raw_metrics().chars:
        raise ValueError("standard accent source slot absent")
    p = RecordingPen()
    b = BoundsPen(glyphs)
    glyphs[name].draw(p)
    glyphs[name].draw(b)
    return dict(
        slot=slot,
        name=name,
        path=p.value,
        bbox=b.bounds,
        metrics=face.raw_metrics().chars[slot],
    )


def rectangle(data):
    path = data["path"]
    x0, y0, x1, y1 = data["bbox"]
    if [op for op, _ in path] != [
        "moveTo",
        "lineTo",
        "lineTo",
        "lineTo",
        "closePath",
    ] or {pts[0] for _, pts in path[:-1]} != {
        (x0, y0),
        (x1, y0),
        (x0, y1),
        (x1, y1),
    }:
        raise ValueError("source bar/minus is not an exact rectangle")
    return x1 - x0, y0, y1


def measure(face):
    data = {s: source_glyph(face, s) for s in [0, 33, 69, 78, 120, 83]}
    bars = [rectangle(data[s]) for s in [78, 120, 83]]
    minus, y0, y1 = rectangle(data[0])
    arrow = data[33]
    ax0, _, ax1, _ = arrow["bbox"]
    head = [
        (x, y) for _, pts in arrow["path"] for x, y in pts if y < y0 or y > y1
    ]
    q = min(x for x, y in head)
    connector = min(minus, q - ax0)
    horizontals = []
    prev = None
    for op, pts in arrow["path"]:
        if op == "lineTo" and prev:
            x, y = pts[0]
            px, py = prev
            if y == py and y in (y0, y1):
                horizontals.append((y, min(x, px), max(x, px)))
        if pts:
            prev = pts[-1]
    if not all(
        any(
            yy == y and a <= ax0 and b >= ax0 + connector
            for yy, a, b in horizontals
        )
        for y in [y0, y1]
    ):
        raise ValueError("source vector connector leaves straight region")
    if any(data[s]["metrics"].get("italic", 0) for s in [33, 78, 120, 83]):
        raise ValueError("source assembly IC unexpectedly nonzero")
    return data, bars, connector, ax1 - ax0, (y0, y1)


def construction(names, advances, records):
    c = ot.MathGlyphConstruction()
    c.MathGlyphVariantRecord = []
    for name, advance in zip(names, advances):
        v = ot.MathGlyphVariantRecord()
        v.VariantGlyph = name
        v.AdvanceMeasurement = ceil(advance)
        c.MathGlyphVariantRecord.append(v)
    c.VariantCount = len(c.MathGlyphVariantRecord)
    ga = ot.GlyphAssembly()
    ga.ItalicsCorrection = _mvr(0)
    ga.PartRecords = [_glyph_part(*r) for r in records]
    ga.PartCount = len(records)
    c.GlyphAssembly = ga
    return c


def build_standard_accents(font, catalog):
    """Construct final standard accents at the CFF measurement boundary.
    """
    M = font["MATH"].table
    V = M.MathVariants
    dy = M.MathConstants.AccentBaseHeight.Value
    if dy != 457 or V.MinConnectorOverlap != 20:
        raise ValueError("standard accent baseline/overlap policy differs")
    cmap = font.getBestCmap()
    ssty = ssty_mapping(font)
    oldbar = cmap[0x304]
    vec = cmap[0x20D7]
    if cmap.get(0x305) != oldbar:
        raise ValueError("expected native fixed-bar source alias")
    fixedbars = [oldbar] + list(ssty[oldbar])
    fixedvecs = [vec] + list(ssty[vec])
    wbar = [cmap[0xE24E]] + list(ssty[cmap[0xE24E]])
    wwbar = [cmap[0xE24A]] + list(ssty[cmap[0xE24A]])
    if any(len(x) != 3 for x in [fixedbars, fixedvecs, wbar, wwbar]):
        raise ValueError("three optical roots required")
    h = dict(zip(V.HorizGlyphCoverage.glyphs, V.HorizGlyphConstruction))
    report = []
    roots = []
    for i, (style, role) in enumerate(
        (("T", "syt"), ("S", "syt_s"), ("SS", "syt_ss"))
    ):
        face = catalog.faces[role]
        data, bars, C, R, minus_y = measure(face)
        B, by0, by1 = bars[-1]
        if not 0 < V.MinConnectorOverlap < min(B, C):
            raise ValueError("connector cannot accommodate common overlap")
        root = "uni0305" + ("" if i == 0 else ".ssty" + str(i))
        roots.append(root)
        _copy_shift(font, fixedbars[i], root)
        # Fixed accents include half-unit coordinates. Preserve them
        # exactly; the generic new-outline helper intentionally rounds
        # near integers.
        top = font["CFF "].cff.topDictIndex[0]
        pen = T2CharStringPen(
            font["hmtx"][fixedbars[i]][0] - top.Private.nominalWidthX,
            font.getGlyphSet(),
            roundTolerance=0,
        )
        font.getGlyphSet()[fixedbars[i]].draw(pen)
        cs = pen.getCharString(
            private=top.Private,
            globalSubrs=top.GlobalSubrs,
        )
        top.CharStrings.charStringsIndex.items[
            top.CharStrings.charStrings[root]
        ] = cs
        font["hmtx"][root] = font["hmtx"][fixedbars[i]]
        copy_math_attributes(font, fixedbars[i], root)
        bp = "standard.overbar.part." + style
        shaft = "standard.vector.shaft." + style
        end = "standard.vector.end." + style

        def rect(name, width, y0, y1):
            def draw(pen):
                pen.moveTo((0, y0))
                pen.lineTo((width, y0))
                pen.lineTo((width, y1))
                pen.lineTo((0, y1))
                pen.closePath()

            _set_charstring(font, name, draw, width)

        glyphs = face.font.getGlyphSet()

        def draw_bar(pen):
            glyphs[data[83]["name"]].draw(
                TransformPen(
                    pen,
                    Transform(1, 0, 0, 1, -data[83]["bbox"][0], 0),
                )
            )

        _set_charstring(font, bp, draw_bar, B)
        rect(shaft, C, minus_y[0] + dy, minus_y[1] + dy)
        glyphs = face.font.getGlyphSet()
        source = glyphs[data[33]["name"]]
        dx = -data[33]["bbox"][0]

        def draw_arrow(pen):
            source.draw(TransformPen(pen, Transform(1, 0, 0, 1, dx, dy)))

        _set_charstring(font, end, draw_arrow, R)
        ta = int(round(1000 * data[33]["metrics"]["width"]) / 2 + dx)
        math_add(font, end, 0, ta)
        h[root] = construction(
            [root, wbar[i], wwbar[i]],
            [b[0] for b in bars],
            [(bp, 0, B, B, 0), (bp, B, B, B, 1), (bp, B, 0, B, 0)],
        )
        vb = data[69]["bbox"]
        h[fixedvecs[i]] = construction(
            [fixedvecs[i], end],
            [vb[2] - vb[0], R],
            [(shaft, C, C, C, 1), (end, C, 0, R, 0)],
        )
        report.append(
            dict(
                style=style,
                source=face.stem,
                bar_root=root,
                vec_root=fixedvecs[i],
                bar_variants=[root, wbar[i], wwbar[i]],
                bar_AM=[b[0] for b in bars],
                bar_part=bp,
                B=B,
                bar_y=[by0, by1],
                shaft=shaft,
                C=C,
                end=end,
                R=R,
                end_TA=ta,
                dy=dy,
                vec_AM=[vb[2] - vb[0], R],
            )
        )
    ssty[roots[0]] = roots[1:]
    oldroots = {"wideoverbar.compat", "widevector.compat"}
    for root in oldroots:
        h.pop(root, None)
    for table in font["cmap"].tables:
        if table.isUnicode():
            table.cmap[0x305] = roots[0]
            table.cmap.pop(0xE286, None)
            table.cmap.pop(0xE287, None)
    pairs = sorted(h.items(), key=lambda pair: font.getGlyphID(pair[0]))
    V.HorizGlyphCoverage.glyphs = [n for n, c in pairs]
    V.HorizGlyphConstruction = [c for n, c in pairs]
    V.HorizGlyphCount = len(pairs)
    return dict(
        styles=report,
        retired_public_PUA=["U+E286", "U+E287"],
        MinConnectorOverlap=V.MinConnectorOverlap,
        overbar_constants_unchanged=True,
        source_measurement=(
            "Catalog original PFB paths and raw TFM; "
            "no supplied numeric dictionary"
        ),
    )


class AlphabetGlyphs:
    """Resolve source identities without deciding public alphabet
    policy.
    """

    def __init__(self, font, catalog):
        from collections import defaultdict

        from math_tables import metrics_values

        self.font, self.catalog = font, catalog
        self.sources = {}
        self.index = defaultdict(list)
        ic, ta = metrics_values(font)
        for name in font.getGlyphOrder():
            key = (
                self.pathkey(font.getGlyphSet(), name),
                font["hmtx"][name][0],
                ic.get(name, 0),
                ta.get(name, round(font["hmtx"][name][0] / 2)),
            )
            self.index[key].append(name)

    @staticmethod
    def pathkey(glyphs, name):
        from fontTools.pens.recordingPen import DecomposingRecordingPen

        pen = DecomposingRecordingPen(glyphs)
        glyphs[name].draw(pen)
        return repr(pen.value)

    def bind(self, role, slot, names):
        import mapping

        for suffix, name in zip(mapping.ALPHABET_SUFFIX, names):
            if name in self.font.getGlyphOrder():
                self.catalog.require(
                    role + suffix, slot, "existing outline identity"
                )
                self.sources[role + suffix, slot] = name

    def glyph(self, role, slot):
        from math_metrics import source_values

        self.catalog.require(role, slot, "alphabet route")
        if (role, slot) in self.sources:
            return self.sources[role, slot]
        record = self.catalog.source_record(role, slot)
        values = source_values(self.catalog, role, slot)
        glyphs = record["font"].getGlyphSet()
        source = record["name"]
        key = (
            self.pathkey(glyphs, source),
            values["width"],
            values["IC"],
            values["TopAccent"],
        )
        found = self.index.get(key, ())
        if found:
            name = found[0]
        else:
            name = f"trial.{self.catalog.faces[role].stem}.s{slot:03d}"
            font = self.font
            top = font["CFF "].cff.topDictIndex[0]
            if name in top.CharStrings.charStrings:
                raise ValueError("source identity collision: " + name)
            pen = T2CharStringPen(
                values["width"] - top.Private.nominalWidthX, glyphs
            )
            glyphs[source].draw(pen)
            char = pen.getCharString(
                private=top.Private, globalSubrs=font["CFF "].cff.GlobalSubrs
            )
            top.CharStrings.charStrings[name] = len(
                top.CharStrings.charStringsIndex.items
            )
            top.CharStrings.charStringsIndex.items.append(char)
            top.charset.append(name)
            font.setGlyphOrder(list(top.charset))
            bounds = BoundsPen(glyphs)
            glyphs[source].draw(bounds)
            font["hmtx"][name] = (
                values["width"],
                round(bounds.bounds[0] if bounds.bounds else 0),
            )
            math_add(font, name, values["IC"], values["TopAccent"])
            self.index[key].append(name)
        self.sources[role, slot] = name
        return name

    def provenance(self):
        return [
            dict(role=role, slot=slot, glyph=name)
            for (role, slot), name in self.sources.items()
        ]


def bind_cmap(font, cmap):
    for table in font["cmap"].tables:
        if table.isUnicode():
            table.cmap = {
                cp: name
                for cp, name in cmap.items()
                if cp < 65536 or table.format in (12, 13)
            }
    font["maxp"].numGlyphs = len(font.getGlyphOrder())
