"""Normalize CFF assemblies, aliases, and metadata with fontTools.

Restore source-dependent scalars from the local build snapshot.
"""

from __future__ import annotations

import math
from copy import deepcopy

from fontTools.ttLib.tables import otTables as ot
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen

from config import FONT_REVISION, FONT_VERSION, identity


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
    width, _ = font['hmtx'][name]
    font['hmtx'][name] = (width, int(round(_bbox(font, name)[0])))


def _set_charstring(font, name, draw_fn, width):
    """Create/replace one CFF1 glyph; ``draw_fn`` receives a pen."""
    top = font['CFF '].cff.topDictIndex[0]
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
        font['maxp'].numGlyphs = len(order)
    font['hmtx'].metrics[name] = (int(round(width)), 0)
    _sync_cff_sidebearing(font, name)


def _copy_shift(font, src, dst, dy=0, dx=0):
    gs = font.getGlyphSet()
    width, _ = font['hmtx'][src]

    def draw(pen):
        gs[src].draw(TransformPen(pen, Transform(1, 0, 0, 1, dx, dy)))

    _set_charstring(font, dst, draw, width)
    return dst


def _merge_two(font, left, right, dst, dy=0):
    gs = font.getGlyphSet()
    wl, _ = font['hmtx'][left]
    wr, _ = font['hmtx'][right]

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
        raise ValueError('missing pre-font_geometry brace assembly template')
    records = list(template.PartRecords or ())
    if len(records) != len(glyphs):
        raise ValueError('brace assembly template length changed unexpectedly')
    ga = ot.GlyphAssembly()
    ga.ItalicsCorrection = _mvr(
        getattr(getattr(template, 'ItalicsCorrection', None), 'Value', 0)
    )
    ga.PartRecords = [
        _glyph_part(
            glyph,
            old.StartConnectorLength,
            old.EndConnectorLength,
            font['hmtx'][glyph][0],
            old.PartFlags,
        )
        for old, glyph in zip(records, glyphs)
    ]
    ga.PartCount = len(ga.PartRecords)
    return ga


def _assembly_ymin(font, assembly):
    if assembly is None or not assembly.PartRecords:
        raise ValueError('missing pre-font_geometry overbrace assembly')
    return min(_bbox(font, rec.glyph)[1] for rec in assembly.PartRecords)


def _fix_braces(font):
    """Normalize brace cusp glyphs without re-encoding source
    measurements.
    """
    m = font['MATH'].table
    cmap = _cmap(font)
    og = cmap.get(0x23DE)
    ug = cmap.get(0x23DF)
    if not og or not ug:
        return
    for req in ('braceld', 'braceru', 'bracelu', 'bracerd', 'brace.hext'):
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
            'brace construction missing from pre-font_geometry font'
        )
    old_over = ocn.GlyphAssembly
    old_under = ucn.GlyphAssembly
    over_target_ymin = _assembly_ymin(font, old_over)

    # TeX brace fill concatenates the two cusp halves directly.  Merge
    # each pair into one fixed non-extender; connector lengths stay
    # those measured from the local source and already stored in the
    # pre-font_geometry assembly.
    oc = 'brace.over.center.v18'
    uc = 'brace.under.center.v18'
    _merge_two(font, 'braceru', 'bracelu', oc)
    _merge_two(font, 'bracerd', 'braceld', uc)

    raw_ymin = min(
        _bbox(font, g)[1] for g in ('braceld', 'bracerd', oc, 'brace.hext')
    )
    dy = int(round(over_target_ymin - raw_ymin))
    ol = _copy_shift(font, 'braceld', 'brace.over.left.v18', dy)
    oe = _copy_shift(font, 'brace.hext', 'brace.over.ext.v18', dy)
    oc2 = _copy_shift(font, oc, 'brace.over.center.shift.v18', dy)
    or_ = _copy_shift(font, 'bracerd', 'brace.over.right.v18', dy)

    ocn.GlyphAssembly = _copy_assembly_geometry(
        font, old_over, [ol, oe, oc2, oe, or_]
    )
    ucn.GlyphAssembly = _copy_assembly_geometry(
        font, old_under, ['bracelu', 'brace.hext', uc, 'brace.hext', 'braceru']
    )
    # Source braces re-use a dedicated glyph at the Unicode entrance.
    # Retain the former fallback construction with the same
    # finalized assembly too.
    for cp, base, con in ((0x23DE, og, ocn), (0x23DF, ug, ucn)):
        fallback = hmap.get(f'uni{cp:04X}')
        if base != f'uni{cp:04X}' and fallback is not None:
            fallback.GlyphAssembly = deepcopy(con.GlyphAssembly)
    # MinConnectorOverlap is intentionally left untouched: the FontForge
    # stage computed it from the local source outlines and
    # serialized it already.


def _add_cmap_alias(font, cp, glyph):
    for t in font['cmap'].tables:
        if not t.isUnicode():
            continue
        if cp > 0xFFFF and t.format not in (12, 13):
            continue
        t.cmap.setdefault(cp, glyph)


