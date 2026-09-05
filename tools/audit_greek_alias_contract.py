#!/usr/bin/env python3
"""Audit same-GID Latin-shaped Greek aliases without adding glyphs or metrics."""
import sys
from fontTools.ttLib import TTFont

EXPECTED = {
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


def cmap_gid(font):
    order = font.getGlyphOrder()
    gid = {g: i for i, g in enumerate(order)}
    return {cp: gid[g] for cp, g in font.getBestCmap().items()}


def main(path):
    f = TTFont(path)
    cmap = cmap_gid(f)
    errors = []
    for alias_cp, source_cp in EXPECTED.items():
        if alias_cp not in cmap:
            errors.append(f'U+{alias_cp:04X}: alias missing')
            continue
        if source_cp not in cmap:
            errors.append(f'U+{alias_cp:04X}: donor U+{source_cp:04X} missing')
            continue
        if cmap[alias_cp] != cmap[source_cp]:
            errors.append(
                f'U+{alias_cp:04X}: GID {cmap[alias_cp]} != donor U+{source_cp:04X} GID {cmap[source_cp]}')
    if errors:
        for e in errors:
            print('ERROR:', e, file=sys.stderr)
        raise SystemExit('Greek Latin-shaped alias contract FAIL: %d/30 errors' % len(errors))
    print('Greek Latin-shaped alias contract PASS: 30/30 same-GID aliases')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: audit_greek_alias_contract.py FONT')
    main(sys.argv[1])
