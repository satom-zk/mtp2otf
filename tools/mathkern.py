"""Apply optional subscript corrections as TopLeft MathKern values.

Other corners remain unset; script-size alternates share the correction.
"""
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot

MU = 1000.0 / 18.0

# Optional subscript corrections in TeX math units.
SUB_CORR_MU = {
    'f': -3, 'j': -2, 'p': -2, 't': +1, 'y': -1,
    'A': -2, 'B': -1, 'D': -1, 'H': -1, 'I': -1,
    'K': -1, 'L': -1, 'M': -1, 'P': -1, 'X': -2,
}


# Map letters to mathematical italic codepoints.
def _codepoint(ch):
    if 'A' <= ch <= 'Z':
        return 0x1D434 + (ord(ch) - ord('A'))
    return 0x1D44E + (ord(ch) - ord('a'))


def _value(v):
    r = ot.MathValueRecord()
    r.Value = int(round(v))
    r.DeviceTable = None
    return r


def _const_kern(v):
    k = ot.MathKern()
    k.HeightCount = 0
    k.CorrectionHeight = []
    k.KernValue = [_value(v)]
    return k


def apply(path, verbose=True):
    f = TTFont(path)
    if 'MATH' not in f:
        return
    cmap = f.getBestCmap()
    gsub = f['GSUB'].table if 'GSUB' in f else None

    # Apply the same correction to optical script forms.
    ssty_alts = {}
    if gsub:
        for lookup_index, lookup in enumerate(gsub.LookupList.Lookup):
            pass
        for fr in gsub.FeatureList.FeatureRecord:
            if fr.FeatureTag != 'ssty':
                continue
            for li in fr.Feature.LookupListIndex:
                lk = gsub.LookupList.Lookup[li]
                for st in lk.SubTable:
                    if getattr(st, 'alternates', None):
                        for base, alts in st.alternates.items():
                            ssty_alts.setdefault(base, []).extend(alts)

    kerns = {}
    for ch, mu in SUB_CORR_MU.items():
        gname = cmap.get(_codepoint(ch))
        if not gname:
            continue
        val = mu * MU
        for g in [gname] + ssty_alts.get(gname, []):
            kerns[g] = val

    if not kerns:
        return

    records, glyphs = [], []
    for g in sorted(kerns, key=lambda n: f.getGlyphID(n)):
        rec = ot.MathKernInfoRecord()
        rec.TopRightMathKern = None
        rec.BottomLeftMathKern = None
        rec.BottomRightMathKern = None
        rec.TopLeftMathKern = _const_kern(kerns[g])
        records.append(rec)
        glyphs.append(g)

    cov = ot.Coverage()
    cov.glyphs = glyphs
    info = ot.MathKernInfo()
    info.MathKernCoverage = cov
    info.MathKernInfoRecords = records
    info.MathKernCount = len(records)
    f['MATH'].table.MathGlyphInfo.MathKernInfo = info
    f.save(path)
    if verbose:
        print('MathKern: %d glyphs' % len(records))


if __name__ == '__main__':
    import sys
    for p in sys.argv[1:]:
        apply(p)