def local_math_values(data):
    values = data.get('constants')
    if not isinstance(values, dict):
        raise ValueError('local MATH snapshot has no constants object')
    return {str(k): int(v) for k, v in values.items()}


def _restore_roundtrip_sensitive_constants(math_table, local_values):
    """Restore scalars FontForge may rewrite, using only the local
    snapshot.
    """
    c = math_table.MathConstants
    for name in ('ScriptPercentScaleDown', 'ScriptScriptPercentScaleDown'):
        if name not in local_values:
            raise ValueError(f'local MATH snapshot missing {name}')
        setattr(c, name, int(local_values[name]))
    if 'SpaceAfterScript' not in local_values:
        raise ValueError('local MATH snapshot missing SpaceAfterScript')
    c.SpaceAfterScript.Value = int(local_values['SpaceAfterScript'])


def preserve_windows_ansi_compatibility(font):
    """Preserve Windows ANSI font selection for this converter's math
    face.
    """
    cmap = font.getBestCmap() or {}
    names = set(font.getGlyphOrder())
    missing = [
        cp
        for cp in range(0x20, 0x7F)
        if cmap.get(cp) == '.notdef' or cmap.get(cp) not in names
    ]
    if missing:
        raise ValueError(
            'ASCII cmap missing valid glyphs: '
            + ', '.join(f'U+{cp:04X}' for cp in missing)
        )
    font['OS/2'].ulCodePageRange1 |= 1


def update_average_width(font):
    """Derive average advance from each nonzero-width GID once."""
    widths = [
        font['hmtx'][name][0]
        for name in font.getGlyphOrder()
        if font['hmtx'][name][0] != 0
    ]
    if not widths:
        raise ValueError('xAvgCharWidth: no nonzero advances')
    average = (2 * sum(widths) + len(widths)) // (2 * len(widths))
    if not 0 <= average <= 32767:
        raise ValueError('xAvgCharWidth: average outside FWORD range')
    font['OS/2'].xAvgCharWidth = average


def edit(f, *, edition, local_values):
    if 'MATH' not in f or 'CFF ' not in f:
        raise ValueError('expected CFF OpenType MATH font')
    m = f['MATH'].table
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
    _sync_cff_sidebearing(f, '.notdef')

    # Canonical single-face install identity.
    family, psname, unique_id = identity(edition)

    # Fixed technical metadata for Windows compatibility.
    preserve_windows_ansi_compatibility(f)
    update_average_width(f)
    f['head'].fontRevision = FONT_REVISION
    f['name'].names = [n for n in f['name'].names if n.nameID not in (3, 5)]
    replacements = {
        1: family,
        2: 'Regular',
        4: family,
        6: psname,
        16: family,
        17: 'Regular',
    }
    for n in f['name'].names:
        repl = replacements.get(n.nameID)
        if repl is not None:
            try:
                n.string = repl.encode(n.getEncoding(), errors='replace')
            except Exception:
                pass
    for platformID, platEncID, langID in ((1, 0, 0), (3, 1, 0x0409)):
        f['name'].setName(unique_id, 3, platformID, platEncID, langID)
        f['name'].setName(FONT_VERSION, 5, platformID, platEncID, langID)
    top = f['CFF '].cff.topDictIndex[0]
    f['CFF '].cff.fontNames = [psname]
    top.FontName = psname
    top.FullName = family
    top.FamilyName = family
    top.Weight = 'Regular'
    try:
        del top.version
    except Exception:
        pass
    top.rawDict.pop('version', None)


MATH_FIELDS = (
    (
        'MathItalicsCorrectionInfo',
        'Coverage',
        'ItalicsCorrection',
        'ItalicsCorrectionCount',
    ),
    (
        'MathTopAccentAttachment',
        'TopAccentCoverage',
        'TopAccentAttachment',
        'TopAccentAttachmentCount',
    ),
)


def math_add(font, name, ic, accent):
    gi = font['MATH'].table.MathGlyphInfo
    for value, (field, cov, array, count) in zip((ic, accent), MATH_FIELDS):
        table = getattr(gi, field)
        pairs = dict(zip(getattr(table, cov).glyphs, getattr(table, array)))
        if name in pairs:
            raise ValueError('MATH mbf identity collision')
        record = ot.MathValueRecord()
        record.Value = value
        record.DeviceTable = None
        pairs[name] = record
        names = sorted(pairs, key=font.getGlyphID)
        getattr(table, cov).glyphs = names
        setattr(table, array, [pairs[n] for n in names])
        setattr(table, count, len(names))


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
    metrics = font['hmtx'].metrics
    hhea = {
        'advanceWidthMax': max(v[0] for v in metrics.values()),
        'minLeftSideBearing': min(metrics[n][1] for n in widths),
        'minRightSideBearing': min(
            metrics[n][0] - metrics[n][1] - w for n, w in widths.items()
        ),
        'xMaxExtent': max(metrics[n][1] + w for n, w in widths.items()),
    }
    return {'FontBBox': box, 'head_bbox': box, 'hhea': hhea}
