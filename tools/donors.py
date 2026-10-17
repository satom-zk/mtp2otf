"""Fixed functional donor selection and validation of user donor inputs.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from dataclasses import dataclass
from typing import TYPE_CHECKING

import mapping as U

if TYPE_CHECKING:
    from fontTools.ttLib import TTFont

MODES = ('minimal', 'extended')
PUBLIC_MODES = MODES
INTERNAL_MODE = 'MTP2_PIPELINE_DONOR_COVERAGE'
PRIVATE_KEYS = (
    'MTP2_DONOR_PROFILE_JSON',
    'MTP2_DONOR_HINT_CONTRACT_JSON',
    'MTP2_DONOR_HINT_REFERENCE_ROOT',
    'MTP2_DONOR_HINT_MODE',
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
            'minimal required output missing: '
            + ', '.join('U+%04X' % u for u in sorted(missing))
        )
    for u, row in observed.items():
        if not row.get('visible') or not math.isfinite(row['advance']):
            raise ValueError(
                'minimal required visible outline/advance invalid: U+%04X' % u
            )
    if set(spec['internal_outputs']) - set(internal) or not all(
        internal.values()
    ):
        raise ValueError('minimal internal dotless-i supply unavailable')
    missing_dependencies = set(dependencies) - set(names)
    if missing_dependencies:
        raise ValueError(
            'minimal glyph dependency missing: '
            + ', '.join(sorted(missing_dependencies))
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
                '' if len(missing) <= 12 else f' (+{len(missing) - 12} more)'
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


def unicode_map(ffont):
    d = {}
    for g in ffont.glyphs():
        u = g.unicode
        if u is not None and u >= 0:
            d[u] = g.glyphname
    return d


def read_supply(path):
    """Read Unicode/name/advance/bounds without constructing an output
    font.
    """
    from fontTools.ttLib import TTFont
    from fontTools.pens.boundsPen import BoundsPen

    with TTFont(path) as font:
        cmap = font.getBestCmap() or {}
        gs = font.getGlyphSet()
        glyphs = {}
        for name in font.getGlyphOrder():
            pen = BoundsPen(gs)
            gs[name].draw(pen)
            glyphs[name] = dict(
                advance=font['hmtx'][name][0], bounds=pen.bounds
            )
        return dict(path=Path(path), cmap=cmap, glyphs=glyphs)


def check_supply(supply, coverage):
    """Fail required donor gaps before output; retain native checks too.
    """
    requirements = [
        dict(source_role=r, source_unicode=cp)
        for r, cs in [
            ('regular', REGULAR_CODEPOINTS),
            ('bold', BOLD_CODEPOINTS),
        ]
        for cp in cs
    ]
    if coverage == 'minimal':
        requirements += load_spec()['roots']
    for row in requirements:
        role, cp = row['source_role'], row['source_unicode']
        face = supply[role]
        if (
            row.get('supply_rule')
            == 'encoded_dotless_j_or_existing_validated_j_derivation'
        ):
            cp = 0x237 if 0x237 in face['cmap'] else 0x6A
        name = face['cmap'].get(cp)
        g = face['glyphs'].get(name, {})
        b = g.get('bounds')
        if (
            not name
            or not b
            or b[2] <= b[0]
            or b[3] <= b[1]
            or not math.isfinite(g.get('advance', float('nan')))
        ):
            raise ValueError(
                f'preflight donor {face["path"].name} role={role} '
                f'U+{cp:04X}: required visible Unicode supply missing'
            )
    regular = supply['regular']
    if 0x237 not in regular['cmap'] and 0x6A not in regular['cmap']:
        raise ValueError('preflight regular donor: neither U+0237 nor U+006A')
    if (
        coverage == 'minimal'
        and 0x131 not in regular['cmap']
        and 'dotlessi' not in regular['glyphs']
    ):
        raise ValueError(
            'preflight minimal internal dotless-i supply unavailable'
        )


# Reserve math and non-Roman ranges against text-donor substitution.
TEXT_ONLY_SKIP = (
    (0x0370, 0x03FF),  # Greek
    (0x0400, 0x052F),  # Cyrillic
    (0x2100, 0x214F),  # Letterlike symbols
    (0x2190, 0x21FF),  # Arrows
    (0x2200, 0x22FF),  # Math operators
    (0x2300, 0x23FF),  # Technical symbols
    (0x25A0, 0x25FF),  # Geometric shapes
    (0x27C0, 0x27EF),  # Supplemental math A
    (0x2980, 0x2AFF),  # Supplemental math B
    (0x1D400, 0x1D7FF),  # Math alphanumerics
)

# Allow text-only letterlike symbols, but
# reserve math-active primes.
TEXT_ONLY_PRIMES = set(range(0x2032, 0x2038)) | {0x2057}

TEXT_ONLY_ALLOW = {
    0x2105,
    0x2116,
    0x211E,
    0x2120,
    0x2121,
    0x2122,
    0x212E,
}


def _is_math_range(u):
    if u in TEXT_ONLY_PRIMES:
        return True
    if u in TEXT_ONLY_ALLOW:
        return False
    return any(a <= u <= b for a, b in TEXT_ONLY_SKIP)


# Limit donor additions to Latin/Common text; math
# ownership takes precedence.
ROMAN_TEXT_EXTRA_RANGES = (
    (0x0020, 0x036F),
    (0x1E00, 0x1EFF),
    (0x2000, 0x218F),
    (0x2500, 0x266F),
    (0x301A, 0x301B),
    (0xFB00, 0xFB06),
)


def _is_roman_text_extra(u):
    return any(first <= u <= last for first, last in ROMAN_TEXT_EXTRA_RANGES)


# Reserve Full-only source codepoints in Lite, including AMSa eth.
CANONICAL_FULL_ONLY_SOURCE_UNICODE = set()
for _u, _name in U.AMSA.values():
    if _u is not None:
        CANONICAL_FULL_ONLY_SOURCE_UNICODE.add(_u)
for _kind in ('bb', 'script', 'frak', 'curly', 'bscript', 'bfrak'):
    for _slot, (_u, _name) in U.alpha_map(_kind).items():
        if _u is not None:
            CANONICAL_FULL_ONLY_SOURCE_UNICODE.add(_u)

# Text-donor symbols used directly by Word math.
ROMAN_EXTRA = {
    'percent': 0x0025,
    'ampersand': 0x0026,
    'at': 0x0040,
    'underscore': 0x005F,
    'asciitilde': 0x007E,
    'numbersign': 0x0023,
    'dollar': 0x0024,
    'degree': 0x00B0,
    'fraction': 0x2044,
    'question': 0x003F,
    'exclam': 0x0021,
}


def text_candidates(
    font, owned_unicode, names, edition, coverage, spec, dependencies
):
    """Select eligible remaining text in source iteration order."""
    todo = []
    for g in font.glyphs():
        u = g.unicode
        if u is None or u < 0x20 or u in owned_unicode:
            continue
        if not _is_roman_text_extra(u):
            continue
        if edition == 'lite' and u in CANONICAL_FULL_ONLY_SOURCE_UNICODE:
            continue
        if _is_math_range(u):
            continue
        if 0xE000 <= u <= 0xF8FF or u in (0xFEFF, 0xFFFD):
            continue
        gn = 'uni%04X' % u if u < 0x10000 else 'u%05X' % u
        if gn in names:
            continue
        todo.append((g.glyphname, u, gn, g.width))
    return select_remaining(todo, coverage, spec, dependencies)
