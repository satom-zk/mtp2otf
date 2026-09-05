#!/usr/bin/env python3
"""Extract policy and geometry from local MTPro2 sources.

Keep source identities public; evaluate source-dependent values during build.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from fractions import Fraction
from pathlib import Path
import argparse
import json
import math
import os
import re
import subprocess
import tempfile
from typing import Dict, Iterable, Mapping, Optional


# Structural source registry.  These are filenames/roles, not evaluated metrics.
SOURCE_FONTS: Dict[str, str] = {
    'mit': 'mt2mit', 'syt': 'mt2syt', 'exa': 'mt2exa', 'xl': 'mt2xl', 'xxxl': 'mt2xxxl',
    'ams': 'mt2syat', 'bb': 'mt2bbt', 'script': 'mt2mst', 'frak': 'mt2mft',
    'curly': 'mt2mct', 'bold': 'mt2mbt',
    'exe': 'mt2exe', 'exf': 'mt2exf', 'exg': 'mt2exg',
    'mit_s': 'mt2mis', 'mit_ss': 'mt2mif', 'syt_s': 'mt2sys', 'syt_ss': 'mt2syf',
    'ams_s': 'mt2syas', 'ams_ss': 'mt2syaf',
    'bb_s': 'mt2bbs', 'bb_ss': 'mt2bbf', 'script_s': 'mt2mss', 'script_ss': 'mt2msf',
    'frak_s': 'mt2mfs', 'frak_ss': 'mt2mff',
    'bold_s': 'mt2mbs', 'bold_ss': 'mt2mbf', 'curly_s': 'mt2mcs', 'curly_ss': 'mt2mcf',
    'bbi': 'mt2bbit', 'bbi_s': 'mt2bbis', 'bbi_ss': 'mt2bbif',
    'bbd': 'mt2bbdt', 'bbd_s': 'mt2bbds', 'bbd_ss': 'mt2bbdf',
    'hrb': 'mt2hrbt', 'hrb_s': 'mt2hrbs', 'hrb_ss': 'mt2hrbf',
    'hrbd': 'mt2hrbdt', 'hrbd_s': 'mt2hrbds', 'hrbd_ss': 'mt2hrbdf',
    'hbi': 'mt2hbit', 'hbi_s': 'mt2hbis', 'hbi_ss': 'mt2hbif',
    'bmit': 'mt2bmit', 'bmit_s': 'mt2bmis', 'bmit_ss': 'mt2bmif',
    'bsyt': 'mt2bsyt', 'bsyt_s': 'mt2bsys', 'bsyt_ss': 'mt2bsyf',
}

LITE_TAGS = frozenset((
    'mit', 'mit_s', 'mit_ss', 'syt', 'syt_s', 'syt_ss',
    'exa', 'exe', 'exf', 'exg', 'xl', 'xxxl',
    'bold', 'bold_s', 'bold_ss',
))

# Full-only .fd declarations that define option-alphabet source identity and
# optical-size ordering.  These are public structural names only.
OPTICAL_FD_GROUPS = {
    'umt2ms.fd': (
        ('curly option family', ('curly_ss', 'curly_s', 'curly')),
        ('script option family', ('script_ss', 'script_s', 'script')),
    ),
    'umt2mf.fd': (
        ('Fraktur family', ('frak_ss', 'frak_s', 'frak')),
    ),
    'umt2bb.fd': (
        ('blackboard family', ('bb_ss', 'bb_s', 'bb')),
        ('italic blackboard family', ('bbi_ss', 'bbi_s', 'bbi')),
        ('bold blackboard family', ('bbd_ss', 'bbd_s', 'bbd')),
    ),
    'umt2hrb.fd': (
        ('holey Roman family', ('hrb_ss', 'hrb_s', 'hrb')),
        ('holey italic family', ('hbi_ss', 'hbi_s', 'hbi')),
        ('holey bold family', ('hrbd_ss', 'hrbd_s', 'hrbd')),
    ),
}

# Tags whose source glyphs are ordinary/simple math characters by construction.
# Symbol-family exceptions are separate because source class, not alphabet role,
# decides whether an italic correction participates in ordinary adjacency.
ORDINARY_ALL_TAGS = frozenset((
    'mit', 'mit_s', 'mit_ss', 'bmit', 'bmit_s', 'bmit_ss',
    'bb', 'bb_s', 'bb_ss', 'script', 'script_s', 'script_ss',
    'frak', 'frak_s', 'frak_ss', 'curly', 'curly_s', 'curly_ss',
    'bold', 'bold_s', 'bold_ss',
    'bbi', 'bbi_s', 'bbi_ss', 'bbd', 'bbd_s', 'bbd_ss',
    'hrb', 'hrb_s', 'hrb_ss', 'hrbd', 'hrbd_s', 'hrbd_ss', 'hbi', 'hbi_s', 'hbi_ss',
))

# The symbol-family ordinary slots are stable TeX identities.  Their *metrics*
# and skew/kern values are always read from local TFM/package sources.
SYMBOL_ORDINARY_SLOTS = frozenset((114, 177))
SYMBOL_ORDINARY_TAGS = frozenset(('syt', 'syt_s', 'syt_ss', 'bsyt', 'bsyt_s', 'bsyt_ss'))

# Map builder tags to the LaTeX declaration that owns their skewchar policy.
# The selector itself is structural; the numeric skewchar is parsed at runtime.
_SKEW_ROLE = {}
for _t in ('mit', 'mit_s', 'mit_ss', 'bmit', 'bmit_s', 'bmit_ss'):
    _SKEW_ROLE[_t] = ('family', 'sty', 'LMP1', 'mtt')
for _t in ('syt', 'syt_s', 'syt_ss'):
    _SKEW_ROLE[_t] = ('shape', 'sty', 'LMP2', 'mtt', 'm', 'n')
for _t in ('bsyt', 'bsyt_s', 'bsyt_ss'):
    _SKEW_ROLE[_t] = ('shape', 'sty', 'LMP2', 'mtt', 'b', 'n')
for _t in ('bold', 'bold_s', 'bold_ss'):
    _SKEW_ROLE[_t] = ('family', 'sty', 'U', 'mtt')
for _t in ('script', 'script_s', 'script_ss', 'curly', 'curly_s', 'curly_ss'):
    _SKEW_ROLE[_t] = ('family', 'umt2ms.fd', 'U', 'mt2ms')
for _t in ('frak', 'frak_s', 'frak_ss'):
    _SKEW_ROLE[_t] = None
for _t in ('bb', 'bb_s', 'bb_ss', 'bbi', 'bbi_s', 'bbi_ss', 'bbd', 'bbd_s', 'bbd_ss'):
    _SKEW_ROLE[_t] = ('family', 'umt2bb.fd', 'U', 'mt2bb')
for _t in ('hrb', 'hrb_s', 'hrb_ss', 'hrbd', 'hrbd_s', 'hrbd_ss', 'hbi', 'hbi_s', 'hbi_ss'):
    _SKEW_ROLE[_t] = ('family', 'umt2hrb.fd', 'U', 'mt2hrb')


@dataclass(frozen=True)
class AccentDeclaration:
    macro: str
    math_class: str
    symbol_family: str
    slot: int


@dataclass(frozen=True)
class DotMacroPolicy:
    vdots_step_num: int
    vdots_step_den: int
    ddots_raise: tuple[tuple[int, int], ...]
    ddots_inner_mu_num: int
    ddots_inner_mu_den: int

    @property
    def vdots_step_pt(self) -> Fraction:
        return Fraction(self.vdots_step_num, self.vdots_step_den)

    @property
    def ddots_raises_pt(self) -> tuple[Fraction, ...]:
        return tuple(Fraction(n, d) for n, d in self.ddots_raise)

    @property
    def ddots_inner_mu(self) -> Fraction:
        return Fraction(self.ddots_inner_mu_num, self.ddots_inner_mu_den)


@dataclass(frozen=True)
class SourcePolicy:
    script_ratio_num: int
    script_ratio_den: int
    scriptscript_ratio_num: int
    scriptscript_ratio_den: int
    skewchar_by_tag: Mapping[str, Optional[int]]
    accents: Mapping[str, AccentDeclaration]
    dot_macros: DotMacroPolicy

    @property
    def script_ratio(self) -> Fraction:
        return Fraction(self.script_ratio_num, self.script_ratio_den)

    @property
    def scriptscript_ratio(self) -> Fraction:
        return Fraction(self.scriptscript_ratio_num, self.scriptscript_ratio_den)

    def to_jsonable(self) -> dict:
        return {
            'script_ratio': {'numerator': self.script_ratio_num, 'denominator': self.script_ratio_den},
            'scriptscript_ratio': {'numerator': self.scriptscript_ratio_num, 'denominator': self.scriptscript_ratio_den},
            'skewchar_by_tag': dict(self.skewchar_by_tag),
            'accents': {k: asdict(v) for k, v in sorted(self.accents.items())},
            'dot_macros': asdict(self.dot_macros),
            'source_font_by_tag': dict(SOURCE_FONTS),
        }


def _strip_comments(text: str) -> str:
    return re.sub(r'(?<!\\)%.*$', '', text, flags=re.MULTILINE)


def _tex_int(token: str) -> int:
    token = token.strip()
    if token.startswith('"'):
        return int(token[1:], 16)
    if token.startswith("'"):
        return int(token[1:], 8)
    return int(token, 10)


def _tex_fraction(token: str) -> Fraction:
    token = token.strip()
    if token.startswith('.'):
        token = '0' + token
    if '.' in token:
        sign = -1 if token.startswith('-') else 1
        if token[0] in '+-':
            token = token[1:]
        a, b = token.split('.', 1)
        n = int((a or '0') + b)
        return Fraction(sign * n, 10 ** len(b))
    return Fraction(int(token), 1)


def _require_one(pattern: str, text: str, label: str, flags: int = 0) -> re.Match[str]:
    hits = list(re.finditer(pattern, text, flags))
    if len(hits) != 1:
        raise ValueError(f'{label}: expected exactly one declaration, found {len(hits)}')
    return hits[0]


def _family_skew(text: str, encoding: str, family: str) -> Optional[int]:
    pat = (r'\\DeclareFontFamily\s*\{' + re.escape(encoding) + r'\}\s*\{' +
           re.escape(family) + r'\}\s*\{([^}]*)\}')
    m = _require_one(pat, text, f'font family {encoding}/{family}', re.DOTALL)
    body = m.group(1)
    sm = re.search(r'\\skewchar\s*\\font\s*([^\s}]+)', body)
    return _tex_int(sm.group(1)) if sm else None


def _shape_skew(text: str, encoding: str, family: str, series: str, shape: str) -> Optional[int]:
    pat = (r'\\DeclareFontShape\s*\{' + re.escape(encoding) + r'\}\s*\{' +
           re.escape(family) + r'\}\s*\{' + re.escape(series) + r'\}\s*\{' +
           re.escape(shape) + r'\}\s*\{.*?\}\s*\{([^}]*)\}')
    m = _require_one(pat, text, f'font shape {encoding}/{family}/{series}/{shape}', re.DOTALL)
    body = m.group(1)
    sm = re.search(r'\\skewchar\s*\\font\s*([^\s}]+)', body)
    return _tex_int(sm.group(1)) if sm else None


def _parse_accents(sty: str) -> Dict[str, AccentDeclaration]:
    # MTPro2 declarations are simple braced tokens; whitespace/newlines are allowed.
    pat = re.compile(
        r'\\DeclareMathAccent\s*\{\\([A-Za-z@]+)\}\s*'
        r'\{\\([A-Za-z@]+)\}\s*\{([^}]+)\}\s*\{([^}]+)\}',
        re.DOTALL,
    )
    out: Dict[str, AccentDeclaration] = {}
    for m in pat.finditer(sty):
        macro, math_class, family, slot_token = m.groups()
        slot = _tex_int(slot_token)
        rec = AccentDeclaration(macro, math_class, family.strip(), slot)
        old = out.get(macro)
        if old is not None and old != rec:
            raise ValueError(f'conflicting \\DeclareMathAccent for \\{macro}')
        out[macro] = rec
    if not out:
        raise ValueError('no \\DeclareMathAccent declarations found in mtpro2.sty')
    return out


def _extract_braced_def_body(text: str, macro: str) -> str:
    r"""Return the balanced body of one ``\def\macro{...}`` declaration."""
    m = _require_one(r'\\def\s*\\' + re.escape(macro) + r'\s*\{',
                     text, macro + ' macro')
    start = m.end() - 1
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        escaped = i > 0 and text[i - 1] == '\\'
        if escaped:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
            if depth < 0:
                break
    raise ValueError(f'{macro}: unbalanced macro body')


def _parse_dot_macros(sty: str) -> DotMacroPolicy:
    """Extract the MTPro2 dot-macro geometry that affects synthesized glyphs."""
    vm = _require_one(
        r'\\def\s*\\vdots.*?\\baselineskip\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*\\p@',
        sty, 'vdots baseline step', re.DOTALL)
    vdots_step = _tex_fraction(vm.group(1))

    body = _extract_braced_def_body(sty, 'ddots')
    raises = []
    for token in re.findall(r'\\raise\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)?)\s*\\p@', body):
        raises.append(_tex_fraction(token or '1'))
    mkerns = [_tex_fraction(x) for x in re.findall(
        r'\\mkern\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*mu', body)]
    if len(raises) != 3 or len(mkerns) < 3:
        raise ValueError('ddots macro geometry is not the expected three-dot structure')
    # The internal spacing is the first kern between two successive dot boxes;
    # edge kerns are math-class padding and are not baked into the glyph.
    inner = mkerns[1]
    if mkerns[-2] != inner:
        raise ValueError('ddots internal spacing is asymmetric')
    return DotMacroPolicy(
        vdots_step.numerator, vdots_step.denominator,
        tuple((x.numerator, x.denominator) for x in raises),
        inner.numerator, inner.denominator,
    )


def required_policy_files(active_tags: Iterable[str]) -> tuple[str, ...]:
    """Return all numeric and structural policy files required by the edition."""
    tags = set(active_tags)
    files = {'mtpro2.sty'}
    for tag in tags:
        role = _SKEW_ROLE.get(tag)
        if role is not None and role[1] != 'sty':
            files.add(role[1])
    for filename, groups in OPTICAL_FD_GROUPS.items():
        if any(any(tag in tags for tag in group_tags) for _, group_tags in groups):
            files.add(filename)
    return tuple(sorted(files))


def validate_source_files(mtpro2_dir: str | Path, active_tags: Iterable[str]) -> None:
    """Require the selected edition's PFB/TFM files."""
    root = Path(mtpro2_dir)
    missing = []
    for tag in sorted(set(active_tags)):
        base = SOURCE_FONTS[tag]
        for suffix in ('.pfb', '.tfm'):
            path = root / (base + suffix)
            if not path.is_file():
                missing.append(path.name)
    if missing:
        raise FileNotFoundError('incomplete MTPro2 source set: ' + ', '.join(missing))


