#!/usr/bin/env python3
"""Check OTF/TTF layout by GID and table bytes, allowing curve approximation.

Audit metric-induced origin shifts separately from outline shape.
"""
import sys
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen

KEEP_IDENTICAL = ('MATH', 'GSUB', 'GPOS', 'cmap', 'hmtx', 'name', 'OS/2', 'GDEF')

# Font-grid allowances for this converter, not general TrueType validity rules.
CFF_LSB_TOLERANCE = 1.0
TT_ORIGIN_TOLERANCE = 2.0


def verify_outline_origins(cff_font, tt_font):
    """Check CFF sidebearings and TrueType origin shifts within conversion tolerances."""
    cff_set = cff_font.getGlyphSet()
    tt_set = tt_font.getGlyphSet()
    errors = []
    max_cff_error = max_tt_shift = 0.0
    for gid, (cn, tn) in enumerate(zip(cff_font.getGlyphOrder(),
                                       tt_font.getGlyphOrder())):
        cp = BoundsPen(cff_set)
        cff_set[cn].draw(cp)
        raw = BoundsPen(tt_set)
        glyph = tt_font['glyf'][tn]
        glyph.draw(raw, tt_font['glyf'])
        drawn = BoundsPen(tt_set)
        tt_set[tn].draw(drawn)
        label = f'GID {gid} ({cn})'
        if cp.bounds is None or raw.bounds is None or drawn.bounds is None:
            if not (cp.bounds is None and raw.bounds is None and drawn.bounds is None):
                errors.append(f'{label}: empty-outline coverage differs')
            elif cff_font['hmtx'][cn][1] or tt_font['hmtx'][tn][1]:
                errors.append(f'{label}: empty outline has nonzero sidebearing')
            continue
        cff_error = abs(cff_font['hmtx'][cn][1] - cp.bounds[0])
        max_cff_error = max(max_cff_error, cff_error)
        if cff_error > CFF_LSB_TOLERANCE:
            errors.append(f'{label}: CFF LSB differs from outline xMin by {cff_error:g}')
        shift = tt_font['hmtx'][tn][1] - glyph.xMin
        max_tt_shift = max(max_tt_shift, abs(shift))
        if abs(shift) > TT_ORIGIN_TOLERANCE:
            errors.append(f'{label}: TrueType metrics shift the raw outline by {shift:g}')
        expected = (raw.bounds[0] + shift, raw.bounds[1],
                    raw.bounds[2] + shift, raw.bounds[3])
        if any(abs(x - y) > 1e-6 for x, y in zip(drawn.bounds, expected)):
            errors.append(f'{label}: unexpected raw/metric-adjusted drawing relation')
    if errors:
        raise SystemExit('OTF/TTF origin contract failed:\n  ' + '\n  '.join(errors[:8]))
    return max_cff_error, max_tt_shift


def cmap_gid_map(font):
    order = font.getGlyphOrder()
    gid = {g: i for i, g in enumerate(order)}
    out = {}
    for table in font['cmap'].tables:
        if not table.isUnicode():
            continue
        for cp, g in table.cmap.items():
            out[cp] = gid[g]
    return out


def hmtx_by_gid(font):
    order = font.getGlyphOrder()
    return [font['hmtx'].metrics[g] for g in order]


def main(otf_path, ttf_path):
    a = TTFont(otf_path)
    b = TTFont(ttf_path)
    if len(a.getGlyphOrder()) != len(b.getGlyphOrder()):
        raise SystemExit('OTF/TTF glyph count differs')
    if cmap_gid_map(a) != cmap_gid_map(b):
        raise SystemExit('OTF/TTF Unicode cmap -> glyph ID mapping differs')
    if hmtx_by_gid(a) != hmtx_by_gid(b):
        raise SystemExit('OTF/TTF advance/sidebearing metrics differ')
    # These tables reference glyph IDs. With an unchanged glyph order they
    # must compile identically across CFF and glyf outline formats.
    for tag in ('MATH', 'GSUB', 'GPOS', 'GDEF'):
        if (tag in a) != (tag in b):
            raise SystemExit(f'OTF/TTF table presence differs: {tag}')
        if tag in a and a.getTableData(tag) != b.getTableData(tag):
            raise SystemExit(f'OTF/TTF table data differs: {tag}')
    if 'CFF ' not in a or 'glyf' in a:
        raise SystemExit('OTF is not the expected CFF build')
    if 'glyf' not in b or 'CFF ' in b:
        raise SystemExit('TTF is not the expected glyf build')
    verify_outline_origins(a, b)
    print('OTF/TTF invariant OK: cmap GIDs, metrics, MATH/GSUB/GPOS/GDEF unchanged; outline origins preserved')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('usage: verify_otf_ttf.py MTPro2Math.otf MTPro2Math.ttf')
    main(sys.argv[1], sys.argv[2])
