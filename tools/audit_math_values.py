#!/usr/bin/env python3
"""Compare serialized MATH values with the local build snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from fontTools.ttLib import TTFont


def _scalar(value):
    return int(getattr(value, 'Value', value))


def load_expected(path: str | Path) -> dict[str, int]:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    constants = data.get('constants')
    if not isinstance(constants, dict):
        raise ValueError('local MATH snapshot has no constants object')
    expected = {str(k): int(v) for k, v in constants.items()}
    if 'MinConnectorOverlap' not in data:
        raise ValueError('local MATH snapshot has no MinConnectorOverlap')
    expected['MinConnectorOverlap'] = int(data['MinConnectorOverlap'])
    return expected


def audit(font_path: str | Path, values_path: str | Path) -> dict:
    expected = load_expected(values_path)
    font = TTFont(str(font_path))
    if 'MATH' not in font:
        raise ValueError(f'{font_path}: no MATH table')
    table = font['MATH'].table
    constants = table.MathConstants
    actual = {}
    missing = []
    for public_name in expected:
        if public_name == 'MinConnectorOverlap':
            actual[public_name] = int(table.MathVariants.MinConnectorOverlap)
            continue
        ot_name = public_name
        if not hasattr(constants, ot_name):
            missing.append((public_name, ot_name))
            continue
        actual[public_name] = _scalar(getattr(constants, ot_name))

    mismatches = {
        name: {'expected': expected[name], 'actual': actual.get(name)}
        for name in expected
        if name not in actual or actual[name] != expected[name]
    }
    if missing or mismatches:
        if missing:
            for public_name, ot_name in missing:
                print(f'MATH VALUE MISSING: {public_name} ({ot_name})')
        for name, vals in sorted(mismatches.items()):
            print('MATH VALUE MISMATCH: %s expected=%s actual=%s' %
                  (name, vals['expected'], vals['actual']))
        raise SystemExit(1)

    result = {
        'font': Path(font_path).name,
        'values_file': Path(values_path).name,
        'checked_names': sorted(expected),
        'actual': {k: actual[k] for k in sorted(actual)},
    }
    print('LOCAL MATH VALUES PASS: %s (%d scalars)' %
          (Path(font_path).name, len(expected)))
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('font')
    ap.add_argument('--values', required=True)
    ap.add_argument('--json-output')
    ns = ap.parse_args()
    result = audit(ns.font, ns.values)
    if ns.json_output:
        Path(ns.json_output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
            encoding='utf-8')


if __name__ == '__main__':
    main()
