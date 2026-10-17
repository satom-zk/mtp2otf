"""FontForge bounds boundary and its small, run-owned process result.

Only standard-library dependencies: safe in FontForge's embedded Python.
This is a numeric result, not a serialized legacy font or a font cache.
"""

import math

SCHEMA = 'mtp2otf7-compatibility-metrics/1'
BOUNDARY = 'fontforge-legacy-windows-assignment'


def assign_windows(font):
    """Compute Windows bounds over the native glyph set."""
    ymin = ymax = 0
    for glyph in font.glyphs():
        box = glyph.boundingBox()
        if box[1] == box[3] == 0 and box[0] == box[2] == 0:
            continue
        ymin = min(ymin, box[1])
        ymax = max(ymax, box[3])
    font.os2_winascent = max(806, int(math.ceil(ymax)))
    font.os2_winascent_add = 0
    font.os2_windescent = max(194, int(math.ceil(-ymin)))
    font.os2_windescent_add = 0
    return [ymin, ymax]


def capture(font, snapshot, bounds):
    result = {
        'schema': SCHEMA,
        'boundary': BOUNDARY,
        'condition': 'legacy',
        'identity': snapshot['build_identity'],
        'input_hashes': snapshot['inputs'],
        'Windows': [font.os2_winascent, font.os2_windescent],
        'typo': [
            font.os2_typoascent,
            font.os2_typodescent,
            font.os2_typolinegap,
        ],
        'hhea': [font.hhea_ascent, font.hhea_descent, font.hhea_linegap],
        'upm': font.em,
        'bounds_y': bounds,
    }
    validate(result, snapshot)
    return result


def integer_values(obj, key, count, lower, upper):
    values = obj.get(key)
    if (
        not isinstance(values, list)
        or len(values) != count
        or any(
            type(value) is not int or not lower <= value <= upper
            for value in values
        )
    ):
        raise ValueError('compatibility metrics integer range: ' + key)
    return values


def validate_identity(obj):
    identity = obj.get('identity')
    if (
        not isinstance(identity, dict)
        or identity.get('edition') not in ('full', 'lite')
        or identity.get('donor_coverage') not in ('minimal', 'extended')
        or type(identity.get('upm')) is not int
        or identity['upm'] != 1000
        or not isinstance(identity.get('run_id'), str)
        or len(identity['run_id']) != 32
        or any(c not in '0123456789abcdef' for c in identity['run_id'])
    ):
        raise ValueError('compatibility metrics identity invalid')
    inputs = obj.get('input_hashes')
    if (
        not isinstance(inputs, dict)
        or not inputs.get('mtpro2')
        or not inputs.get('donors')
    ):
        raise ValueError('compatibility metrics input identity missing')


def validate(result, snapshot=None):
    if not isinstance(result, dict):
        raise ValueError('compatibility metrics result must be an object')
    if (
        result.get('schema') != SCHEMA
        or result.get('boundary') != BOUNDARY
        or result.get('condition') != 'legacy'
    ):
        raise ValueError('invalid compatibility metrics boundary')
    validate_identity(result)
    windows = integer_values(result, 'Windows', 2, 0, 65535)
    for key in ('typo', 'hhea'):
        if integer_values(result, key, 3, -32768, 32767) != [806, -194, 200]:
            raise ValueError(
                'compatibility metrics vertical metrics mismatch: ' + key
            )
    if (
        type(result.get('upm')) is not int
        or result['upm'] != result['identity']['upm']
    ):
        raise ValueError('compatibility metrics UPM mismatch')
    bounds = result.get('bounds_y')
    if (
        not isinstance(bounds, list)
        or len(bounds) != 2
        or any(
            type(value) not in (int, float) or not math.isfinite(value)
            for value in bounds
        )
        or not bounds[0] <= 0 <= bounds[1]
    ):
        raise ValueError('compatibility metrics bounds invalid')
    if windows != [
        max(806, math.ceil(bounds[1])),
        max(194, math.ceil(-bounds[0])),
    ]:
        raise ValueError('compatibility metrics bounds/Windows mismatch')
    if snapshot is not None:
        if result['identity'] != snapshot['build_identity']:
            raise ValueError(
                'compatibility metrics run/edition/coverage/UPM mismatch'
            )
        if result['input_hashes'] != snapshot['inputs']:
            raise ValueError('compatibility metrics source input mismatch')
    return result
