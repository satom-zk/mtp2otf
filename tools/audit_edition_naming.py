#!/usr/bin/env python3
import argparse, re, sys
from fontTools.ttLib import TTFont
from build_config import EDITIONS, FONT_REVISION, FONT_VERSION, identity

PACKAGE_VERSION_RE = re.compile(r'(?i)\bv?\d+\.\d+(?:\.\d+)?\b')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('font')
    ap.add_argument('--edition', choices=EDITIONS, required=True)
    ns = ap.parse_args()
    family, psname, unique = identity(ns.edition)
    e = dict(family=family, ps=psname, unique=unique)
    f = TTFont(ns.font)
    by = {}
    bad = []
    if abs(float(f['head'].fontRevision) - FONT_REVISION) > 1e-9:
        bad.append('head.fontRevision differs from the technical font revision')
    for n in f['name'].names:
        try:
            v = n.toUnicode()
        except Exception:
            continue
        by.setdefault(n.nameID, set()).add(v)
        if n.nameID not in (0, 5, 7) and PACKAGE_VERSION_RE.search(v):
            bad.append('package version string in name ID %d: %r' % (n.nameID, v))
    want = {1: {e['family']}, 2: {'Regular'}, 3: {e['unique']}, 4: {e['family']},
            5: {FONT_VERSION}, 6: {e['ps']}, 16: {e['family']}, 17: {'Regular'}}
    for nid, w in want.items():
        if by.get(nid) != w:
            bad.append('name ID %d = %r, expected %r' % (nid, by.get(nid), w))
    if 'CFF ' in f:
        c = f['CFF '].cff
        top = c.topDictIndex[0]
        if getattr(top, 'version', None) not in (None, ''):
            bad.append('CFF Top DICT version must be absent')
        if list(c.fontNames) != [e['ps']]:
            bad.append('CFF fontNames = %r' % list(c.fontNames))
        for attr, w in [('FontName', e['ps']), ('FullName', e['family']), ('FamilyName', e['family']), ('Weight', 'Regular')]:
            if getattr(top, attr, None) != w:
                bad.append('CFF %s = %r, expected %r' % (attr, getattr(top, attr, None), w))
    if bad:
        for x in bad:
            print('edition naming:', x, file=sys.stderr)
        raise SystemExit('EDITION NAMING CONTRACT FAIL')


if __name__ == '__main__':
    main()
