"""Add Word same-run prime forms shifted by preceding MATH italic correction.

Use padding and measurements from the local build and generated font.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import unicodedata

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen


# Context classes are a compact Word-compatibility approximation, expressed as
# fractions of the output em rather than copied MTPro2 measurements.
_CLASS_STEP = Fraction(3, 100)
_CLASS_CAP = Fraction(27, 100)


def _scaled_policy(upm: int) -> tuple[int, int]:
    step = max(1, round(_CLASS_STEP * upm))
    cap = max(step, round(_CLASS_CAP * upm))
    return step, cap


def apply(path: str, *, base_shift: int, verbose: bool = True) -> None:
    f = TTFont(path)
    if 'MATH' not in f or 'GSUB' not in f:
        return
    if 'CFF ' not in f:
        raise ValueError('prime contextualization expects the generated CFF OTF')

    cmap = f.getBestCmap()
    gi = f['MATH'].table.MathGlyphInfo
    icinfo = gi.MathItalicsCorrectionInfo
    ics = dict(zip(icinfo.Coverage.glyphs,
                   [v.Value for v in icinfo.ItalicsCorrection]))
    step, cap = _scaled_policy(f['head'].unitsPerEm)

    # Only encoded mathematical letters participate.  Operators and punctuation
    # follow their own OpenType MATH placement paths.
    classes: dict[int, list[str]] = {}
    for u, g in cmap.items():
        if u < 0x370:
            continue
        try:
            category = unicodedata.category(chr(u))
        except ValueError:
            continue
        if not category.startswith('L'):
            continue
        ic = int(ics.get(g, 0) or 0)
        klass = max(0, min(cap, int(round(ic / step)) * step))
        if abs(klass - base_shift) < step / 2:
            continue
        classes.setdefault(klass, []).append(g)
    if not classes:
        return

    primes = [g for g in (cmap.get(0x2032), cmap.get(0x2033),
                          cmap.get(0x2034), cmap.get(0x2057)) if g]
    if not primes:
        return

    # Create translated copies.  Width and left sidebearing move by the same
    # delta, so the outline-to-advance relationship is preserved exactly.
    cff = f['CFF '].cff[f['CFF '].cff.fontNames[0]]
    cs = cff.CharStrings
    hmtx = f['hmtx']
    order = f.getGlyphOrder()
    glyphset = f.getGlyphSet()
    made: dict[tuple[str, int], str] = {}
    for klass in sorted(classes):
        dx = klass - int(base_shift)
        for src in primes:
            new = f'{src}.ic{klass}'
            rp = RecordingPen()
            glyphset[src].draw(rp)
            width = hmtx[src][0] + dx
            pen = T2CharStringPen(width, None)
            rp.replay(TransformPen(pen, (1, 0, 0, 1, dx, 0)))
            chstr = pen.getCharString(private=cs[src].private,
                                      globalSubrs=cs.globalSubrs)
            cs.charStringsIndex.append(chstr)
            cs.charStrings[new] = len(cs.charStringsIndex) - 1
            hmtx[new] = (width, hmtx[src][1] + dx)
            order.append(new)
            made[(src, klass)] = new
    f.setGlyphOrder(order)
    cff.charset = order
    f['maxp'].numGlyphs = len(order)

    gsub = f['GSUB'].table
    lookups = gsub.LookupList.Lookup

    def single_lookup(mapping):
        st = ot.SingleSubst()
        st.mapping = dict(mapping)
        lk = ot.Lookup()
        lk.LookupType = 1
        lk.LookupFlag = 0
        lk.SubTable = [st]
        lk.SubTableCount = 1
        lookups.append(lk)
        return len(lookups) - 1

    def coverage(glyphs):
        c = ot.Coverage()
        c.glyphs = sorted(set(glyphs), key=f.getGlyphID)
        return c

    ctx_indices = []
    for klass in sorted(classes):
        sub_idx = single_lookup({src: made[(src, klass)] for src in primes})
        chain = ot.ChainContextSubst()
        chain.Format = 3
        chain.BacktrackGlyphCount = 1
        chain.BacktrackCoverage = [coverage(classes[klass])]
        chain.InputGlyphCount = 1
        chain.InputCoverage = [coverage(primes)]
        chain.LookAheadGlyphCount = 0
        chain.LookAheadCoverage = []
        rec = ot.SubstLookupRecord()
        rec.SequenceIndex = 0
        rec.LookupListIndex = sub_idx
        chain.SubstLookupRecord = [rec]
        chain.SubstCount = 1
        lk = ot.Lookup()
        lk.LookupType = 6
        lk.LookupFlag = 0
        lk.SubTable = [chain]
        lk.SubTableCount = 1
        lookups.append(lk)
        ctx_indices.append(len(lookups) - 1)
    gsub.LookupList.LookupCount = len(lookups)

    feature_count = 0
    for fr in gsub.FeatureList.FeatureRecord:
        if fr.FeatureTag == 'ccmp':
            fr.Feature.LookupListIndex.extend(ctx_indices)
            fr.Feature.LookupCount = len(fr.Feature.LookupListIndex)
            feature_count += 1
    f.save(path)
    if verbose:
        print('prime contextual coverage:', len(classes), 'IC classes x',
              len(primes), 'prime forms;', feature_count, 'ccmp records')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('font')
    ap.add_argument('--base-shift', required=True, type=int,
                    help='local source-derived raw-prime padding')
    ns = ap.parse_args()
    apply(ns.font, base_shift=ns.base_shift)


if __name__ == '__main__':
    main()