def extract_policy(mtpro2_dir: str | Path, active_tags: Optional[Iterable[str]] = None) -> SourcePolicy:
    root = Path(mtpro2_dir)
    sty_path = root / 'mtpro2.sty'
    if not sty_path.is_file():
        raise FileNotFoundError(sty_path)
    texts = {'sty': _strip_comments(sty_path.read_text(encoding='latin-1'))}

    tags = set(active_tags) if active_tags is not None else set(_SKEW_ROLE)
    # Only require .fd files that are actually referenced by the active edition.
    # Lite must not accidentally depend on Full-only option-family declarations.
    required_text_sources = [name for name in required_policy_files(tags)
                             if name != 'mtpro2.sty']
    for name in required_text_sources:
        p = root / name
        if not p.is_file():
            raise FileNotFoundError(p)
        texts[name] = _strip_comments(p.read_text(encoding='latin-1'))

    sty = texts['sty']
    sr = _tex_fraction(_require_one(
        r'\\def\s*\\defaultscriptratio\s*\{([^}]+)\}', sty,
        'defaultscriptratio').group(1))
    ssr = _tex_fraction(_require_one(
        r'\\def\s*\\defaultscriptscriptratio\s*\{([^}]+)\}', sty,
        'defaultscriptscriptratio').group(1))
    if not (0 < sr <= 1 and 0 < ssr <= sr):
        raise ValueError('invalid MTPro2 script ratios')

    skew: Dict[str, Optional[int]] = {}
    for tag in sorted(tags):
        role = _SKEW_ROLE.get(tag)
        if tag not in _SKEW_ROLE:
            continue
        if role is None:
            skew[tag] = None
            continue
        kind, source, enc, fam, *rest = role
        text = texts[source]
        if kind == 'family':
            skew[tag] = _family_skew(text, enc, fam)
        elif kind == 'shape':
            skew[tag] = _shape_skew(text, enc, fam, rest[0], rest[1])
        else:
            raise AssertionError(role)

    return SourcePolicy(
        sr.numerator, sr.denominator,
        ssr.numerator, ssr.denominator,
        skew,
        _parse_accents(sty),
        _parse_dot_macros(sty),
    )


