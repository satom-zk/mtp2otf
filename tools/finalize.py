"""Normalize CFF assemblies, aliases, and metadata with fontTools.

Restore source-dependent scalars from the local build snapshot.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen


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
    """Keep advance and outline intact; derive LSB from the CFF outline."""
    width, _ = font['hmtx'][name]
    font['hmtx'][name] = (width, int(round(_bbox(font, name)[0])))


def _set_charstring(font, name, draw_fn, width):
    """Create/replace one CFF1 glyph; ``draw_fn`` receives a pen."""
    top = font['CFF '].cff.topDictIndex[0]
    gs = font.getGlyphSet()
    pen = T2CharStringPen(width, gs)
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
    """Rebuild an assembly while retaining its source-measured connector lengths."""
    if template is None:
        raise ValueError('missing pre-finalize brace assembly template')
    records = list(template.PartRecords or ())
    if len(records) != len(glyphs):
        raise ValueError('brace assembly template length changed unexpectedly')
    ga = ot.GlyphAssembly()
    ga.ItalicsCorrection = _mvr(
        getattr(getattr(template, 'ItalicsCorrection', None), 'Value', 0))
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
        raise ValueError('missing pre-finalize overbrace assembly')
    return min(_bbox(font, rec.glyph)[1] for rec in assembly.PartRecords)


def _fix_braces(font):
    """Normalize brace cusp glyphs without re-encoding source measurements."""
    m = font['MATH'].table
    cmap = _cmap(font)
    og = cmap.get(0x23DE)
    ug = cmap.get(0x23DF)
    if not og or not ug:
        return
    for req in ('braceld', 'braceru', 'bracelu', 'bracerd', 'brace.hext'):
        if req not in font.getGlyphOrder():
            return

    hmap = dict(zip(m.MathVariants.HorizGlyphCoverage.glyphs,
                    m.MathVariants.HorizGlyphConstruction))
    ocn = hmap.get(og)
    ucn = hmap.get(ug)
    if ocn is None or ucn is None:
        raise ValueError('brace construction missing from pre-finalize font')
    old_over = ocn.GlyphAssembly
    old_under = ucn.GlyphAssembly
    over_target_ymin = _assembly_ymin(font, old_over)

    # TeX brace fill concatenates the two cusp halves directly.  Merge each pair
    # into one fixed non-extender; connector lengths stay those measured from the
    # local source and already stored in the pre-finalize assembly.
    oc = 'brace.over.center.v18'
    uc = 'brace.under.center.v18'
    _merge_two(font, 'braceru', 'bracelu', oc)
    _merge_two(font, 'bracerd', 'braceld', uc)

    raw_ymin = min(_bbox(font, g)[1]
                   for g in ('braceld', 'bracerd', oc, 'brace.hext'))
    dy = int(round(over_target_ymin - raw_ymin))
    ol = _copy_shift(font, 'braceld', 'brace.over.left.v18', dy)
    oe = _copy_shift(font, 'brace.hext', 'brace.over.ext.v18', dy)
    oc2 = _copy_shift(font, oc, 'brace.over.center.shift.v18', dy)
    or_ = _copy_shift(font, 'bracerd', 'brace.over.right.v18', dy)

    ocn.GlyphAssembly = _copy_assembly_geometry(
        font, old_over, [ol, oe, oc2, oe, or_])
    ucn.GlyphAssembly = _copy_assembly_geometry(
        font, old_under, ['bracelu', 'brace.hext', uc, 'brace.hext', 'braceru'])
    # MinConnectorOverlap is intentionally left untouched: the FontForge stage
    # computed it from the local source outlines and serialized it already.


def _add_cmap_alias(font, cp, glyph):
    for t in font['cmap'].tables:
        if not t.isUnicode():
            continue
        if cp > 0xFFFF and t.format not in (12, 13):
            continue
        t.cmap.setdefault(cp, glyph)


def _load_local_math_values(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    values = data.get('constants')
    if not isinstance(values, dict):
        raise ValueError('local MATH snapshot has no constants object')
    return {str(k): int(v) for k, v in values.items()}


def _restore_roundtrip_sensitive_constants(math_table, local_values):
    """Restore scalars FontForge may rewrite, using only the local snapshot."""
    c = math_table.MathConstants
    for name in ('ScriptPercentScaleDown', 'ScriptScriptPercentScaleDown'):
        if name not in local_values:
            raise ValueError(f'local MATH snapshot missing {name}')
        setattr(c, name, int(local_values[name]))
    if 'SpaceAfterScript' not in local_values:
        raise ValueError('local MATH snapshot missing SpaceAfterScript')
    c.SpaceAfterScript.Value = int(local_values['SpaceAfterScript'])


def apply(path, output=None, subscript_correction=False, edition='full',
          math_values_path=None):
    if not math_values_path:
        raise ValueError('--math-values is required; use the local build snapshot')
    local_values = _load_local_math_values(math_values_path)

    f = TTFont(path)
    if 'MATH' not in f or 'CFF ' not in f:
        raise ValueError('expected CFF OpenType MATH font')
    m = f['MATH'].table
    _restore_roundtrip_sensitive_constants(m, local_values)

    if not subscript_correction:
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
    if edition == 'lite':
        family = 'MTPro2 Math Lite'
        psname = 'MTPro2MathLite'
        unique_id = 'MTP2;MTPro2MathLite'
    else:
        family = 'MTPro2 Math'
        psname = 'MTPro2Math'
        unique_id = 'MTP2;MTPro2Math'

    # Fixed technical metadata for Windows compatibility.
    f['head'].fontRevision = 1.0
    f['name'].names = [n for n in f['name'].names if n.nameID not in (3, 5)]
    replacements = {1: family, 2: 'Regular', 4: family,
                    6: psname, 16: family, 17: 'Regular'}
    for n in f['name'].names:
        repl = replacements.get(n.nameID)
        if repl is not None:
            try:
                n.string = repl.encode(n.getEncoding(), errors='replace')
            except Exception:
                pass
    for platformID, platEncID, langID in ((1, 0, 0), (3, 1, 0x0409)):
        f['name'].setName(unique_id, 3, platformID, platEncID, langID)
        f['name'].setName('Version 1.0', 5, platformID, platEncID, langID)
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
    out = output or path
    f.save(out)
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('font')
    ap.add_argument('-o', '--output')
    ap.add_argument('--subscript-correction', action='store_true')
    ap.add_argument('--edition', choices=('full', 'lite'), default='full')
    ap.add_argument('--math-values', required=True,
                    help='local build/generated/math-constants.json snapshot')
    a = ap.parse_args()
    print(apply(a.font, a.output, a.subscript_correction, a.edition, a.math_values))
