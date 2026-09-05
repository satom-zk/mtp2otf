#!/usr/bin/env python3
"""Add a compact ordinary CHARIC PairPos lookup.

It accumulates with the serialized TFM kern lookup while preserving hmtx and
MATH ItalicsCorrection. Exclude prime and combining-accent paths.
"""
from __future__ import annotations
import argparse, json, unicodedata
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables

VALUE_XADVANCE = 0x0004
EXCLUDED_CODEPOINTS = {
    # Source fixed/wide accent glyphs exposed in PUA; these are accent commands,
    # not ordinary right-neighbour characters.
    0xE24A, 0xE24B, 0xE24C, 0xE24E, 0xE24F, 0xE250, 0xE251, 0xE254, 0xE255, 0xE286, 0xE287,
}
ALLOWED_GSUB_FEATURES = {'ssty', 'salt', 'dtls'} | {f'cv{i:02d}' for i in range(1, 13)}


def _is_excluded_cp(cp: int) -> bool:
    if cp in EXCLUDED_CODEPOINTS or cp == 0x20:
        return True
    if 0x2032 <= cp <= 0x2037:  # prime family
        return True
    try:
        return unicodedata.category(chr(cp)).startswith('M')
    except ValueError:
        return False


def _feature_lookup_indices(font, tags):
    if 'GSUB' not in font or not font['GSUB'].table.FeatureList:
        return set()
    out = set()
    for fr in font['GSUB'].table.FeatureList.FeatureRecord:
        if fr.FeatureTag in tags:
            out.update(fr.Feature.LookupListIndex)
    return out


def _gsub_outputs(font, lookup_indices):
    out = set()
    if 'GSUB' not in font or not font['GSUB'].table.LookupList:
        return out
    lookups = font['GSUB'].table.LookupList.Lookup
    for idx in lookup_indices:
        if idx >= len(lookups):
            continue
        lk = lookups[idx]
        subtables = []
        if lk.LookupType in (1, 3):
            subtables = lk.SubTable
        elif lk.LookupType == 7:  # ExtensionSubst
            subtables = [st.ExtSubTable for st in lk.SubTable
                         if getattr(st, 'ExtensionLookupType', None) in (1, 3)]
        for st in subtables:
            if hasattr(st, 'mapping'):
                out.update(st.mapping.values())
            if hasattr(st, 'alternates'):
                for vals in st.alternates.values():
                    out.update(vals)
    return out


def _right_domain(font, left_glyphs):
    cmap = font.getBestCmap()
    by_glyph = {}
    for cp, g in cmap.items():
        by_glyph.setdefault(g, []).append(cp)
    rights = set()
    for g, cps in by_glyph.items():
        # Keep a glyph if it has at least one ordinary/non-mark encoded identity.
        if any(not _is_excluded_cp(int(cp)) for cp in cps):
            rights.add(g)
    rights.update(_gsub_outputs(font, _feature_lookup_indices(font, ALLOWED_GSUB_FEATURES)))
    # ssty/cv outputs can be unencoded.  Left glyphs themselves must also be
    # valid right glyphs for adjacency within the same optical/alternate run.
    rights.update(left_glyphs)

    # GDEF class 3 = mark.  This catches unencoded ssty/cv accent outputs that
    # cannot be filtered by Unicode General_Category alone.  TeX accent noads
    # and combining-mark shaping are not ordinary adjacency semantics.
    mark_glyphs = set()
    if 'GDEF' in font and font['GDEF'].table.GlyphClassDef:
        mark_glyphs = {g for g, c in font['GDEF'].table.GlyphClassDef.classDefs.items()
                       if int(c) == 3}

    # Never allow prime contextual products or mark glyphs into the ordinary
    # right class.  Prime/script/accent paths have their own TeX semantics.
    rights = {g for g in rights
              if g not in mark_glyphs
              and 'prime' not in g.lower()
              and not g.endswith('.icK')}
    return rights


