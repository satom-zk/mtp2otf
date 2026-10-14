"""Fixed structural alternate routes; measurements come from user inputs."""
import hashlib
import json
from pathlib import Path
import re

SCHEMA = 'mtp2otf7-source-alternates/1'
ROWS_SHA256 = (
    '05a7eb6388d9893e35510243b076c5c19e7ea13356f95ca6c1f1041f5f013502'
)


def _keys(value, names, label):
    if not isinstance(value, dict) or set(value) != set(names):
        raise ValueError('alternate ledger key allowlist mismatch: ' + label)


def _text(value):
    return isinstance(value, str) and bool(value)


def validate(data):
    """Check one allowlist and the exact adopted ordered route identities."""
    _keys(data, ('schema', 'rows'), 'top-level')
    if (
        data['schema'] != SCHEMA
        or not isinstance(data['rows'], list)
        or len(data['rows']) != 31
    ):
        raise ValueError('fixed alternate schema and 31 routes required')
    identities = []
    for row in data['rows']:
        _keys(
            row,
            (
                'semantic_id', 'group', 'weight', 'base_unicode',
                'source_styles'
            ),
            'row'
        )
        if not all(
            _text(row[k])
            for k in ('semantic_id', 'group', 'weight', 'base_unicode')
        ):
            raise ValueError('alternate route string required')
        if (
            not re.fullmatch(r'U\+[0-9A-F]{4,6}', row['base_unicode'])
            or int(row['base_unicode'][2:], 16) > 0x10FFFF
        ):
            raise ValueError('alternate Unicode identity invalid')
        identities.append(row['semantic_id'])
        styles = row['source_styles']
        if not isinstance(styles, list) or len(styles) != 3:
            raise ValueError('three optical styles required')
        for item, expected in zip(styles, ('text', 'script', 'scriptscript')):
            _keys(item, ('style', 'alternate', 'current_standard'), 'style')
            if item['style'] != expected:
                raise ValueError('alternate optical style order differs')
            alt = item['alternate']
            _keys(
                alt,
                (
                    'tag', 'font', 'slot', 'PFB_name', 'PFB_SHA256',
                    'TFM_SHA256', 'accent_calibration'
                ),
                'alternate'
            )
            if not all(_text(alt[k]) for k in ('tag', 'font', 'PFB_name')):
                raise ValueError('alternate source identity string required')
            if type(alt['slot']) is not int or not 0 <= alt['slot'] <= 255:
                raise ValueError('alternate slot invalid')
            if not all(
                isinstance(alt[k], str)
                and re.fullmatch(r'[0-9a-f]{64}', alt[k])
                for k in ('PFB_SHA256', 'TFM_SHA256')
            ):
                raise ValueError('alternate source SHA invalid')
            _keys(
                alt['accent_calibration'], ('skewchar',), 'accent calibration'
            )
            skew = alt['accent_calibration']['skewchar']
            if (
                skew is not None
                and (type(skew) is not int or not 0 <= skew <= 255)
            ):
                raise ValueError('alternate skewchar slot invalid')
            _keys(item['current_standard'], ('glyph',), 'current standard')
            if not _text(item['current_standard']['glyph']):
                raise ValueError('alternate standard glyph identity required')
    if len(set(identities)) != 31:
        raise ValueError('duplicate alternate route')
    raw = json.dumps(
        {'rows': data['rows']}, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')
    ).encode('utf-8')
    if hashlib.sha256(raw).hexdigest() != ROWS_SHA256:
        raise ValueError(
            'fixed ordered alternate routes/source identities differ'
        )
    return data


def load(path):
    """Read the product's fixed route data; historical projections are dev-
    only.
    """
    return validate(json.loads(Path(path).read_bytes()))