def is_ordinary_left(tag: str, slot: int) -> bool:
    return tag in ORDINARY_ALL_TAGS or (tag in SYMBOL_ORDINARY_TAGS and slot in SYMBOL_ORDINARY_SLOTS)


def load_policy_json(path: str | Path) -> SourcePolicy:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    sr = data['script_ratio']
    ssr = data['scriptscript_ratio']
    accents = {k: AccentDeclaration(**v) for k, v in data['accents'].items()}
    dm = data['dot_macros']
    dots = DotMacroPolicy(
        int(dm['vdots_step_num']), int(dm['vdots_step_den']),
        tuple((int(n), int(d)) for n, d in dm['ddots_raise']),
        int(dm['ddots_inner_mu_num']), int(dm['ddots_inner_mu_den']),
    )
    return SourcePolicy(
        int(sr['numerator']), int(sr['denominator']),
        int(ssr['numerator']), int(ssr['denominator']),
        {k: (None if v is None else int(v)) for k, v in data['skewchar_by_tag'].items()},
        accents,
        dots,
    )


def _type1_slot_path(pfb_path: Path, slot: int) -> dict:
    """Return one local Type1 slot as a JSON-safe cubic path description."""
    from fontTools import t1Lib
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.boundsPen import BoundsPen

    font = t1Lib.T1Font(str(pfb_path))
    font.parse()
    encoding = font.font.get('Encoding')
    if not isinstance(encoding, list) or not (0 <= slot < len(encoding)):
        raise ValueError(f'{pfb_path.name}: no usable Type1 encoding for slot {slot}')
    glyph_name = encoding[slot]
    glyphs = font.getGlyphSet()
    if glyph_name not in glyphs:
        raise ValueError(f'{pfb_path.name}: slot {slot} glyph {glyph_name!r} missing')
    rec = RecordingPen()
    glyphs[glyph_name].draw(rec)
    bounds = BoundsPen(glyphs)
    glyphs[glyph_name].draw(bounds)
    ops = []
    for op, args in rec.value:
        ops.append({'op': op, 'points': [[float(x), float(y)] for (x, y) in args]})
    return {
        'source_file': pfb_path.name,
        'slot': int(slot),
        'glyph_name': glyph_name,
        'bounds': [float(v) for v in (bounds.bounds or (0, 0, 0, 0))],
        'path': ops,
    }