def _value_record(xadvance):
    v = otTables.ValueRecord()
    v.XAdvance = int(xadvance)
    return v


def add_bridge(font, contract):
    if 'GPOS' not in font or not font['GPOS'].table.LookupList:
        raise SystemExit('font has no GPOS LookupList')
    glyph_order = set(font.getGlyphOrder())
    left_ic = {}
    for rec in contract.get('ordinary_ic_lefts', []):
        g = rec['glyph']
        ic = int(rec['italic_correction'])
        if not ic or g not in glyph_order:
            continue
        prev = left_ic.get(g)
        if prev is not None and prev != ic:
            raise SystemExit(f'conflicting ordinary IC for {g}: {prev} vs {ic}')
        left_ic[g] = ic
    if not left_ic:
        raise SystemExit('contract has no usable ordinary_ic_lefts')

    rights = _right_domain(font, set(left_ic)) & glyph_order
    if not rights:
        raise SystemExit('ordinary right class is empty')

    # Group left glyphs by IC so PairPos Format 2 stays compact.
    values = sorted(set(left_ic.values()))
    class_for_value = {v: i + 1 for i, v in enumerate(values)}
    classdef1 = {g: class_for_value[v] for g, v in left_ic.items()}
    classdef2 = {g: 1 for g in rights}

    sub = otTables.PairPos()
    sub.Format = 2
    sub.Coverage = otTables.Coverage()
    order_index = {g: i for i, g in enumerate(font.getGlyphOrder())}
    sub.Coverage.glyphs = sorted(left_ic, key=lambda g: order_index[g])
    sub.ValueFormat1 = VALUE_XADVANCE
    sub.ValueFormat2 = 0
    sub.ClassDef1 = otTables.ClassDef()
    sub.ClassDef1.classDefs = classdef1
    sub.ClassDef2 = otTables.ClassDef()
    sub.ClassDef2.classDefs = classdef2
    sub.Class1Count = len(values) + 1
    sub.Class2Count = 2
    sub.Class1Record = []
    value_for_class = {class_for_value[v]: v for v in values}
    for c1 in range(sub.Class1Count):
        r1 = otTables.Class1Record()
        r1.Class2Record = []
        for c2 in range(sub.Class2Count):
            r2 = otTables.Class2Record()
            x = value_for_class.get(c1, 0) if c2 == 1 else 0
            r2.Value1 = _value_record(x)
            r2.Value2 = None
            r1.Class2Record.append(r2)
        sub.Class1Record.append(r1)

    lookup = otTables.Lookup()
    lookup.LookupType = 2
    lookup.LookupFlag = 0
    lookup.SubTable = [sub]
    lookup.SubTableCount = 1
    lookup.MarkFilteringSet = None
    ll = font['GPOS'].table.LookupList
    idx = len(ll.Lookup)
    ll.Lookup.append(lookup)
    ll.LookupCount = len(ll.Lookup)

    features = []
    fl = font['GPOS'].table.FeatureList
    if fl:
        for fr in fl.FeatureRecord:
            if fr.FeatureTag == 'kern':
                if idx not in fr.Feature.LookupListIndex:
                    fr.Feature.LookupListIndex.append(idx)
                    fr.Feature.LookupCount = len(fr.Feature.LookupListIndex)
                features.append(fr)
    if not features:
        raise SystemExit('font has no existing kern feature; refusing to invent script wiring')
    return len(left_ic), len(values), len(rights), idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('font')
    ap.add_argument('--contract', required=True)
    ap.add_argument('--output')
    ns = ap.parse_args()
    f = TTFont(ns.font)
    con = json.load(open(ns.contract, encoding='utf-8'))
    lefts, classes, rights, idx = add_bridge(f, con)
    out = ns.output or ns.font
    f.save(out, reorderTables=False)
    print(f'ordinary IC GPOS bridge: {lefts} left glyphs / {classes} IC classes / '
          f'{rights} right glyphs / lookup {idx}')


if __name__ == '__main__':
    main()
