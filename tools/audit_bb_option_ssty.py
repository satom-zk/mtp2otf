#!/usr/bin/env python3
"""Audit optical blackboard options for both cv/ssty shaping orders."""
from __future__ import annotations
import argparse, json
from fontTools.ttLib import TTFont
import uni_map as U

CV = {
    'cv03': ('bbd', 'bbd_s', 'bbd_ss'),
    'cv04': ('bbi', 'bbi_s', 'bbi_ss'),
    'cv05': ('hrb', 'hrb_s', 'hrb_ss'),
    'cv06': ('hrbd', 'hrbd_s', 'hrbd_ss'),
    'cv07': ('hbi', 'hbi_s', 'hbi_ss'),
}
BASE = ('bb', 'bb_s', 'bb_ss')


def feature_lookups(font, tag):
    t = font['GSUB'].table
    out = []
    if not t.FeatureList or not t.LookupList:
        return out
    for fr in t.FeatureList.FeatureRecord:
        if fr.FeatureTag == tag:
            out.extend(t.LookupList.Lookup[i] for i in fr.Feature.LookupListIndex)
    return out


def single_mapping(font, tag):
    out = {}
    for lk in feature_lookups(font, tag):
        for st in lk.SubTable:
            if lk.LookupType == 1:
                out.update(getattr(st, 'mapping', {}) or {})
            elif lk.LookupType == 7 and getattr(st, 'ExtensionLookupType', None) == 1:
                out.update(getattr(st.ExtSubTable, 'mapping', {}) or {})
    return out


def alternate_mapping(font, tag):
    out = {}
    for lk in feature_lookups(font, tag):
        for st in lk.SubTable:
            if lk.LookupType == 3:
                out.update(getattr(st, 'alternates', {}) or {})
            elif lk.LookupType == 7 and getattr(st, 'ExtensionLookupType', None) == 3:
                out.update(getattr(st.ExtSubTable, 'alternates', {}) or {})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('font')
    ap.add_argument('--contract', required=True)
    ns = ap.parse_args()
    f = TTFont(ns.font)
    con = json.load(open(ns.contract, encoding='utf-8'))
    by = {}
    for r in con['records']:
        by[(r['tag'], int(r['slot']))] = r['output_glyph']

    slots = sorted(U.alpha_map('bb'))
    errors = []
    ssty = alternate_mapping(f, 'ssty')
    checked_cv = checked_ssty = 0
    for cv, tags in CV.items():
        cmap = single_mapping(f, cv)
        for level, (bt, at) in enumerate(zip(BASE, tags)):
            for slot in slots:
                b = by.get((bt, slot))
                a = by.get((at, slot))
                if not b or not a:
                    errors.append(
                        f'{cv}: missing source record level{level} slot {slot}: {bt}->{at}')
                    continue
                got = cmap.get(b)
                if got != a:
                    errors.append(f'{cv}: {b} -> {got!r}, expected {a} (level{level} slot {slot})')
                else:
                    checked_cv += 1
        # Also require cv->ssty path for the option text glyph itself.
        text, script, ss = tags
        for slot in slots:
            b = by.get((text, slot))
            a1 = by.get((script, slot))
            a2 = by.get((ss, slot))
            if not b or not a1 or not a2:
                continue
            got = ssty.get(b)
            if got is None or list(got)[:2] != [a1, a2]:
                errors.append(f'ssty: {b} -> {got!r}, expected [{a1}, {a2}] ({cv} slot {slot})')
            else:
                checked_ssty += 1

    if errors:
        for e in errors[:80]:
            print('BB OPTION SSTY:', e)
        raise SystemExit(f'BB OPTION SSTY FAIL: {len(errors)} errors')
    expected = len(slots) * 3 * len(CV)
    expected_ssty = len(slots) * len(CV)
    if checked_cv != expected or checked_ssty != expected_ssty:
        raise SystemExit(
            f'BB OPTION SSTY FAIL: checked cv={checked_cv}/{expected}, ssty={checked_ssty}/{expected_ssty}')
    print(
        f'BB OPTION SSTY CONTRACT OK: cv03..cv07 {checked_cv} mappings; option ssty {checked_ssty} mappings')


if __name__ == '__main__':
    main()
