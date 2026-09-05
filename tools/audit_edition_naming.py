#!/usr/bin/env python3
import argparse, sys
from fontTools.ttLib import TTFont
EXPECTED = {'full': dict(family='MTPro2 Math', ps='MTPro2Math', unique='MTP2;MTPro2Math'), 'lite': dict(
    family='MTPro2 Math Lite', ps='MTPro2MathLite', unique='MTP2;MTPro2MathLite')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('font')
    ap.add_argument('--edition', choices=('full', 'lite'), required=True)
    ns = ap.parse_args()
    e = EXPECTED[ns.edition]
    f = TTFont(ns.font)
    by = {}
    bad = []
    for n in f['name'].names:
        try:
            v = n.toUnicode()
        except Exception:
            continue
        by.setdefault(n.nameID, set()).add(v)
    want = {1: {e['family']}, 2: {'Regular'}, 3: {e['unique']}, 4: {e['family']},
            5: {'Version 1.0'}, 6: {e['ps']}, 16: {e['family']}, 17: {'Regular'}}
    for nid, w in want.items():
        if by.get(nid) != w:
            bad.append('name ID %d = %r, expected %r' % (nid, by.get(nid), w))
    if 'CFF ' in f:
        c = f['CFF '].cff
        top = c.topDictIndex[0]
        if list(c.fontNames) != [e['ps']]:
            bad.append('CFF fontNames = %r' % list(c.fontNames))
        for attr, w in [('FontName', e['ps']), ('FullName', e['family']), ('FamilyName', e['family']), ('Weight', 'Regular')]:
            if getattr(top, attr, None) != w:
                bad.append('CFF %s = %r, expected %r' % (attr, getattr(top, attr, None), w))
    if bad:
        for x in bad:
            print('edition naming:', x, file=sys.stderr)
        raise SystemExit('EDITION NAMING CONTRACT FAIL')
    print('EDITION NAMING CONTRACT PASS: %s -> family=%r PS=%r' %
          (ns.edition, e['family'], e['ps']))


if __name__ == '__main__':
    main()
