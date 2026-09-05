#!/usr/bin/env python3
"""Validate generated font structure, metadata, and math layout contracts."""
import sys
from fontTools.ttLib import TTFont

err, warn = [], []


def E(msg):
    err.append(msg)


def W(msg):
    warn.append(msg)


def check(path):
    del err[:], warn[:]
    f = TTFont(path)
    names = set(f.getGlyphOrder())
    cmap = f.getBestCmap()
    print(f'\n=== {path}')
    print(f'glyphs {len(names)} / cmap {len(cmap)}')

    # Required tables.
    for t in ('MATH', 'GSUB', 'GPOS', 'cmap', 'name', 'OS/2', 'head', 'hhea'):
        if t not in f:
            E(f'{t}: missing table')
    if 'CFF ' not in f and 'glyf' not in f:
        E('Missing CFF/glyf outlines')

    # cmap
    if any(g == '.notdef' for g in cmap.values()):
        E('cmap contains mappings to .notdef')
    missing = [c for c, g in cmap.items() if g not in names]
    if missing:
        E(f'Missing cmap targets: {len(missing)} entries')
    for cp, what in ((0x2061, 'function application'), (0x2062, 'invisible multiplication'),
                     (0x2063, 'invisible separator'), (0x0020, 'space')):
        if cp not in cmap:
            W(f'U+{cp:04X} ({what}) missing; Word may show a missing-glyph box')

    # Validate aliases independently of uni_map.py to catch mapping errors.
    _greek_alias_expected = {
        0x0391: 0x0041, 0x0392: 0x0042, 0x0395: 0x0045, 0x0396: 0x005A,
        0x0397: 0x0048, 0x0399: 0x0049, 0x039A: 0x004B, 0x039C: 0x004D,
        0x039D: 0x004E, 0x039F: 0x004F, 0x03A1: 0x0050, 0x03A4: 0x0054,
        0x03A7: 0x0058, 0x03F4: 0x0398, 0x03BF: 0x006F,
        0x1D6E2: 0x1D434, 0x1D6E3: 0x1D435, 0x1D6E6: 0x1D438,
        0x1D6E7: 0x1D44D, 0x1D6E8: 0x1D43B, 0x1D6EA: 0x1D43C,
        0x1D6EB: 0x1D43E, 0x1D6ED: 0x1D440, 0x1D6EE: 0x1D441,
        0x1D6F0: 0x1D442, 0x1D6F2: 0x1D443, 0x1D6F3: 0x1D6E9,
        0x1D6F5: 0x1D447, 0x1D6F8: 0x1D44B, 0x1D70A: 0x1D45C,
    }
    _greek_ok = 0
    for alias_cp, source_cp in _greek_alias_expected.items():
        ag = cmap.get(alias_cp)
        sg = cmap.get(source_cp)
        if ag is None:
            E(f'Greek Latin-shaped alias U+{alias_cp:04X} missing from cmap')
        elif sg is None:
            E(f'Greek alias donor U+{source_cp:04X} missing from cmap')
        elif ag != sg:
            E(f'Greek alias U+{alias_cp:04X} ({ag}) does not share a GID with donor U+{source_cp:04X} ({sg})')
        else:
            _greek_ok += 1
    print(f'Greek Latin-shaped aliases: {_greek_ok}/30 same-GID')

    # Reject digit-leading glyph names for Word subsetting.
    import re as _re
    _dig = [g for g in names if g and g[0].isdigit()]
    if _dig:
        E(f'Digit-leading glyph names: {len(_dig)} ({", ".join(sorted(_dig)[:3])} …) — '
          f'Invalid PostScript names may cause Word to rasterize text')
    _badch = [g for g in names if not _re.fullmatch(r'[A-Za-z0-9._]+', g or '')]
    if _badch:
        E(f'Invalid glyph-name characters: {_badch[:3]}')
    _long = [g for g in names if len(g) > 63]
    if _long:
        W(f'Glyph names longer than 63 characters: {len(_long)} entries')

    # OS/2 and naming.
    os2 = f['OS/2']
    if os2.fsType == 2:
        W('fsType is 2: restricted embedding; Word cannot embed the font')
    elif os2.fsType == 4:
        W('fsType is 4: preview/print embedding; Word PDF export '
          'may rasterize text')
    # Windows clipping bounds must cover the outlines.
    from fontTools.pens.boundsPen import BoundsPen as _BP
    gs = f.getGlyphSet()
    ymin = ymax = 0
    for g in names:
        b = _BP(gs)
        try:
            gs[g].draw(b)
        except Exception:
            continue
        if b.bounds:
            ymin = min(ymin, b.bounds[1])
            ymax = max(ymax, b.bounds[3])
    if os2.usWinAscent < ymax or os2.usWinDescent < -ymin:
        E(f'usWinAscent/Descent ({os2.usWinAscent}/{os2.usWinDescent}) - '
          f'glyph bounds ({ymax}/{-ymin}) are not covered; '
          f'Windows may clip extended delimiters or integrals')
    nm = {r.nameID: str(r) for r in f['name'].names}
    for i, what in ((1, 'family name'), (2, 'style name'), (6, 'PostScript name'),
                    (7, 'trademark')):
        if i not in nm:
            W(f'name ID {i} ({what}) missing')

    # MATH
    m = f['MATH'].table
    mv, gi = m.MathVariants, m.MathGlyphInfo
    ic = gi.MathItalicsCorrectionInfo
    for g in ic.Coverage.glyphs:
        if g not in names:
            E(f'Italic-correction target {g} does not exist')
    ta = gi.MathTopAccentAttachment
    _topaccent = {
        g: int(v.Value)
        for g, v in zip(ta.TopAccentCoverage.glyphs, ta.TopAccentAttachment)
    }
    for g in ta.TopAccentCoverage.glyphs:
        if g not in names:
            E(f'TopAccent target {g} does not exist')
    ovl = mv.MinConnectorOverlap
    n_var = n_part = 0
    for label, cov, cons in (('vertical', mv.VertGlyphCoverage, mv.VertGlyphConstruction),
                             ('horizontal', mv.HorizGlyphCoverage, mv.HorizGlyphConstruction)):
        if cov is None:
            continue
        if len(cov.glyphs) != len(cons):
            E(f'{label} constructions: coverage {len(cov.glyphs)} differs from construction count {len(cons)}')
        for base, rec in zip(cov.glyphs, cons):
            if base not in names:
                E(f'{label} construction base {base} does not exist')
            prev = None
            for v in (rec.MathGlyphVariantRecord or []):
                n_var += 1
                if v.VariantGlyph not in names:
                    E(f'{base}: variant {v.VariantGlyph} does not exist')
                if prev is not None and v.AdvanceMeasurement < prev:
                    W(f'{base}: variant sizes are not monotonic '
                      f'({prev} → {v.AdvanceMeasurement})')
                prev = v.AdvanceMeasurement
            asm = rec.GlyphAssembly
            if asm:
                has_ext = False
                for p in asm.PartRecords:
                    n_part += 1
                    if p.glyph not in names:
                        E(f'{base}: assembly part {p.glyph} does not exist')
                    if p.PartFlags & 1:
                        has_ext = True
                    for attr in ('StartConnectorLength', 'EndConnectorLength'):
                        v = getattr(p, attr)
                        if v and v < ovl:
                            E(f'{base}/{p.glyph}: {attr} {v} - '
                              f'MinConnectorOverlap {ovl}')
                if not has_ext:
                    E(f'{base}: assembly has no extender (PartFlags=1)')
    print(f'MATH: vertical {len(mv.VertGlyphCoverage.glyphs)} / '
          f'horizontal {len(mv.HorizGlyphCoverage.glyphs) if mv.HorizGlyphCoverage else 0} '
          f'/ variants {n_var} / parts {n_part} / MinOverlap {ovl}')

    # Check connectors and ink continuity at the active minimum overlap.
    from fontTools.pens.boundsPen import BoundsPen as _HBP
    _hgs = f.getGlyphSet()

    def _hb(gname):
        pen = _HBP(_hgs)
        _hgs[gname].draw(pen)
        return pen.bounds or (0, 0, 0, 0)

    hcons = {}
    if mv.HorizGlyphCoverage:
        hcons = dict(zip(mv.HorizGlyphCoverage.glyphs, mv.HorizGlyphConstruction))

    def _hcon(cp):
        gn = cmap.get(cp)
        return gn, (hcons.get(gn) if gn else None)

    # Relation arrows stretch; public bar and right-vector accents remain fixed.
    for cp, label in ((0x0304, 'bar/macron'), (0x0305, 'bar/overline alias'),
                      (0x20D7, 'right vector accent')):
        gn, con = _hcon(cp)
        if not gn:
            E(f'U+{cp:04X}: {label}: missing glyph')
        elif con is not None:
            E(f'U+{cp:04X}: {label}: unexpected horizontal MATH construction')

    # U+E286 keeps the finite source-bar ladder, positive advance, and center attachment.
    wg, wc = _hcon(0xE286)
    if not wg or not wc:
        E('Missing U+E286 wideoverbar compatibility construction')
    elif wc.GlyphAssembly:
        E('U+E286 wideoverbar must use fixed source variants, without an assembly')
    else:
        _wrecs = list(wc.MathGlyphVariantRecord or [])
        _wadv = [r.AdvanceMeasurement for r in _wrecs]
        if len(_wadv) != 3 or any(b <= a for a, b in zip(_wadv, _wadv[1:])):
            E('U+E286 wideoverbar ladder must contain three strictly increasing finite rungs')

        _wbar = cmap.get(0xE24E)
        _wwbar = cmap.get(0xE24A)
        _want_glyphs = [wg, _wbar, _wwbar]
        _got_glyphs = [r.VariantGlyph for r in _wrecs]
        if None in _want_glyphs:
            E('U+E286 ladder: missing fixed source-accent donors E24E/E24A in cmap')
        elif _got_glyphs != _want_glyphs:
            E(f'U+E286 ladder glyphs {_got_glyphs} != {_want_glyphs}')

        # Check advance-center attachment separately from ink-center proximity.
        for _ag in _want_glyphs:
            if not _ag or _ag not in names:
                continue
            _aw = f['hmtx'][_ag][0]
            if _aw <= 0:
                E(f'{_ag}: U+E286 finite-rung advance {_aw} must be positive')
                continue
            _want_ta = _aw // 2
            _have_ta = _topaccent.get(_ag)
            if _have_ta is None:
                E(f'{_ag}: missing U+E286 fixed-variant TopAccentAttachment')
                continue
            if _have_ta != _want_ta:
                E(f'{_ag}: TopAccent {_have_ta} != advance-centre {_want_ta}')
            _abb = _hb(_ag)
            _ink_center = (_abb[0] + _abb[2]) / 2
            if abs(_have_ta - _ink_center) > 2:
                E(f'{_ag}: TopAccent {_have_ta} differs from ink center {_ink_center:.1f} by more than 2u')

    # U+E287 uses an accent-height assembly, separate from the relation arrow.
    vg, vc = _hcon(0xE287)
    if not vg or not vc or not vc.GlyphAssembly:
        E('Missing U+E287 widevector compatibility assembly')
    else:
        _vpr = vc.GlyphAssembly.PartRecords
        if len(_vpr) != 2 or not (_vpr[0].PartFlags & 1) or (_vpr[1].PartFlags & 1):
            E('U+E287 widevector assembly must contain an extender and a fixed endpoint')
        if f['hmtx'][vg][0] != 0:
            E(f'U+E287 widevector base advance {f["hmtx"][vg][0]} != 0')
        _public_vec = cmap.get(0x20D7)
        if _public_vec:
            _vta = _topaccent.get(vg)
            _pta = _topaccent.get(_public_vec)
            if _vta is None or _pta is None:
                E('Missing U+E287/U+20D7 vector TopAccentAttachment')
            elif _vta != _pta:
                E(f'U+E287 TopAccent {_vta} != normalized U+20D7 TopAccent {_pta}')

    for cp in (0x2190, 0x2192, 0x2194, 0x21D0, 0x21D2, 0x21D4):
        gn, con = _hcon(cp)
        if not gn or not con or not con.GlyphAssembly:
            E(f'U+{cp:04X}: missing horizontal assembly with valid connectors')
            continue
        prs = con.GlyphAssembly.PartRecords
        if len(prs) != 3 or not (prs[1].PartFlags & 1):
            E(f'U+{cp:04X}: relation-arrow assembly must use fixed/extender/fixed parts')
        for a, b in zip(prs, prs[1:]):
            ba, bb = _hb(a.glyph), _hb(b.glyph)
            gap = a.FullAdvance - ovl + bb[0] - ba[2]
            if gap > 0:
                E(f'U+{cp:04X}: {a.glyph}→{b.glyph}: gap at minimum overlap: {gap:.1f}u')

    # U+20D6 uses its designated left-vector assembly.
    for cp, endpoint_cp, extender_index in ((0x20D6, 0x2190, 1),):
        gn, con = _hcon(cp)
        if not gn or not con or not con.GlyphAssembly:
            E(f'U+{cp:04X}: missing horizontal vector assembly')
            continue
        prs = con.GlyphAssembly.PartRecords
        if len(prs) != 2 or not (prs[extender_index].PartFlags & 1):
            E(f'U+{cp:04X}: vector assembly must use a complete endpoint and optional extender')
        fixed = [r for r in prs if not (r.PartFlags & 1)]
        ep = cmap.get(endpoint_cp)
        epw = f['hmtx'].metrics[ep][0] if ep else 0
        if len(fixed) != 1 or abs(fixed[0].FullAdvance - epw) > 1:
            got = fixed[0].FullAdvance if fixed else None
            E(f'U+{cp:04X}: shortest vector width {got} != completed arrow width {epw}')
        for a, b in zip(prs, prs[1:]):
            ba, bb = _hb(a.glyph), _hb(b.glyph)
            gap = a.FullAdvance - ovl + bb[0] - ba[2]
            if gap > 0:
                E(f'U+{cp:04X}: {a.glyph}→{b.glyph}: gap at minimum overlap: {gap:.1f}u')

    # Mapsto has dedicated finite source glyphs, not an arbitrary-width assembly.
    mg, mc = _hcon(0x21A6)
    if mg and mc:
        if mc.GlyphAssembly:
            E('U+21A6: unexpected mapsto assembly; only short/long variants are allowed')
        if len(mc.MathGlyphVariantRecord or []) < 2:
            E('U+21A6: missing short/long MTPro2 mapsto variants')

    # Keep overparen, standard corner-and-rule braces, and overcbrace designs distinct.
    pg, pc = _hcon(0x23DC)
    og, oc = _hcon(0x23DE)
    ug, uc = _hcon(0x23DF)

    def _construction_glyphs(con):
        if not con:
            return set()
        outg = {r.VariantGlyph for r in (con.MathGlyphVariantRecord or [])}
        if con.GlyphAssembly:
            outg.update(p.glyph for p in con.GlyphAssembly.PartRecords)
        return outg

    if pc:
        pglyphs = _construction_glyphs(pc)
        # Only the designated source continuation belongs to the overparen ladder.
        bad = [g for g in pglyphs if '.exe' in g or '.exg' in g
               or ('.exf' in g and not g.startswith(f'{pg}.exf'))]
        if bad:
            E(f'U+23DC: unrelated extension glyph in TOP PARENTHESIS: {bad[:4]}')
        vals = [r.AdvanceMeasurement for r in (pc.MathGlyphVariantRecord or [])]
        if not vals or max(vals) < 12000:
            E(f'U+23DC: overparen ladder does not reach 12em (max={max(vals) if vals else 0})')
        # Bridge fixed overparen ladders without early saturation.
        if not pc.GlyphAssembly:
            E('U+23DC: missing assembly between fixed variant ladders')
        else:
            prs = pc.GlyphAssembly.PartRecords
            if len(prs) != 3 or not (prs[1].PartFlags & 1):
                E(f'U+23DC: overparen assembly requires fixed/extender/fixed parts ({len(prs)} parts)')
            for a, b in zip(prs, prs[1:]):
                ba, bb = _hb(a.glyph), _hb(b.glyph)
                gap = a.FullAdvance - ovl + bb[0] - ba[2]
                if gap > 0:
                    E(f'U+23DC: {a.glyph}→{b.glyph}: gap at minimum overlap: {gap:.1f}u')
    for cp, base_g, con in ((0x23DE, og, oc), (0x23DF, ug, uc)):
        if base_g and any(f'.{tag}' in base_g for tag in ('exe', 'exf', 'exg')):
            E(f'U+{cp:04X}: base glyph belongs to the separate overcbrace/undercbrace family ({base_g})')
        if not con or not con.GlyphAssembly:
            E(f'U+{cp:04X}: missing standard brace assembly')
            continue
        prs = con.GlyphAssembly.PartRecords
        if len(prs) != 5:
            E(f'U+{cp:04X}: standard brace assembly requires 5 parts; found {len(prs)} parts')
        elif not ((prs[1].PartFlags & 1) and (prs[3].PartFlags & 1)):
            E(f'U+{cp:04X}: rule extenders are not in their two expected positions')
        bad = [g for g in _construction_glyphs(con)
               if any(f'.{tag}' in g for tag in ('exe', 'exf', 'exg'))]
        if bad:
            E(f'U+{cp:04X}: separate overcbrace/undercbrace glyph in standard brace: {bad[:4]}')

    if pc and oc:
        cross = _construction_glyphs(pc) & _construction_glyphs(oc)
        if cross:
            E(f'U+23DC/U+23DE: overlapping variant/assembly glyph sets: {sorted(cross)[:4]}')

    # audit_source_contract.py checks source metrics; keep this validator structural.

    fitalic = cmap.get(0x1D453)
    if fitalic and fitalic not in dict(zip(ic.Coverage.glyphs, [v.Value for v in ic.ItalicsCorrection])):
        E('U+1D453 math italic f: missing MATH ItalicsCorrection')

    # GSUB
    g = f['GSUB'].table
    feat = {}
    feat_lookup_count = {}
    for fr in g.FeatureList.FeatureRecord:
        cnt = 0
        feat_lookup_count[fr.FeatureTag] = len(fr.Feature.LookupListIndex)
        for li in fr.Feature.LookupListIndex:
            lk = g.LookupList.Lookup[li]
            for st in lk.SubTable:
                mp = getattr(st, 'mapping', None) or {}
                al = getattr(st, 'alternates', None) or {}
                lig = getattr(st, 'ligatures', None) or {}
                for b, v in list(mp.items()):
                    cnt += 1
                    if b not in names or v not in names:
                        E(f'{fr.FeatureTag}: {b} → {v}: missing glyph')
                for b, vs in list(al.items()):
                    cnt += len(vs)
                    if b not in names or any(v not in names for v in vs):
                        E(f'{fr.FeatureTag}: {b}: missing alternate glyph')
                for first, recs in list(lig.items()):
                    cnt += len(recs)
                    if first not in names:
                        E(f'{fr.FeatureTag}: ligature first {first} does not exist')
                    for rec in recs:
                        if rec.LigGlyph not in names or any(x not in names for x in rec.Component):
                            E(f'{fr.FeatureTag}: missing ligature glyph')
        feat[fr.FeatureTag] = cnt
    print('GSUB:', ' '.join(
        f'{k}={v}({feat_lookup_count.get(k, 0)}L)' for k, v in sorted(feat.items())))
    for tag in ('ssty', 'dtls', 'ccmp'):
        if tag not in feat:
            W(f'{tag}: missing feature')

    # Infer raw-prime classes and padding from the generated glyphs.
    import math as _math
    import unicodedata as _ud
    primes = {cmap.get(x) for x in (0x2032, 0x2033, 0x2034, 0x2057)} - {None}
    icvals = dict(zip(ic.Coverage.glyphs, [v.Value for v in ic.ItalicsCorrection]))
    variant_deltas = set()
    actual = set()
    for fr in g.FeatureList.FeatureRecord:
        if fr.FeatureTag != 'ccmp':
            continue
        for li in fr.Feature.LookupListIndex:
            lk = g.LookupList.Lookup[li]
            if lk.LookupType != 6:
                continue
            for st in lk.SubTable:
                if getattr(st, 'Format', None) != 3 or not getattr(st, 'InputCoverage', None):
                    continue
                inp = set(st.InputCoverage[0].glyphs)
                if not (inp & primes):
                    continue
                for cov in (getattr(st, 'BacktrackCoverage', None) or []):
                    actual.update(cov.glyphs)
                # Use substitution advances rather than names, which TTF post format 3 drops.
                for rec in (getattr(st, 'SubstLookupRecord', None) or []):
                    if rec.SequenceIndex != 0:
                        continue
                    sub_lookup = g.LookupList.Lookup[rec.LookupListIndex]
                    subtables = []
                    if sub_lookup.LookupType == 1:
                        subtables = list(sub_lookup.SubTable)
                    elif sub_lookup.LookupType == 7:
                        subtables = [x.ExtSubTable for x in sub_lookup.SubTable
                                     if getattr(x, 'ExtensionLookupType', None) == 1]
                    for sub in subtables:
                        for src, dst in (getattr(sub, 'mapping', None) or {}).items():
                            if src in primes:
                                variant_deltas.add(
                                    f['hmtx'][dst][0] - f['hmtx'][src][0])

    if variant_deltas:
        ordered_delta = sorted(variant_deltas)
        diffs = [b - a for a, b in zip(ordered_delta, ordered_delta[1:]) if b > a]
        step = 0
        for d in diffs:
            step = _math.gcd(step, d)
        if step <= 0:
            W('prime contextual class step could not be inferred')
        else:
            # The smallest advance delta identifies class zero and the source-derived padding.
            base_shift = -min(ordered_delta)
            class_values = {d + base_shift for d in ordered_delta}
            cap = max(class_values)
            expected = set()
            for u, gn in cmap.items():
                if u < 0x370:
                    continue
                try:
                    if not _ud.category(chr(u)).startswith('L'):
                        continue
                except ValueError:
                    continue
                kval = max(0, min(cap, int(round(icvals.get(gn, 0) / step)) * step))
                if abs(kval - base_shift) >= step / 2:
                    expected.add(gn)
            missing_prime = expected - actual
            extra_prime = actual - expected
            if missing_prime:
                E(f'prime ccmp backtrack coverage missing {len(missing_prime)} eligible glyphs')
            if extra_prime:
                W(f'prime ccmp backtrack coverage has {len(extra_prime)} extra glyphs')
            if not missing_prime:
                print('prime ccmp: all inferred eligible glyphs covered')
    elif actual:
        E('prime ccmp coverage exists but no contextual prime variants were found')

    # Verify that the font can be serialized.
    import io
    try:
        buf = io.BytesIO()
        f.save(buf)
        TTFont(io.BytesIO(buf.getvalue()))['MATH']
    except Exception as e:
        E(f'Save/reload failed: {e}')

    for e in err:
        print('  ★', e)
    for w in warn:
        print('  !', w)
    print(f'errors {len(err)} / warnings {len(warn)}')
    return len(err)


if __name__ == '__main__':
    bad = 0
    for p in sys.argv[1:]:
        bad += check(p)
    sys.exit(1 if bad else 0)
