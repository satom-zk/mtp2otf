#!/usr/bin/env python3
"""Audit source widths, italic corrections, TopAccent, and cumulative IC/kern.

Check transformed prime metrics through their separate compatibility path.
"""
from __future__ import annotations
import argparse, json, os, subprocess, tempfile
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from tfmpl import TFM
from add_ordinary_ic_gpos import _right_domain
import source_policy


# The ordinary-left domain and source identities are structural interoperability
# rules shared with the builder. Evaluated skew/metric values are parsed from the
# licensee's local source tree below.

# The ordinary-left domain is structural: alphabet families are ordinary by
# construction, while symbol-family exceptions are explicit TeX identities.
def expected_ordinary_left(tag, slot):
    return source_policy.is_ordinary_left(tag, slot)


def load_tfm(tfm_dir, base):
    path = os.path.join(tfm_dir, base + '.tfm')
    if not os.path.isfile(path):
        raise SystemExit('missing TFM: ' + path)
    with tempfile.NamedTemporaryFile(suffix='.pl', delete=False) as t:
        pl = t.name
    try:
        subprocess.run(['tftopl', path, pl], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return TFM(pl)
    finally:
        try:
            os.unlink(pl)
        except OSError:
            pass


def pair_xadvance(font, left, right):
    if 'GPOS' not in font or not font['GPOS'].table.LookupList:
        return 0
    total = 0
    for lk in font['GPOS'].table.LookupList.Lookup:
        sts = []
        if lk.LookupType == 2:
            sts = list(lk.SubTable)
        elif lk.LookupType == 9:
            sts = [s.ExtSubTable for s in lk.SubTable if getattr(
                s, 'ExtensionLookupType', None) == 2]
        for st in sts:
            fmt = getattr(st, 'Format', None)
            if fmt == 1:
                if left not in st.Coverage.glyphs:
                    continue
                ps = st.PairSet[st.Coverage.glyphs.index(left)]
                for rec in ps.PairValueRecord:
                    if rec.SecondGlyph == right:
                        v = getattr(rec, 'Value1', None)
                        total += int(getattr(v, 'XAdvance', 0) or 0) if v else 0
            elif fmt == 2:
                if left not in st.Coverage.glyphs:
                    continue
                c1 = st.ClassDef1.classDefs.get(left, 0)
                c2 = st.ClassDef2.classDefs.get(right, 0)
                rec = st.Class1Record[c1].Class2Record[c2]
                v = getattr(rec, 'Value1', None)
                total += int(getattr(v, 'XAdvance', 0) or 0) if v else 0
    return total


def math_ic(font):
    gi = font['MATH'].table.MathGlyphInfo
    info = gi.MathItalicsCorrectionInfo
    return {g: int(v.Value) for g, v in zip(info.Coverage.glyphs, info.ItalicsCorrection)}


def topaccent(font):
    gi = font['MATH'].table.MathGlyphInfo
    ta = gi.MathTopAccentAttachment
    return {g: int(v.Value) for g, v in zip(ta.TopAccentCoverage.glyphs, ta.TopAccentAttachment)}


def _cmap_gid_map(font):
    order = font.getGlyphOrder()
    gid = {g: i for i, g in enumerate(order)}
    out = {}
    for st in font['cmap'].tables:
        if not st.isUnicode():
            continue
        for cp, g in st.cmap.items():
            out[int(cp)] = gid[g]
    return out


def _reference_name_map(target, reference):
    """Resolve canonical OTF names by unchanged GID; TTF post format 3 drops names."""
    ro = reference.getGlyphOrder()
    to = target.getGlyphOrder()
    if len(ro) != len(to):
        raise SystemExit('reference/target glyph count differs')
    if _cmap_gid_map(reference) != _cmap_gid_map(target):
        raise SystemExit('reference/target Unicode cmap -> GID mapping differs')
    return dict(zip(ro, to))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('font')
    ap.add_argument('--contract', required=True)
    ap.add_argument('--tfm-dir', required=True)
    ap.add_argument('--edition', choices=('full', 'lite'), default='full')
    ap.add_argument('--reference-font',
                    help='canonical-name reference font with identical glyph IDs; '
                         'required for post-3 TTF source audits')
    ns = ap.parse_args()
    con = json.load(open(ns.contract, encoding='utf-8'))
    f = TTFont(ns.font)
    ref = TTFont(ns.reference_font) if ns.reference_font else None
    if ref is None and 'glyf' in f and 'post' in f and float(f['post'].formatType) == 3.0:
        raise SystemExit(
            'post format 3 TrueType target requires --reference-font for canonical glyph-name resolution')
    name_map = _reference_name_map(f, ref) if ref is not None else {
        g: g for g in f.getGlyphOrder()}

    def target_name(canonical):
        return name_map.get(canonical)
    canonical_cmap = (ref.getBestCmap() if ref is not None else f.getBestCmap())
    hm = f['hmtx'].metrics
    icm = math_ic(f)
    tam = topaccent(f)
    font_by_tag = con['source_font_by_tag']
    skew = con['skewchar_by_tag']
    errors = []
    metric_checked = ta_checked = 0

    # Reparse source policy independently of the builder-generated contract.
    # This catches stale/tampered contract data without duplicating proprietary
    # skewchar values in the public auditor.
    active = source_policy.LITE_TAGS if ns.edition == 'lite' else source_policy.SOURCE_FONTS.keys()
    try:
        local_policy = source_policy.extract_policy(ns.tfm_dir, active)
    except Exception as exc:
        raise SystemExit(f'cannot reconstruct local MTPro2 source policy: {exc}') from exc
    expected_skew = dict(local_policy.skewchar_by_tag)
    expected_source_font = {tag: source_policy.SOURCE_FONTS[tag] for tag in expected_skew}
    if skew != expected_skew:
        errors.append('skewchar_by_tag differs from independently parsed local source policy')
    if font_by_tag != expected_source_font:
        errors.append('source_font_by_tag differs from the public structural source registry')
    tfms = {tag: load_tfm(ns.tfm_dir, base) for tag, base in expected_source_font.items()}

    # The public prime base and its scriptscript alternate are deliberate
    # compatibility transforms rather than source-metric glyphs. Identify those
    # exceptions from cmap + contract identity, never from a copied source slot.
    _prime = canonical_cmap.get(0x2032)
    _prime_metric_transforms = set()
    if _prime:
        for rec in con.get('records', []):
            if rec.get('output_glyph') in (_prime, _prime + '.ssty2'):
                _prime_metric_transforms.add((rec['tag'], int(rec['slot']), rec['output_glyph']))

    rec_by_key = {}
    for r in con['records']:
        tag = r['tag']
        slot = int(r['slot'])
        cg = r['output_glyph']
        rec_by_key[(tag, slot)] = r
        g = target_name(cg)
        if tag not in tfms:
            continue
        if g is None or g not in hm:
            errors.append(f'{cg}: canonical glyph cannot be resolved in target font')
            continue
        t = tfms[tag]
        if slot not in t.chars:
            errors.append(f'{tag}:{slot}: missing source char')
            continue
        wd = round((t.chars[slot].get('wd') or 0) * 1000)
        ic = round((t.chars[slot].get('ic') or 0) * 1000)
        normalized = bool(r.get('normalized_combining_accent'))
        fixed_accent = bool(r.get('fixed_source_accent'))
        want_hmtx = 0 if normalized else wd
        _prime_transformed = (tag, slot, cg) in _prime_metric_transforms
        if not _prime_transformed and hm[g][0] != want_hmtx:
            errors.append(
                f'{cg}: hmtx {hm[g][0]} != source/transform target {want_hmtx} ({tag}:{slot})')
        have_ic = icm.get(g, 0)
        if have_ic != ic:
            errors.append(f'{cg}: MATH IC {have_ic} != source IC {ic} ({tag}:{slot})')
        sk = skew.get(tag)
        skern = round(((t.kerns.get((slot, int(sk)), 0) or 0) if sk is not None else 0) * 1000)
        if normalized:
            gs = f.getGlyphSet()
            pen = BoundsPen(gs)
            gs[g].draw(pen)
            bbx = pen.bounds or (0, 0, 0, 0)
            want_ta = round((bbx[0] + bbx[2]) / 2)
        elif fixed_accent:
            want_ta = wd // 2
        else:
            want_ta = round((((t.chars[slot].get('wd') or 0) + (t.chars[slot].get('ic') or 0)) / 2
                             + ((t.kerns.get((slot, int(sk)), 0) or 0) if sk is not None else 0)) * 1000)
        have_ta = tam.get(g)
        if have_ta is None:
            errors.append(f'{cg}: TopAccent missing ({tag}:{slot})')
        elif have_ta != want_ta:
            errors.append(
                f'{cg}: TopAccent {have_ta} != {want_ta} ({tag}:{slot}, skew={sk}, skern={skern})')
        metric_checked += 1
        ta_checked += 1

    # Independently reconstruct every explicit ordinary TFM pair from imported source slots.
    expected_kern = {}
    for tag, t in tfms.items():
        sk = skew.get(tag)
        slots = {slot: r['output_glyph'] for (tg, slot), r in rec_by_key.items() if tg == tag}
        for (l, r), v in t.kerns.items():
            if sk is not None and int(r) == int(sk):
                continue
            if l not in slots or r not in slots:
                continue
            k = round((v or 0) * 1000)
            if not k:
                continue
            key = (slots[l], slots[r])
            prev = expected_kern.get(key)
            if prev is not None and prev != k:
                errors.append(f'{key[0]}/{key[1]}: conflicting independent TFM kern {prev} vs {k}')
            expected_kern[key] = k

    contract_kern = {(r['left'], r['right']): int(r['xadvance'])
                     for r in con.get('tfm_kern_pairs', [])}
    if contract_kern != expected_kern:
        miss = [(k, v) for k, v in expected_kern.items() if contract_kern.get(k) != v]
        extra = [(k, v) for k, v in contract_kern.items() if expected_kern.get(k) != v]
        if miss:
            errors.append('contract missing/wrong TFM kern: ' + \
                          ', '.join(f'{a}/{b}:{v:+d}' for (a, b), v in miss[:12]))
        if extra:
            errors.append('contract extra/wrong TFM kern: ' + \
                          ', '.join(f'{a}/{b}:{v:+d}' for (a, b), v in extra[:12]))

    # Reconstruct the expected ordinary-IC left set from source records and the
    # independently stated TeX-family domain above; do not trust the builder JSON
    # to define its own coverage.
    expected_left_ic = {}
    for r in con['records']:
        tag = r['tag']
        slot = int(r['slot'])
        g = r['output_glyph']
        if tag not in tfms or not expected_ordinary_left(tag, slot):
            continue
        t = tfms[tag]
        if slot not in t.chars:
            continue
        val = round((t.chars[slot].get('ic') or 0) * 1000)
        if val:
            prev = expected_left_ic.get(g)
            if prev is not None and prev != val:
                errors.append(
                    f'{g}: independently reconstructed ordinary IC conflict {prev} vs {val}')
            expected_left_ic[g] = val

    left_ic = {r['glyph']: int(r['italic_correction']) for r in con.get('ordinary_ic_lefts', [])}
    if left_ic != expected_left_ic:
        miss = [(g, v) for g, v in expected_left_ic.items() if left_ic.get(g) != v]
        extra = [(g, v) for g, v in left_ic.items() if expected_left_ic.get(g) != v]
        if miss:
            errors.append('ordinary IC contract missing/wrong: ' + \
                          ', '.join(f'{g}:{v:+d}' for g, v in miss[:16]))
        if extra:
            errors.append('ordinary IC contract extra/wrong: ' + \
                          ', '.join(f'{g}:{v:+d}' for g, v in extra[:16]))
    mapped_lefts = {target_name(g) for g in left_ic if target_name(g) is not None}
    rights = _right_domain(f, mapped_lefts)

    # Every ordinary IC left must show its IC against a broad neutral right.
    # Canonical contract names are resolved to target names by glyph ID when the
    # target is a post-format-3 TTF.
    neutral_canon = canonical_cmap.get(0x30) or canonical_cmap.get(0x31)
    neutral = target_name(neutral_canon) if neutral_canon else None
    if not neutral_canon or not neutral:
        errors.append('no neutral digit glyph for IC bridge audit')
    else:
        for cg, ic in left_ic.items():
            g = target_name(cg)
            if g is None:
                errors.append(f'{cg}: ordinary IC glyph cannot be resolved in target font')
                continue
            want = ic + expected_kern.get((cg, neutral_canon), 0)
            got = pair_xadvance(f, g, neutral)
            if got != want:
                errors.append(
                    f'{cg}/{neutral_canon}: combined PairPos {got:+d} != IC+kern {want:+d}')

    # Every explicit source kern must accumulate IC if its left glyph is an
    # ordinary IC left and the mapped right glyph belongs to the ordinary bridge
    # domain.
    for (cl, cr), k in expected_kern.items():
        l = target_name(cl)
        r = target_name(cr)
        if l is None or r is None:
            errors.append(f'{cl}/{cr}: source pair cannot be resolved in target font')
            continue
        want = k + (left_ic.get(cl, 0) if r in rights else 0)
        got = pair_xadvance(f, l, r)
        if got != want:
            errors.append(f'{cl}/{cr}: serialized PairPos {got:+d} != source total {want:+d}')

    if errors:
        for e in errors[:60]:
            print('source-contract:', e)
        raise SystemExit(f'SOURCE CONTRACT FAIL: {len(errors)} errors')
    print(f'SOURCE CONTRACT OK: metrics {metric_checked}; TopAccent {ta_checked}; '
          f'ordinary IC lefts {len(left_ic)}; TFM pairs {len(expected_kern)}')


if __name__ == '__main__':
    main()
