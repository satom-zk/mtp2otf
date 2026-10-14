"""Fixed functional donor selection and validation of user donor inputs."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from dataclasses import dataclass

MODES = ('minimal', 'extended')
PUBLIC_MODES = MODES
INTERNAL_MODE = 'MTP2_PIPELINE_DONOR_COVERAGE'
PRIVATE_KEYS = (
    'MTP2_DONOR_PROFILE_JSON', 'MTP2_DONOR_HINT_CONTRACT_JSON',
    'MTP2_DONOR_HINT_REFERENCE_ROOT', 'MTP2_DONOR_HINT_MODE'
)
SPEC_PATH = Path(__file__).with_name('donor_scope.json')
SPEC_SHA256 = (
    '4a3e444b7aebdbaa968d51d8185ad934256a4494a524697f947cdb6508f28e50'
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def public_mode(value):
    """Accept only the public coverage spellings."""
    if value not in PUBLIC_MODES:
        raise ValueError('expected minimal or extended')
    return value


def resolve_mode(mode, environ):
    if mode is not None and mode not in MODES:
        raise ValueError('unknown donor coverage mode')
    conflicts = [k for k in PRIVATE_KEYS if k in environ]
    if mode is not None and conflicts:
        raise ValueError(
            'unsupported retired private donor settings: '
            + ', '.join(conflicts)
        )
    return mode


def child_environment(mode, environ):
    resolve_mode(mode, environ)
    child = dict(environ)
    for key in tuple(child):
        if key.startswith('MTP2_'):
            child.pop(key)
    if mode is not None:
        child[INTERNAL_MODE] = mode
    return child


def load_spec(path=SPEC_PATH):
    if sha(path) != SPEC_SHA256:
        raise ValueError('unknown public donor spec or modified fixed scope')
    s = json.loads(Path(path).read_text(encoding='utf-8'))
    if (
        s['schema'] != 'mtp2otf7-public-donor-scope/1'
        or s['id'] != 'BI-minimal-317-r01'
    ):
        raise ValueError('unknown public donor spec schema/id')
    roots = s['roots']
    codes = [r['output_unicode'] for r in roots]
    if (
        len(codes) != 317
        or len(set(codes)) != 317
        or set(codes) != {u for g in s['groups'].values() for u in g}
    ):
        raise ValueError('public donor scope roots/groups differ')
    if (
        sum(r['source_role'] == 'regular' for r in roots) != 255
        or sum(r['source_role'] == 'bold' for r in roots) != 62
    ):
        raise ValueError('public donor scope role mismatch')
    return s


def select_remaining(candidates, mode, spec=None, runtime_dependencies=()):
    if mode not in (None, *MODES):
        raise ValueError('unknown donor coverage mode')
    if mode != 'minimal':
        return candidates
    spec = spec if spec is not None else load_spec()
    codes = [r[1] for r in candidates]
    if len(set(codes)) != len(codes):
        raise ValueError('duplicate remaining donor output')
    required = {r['output_unicode'] for r in spec['roots']}
    removed = {r[2] for r in candidates if r[1] not in required}
    if removed & set(runtime_dependencies):
        raise ValueError(
            'retained runtime dependency requires excluded donor glyph'
        )
    return [r for r in candidates if r[1] in required]


def validate_outputs(spec, observed, internal, dependencies=(), names=()):
    missing = {r['output_unicode'] for r in spec['roots']} - set(observed)
    if missing:
        raise ValueError(
            'minimal required output missing: ' + ', '.join(
                'U+%04X' % u for u in sorted(missing)
            )
        )
    for u, row in observed.items():
        if not row.get('visible') or not math.isfinite(row['advance']):
            raise ValueError(
                'minimal required visible outline/advance invalid: U+%04X' % u
            )
    if (
        set(spec['internal_outputs']) - set(internal)
        or not all(internal.values())
    ):
        raise ValueError('minimal internal dotless-i supply unavailable')
    missing_dependencies = set(dependencies) - set(names)
    if missing_dependencies:
        raise ValueError(
            'minimal glyph dependency missing: ' + ', '.join(
                sorted(missing_dependencies)
            )
        )


REGULAR_CODEPOINTS = tuple(range(0x41, 0x5B)) + tuple(range(0x61, 0x7B))
BOLD_CODEPOINTS = REGULAR_CODEPOINTS + tuple(range(0x30, 0x3A))


@dataclass(frozen=True)
class DonorInfo:
    path: Path
    family: str
    upm: int
    weight: int
    outline: str


def _name_values(font: TTFont, name_id: int) -> set[str]:
    values: set[str] = set()
    for record in font['name'].names:
        if record.nameID != name_id:
            continue
        try:
            value = record.toUnicode().strip()
        except Exception:
            continue
        if value:
            values.add(value)
    return values


def _family(font: TTFont) -> str:
    values = _name_values(font, 16) or _name_values(font, 1)
    if not values:
        raise ValueError('missing family name (name ID 16/1)')
    return sorted(values, key=lambda value: (len(value), value.casefold()))[0]


def _outline_format(font: TTFont) -> str:
    if 'CFF ' in font:
        return 'CFF'
    if 'glyf' in font:
        return 'TrueType'
    raise ValueError(
        'unsupported outline format (expected static CFF or TrueType)'
    )


def _inspect(path: str | Path, kind: str) -> DonorInfo:
    from fontTools.ttLib import TTFont
    p = Path(path)
    try:
        font = TTFont(p)
    except Exception as exc:
        raise ValueError(f'cannot open {kind} donor {p}: {exc}') from exc
    with font:
        for tag in ('head', 'hmtx', 'cmap', 'name', 'OS/2', 'post'):
            if tag not in font:
                raise ValueError(
                    f'{kind} donor {p} is missing required {tag} table'
                )
        if 'fvar' in font:
            raise ValueError(
                f'{kind} donor {p} is variable; select a static instance'
            )

        outline = _outline_format(font)
        upm = int(font['head'].unitsPerEm)
        if not 16 <= upm <= 16384:
            raise ValueError(f'{kind} donor {p} has invalid unitsPerEm={upm}')

        os2 = font['OS/2']
        post = font['post']
        weight = int(os2.usWeightClass)
        italic = bool(os2.fsSelection & 0x01)
        oblique = bool(os2.fsSelection & 0x200)
        if abs(float(post.italicAngle)) > 0.01 or italic or oblique:
            raise ValueError(
                f'{kind} donor must be upright: {p} '
                f'(italicAngle={post.italicAngle}, '
                f'fsSelection={os2.fsSelection:#x})'
            )
        if kind == 'Regular' and not 300 <= weight < 600:
            raise ValueError(
                f'Regular donor has non-Regular weight {weight}: {p}'
            )
        if kind == 'Bold' and not 600 <= weight <= 900:
            raise ValueError(f'Bold donor has non-Bold weight {weight}: {p}')
        if int(getattr(post, 'isFixedPitch', 0) or 0):
            raise ValueError(
                f'{kind} donor is fixed-pitch, not a proportional Roman: {p}'
            )

        cmap = font.getBestCmap() or {}
        required = REGULAR_CODEPOINTS if kind == 'Regular' else BOLD_CODEPOINTS
        missing = [cp for cp in required if cp not in cmap]
        if missing:
            sample = ', '.join(f'U+{cp:04X}' for cp in missing[:12])
            more = (
                '' if len(missing) <= 12
                else f' (+{len(missing) - 12} more)'
            )
            raise ValueError(
                f'{kind} donor lacks required characters: {sample}{more}'
            )

        result = DonorInfo(p, _family(font), upm, weight, outline)
        return result


def validate_inputs(
    regular: str | Path, bold: str | Path
) -> tuple[DonorInfo, DonorInfo]:
    reg = _inspect(regular, 'Regular')
    bld = _inspect(bold, 'Bold')
    if reg.family.casefold() != bld.family.casefold():
        raise ValueError(
            f'Regular/Bold donor families do not match: {reg.family!r} '
            f'!= {bld.family!r}'
        )
    return reg, bld
