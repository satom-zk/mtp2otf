#!/usr/bin/env python3
"""Check Roman donor inputs and normalized bounding boxes and advances."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont


REGULAR_CODEPOINTS = tuple(range(0x41, 0x5B)) + tuple(range(0x61, 0x7B))
BOLD_CODEPOINTS = REGULAR_CODEPOINTS + tuple(range(0x30, 0x3A))

# Keep this independent copy of the builder's permitted text-donor domain.
# The output audit probes overlapping code points outside this domain using
# normalized bounding boxes and advances, not outline equality.
ROMAN_TEXT_EXTRA_RANGES = (
    (0x0020, 0x036F),
    (0x1E00, 0x1EFF),
    (0x2000, 0x218F),
    (0x2500, 0x266F),
    (0x301A, 0x301B),
    (0xFB00, 0xFB06),
)


def _is_roman_text_extra(codepoint: int) -> bool:
    return any(first <= codepoint <= last
               for first, last in ROMAN_TEXT_EXTRA_RANGES)


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
    raise ValueError('unsupported outline format (expected static CFF or TrueType)')


def _inspect(path: str | Path, kind: str) -> DonorInfo:
    p = Path(path)
    try:
        font = TTFont(p)
    except Exception as exc:
        raise ValueError(f'cannot open {kind} donor {p}: {exc}') from exc
    for tag in ('head', 'hmtx', 'cmap', 'name', 'OS/2', 'post'):
        if tag not in font:
            raise ValueError(f'{kind} donor {p} is missing required {tag} table')
    if 'fvar' in font:
        raise ValueError(f'{kind} donor {p} is variable; select a static instance')

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
            f'(italicAngle={post.italicAngle}, fsSelection={os2.fsSelection:#x})')
    if kind == 'Regular' and not 300 <= weight < 600:
        raise ValueError(f'Regular donor has non-Regular weight {weight}: {p}')
    if kind == 'Bold' and not 600 <= weight <= 900:
        raise ValueError(f'Bold donor has non-Bold weight {weight}: {p}')
    if int(getattr(post, 'isFixedPitch', 0) or 0):
        raise ValueError(f'{kind} donor is fixed-pitch, not a proportional Roman: {p}')

    cmap = font.getBestCmap() or {}
    required = REGULAR_CODEPOINTS if kind == 'Regular' else BOLD_CODEPOINTS
    missing = [cp for cp in required if cp not in cmap]
    if missing:
        sample = ', '.join(f'U+{cp:04X}' for cp in missing[:12])
        more = '' if len(missing) <= 12 else f' (+{len(missing) - 12} more)'
        raise ValueError(f'{kind} donor lacks required characters: {sample}{more}')

    return DonorInfo(p, _family(font), upm, weight, outline)


def validate_inputs(regular: str | Path, bold: str | Path) -> tuple[DonorInfo, DonorInfo]:
    reg = _inspect(regular, 'Regular')
    bld = _inspect(bold, 'Bold')
    if reg.family.casefold() != bld.family.casefold():
        raise ValueError(
            f'Regular/Bold donor families do not match: {reg.family!r} != {bld.family!r}')
    print(
        'ROMAN DONOR INPUTS PASS: '
        f'family={reg.family!r}; Regular={reg.outline}/{reg.upm}upm/{reg.weight}; '
        f'Bold={bld.outline}/{bld.upm}upm/{bld.weight}')
    return reg, bld


def _bbox(font: TTFont, glyph_name: str):
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()[glyph_name].draw(pen)
    return pen.bounds


def _bbox_close(actual, source, scale: float, tolerance: float = 2.1) -> bool:
    if actual is None or source is None:
        return actual is None and source is None
    expected = tuple(float(value) * scale for value in source)
    return all(abs(float(a) - e) <= tolerance for a, e in zip(actual, expected))


def audit_output(
        output_path: str | Path,
        regular_path: str | Path,
        bold_path: str | Path,
        sty_path: str | Path | None = None) -> None:
    validate_inputs(regular_path, bold_path)
    if sty_path:
        source = Path(sty_path).read_text(encoding='latin-1', errors='ignore')
        compact = re.sub(r'\s+', '', source)
        mathbf_patterns = (
            r'\\DeclareMathAlphabet\{\\mathbf\}\{\\encodingdefault\}\{\\rmdefault\}\{b\}\{n\}',
            r'\\DeclareMathAlphabet\{\\mathbf\}\{\\encodingdefault\}\{\\rmdefault\}\{\\bfdefault\}\{\\updefault\}',
        )
        mbf_patterns = (
            r'\\DeclareMathAlphabet\{\\mbf\}\{U\}\{mtt\}\{b\}\{n\}',
            r'\\DeclareMathAlphabet\{\\mbf\}\{U\}\{mtt\}\{\\bfdefault\}\{\\updefault\}',
        )
        if not any(re.search(pattern, compact) for pattern in mathbf_patterns):
            raise SystemExit(r'mtpro2.sty contract missing: \mathbf -> rmdefault bold upright')
        if not any(re.search(pattern, compact) for pattern in mbf_patterns):
            raise SystemExit(r'mtpro2.sty contract missing: \mbf -> U/mtt bold upright')
        print(r'mtpro2.sty Roman contract OK: \mathbf=rmdefault bold upright, \mbf=U/mtt bold upright')

    out = TTFont(output_path)
    reg = TTFont(regular_path)
    bold = TTFont(bold_path)
    output_upm = int(out['head'].unitsPerEm)
    reg_scale = output_upm / int(reg['head'].unitsPerEm)
    bold_scale = output_upm / int(bold['head'].unitsPerEm)
    output_cmap = out.getBestCmap() or {}
    regular_cmap = reg.getBestCmap() or {}
    bold_cmap = bold.getBestCmap() or {}
    output_hmtx = out['hmtx'].metrics
    regular_hmtx = reg['hmtx'].metrics
    bold_hmtx = bold['hmtx'].metrics
    errors: list[str] = []
    checked = 0
    leakage_probes = 0

    def one(source_font, source_cmap, source_hmtx, scale,
            source_cp, destination_cp, label):
        nonlocal checked
        source_glyph = source_cmap.get(source_cp)
        destination_glyph = output_cmap.get(destination_cp)
        if not source_glyph or not destination_glyph:
            errors.append(
                f'{label}: missing src/dst U+{source_cp:04X}->U+{destination_cp:04X}')
            return
        checked += 1
        expected_advance = round(source_hmtx[source_glyph][0] * scale)
        actual_advance = output_hmtx[destination_glyph][0]
        if actual_advance != expected_advance:
            errors.append(
                f'{label}: advance {actual_advance} != normalized donor {expected_advance}')
        if not _bbox_close(
                _bbox(out, destination_glyph), _bbox(source_font, source_glyph), scale):
            errors.append(
                f'{label}: outline bbox {_bbox(out, destination_glyph)} != '
                f'normalized donor {_bbox(source_font, source_glyph)} scale={scale:g}')

    for cp in REGULAR_CODEPOINTS:
        one(reg, regular_cmap, regular_hmtx, reg_scale, cp, cp, f'Regular U+{cp:04X}')
    for index, cp in enumerate(range(0x41, 0x5B)):
        one(bold, bold_cmap, bold_hmtx, bold_scale,
            cp, 0x1D400 + index, f'Bold {chr(cp)}')
    for index, cp in enumerate(range(0x61, 0x7B)):
        one(bold, bold_cmap, bold_hmtx, bold_scale,
            cp, 0x1D41A + index, f'Bold {chr(cp)}')
    for index, cp in enumerate(range(0x30, 0x3A)):
        one(bold, bold_cmap, bold_hmtx, bold_scale,
            cp, 0x1D7CE + index, f'Bold digit {chr(cp)}')

    # Compare normalized bounding boxes and advances at overlapping code points.
    # This is a heuristic for unintended donor imports, not an outline comparison.
    leaked: list[int] = []
    permitted_output_glyphs = {
        glyph_name for cp, glyph_name in output_cmap.items()
        if _is_roman_text_extra(cp)
    }
    for cp, source_glyph in regular_cmap.items():
        if _is_roman_text_extra(cp):
            continue
        destination_glyph = output_cmap.get(cp)
        if not destination_glyph:
            continue
        # MTPro2 intentionally gives several Latin-shaped Greek characters a
        # same-GID alias to Basic Latin.  That is not an imported extra glyph.
        if destination_glyph in permitted_output_glyphs:
            continue
        source_bbox = _bbox(reg, source_glyph)
        if source_bbox is None:
            continue
        leakage_probes += 1
        expected_advance = round(regular_hmtx[source_glyph][0] * reg_scale)
        if (output_hmtx[destination_glyph][0] == expected_advance and
                _bbox_close(_bbox(out, destination_glyph), source_bbox, reg_scale)):
            leaked.append(cp)
    if leaked:
        sample = ', '.join(f'U+{cp:04X}' for cp in leaked[:20])
        more = '' if len(leaked) <= 20 else f' (+{len(leaked) - 20} more)'
        errors.append(
            f'Possible Regular-donor import outside text domain '
            f'(bbox/advance match): {sample}{more}')

    print(f'Roman donor contract: {checked}/114 glyphs checked')
    print(f'Roman donor domain: {leakage_probes} outside-domain overlap probes checked')
    if errors:
        print('ROMAN DONOR CONTRACT FAILED')
        for error in errors[:40]:
            print('  -', error)
        if len(errors) > 40:
            print(f'  ... {len(errors) - 40} more')
        raise SystemExit(1)
    print('Roman donor domain heuristic PASS: no unexpected bbox/advance matches in checked overlaps')
    print(
        'ROMAN DONOR CONTRACT PASS: normalized bounding boxes (within tolerance) '
        'and advances match for the checked glyphs')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('font', nargs='?')
    ap.add_argument('--regular', required=True)
    ap.add_argument('--bold', required=True)
    ap.add_argument('--sty')
    ap.add_argument('--check-inputs-only', action='store_true')
    ns = ap.parse_args()
    try:
        if ns.check_inputs_only:
            if ns.font:
                ap.error('FONT is not used with --check-inputs-only')
            validate_inputs(ns.regular, ns.bold)
            return
        if not ns.font:
            ap.error('FONT is required unless --check-inputs-only is used')
        audit_output(ns.font, ns.regular, ns.bold, ns.sty)
    except ValueError as exc:
        raise SystemExit(f'ROMAN DONOR CONTRACT FAIL: {exc}') from exc


if __name__ == '__main__':
    main()
