#!/usr/bin/env python3
"""Write private build provenance and evaluated values under out/<edition>/."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from audit_math_values import audit as audit_math_values
from fontTools.ttLib import TTFont


def _load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _active_source_files(mtpro2: Path, policy: dict) -> list[Path]:
    files = []
    for base in sorted(set(policy.get('source_font_by_tag', {}).values())):
        for suffix in ('.pfb', '.tfm'):
            p = mtpro2 / (base + suffix)
            if not p.is_file():
                raise FileNotFoundError(p)
            files.append(p)
    policy_files = policy.get('policy_source_files')
    if not isinstance(policy_files, list) or not policy_files:
        raise ValueError('source policy snapshot has no policy_source_files')
    for name in policy_files:
        p = mtpro2 / str(name)
        if not p.is_file():
            raise FileNotFoundError(p)
        files.append(p)
    return sorted(set(files))


def _file_record(path: Path) -> dict:
    return {'name': path.name, 'sha256': _sha256(path), 'size': path.stat().st_size}


def _donor_record(path: Path, role: str) -> dict:
    font = TTFont(path)
    names = []
    for name_id in (16, 1):
        for record in font['name'].names:
            if record.nameID != name_id:
                continue
            try:
                value = record.toUnicode().strip()
            except Exception:
                continue
            if value:
                names.append(value)
        if names:
            break
    outline = 'CFF' if 'CFF ' in font else 'TrueType' if 'glyf' in font else 'unknown'
    result = _file_record(path)
    result.update({
        'role': role,
        'family': sorted(set(names), key=lambda value: (len(value), value.casefold()))[0]
                  if names else None,
                  'units_per_em': int(font['head'].unitsPerEm),
                  'weight_class': int(font['OS/2'].usWeightClass),
                  'outline_format': outline,
                  })
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--edition', choices=('full', 'lite'), required=True)
    ap.add_argument('--source-policy', required=True)
    ap.add_argument('--source-contract', required=True)
    ap.add_argument('--math-values', required=True)
    ap.add_argument('--otf', required=True)
    ap.add_argument('--ttf', required=True)
    ap.add_argument('--mtpro2-dir', required=True)
    ap.add_argument('--regular-donor', required=True)
    ap.add_argument('--bold-donor', required=True)
    ap.add_argument('--output-dir', required=True)
    ns = ap.parse_args()

    output = Path(ns.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    policy_path = Path(ns.source_policy)
    contract_path = Path(ns.source_contract)
    math_path = Path(ns.math_values)
    mtpro2 = Path(ns.mtpro2_dir)
    otf = Path(ns.otf)
    ttf = Path(ns.ttf)

    policy = _load(policy_path)
    contract = _load(contract_path)
    math_values = _load(math_path)
    otf_check = audit_math_values(otf, math_path)
    ttf_check = audit_math_values(ttf, math_path)

    source_files = [_file_record(p) for p in _active_source_files(mtpro2, policy)]
    donors = [
        _donor_record(Path(ns.regular_donor), 'regular'),
        _donor_record(Path(ns.bold_donor), 'bold'),
    ]

    local_source = {
        'edition': ns.edition,
        'source_files': source_files,
        'donor_files': donors,
        'source_policy': policy,
        'source_contract': contract,
    }
    (output / 'LOCAL-SOURCE-VALUES.json').write_text(
        json.dumps(local_source, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        encoding='utf-8')

    local_math = {
        'edition': ns.edition,
        'computed': math_values,
        'serialized_font_checks': {'otf': otf_check, 'ttf': ttf_check},
    }
    (output / 'LOCAL-MATH-VALUES.json').write_text(
        json.dumps(local_math, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        encoding='utf-8')

    records = contract.get('records', [])
    lefts = contract.get('ordinary_ic_lefts', [])
    pairs = contract.get('tfm_kern_pairs', [])
    lines = [
        'MTPro2Math local build memo',
        '===========================',
        f'edition: {ns.edition}',
        f'OTF: {otf.name} sha256={_sha256(otf)}',
        f'TTF: {ttf.name} sha256={_sha256(ttf)}',
        '',
        'Local source snapshot',
        f'active source files: {len(source_files)}',
        f'source metric records: {len(records)}',
        f'ordinary nonzero-IC lefts: {len(lefts)}',
        f'ordinary TFM kern pairs: {len(pairs)}',
        '',
        'Selected upright Roman donors',
        *(f"{record['role']}: {record['family']} / {record['outline_format']} / "
          f"{record['units_per_em']} UPM / weight {record['weight_class']} / "
          f"{record['name']} sha256={record['sha256']}" for record in donors),
        '',
        'MATH scalar values (computed from this local source/build policy)',
    ]
    for name, value in sorted(math_values.get('constants', {}).items()):
        lines.append(f'{name} = {value}')
    lines.append('MinConnectorOverlap = %s' % math_values.get('MinConnectorOverlap'))
    lines.append('')
    (output / 'LOCAL-BUILD-MEMO.txt').write_text('\n'.join(lines), encoding='utf-8')
    print('local build evidence written:', output)


if __name__ == '__main__':
    main()