def _load_tfm_file(path: Path):
    """Parse one local TFM through the independent tftopl -> PL path."""
    from tfmpl import TFM
    fd, pl = tempfile.mkstemp(suffix='.pl')
    os.close(fd)
    try:
        subprocess.run(
            ['tftopl', str(path), pl],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        return TFM(pl)
    finally:
        try:
            os.unlink(pl)
        except OSError:
            pass


def _type1_upm(font) -> int:
    matrix = font.font.get('FontMatrix')
    if not matrix or not matrix[0]:
        raise ValueError('Type1 font has no usable FontMatrix')
    upm = round(abs(1.0 / float(matrix[0])))
    if upm <= 0:
        raise ValueError('Type1 font has an invalid FontMatrix scale')
    return upm


def _extract_prime_padding(mtpro2_dir: str | Path, script_ratio: Fraction) -> dict:
    """Derive prime padding from local italic overhang and script-prime ink.

    Use the minimum em-quantized shift plus conversion-policy clearance.
    """
    from fontTools import t1Lib
    from fontTools.pens.boundsPen import BoundsPen
    import uni_map as U

    root = Path(mtpro2_dir)
    italic_tag = 'mit'
    italic_base = SOURCE_FONTS[italic_tag]
    italic_pfb = root / (italic_base + '.pfb')
    italic_tfm = root / (italic_base + '.tfm')
    font = t1Lib.T1Font(str(italic_pfb))
    font.parse()
    encoding = font.font.get('Encoding')
    if not isinstance(encoding, list):
        raise ValueError(f'{italic_pfb.name}: no usable Type1 encoding')
    source_upm = _type1_upm(font)
    tfm = _load_tfm_file(italic_tfm)
    glyphs = font.getGlyphSet()
    overhangs = []
    for slot in tuple(range(ord('A'), ord('Z') + 1)) + tuple(range(ord('a'), ord('z') + 1)):
        if slot not in tfm.chars or slot >= len(encoding):
            continue
        glyph_name = encoding[slot]
        if glyph_name not in glyphs:
            continue
        pen = BoundsPen(glyphs)
        glyphs[glyph_name].draw(pen)
        if not pen.bounds:
            continue
        ink_right = float(pen.bounds[2]) * 1000.0 / source_upm
        advance = float(tfm.chars[slot]['wd']) * 1000.0
        overhangs.append(ink_right - advance)
    if not overhangs:
        raise ValueError('cannot derive raw-prime padding from local math italic source')
    max_overhang = max(0.0, max(overhangs))

    prime_slot = next((slot for slot, (u, _name) in U.SYT.items() if u == 0x2032), None)
    if prime_slot is None:
        raise ValueError('public source registry has no prime identity')
    prime_tag = 'syt_s'
    prime_pfb = root / (SOURCE_FONTS[prime_tag] + '.pfb')
    pfont = t1Lib.T1Font(str(prime_pfb))
    pfont.parse()
    penc = pfont.font.get('Encoding')
    if not isinstance(penc, list) or prime_slot >= len(penc):
        raise ValueError(f'{prime_pfb.name}: no usable prime encoding')
    pglyphs = pfont.getGlyphSet()
    pglyph_name = penc[prime_slot]
    if pglyph_name not in pglyphs:
        raise ValueError(f'{prime_pfb.name}: prime source glyph is missing')
    ppen = BoundsPen(pglyphs)
    pglyphs[pglyph_name].draw(ppen)
    if not ppen.bounds:
        raise ValueError(f'{prime_pfb.name}: prime source glyph has no ink bounds')
    prime_upm = _type1_upm(pfont)
    prime_left = float(ppen.bounds[0]) * 1000.0 / prime_upm * float(script_ratio)

    quantum = max(1, round(float(Fraction(1, 100)) * 1000))
    clearance = quantum
    required_shift = max(0.0, max_overhang + clearance - prime_left)
    padding = int(math.ceil(required_shift / quantum) * quantum)
    return {
        'italic_source_tag': italic_tag,
        'prime_source_tag': prime_tag,
        'max_math_italic_overhang': max_overhang,
        'scaled_prime_ink_left': prime_left,
        'clearance': clearance,
        'quantum': quantum,
        'padding': padding,
    }


def extract_geometry(mtpro2_dir: str | Path, policy: SourcePolicy | None = None) -> dict:
    """Extract geometry for synthesized forms from local PFB slots."""
    import uni_map as U
    chain = U.H_CHAINS.get(0x23DC)
    if not chain:
        raise ValueError('missing TOP PARENTHESIS source chain')
    tag, slot = chain[-1]
    base = SOURCE_FONTS[tag]
    return {
        'overparen_template': _type1_slot_path(Path(mtpro2_dir) / (base + '.pfb'), int(slot)),
        'prime_padding': _extract_prime_padding(mtpro2_dir, (policy or extract_policy(mtpro2_dir)).script_ratio),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--mtpro2-dir', required=True)
    ap.add_argument('--edition', choices=('full', 'lite'), default='full')
    ap.add_argument('-o', '--output')
    ap.add_argument('--include-geometry', action='store_true')
    ns = ap.parse_args()
    active = LITE_TAGS if ns.edition == 'lite' else SOURCE_FONTS.keys()
    validate_source_files(ns.mtpro2_dir, active)
    policy = extract_policy(ns.mtpro2_dir, active)
    payload = policy.to_jsonable()
    payload['source_font_by_tag'] = {tag: SOURCE_FONTS[tag] for tag in sorted(active)}
    payload['policy_source_files'] = list(required_policy_files(active))
    if ns.include_geometry:
        payload['geometry'] = extract_geometry(ns.mtpro2_dir, policy)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    if ns.output:
        Path(ns.output).parent.mkdir(parents=True, exist_ok=True)
        Path(ns.output).write_text(text, encoding='utf-8')
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
