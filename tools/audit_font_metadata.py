#!/usr/bin/env python3
"""Enforce fixed Windows-compatible font metadata."""
import re, sys
from fontTools.ttLib import TTFont

PACKAGE_VERSION_RE = re.compile(r'(?i)\bv?\d+\.\d+(?:\.\d+)?\b')


def main(path):
    f = TTFont(path)
    bad = []
    rev = float(f['head'].fontRevision)
    if abs(rev - 1.0) > 1e-9:
        bad.append('head.fontRevision must be fixed technical 1.0, got %r' % rev)
    byid = {}
    for n in f['name'].names:
        try:
            s = n.toUnicode()
        except Exception:
            continue
        byid.setdefault(n.nameID, set()).add(s)
        if n.nameID not in (0, 5, 7) and PACKAGE_VERSION_RE.search(s):
            bad.append('package version string in name ID %d: %r' % (n.nameID, s))
    if byid.get(3) not in ({'MTP2;MTPro2Math'}, {'MTP2;MTPro2MathLite'}):
        bad.append('name ID 3 must be the MTPro2Math edition Unique ID: %r' % byid.get(3))
    if byid.get(5) != {'Version 1.0'}:
        bad.append('name ID 5 must be fixed technical Version 1.0: %r' % byid.get(5))
    if 'CFF ' in f:
        top = f['CFF '].cff.topDictIndex[0]
        if getattr(top, 'version', None) not in (None, ''):
            bad.append('CFF Top DICT version must be absent: %r' % getattr(top, 'version', None))
    if bad:
        for x in bad:
            print('metadata:', x, file=sys.stderr)
        raise SystemExit('FONT METADATA CONTRACT FAIL')
    print('FONT METADATA CONTRACT OK: fixed names and Windows-compatible technical Version 1.0')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: audit_font_metadata.py FONT')
    main(sys.argv[1])
