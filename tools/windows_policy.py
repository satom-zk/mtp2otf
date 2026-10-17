"""Bind final source-TTF Windows values to this run's FontForge
measurement.
"""

import hashlib
import json
from pathlib import Path

from config import identity
from compatibility_metrics import integer_values, validate, validate_identity


POLICY = 'source-ttf-fontforge-compatibility-windows/1'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    obj = json.loads(Path(path).read_text(encoding='utf-8'))
    if obj.get('policy') != POLICY or obj.get('profile') != 'source':
        raise ValueError('invalid Windows policy')
    validate_identity(obj)
    measurement = obj.get('measurement')
    if not isinstance(measurement, dict):
        raise ValueError('Windows policy lacks current measurement')
    validate(
        measurement,
        {'build_identity': obj['identity'], 'inputs': obj['input_hashes']},
    )
    for key in ('Windows', 'typo', 'hhea', 'upm'):
        if obj.get(key) != measurement[key]:
            raise ValueError('Windows policy/measurement mismatch: ' + key)
    integer_values(obj, 'source_head_bbox', 4, -32768, 32767)
    if (
        not isinstance(obj.get('source_otf_sha256'), str)
        or len(obj['source_otf_sha256']) != 64
    ):
        raise ValueError('Windows policy lacks source artifact identity')
    return obj


def provenance_errors(obj, edition, manifest, source_path=None):
    out = []
    if edition is None:
        out.append('Windows policy caller edition absent')
    elif obj['identity']['edition'] != edition:
        out.append('Windows policy edition mismatch')
    if manifest is None:
        out.append(
            'Windows policy input manifest absent: provenance unverified'
        )
    else:
        snapshot = json.loads(Path(manifest).read_text(encoding='utf-8'))
        if snapshot.get('large_variants') != 'source':
            out.append('Windows policy source condition mismatch')
        if obj['identity'] != snapshot.get('build_identity'):
            out.append('Windows policy run/edition/coverage/UPM mismatch')
        if obj['input_hashes'] != snapshot.get('inputs'):
            out.append('Windows policy source input mismatch')
    if source_path is None:
        out.append(
            'Windows policy source OTF path absent: provenance unverified'
        )
    elif sha(source_path) != obj['source_otf_sha256']:
        out.append('Windows policy source OTF hash mismatch')
    return out


def errors(
    font,
    obj,
    profile,
    *,
    font_path=None,
    edition=None,
    manifest=None,
    source_path=None
):
    if profile != 'source' or 'glyf' not in font:
        return ['Windows compatibility policy is restricted to source TTF']
    out = provenance_errors(obj, edition, manifest, source_path)
    os2, hhea = font['OS/2'], font['hhea']
    if font_path is None:
        out.append(
            'Windows policy target TTF path absent: artifact unverified'
        )
    elif (
        not obj.get('target_ttf_sha256')
        or sha(font_path) != obj['target_ttf_sha256']
    ):
        out.append('Windows policy target TTF hash mismatch')
    actual = {
        'Windows': [os2.usWinAscent, os2.usWinDescent],
        'typo': [os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap],
        'hhea': [hhea.ascent, hhea.descent, hhea.lineGap],
        'upm': font['head'].unitsPerEm,
    }
    for key, value in actual.items():
        if value != obj[key]:
            out.append('Windows policy ' + key + ' mismatch')
    if [
        getattr(font['head'], n) for n in ('xMin', 'yMin', 'xMax', 'yMax')
    ] != obj.get('source_ttf_head_bbox'):
        out.append('Windows policy source bbox changed')
    head = font['head']
    if head.yMax <= os2.usWinAscent and -head.yMin <= os2.usWinDescent:
        out.append('Windows source TTF exception lacks noncontainment')
    return out


def derive(source_otf, measurement, snapshot, source_sha):
    """Use explicitly bound numeric input, never a legacy final
    file/path.
    """
    from fontTools.ttLib import TTFont

    validate(measurement, snapshot)
    edition = snapshot['build_identity']['edition']
    with TTFont(source_otf) as font:
        if font['name'].getDebugName(6) != identity(edition)[1]:
            raise ValueError('Windows actual font edition mismatch')
        os2, hhea = font['OS/2'], font['hhea']
        if font['head'].unitsPerEm != measurement['upm']:
            raise ValueError('Windows source/measurement UPM mismatch')
        if [
            os2.sTypoAscender,
            os2.sTypoDescender,
            os2.sTypoLineGap,
        ] != measurement['typo'] or [
            hhea.ascent,
            hhea.descent,
            hhea.lineGap,
        ] != measurement[
            'hhea'
        ]:
            raise ValueError(
                'Windows source/measurement vertical metrics mismatch'
            )
        return {
            'policy': POLICY,
            'profile': 'source',
            'identity': measurement['identity'],
            'input_hashes': measurement['input_hashes'],
            'measurement': measurement,
            'source_otf_sha256': source_sha,
            'source_head_bbox': [
                getattr(font['head'], n)
                for n in ('xMin', 'yMin', 'xMax', 'yMax')
            ],
            **{
                key: measurement[key]
                for key in ('Windows', 'typo', 'hhea', 'upm')
            },
        }
