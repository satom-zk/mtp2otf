#!/usr/bin/env python3
"""Check Lite capabilities and reserve missing Full-only identities."""
from __future__ import annotations
import argparse
from fontTools.ttLib import TTFont

# Full-only GSUB features whose source families are absent from official Lite.
ABSENT_FEATURES = {'cv02', 'cv03', 'cv04', 'cv05', 'cv06', 'cv07', 'cv09', 'cv10', 'salt'}
# Core/shared features expected from the 15 Lite source families.
PRESENT_FEATURES = {'ccmp', 'cv01', 'cv08', 'cv11', 'cv12', 'dtls', 'ssty'}

# Unicode/PUA semantic sentinels.
ABSENT_CODEPOINTS = {
    0x00F0: 'AMSa eth (must not be replaced by Roman-donor text eth)',
    0x1D538: 'Mathematical double-struck A',
    0x1D49C: 'Mathematical script A',
    0x1D504: 'Mathematical fraktur A',
    0x1D468: 'Mathematical bold italic A',
    0xE001: 'Full-only varnothing PUA',
}
PRESENT_CODEPOINTS = {
    0x1D434: 'Mathematical italic A',
    0x1D400: 'standard Mathematical Bold A (selected rmdefault donor path)',
    0xE000: 'zswash PUA mapping',
    0xE286: 'wideoverbar.compat',
    0xE287: 'widevector.compat',
}


def feature_tags(font):
    if 'GSUB' not in font:
        return set()
    fl = font['GSUB'].table.FeatureList
    if not fl:
        return set()
    return {r.FeatureTag for r in fl.FeatureRecord}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('font')
    ns = ap.parse_args()
    f = TTFont(ns.font, lazy=False)
    cmap = f.getBestCmap() or {}
    tags = feature_tags(f)
    errors = []

    for tag in sorted(ABSENT_FEATURES & tags):
        errors.append(f'Full-only GSUB feature present in Lite: {tag}')
    for tag in sorted(PRESENT_FEATURES - tags):
        errors.append(f'core/shared GSUB feature missing in Lite: {tag}')

    for cp, label in ABSENT_CODEPOINTS.items():
        if cp in cmap:
            errors.append(f'U+{cp:04X} unexpectedly present in Lite: {label} -> {cmap[cp]}')
    for cp, label in PRESENT_CODEPOINTS.items():
        if cp not in cmap:
            errors.append(f'U+{cp:04X} missing in Lite: {label}')

    if errors:
        for e in errors:
            print('LITE-SEMANTIC:', e)
        raise SystemExit(f'MTPro2 Lite semantic contract FAIL: {len(errors)} errors')
    print('MTPro2 Lite semantic contract PASS: Full-only source semantics remain absent; '
          'core/shared features and PUA sentinels reachable')


if __name__ == '__main__':
    main()
