"""Build unified OpenType MATH from local MTPro2 sources and Roman donors.

Run through build.sh with FontForge Python.
"""
import sys, os, json, math, subprocess
if any(arg == '--family' or arg.startswith('--family=') for arg in sys.argv[1:]):
    print('error: --family is not supported; Full and Lite use fixed installation names.', file=sys.stderr)
    raise SystemExit(2)

from fractions import Fraction
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fontforge, psMat
from tfmpl import TFM
import uni_map as U
import math_constants
import source_policy

# Allow the project root to be overridden by MTP2_ROOT.
ROOT = os.environ.get('MTP2_ROOT') or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
T1DIR = f'{ROOT}/mtpro2'
TFMDIR = f'{ROOT}/mtpro2'
TIMESDIR = f'{ROOT}/times'
PLDIR = f'{ROOT}/build/pl'
OUTDIR = f'{ROOT}/out'
os.makedirs(PLDIR, exist_ok=True)
os.makedirs(OUTDIR, exist_ok=True)
SUBSCRIPT_CORRECTION = '--subscript-correction' in sys.argv
# Editable embedding by default; --fstype overrides the metadata flag.
FSTYPE = 8
# Bound fixed variants for Windows; larger sizes use MATH assemblies.
MAXVAR = 5580
MAXWIDTH = 12000
# Conversion tolerance for stable connector profiles.
CONNECTOR_PROFILE_TOLERANCE = 8
if '--fstype' in sys.argv:
    FSTYPE = int(sys.argv[sys.argv.index('--fstype') + 1])
if '--max-variant' in sys.argv:
    MAXVAR = int(sys.argv[sys.argv.index('--max-variant') + 1])
if '--max-width' in sys.argv:
    MAXWIDTH = int(sys.argv[sys.argv.index('--max-width') + 1])

# Select the edition explicitly; missing Full inputs must not imply Lite.
EDITION = os.environ.get('MTP2_EDITION', 'full').strip().lower()
for _arg in sys.argv:
    if _arg.startswith('--edition='):
        EDITION = _arg.split('=', 1)[1].strip().lower()
if EDITION not in ('full', 'lite'):
    raise SystemExit('unknown MTPro2 edition %r (expected full or lite)' % EDITION)

# Share source identities; read numeric policy from local inputs.
LITE_TAGS = source_policy.LITE_TAGS
SRC = source_policy.SOURCE_FONTS

if EDITION == 'lite':
    FAMILY, FONT_PSNAME, FONT_BASENAME = 'MTPro2 Math Lite', 'MTPro2MathLite', 'MTPro2MathLite'
else:
    FAMILY, FONT_PSNAME, FONT_BASENAME = 'MTPro2 Math', 'MTPro2Math', 'MTPro2Math'
STYLE = 'Regular'


def load(tag):
    name = SRC[tag]
    plp = f'{PLDIR}/{name}.pl'
    # Regenerate PL so the active TFM and PFB form one input set.
    subprocess.run(
        ['tftopl', f'{TFMDIR}/{name}.tfm', plp],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    tfm = TFM(plp)
    pfb = fontforge.open(f'{T1DIR}/{name}.pfb')
    slots = {g.encoding: g.glyphname for g in pfb.glyphs() if g.encoding < 0x10000}
    return pfb, tfm, slots


fonts = {}
_active_tags = [tag for tag in SRC if EDITION != 'lite' or tag in LITE_TAGS]
_load_errors = []
for tag in _active_tags:
    try:
        fonts[tag] = load(tag)
    except Exception as exc:
        _load_errors.append((tag, exc))
if _load_errors:
    details = '; '.join('%s(%s): %s' % (tag, SRC[tag], exc)
                        for tag, exc in _load_errors)
    raise SystemExit('MTPro2 source load failed: ' + details)
_missing = [tag for tag in _active_tags if tag not in fonts]
if _missing:
    raise SystemExit('MTPro2 source set is incomplete: ' +
                     ', '.join('%s(%s)' % (tag, SRC[tag]) for tag in _missing))
print('MTPro2 edition:', EDITION, 'source families:', len(fonts))

# Read the local snapshot prepared by build.sh outside FontForge Python.
_SOURCE_POLICY_PATH = os.environ.get('MTP2_SOURCE_POLICY_JSON')
if not _SOURCE_POLICY_PATH or not os.path.isfile(_SOURCE_POLICY_PATH):
    raise SystemExit('missing local source snapshot; run this builder through ./build.sh')
_SOURCE_SNAPSHOT = json.load(open(_SOURCE_POLICY_PATH, encoding='utf-8'))
SOURCE_POLICY = source_policy.load_policy_json(_SOURCE_POLICY_PATH)
SOURCE_SKEW = dict(SOURCE_POLICY.skewchar_by_tag)
SCRIPT_RATIO = SOURCE_POLICY.script_ratio
SCRIPTSCRIPT_RATIO = SOURCE_POLICY.scriptscript_ratio

out = fontforge.font()
out.encoding = 'UnicodeFull'
out.em = 1000
out.familyname = FAMILY
out.fontname = FONT_PSNAME
out.fullname = FAMILY
out.weight = 'Regular'
out.copyright = ('Copyright (C) Publish or Perish, Inc. 2005.  '
                 'Outlines from the MathTime(TM) Professional II Type1 fonts. '
                 'Unofficial OpenType MATH conversion for the licensee\'s own use; '
                 'redistribution of this font file is not permitted.')

imported = {}          # (tag, slot) -> glyphname in out
uni_owner = {}         # unicode -> glyphname


def uname(u):
    return 'uni%04X' % u if u < 0x10000 else 'u%05X' % u


# Prefix digit-leading names for Word font subsetting.
_DIGIT_NAME = ('zero', 'one', 'two', 'three', 'four',
               'five', 'six', 'seven', 'eight', 'nine')


def safe_gname(name):
    if name and name[0].isdigit():
        return _DIGIT_NAME[int(name[0])] + name[1:]
    return name


def _axis_height():
    """Return the local MTPro2 math axis from the active symbol TFM."""
    return round(fonts['syt'][1].fontdimen[22] * out.em)


def _tfm_design_size(tfm):
    size = getattr(tfm, 'design_size', None)
    if not size or size <= 0:
        raise RuntimeError('local TFM is missing a usable DESIGNSIZE')
    return Fraction(str(size))


def _pt_to_units(value, tfm):
    """Convert a package dimension in TeX points to output-font units."""
    return round(value / _tfm_design_size(tfm) * out.em)


def _mu_to_units(value):
    """Convert TeX math units to output-font units (one em is eighteen mu)."""
    return round(value / 18 * out.em)


def recenter_on_axis(gname):
    """Center delimiter variants on the math axis to bound Windows clipping metrics."""
    g = out[gname]
    bb = g.boundingBox()
    if bb == (0, 0, 0, 0):
        return
    dy = _axis_height() - (bb[1] + bb[3]) / 2.0
    if abs(dy) >= 1:
        g.transform(psMat.translate(0, round(dy)))


def import_glyph(tag, slot, name=None, unicode_=None, force_alt=False):
    """Copy a source slot, or return its existing output glyph name."""
    key = (tag, slot)
    if key in imported:
        gname = imported[key]
        if unicode_ is not None and unicode_ not in uni_owner and not force_alt:
            g = out[gname]
            if g.unicode == -1:
                g.unicode = unicode_
                # Use codepoint-based names.
                nn = uname(unicode_)
                if nn not in out:
                    g.glyphname = nn
                    imported[key] = nn
                    gname = nn
            else:
                out[gname].altuni = ((out[gname].altuni or ()) + ((unicode_, -1, 0),))
            uni_owner[unicode_] = gname
        return gname
    pfb, tfm, slots = fonts[tag]
    if slot not in slots or slot not in tfm.chars:
        return None
    srcname = slots[slot]
    if unicode_ is not None and unicode_ in uni_owner:
        force_alt = True
        base = uni_owner[unicode_]
        unicode_ = None
        name = name or f'{base}.{tag}alt'
    if unicode_ is not None:
        gname = uname(unicode_)
        if name and not name.startswith('uni') and not name.startswith('u1'):
            gname = uname(unicode_)  # Prefer the canonical codepoint name.
    else:
        gname = name or f'{tag}.{slot}'
    if gname in out:
        gname = f'{gname}.{tag}{slot}'
    gname = safe_gname(gname)
    pfb.selection.select(('encoding',), slot)
    pfb.copy()
    out.createChar(-1, gname)
    out.selection.select(gname)
    out.paste()
    g = out[gname]
    # Scale by the package-declared design size.
    scale = {'xxxl': 2.0, 'exe': 2.0, 'exf': 4.0, 'exg': 8.0}.get(tag, 1.0)
    if scale != 1.0:
        g.transform(psMat.scale(scale))
    if tag in ('xl', 'xxxl'):
        # PFB vertical placement assumes TeX-side raising; recenter on the local math axis.
        bb = g.boundingBox()
        g.transform(psMat.translate(0, _axis_height() - (bb[1] + bb[3]) / 2))
    _wd = tfm.chars[slot]['wd']
    _ic = tfm.chars[slot]['ic']
    if tag in ('exa', 'xl', 'xxxl') and _ic:
        # Include the slanted operator overhang in advance for OpenType script placement.
        g.width = round((_wd + _ic) * 1000 * scale)
    else:
        g.width = round(_wd * 1000 * scale)
    if unicode_ is not None:
        g.unicode = unicode_
        uni_owner[unicode_] = gname
    ic = tfm.chars[slot]['ic']
    if ic:
        g.italicCorrection = round(ic * 1000 * scale)
    imported[key] = gname
    return gname


# Core Unicode mappings.
plan = [('mit', U.MIT), ('syt', U.SYT)]
for tag, table in plan:
    if tag not in fonts:
        continue
    for slot, (u, name) in sorted(table.items()):
        import_glyph(tag, slot, name=name, unicode_=u)

# Encode text operators; keep display variants in size order.
op_variants = {}  # base glyph -> size-ordered variants, including the base
if 'exa' in fonts:
    for slot, (u, name, dslot) in U.EXA_OPS.items():
        base = import_glyph('exa', slot, name=name, unicode_=u)
        if base is None:
            continue
        var = [base]
        d = import_glyph('exa', dslot, name=f'{base}.dsp')
        if d:
            var.append(d)
        # xl / XL / XXL / XXXL
        if name in U.XL_TABLE and 'xl' in fonts:
            xl, XL, XXL, XXXL = U.XL_TABLE[name]
            for sz, (ftag, sl) in enumerate([('xl', xl), ('xl', XL), ('xl', XXL), ('xxxl', XXXL)]):
                if ftag not in fonts:
                    continue
                sfx = ['.xl', '.XL', '.XXL', '.XXXL'][sz]
                if isinstance(sl, tuple):  # Compose the two source halves.
                    l = import_glyph(ftag, sl[0], name=f'{base}{sfx}.l')
                    r = import_glyph(ftag, sl[1], name=f'{base}{sfx}.r')
                    if l and r:
                        gn = f'{base}{sfx}'
                        out.createChar(-1, gn)
                        g = out[gn]
                        g.addReference(l)
                        g.addReference(r, psMat.translate(out[l].width, 0))
                        g.width = out[l].width + out[r].width
                        var.append(gn)
                else:
                    v = import_glyph(ftag, sl, name=f'{base}{sfx}')
                    if v:
                        var.append(v)
        # Limit fixed sizes to keep Windows clipping bounds manageable.
        trimmed = [var[0]]
        for gn in var[1:]:
            bb = out[gn].boundingBox()
            if MAXVAR and bb[3] - bb[1] > MAXVAR:
                dead = {gn} | {r[0] for r in (out[gn].references or ())}
                for k, v in list(imported.items()):
                    if v in dead:
                        del imported[k]
                for d in dead:
                    if d in out:
                        out.removeGlyph(out[d])
                continue
            recenter_on_axis(gn)
            trimmed.append(gn)
        op_variants[base] = trimmed

# AMSa
if 'ams' in fonts:
    for slot, (u, name) in sorted(U.AMSA.items()):
        import_glyph('ams', slot, name=name, unicode_=u)

# Math alphabets.
for tag, kind in [('bb', 'bb'), ('script', 'script'), ('frak', 'frak'),
                  ('curly', 'curly')]:
    if tag not in fonts:
        continue
    for slot, (u, name) in sorted(U.alpha_map(kind).items()):
        import_glyph(tag, slot, name=name, unicode_=u)


# Regular/Bold Roman donors supply upright Latin and mathematical bold.
# MTPro2 supplies mathematical italic; mt2mb* is the separate mbf alphabet.
def _find_roman_regular():
    path = (os.environ.get('MTP2_ROMAN_REGULAR') or
            os.environ.get('MTP2_TIMES_REGULAR') or
            os.path.join(TIMESDIR, 'NimbusRoman-Regular.otf'))
    if not os.path.isfile(path):
        raise SystemExit(
            'Missing Regular Roman donor: %s; provide it or use build.sh --roman-regular.' % path)
    return path


def _find_roman_bold():
    path = (os.environ.get('MTP2_ROMAN_BOLD') or
            os.environ.get('MTP2_TIMES_BOLD') or
            os.path.join(TIMESDIR, 'NimbusRoman-Bold.otf'))
    if not os.path.isfile(path):
        raise SystemExit(
            'Missing Bold Roman donor: %s; provide it or use build.sh --roman-bold.' % path)
    return path


def _donor_unicode_map(ffont):
    d = {}
    for g in ffont.glyphs():
        u = g.unicode
        if u is not None and u >= 0:
            d[u] = g.glyphname
    return d


def _copy_donor_glyph(ffont, byuni, src_u, dst_u, dst_name=None):
    src_name = byuni.get(src_u)
    if src_name is None:
        raise RuntimeError('Roman donor missing U+%04X' % src_u)
    if dst_u is not None and dst_u in uni_owner:
        return uni_owner[dst_u]
    gn = dst_name or uname(dst_u)
    ffont.selection.select(src_name)
    ffont.copy()
    out.createChar(dst_u if dst_u is not None else -1, gn)
    out.selection.select(gn)
    out.paste()
    scale = float(out.em) / float(ffont.em)
    if abs(scale - 1.0) > 1e-12:
        out[gn].transform(psMat.scale(scale))
    out[gn].width = round(ffont[src_name].width * scale)
    if dst_u is not None:
        uni_owner[dst_u] = gn
    return gn


ROMAN_REG = _find_roman_regular()
ROMAN_BOLD = _find_roman_bold()
upright_dotless = None

_nf_reg = fontforge.open(ROMAN_REG)
_nr = _donor_unicode_map(_nf_reg)
for _u in list(range(0x41, 0x5B)) + list(range(0x61, 0x7B)):
    _copy_donor_glyph(_nf_reg, _nr, _u, _u)
# dotless i is used internally by dtls.  Prefer the encoded U+0131 if present.
if 0x0131 in _nr:
    upright_dotless = _copy_donor_glyph(_nf_reg, _nr, 0x0131, None, 'i.dotless')
elif 'dotlessi' in _nf_reg:
    _nf_reg.selection.select('dotlessi')
    _nf_reg.copy()
    out.createChar(-1, 'i.dotless')
    out.selection.select('i.dotless')
    out.paste()
    _roman_reg_scale = float(out.em) / float(_nf_reg.em)
    if abs(_roman_reg_scale - 1.0) > 1e-12:
        out['i.dotless'].transform(psMat.scale(_roman_reg_scale))
    out['i.dotless'].width = round(_nf_reg['dotlessi'].width * _roman_reg_scale)
    upright_dotless = 'i.dotless'
_nf_reg.close()

_nf_bold = fontforge.open(ROMAN_BOLD)
_nb = _donor_unicode_map(_nf_bold)
# Unicode Mathematical Bold Latin and digits follow \mathbf / rmdefault bold.
for _i, _u in enumerate(range(0x41, 0x5B)):
    _copy_donor_glyph(_nf_bold, _nb, _u, 0x1D400 + _i)
for _i, _u in enumerate(range(0x61, 0x7B)):
    _copy_donor_glyph(_nf_bold, _nb, _u, 0x1D41A + _i)
for _i, _u in enumerate(range(0x30, 0x3A)):
    _copy_donor_glyph(_nf_bold, _nb, _u, 0x1D7CE + _i)
_nf_bold.close()


# Import MTPro2 bold math sources into the unified font.
def alias_unicode(gname, u):
    old = uni_owner.get(u)
    if old is not None and old != gname:
        raise RuntimeError('Unicode U+%04X already owned by %s, cannot alias %s' % (u, old, gname))
    g = out[gname]
    if g.unicode == -1:
        g.unicode = u
    elif g.unicode != u:
        vals = list(g.altuni or ())
        if not any(a[0] == u for a in vals):
            vals.append((u, -1, 0))
            g.altuni = tuple(vals)
    uni_owner[u] = gname
    return gname


# Latin-shaped Greek aliases share glyph IDs, metrics, and substitutions.
def _install_greek_latin_shaped_aliases():
    groups = (
        ('Basic Greek', U.GREEK_LATIN_SHAPED_BASIC_ALIASES),
        ('Mathematical Italic Greek', U.GREEK_LATIN_SHAPED_MATH_ITALIC_ALIASES),
    )
    count = 0
    for label, table in groups:
        for target_cp, source_cp in table.items():
            source_glyph = uni_owner.get(source_cp)
            if source_glyph is None:
                raise RuntimeError('%s alias source U+%04X missing for U+%04X' %
                                   (label, source_cp, target_cp))
            alias_unicode(source_glyph, target_cp)
            count += 1
    if count != 30:
        raise RuntimeError('Greek Latin-shaped alias contract expected 30 entries, got %d' % count)


_install_greek_latin_shaped_aliases()

_MIT_CP_SLOT = {u: slot for slot, (u, _name) in U.MIT.items() if u is not None}
_SYT_CP_SLOT = {u: slot for slot, (u, _name) in U.SYT.items() if u is not None}


def bmit_cp(source_cp, target_cp, name=None):
    slot = _MIT_CP_SLOT.get(source_cp)
    if slot is None:
        raise RuntimeError('mt2bmit source mapping missing U+%04X' % source_cp)
    return import_glyph('bmit', slot, name=name, unicode_=target_cp)


bold_it_latin = {}
bold_dotless_i = None
bold_dotless_j = None
# Lite has donor bold Latin/digits, but no synthesized Full-only bold math.
if 'bmit' in fonts and 'bsyt' in fonts:
    # Mathematical Bold Italic Latin U+1D468..U+1D49B.
    bold_it_latin = {}
    for i, ch in enumerate('ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
        g = import_glyph('bmit', ord('A') + i, unicode_=0x1D468 + i)
        bold_it_latin[ch] = g
    for i, ch in enumerate('abcdefghijklmnopqrstuvwxyz'):
        g = import_glyph('bmit', ord('a') + i, unicode_=0x1D482 + i)
        bold_it_latin[ch] = g

    # Keep bold dotless forms unencoded; public dotless codepoints belong to italic.
    bold_dotless_i = import_glyph('bmit', 0x7B, name='u1D48A.dotless')
    bold_dotless_j = import_glyph('bmit', 0x7C, name='u1D48B.dotless')

    # Greek uppercase order in the Unicode Mathematical Alphanumeric block.
    greek_cap_names = [
        'ALPHA', 'BETA', 'GAMMA', 'DELTA', 'EPSILON', 'ZETA', 'ETA', 'THETA', 'IOTA', 'KAPPA',
        'LAMDA', 'MU', 'NU', 'XI', 'OMICRON', 'PI', 'RHO', 'THETA SYMBOL', 'SIGMA', 'TAU',
        'UPSILON', 'PHI', 'CHI', 'PSI', 'OMEGA']
    basic_cap = {
        'ALPHA': 0x0391, 'BETA': 0x0392, 'GAMMA': 0x0393, 'DELTA': 0x0394, 'EPSILON': 0x0395,
        'ZETA': 0x0396, 'ETA': 0x0397, 'THETA': 0x0398, 'IOTA': 0x0399, 'KAPPA': 0x039A,
        'LAMDA': 0x039B, 'MU': 0x039C, 'NU': 0x039D, 'XI': 0x039E, 'OMICRON': 0x039F,
        'PI': 0x03A0, 'RHO': 0x03A1, 'SIGMA': 0x03A3, 'TAU': 0x03A4, 'UPSILON': 0x03A5,
        'PHI': 0x03A6, 'CHI': 0x03A7, 'PSI': 0x03A8, 'OMEGA': 0x03A9}
    latin_visual = {
        'ALPHA': 'A', 'BETA': 'B', 'EPSILON': 'E', 'ZETA': 'Z', 'ETA': 'H', 'IOTA': 'I',
        'KAPPA': 'K', 'MU': 'M', 'NU': 'N', 'OMICRON': 'O', 'RHO': 'P', 'TAU': 'T', 'CHI': 'X'}

    # Use mt2bmit for non-Latin-shaped bold Greek and Latin aliases for the rest.
    bold_greek = {}
    for idx, name in enumerate(greek_cap_names):
        tgt = 0x1D6A8 + idx
        if name == 'THETA SYMBOL':
            g = bold_greek['THETA']
            alias_unicode(g, tgt)
        elif basic_cap[name] in _MIT_CP_SLOT:
            g = bmit_cp(basic_cap[name], tgt)
        else:
            g = uni_owner[0x1D400 + (ord(latin_visual[name]) - ord('A'))]
            alias_unicode(g, tgt)
        bold_greek[name] = g

    # Genuine bold nabla from mt2bsyt; upright and italic mathematical nabla share it.
    _bsnabla_slot = _SYT_CP_SLOT.get(0x2207)
    if _bsnabla_slot is None:
        raise RuntimeError('mt2bsyt nabla source missing')
    bold_nabla = import_glyph('bsyt', _bsnabla_slot, unicode_=0x1D6C1)
    alias_unicode(bold_nabla, 0x1D735)

    small_order = [
        ('ALPHA', 0x03B1), ('BETA', 0x03B2), ('GAMMA', 0x03B3), ('DELTA', 0x03B4),
        ('EPSILON', 0x03B5), ('ZETA', 0x03B6), ('ETA', 0x03B7), ('THETA', 0x03B8),
        ('IOTA', 0x03B9), ('KAPPA', 0x03BA), ('LAMDA', 0x03BB), ('MU', 0x03BC),
        ('NU', 0x03BD), ('XI', 0x03BE), ('OMICRON', 0x03BF), ('PI', 0x03C0),
        ('RHO', 0x03C1), ('FINAL SIGMA', 0x03C2), ('SIGMA', 0x03C3), ('TAU', 0x03C4),
        ('UPSILON', 0x03C5), ('PHI', 0x03C6), ('CHI', 0x03C7), ('PSI', 0x03C8), ('OMEGA', 0x03C9)]
    for idx, (_name, source_cp) in enumerate(small_order):
        tgt = 0x1D6C2 + idx
        if source_cp in _MIT_CP_SLOT:
            bmit_cp(source_cp, tgt)
        else:  # Greek omicron has the Latin o design.
            alias_unicode(uni_owner[0x1D41A + (ord('o') - ord('a'))], tgt)

    # Bold partial differential and upright variant Greek symbols.
    bold_partial = bmit_cp(0x1D715, 0x1D6DB)
    for i, source_cp in enumerate((0x03F5, 0x03D1, 0x03F0, 0x03D5, 0x03F1, 0x03D6)):
        bmit_cp(source_cp, 0x1D6DC + i)

    # Mathematical Bold Italic Greek U+1D71C..U+1D755.
    italic_cap_regular = {
        'GAMMA': 0x1D6E4, 'DELTA': 0x1D6E5, 'THETA': 0x1D6E9, 'LAMDA': 0x1D6EC,
        'XI': 0x1D6EF, 'PI': 0x1D6F1, 'SIGMA': 0x1D6F4, 'UPSILON': 0x1D6F6,
        'PHI': 0x1D6F7, 'PSI': 0x1D6F9, 'OMEGA': 0x1D6FA}
    bold_it_greek = {}
    for idx, name in enumerate(greek_cap_names):
        tgt = 0x1D71C + idx
        if name == 'THETA SYMBOL':
            g = bold_it_greek['THETA']
            alias_unicode(g, tgt)
        elif name in italic_cap_regular:
            g = bmit_cp(italic_cap_regular[name], tgt)
        else:
            g = bold_it_latin[latin_visual[name]]
            alias_unicode(g, tgt)
        bold_it_greek[name] = g

    reg_it_small = [
        0x1D6FC, 0x1D6FD, 0x1D6FE, 0x1D6FF, 0x1D700, 0x1D701, 0x1D702, 0x1D703,
        0x1D704, 0x1D705, 0x1D706, 0x1D707, 0x1D708, 0x1D709, 0x1D70A, 0x1D70B,
        0x1D70C, 0x1D70D, 0x1D70E, 0x1D70F, 0x1D710, 0x1D711, 0x1D712, 0x1D713, 0x1D714]
    for i, source_cp in enumerate(reg_it_small):
        tgt = 0x1D736 + i
        if source_cp in _MIT_CP_SLOT:
            bmit_cp(source_cp, tgt)
        else:  # mathematical italic omicron = Latin italic o
            alias_unicode(bold_it_latin['o'], tgt)
    alias_unicode(bold_partial, 0x1D74F)
    for i, source_cp in enumerate((0x1D716, 0x1D717, 0x1D718, 0x1D719, 0x1D71A, 0x1D71B)):
        bmit_cp(source_cp, 0x1D750 + i)


# Vertical delimiter variants and assemblies.
def exa_chain(start):
    """Return the NEXTLARGER chain and its terminal VARCHAR recipe."""
    _, tfm, _ = fonts['exa']
    seq, c, seen = [], start, set()
    while c is not None and c in tfm.chars and c not in seen:
        seen.add(c)
        seq.append(c)
        vc = tfm.chars[c]['varchar']
        nxt = tfm.chars[c]['next']
        if nxt is None:
            return seq, vc
        c = nxt
    return seq, None


MINOVL = None  # Assigned from MathConstants below.
vert_variants = {}     # base gname -> [gnames]
vert_assembly = {}  # base -> [(glyph, extender)], bottom to top
# Cap generic connector estimates with local source geometry where needed.
connector_limits = {}
piece_names = dict(U.EXA_PIECES)


def piece(slot):
    nm = piece_names.get(slot, f'exa.piece{slot}')
    return import_glyph('exa', slot, name=nm)


def build_vdelim(basespec, exastart, base_uni=None, base_name=None):
    tag, slot = basespec
    base = import_glyph(tag, slot, name=base_name, unicode_=base_uni)
    if base is None or 'exa' not in fonts:
        return
    _, tfm, _ = fonts['exa']
    seq, vc = exa_chain(exastart)
    var = [base]
    for c in seq:
        # A TeX VARCHAR slot selects an assembly, not a fixed-size variant.
        is_terminal_piece = bool(tfm.chars.get(c, {}).get('varchar')) or (
            vc is not None and c == seq[-1]
            and c in (vc.get('TOP'), vc.get('BOT'), vc.get('MID'))
            and c != vc.get('REP'))
        if is_terminal_piece and len(seq) > 1:
            continue  # Exclude assembly parts from fixed-size variants.
        v = import_glyph('exa', c, name=f'{base}.v{len(var)}')
        if v:
            var.append(v)
    vert_variants[base] = var
    if vc and 'REP' in vc:
        parts = []  # Bottom to top.
        if 'BOT' in vc:
            parts.append((piece(vc['BOT']), 0))
        parts.append((piece(vc['REP']), 1))
        if 'MID' in vc:
            parts.append((piece(vc['MID']), 0))
            parts.append((piece(vc['REP']), 1))
        if 'TOP' in vc:
            parts.append((piece(vc['TOP']), 0))
        parts = [(p, e) for (p, e) in parts if p]
        if parts and not any(e == 0 for (p, e) in parts):
            # Repeat-only recipes use the same glyph as fixed ends and a central extender.
            rep = parts[0][0]
            parts = [(rep, 0), (rep, 1), (rep, 0)]
        if parts:
            vert_assembly[base] = parts


for u, (bspec, ex0) in U.V_DELIMS.items():
    build_vdelim(bspec, ex0, base_uni=u)
for nm, (bspec, ex0) in U.V_DELIMS_ALT.items():
    build_vdelim(bspec, ex0, base_name=nm)

# Include operator variants.
vert_variants.update(op_variants)

# Extend variant ladders from the package-selected extension families.
EXT_TAGS = ('exe', 'exf', 'exg')


def chain_slots(tfm, start):
    """Follow the TFM NEXTLARGER chain."""
    out, seen, s = [], set(), start
    while s is not None and s in tfm.chars and s not in seen:
        seen.add(s)
        out.append(s)
        s = tfm.chars[s].get('next')
    return out


def chain_heads(tfm):
    """Return slots with no incoming NEXTLARGER link."""
    targets = {c['next'] for c in tfm.chars.values() if c.get('next') is not None}
    return {s for s in tfm.chars if s not in targets}


def extend_chain(base_gname, slot, table, size_key):
    """Append an extension chain only when its head matches the base source."""
    added = []
    for tag in EXT_TAGS:
        if tag not in fonts:
            continue
        _, tfm, _ = fonts[tag]
        if slot not in tfm.chars or slot not in chain_heads(tfm):
            continue
        for s in chain_slots(tfm, slot):
            g = import_glyph(tag, s, name=f'{base_gname}.{tag}{s}')
            if not g:
                continue
            bb = out[g].boundingBox()
            # Compare height for vertical variants and advance for horizontal variants.
            if size_key == 'h':
                extent, cap = bb[3] - bb[1], MAXVAR
            else:
                extent, cap = out[g].width, MAXWIDTH
            if cap and extent > cap:
                # Discard oversized variants and their import records.
                imported.pop((tag, s), None)
                out.removeGlyph(out[g])
                continue
            if size_key == 'h':
                recenter_on_axis(g)
            added.append(g)
    if added:
        table[base_gname] = table.get(base_gname, [base_gname]) + added
        # Sort variants by size; equal-size stages may remain.
        key = (lambda gn: out[gn].width) if size_key == 'w' else \
              (lambda gn: out[gn].boundingBox()[3] - out[gn].boundingBox()[1])
        head, rest = table[base_gname][0], table[base_gname][1:]
        table[base_gname] = [head] + sorted(rest, key=key)
    return added


# Only extend matching chain heads; brackets, floors, and ceilings have none.
for u, (bspec, ex0) in U.V_DELIMS.items():
    if u not in uni_owner:
        continue
    base = uni_owner[u]
    extend_chain(base, ex0, vert_variants, 'h')

# Horizontal variants and brace assemblies.
horiz_variants = {}
for u, chain in U.H_CHAINS.items():
    gnames = []
    for tag, slot in chain:
        if tag not in fonts:
            continue
        g = import_glyph(tag, slot, unicode_=u if not gnames else None,
                         name=None if not gnames else None)
        if g:
            gnames.append(g)
    if len(gnames) >= 1:
        horiz_variants[gnames[0]] = gnames

# Keep public bar accents fixed. Private variants do not remap standard commands.
_bar_base = uni_owner.get(0x0304)
if _bar_base is not None:
    _bar_chain = list(horiz_variants.get(_bar_base, [_bar_base]))
    if len(_bar_chain) > 1:
        _widebar_cp = 0xE286
        _widebar_name = 'wideoverbar.compat'
        if _widebar_name not in out:
            out.createChar(_widebar_cp, _widebar_name)
            _wg = out[_widebar_name]
            _wg.addReference(_bar_base)
            # The private finite bar keeps its advance and outline; attachment is width/2.
            _wg.width = out[_bar_base].width
            _wg.unlinkRef()
        uni_owner[_widebar_cp] = _widebar_name
        horiz_variants[_widebar_name] = [_widebar_name] + _bar_chain[1:]
    horiz_variants.pop(_bar_base, None)

# Extend only matching wide-accent chains. Equal slots can have different semantics.
_WIDE_ACCENT_EXTENSION = (0x0302, 0x0303, 0x030C)
for u in _WIDE_ACCENT_EXTENSION:
    chain = U.H_CHAINS.get(u, ())
    if u not in uni_owner:
        continue
    exa_slots = [slot for (tag, slot) in chain if tag == 'exa']
    if exa_slots:
        extend_chain(uni_owner[u], exa_slots[0], horiz_variants, 'w')

# Use the designated mt2exf overparen continuation at its source scale.
if 0x23DC in uni_owner and 'exf' in fonts:
    base = uni_owner[0x23DC]
    extra = []
    for slot in range(177, 184):
        g = import_glyph('exf', slot, name=f'{base}.exf{slot}')
        if not g:
            continue
        if MAXWIDTH and out[g].width > MAXWIDTH:
            imported.pop(('exf', slot), None)
            out.removeGlyph(out[g])
            continue
        extra.append(g)
    if extra:
        vals = horiz_variants.get(base, [base]) + extra
        # Deduplicate equal-width stages while preserving the first source form.
        seen_w = set()
        dedup = []
        for gn in sorted(vals, key=lambda q: out[q].width):
            w = out[gn].width
            if w in seen_w:
                continue
            seen_w.add(w)
            dedup.append(gn)
        horiz_variants[base] = dedup

    # Bridge the fixed overparen ladders with an assembly derived from the local outline.
    def _make_overparen_parts():
        left = 'overparen.left.mt2'
        ext = 'overparen.ext.mt2'
        right = 'overparen.right.mt2'

        try:
            tpl = _SOURCE_SNAPSHOT['geometry']['overparen_template']
            ops = tpl['path']
        except Exception as exc:
            raise RuntimeError('local overparen source geometry is missing') from exc
        expected_ops = ('moveTo', 'lineTo', 'curveTo', 'curveTo',
                        'lineTo', 'curveTo', 'curveTo', 'closePath')
        if tuple(rec.get('op') for rec in ops) != expected_ops:
            raise RuntimeError('unexpected local MTPro2 overparen contour topology')

        def ipoints(i):
            pts = []
            for x, y in ops[i]['points']:
                if round(x) != x or round(y) != y:
                    raise RuntimeError('non-integral local Type1 overparen coordinate')
                pts.append((int(x), int(y)))
            return pts

        start_pt = ipoints(0)[0]
        left_inner = ipoints(1)[0]
        lower_left = ipoints(2)
        lower_right = ipoints(3)
        right_edge = ipoints(4)[0]
        upper_right = ipoints(5)
        upper_left = ipoints(6)
        mid_lower = lower_left[-1]
        mid_upper = upper_right[-1]
        if mid_lower[0] != mid_upper[0] or start_pt != upper_left[-1]:
            raise RuntimeError(
                'local overparen source contour is not the expected symmetric-cap topology')
        span = right_edge[0] - start_pt[0]
        if span <= 0:
            raise RuntimeError('invalid local overparen source span')

        # Derive connector proportions from the local span.
        connector = round(span / 15)
        ext_width = round(span / 6)
        inner_x = mid_lower[0] + connector
        right_dx = connector - mid_lower[0]
        left_width = inner_x - start_pt[0]
        right_width = right_edge[0] + right_dx

        if left not in out:
            out.createChar(-1, left)
            g = out[left]
            pen = g.glyphPen()
            pen.moveTo(start_pt)
            pen.lineTo(left_inner)
            pen.curveTo(*lower_left)
            pen.lineTo((inner_x, mid_lower[1]))
            pen.lineTo((inner_x, mid_upper[1]))
            pen.lineTo(mid_upper)
            pen.curveTo(*upper_left)
            pen.closePath()
            pen = None
            g.width = left_width
        if ext not in out:
            out.createChar(-1, ext)
            g = out[ext]
            pen = g.glyphPen()
            pen.moveTo((0, mid_lower[1]))
            pen.lineTo((ext_width, mid_lower[1]))
            pen.lineTo((ext_width, mid_upper[1]))
            pen.lineTo((0, mid_upper[1]))
            pen.closePath()
            pen = None
            g.width = ext_width
        if right not in out:
            def tx(pt): return (pt[0] + right_dx, pt[1])
            out.createChar(-1, right)
            g = out[right]
            pen = g.glyphPen()
            pen.moveTo((0, mid_lower[1]))
            pen.lineTo((connector, mid_lower[1]))
            pen.curveTo(*(tx(q) for q in lower_right))
            pen.lineTo(tx(right_edge))
            pen.curveTo(*(tx(q) for q in upper_right))
            pen.lineTo((0, mid_upper[1]))
            pen.closePath()
            pen = None
            g.width = right_width
        return left, ext, right

    _opl, _ope, _opr = _make_overparen_parts()
    vert_assembly[('H', base)] = [(_opl, 0), (_ope, 1), (_opr, 0)]


# Normalize combining accents: zero advance, left-shifted ink, TopAccent alignment.
_NORMALIZED_ACCENT_MACROS = (
    'grave', 'acute', 'check', 'breve', 'bar', 'hat', 'dot', 'tilde', 'ddot', 'mathring',
    'vec', 'dotup', 'ddotup', 'dddot', 'ddddot', 'dddotup', 'ddddotup',
)
try:
    ACCENT_SLOTS = [SOURCE_POLICY.accents[name].slot for name in _NORMALIZED_ACCENT_MACROS]
except KeyError as exc:
    raise RuntimeError('required local MTPro2 accent declaration missing: %s' % exc.args[0])
accent_glyphs = set()
ACC_CENTER = -(_axis_height() + round((fonts['exa'][1].fontdimen[8] * out.em) / 4))
for slot in ACCENT_SLOTS:
    key = ('syt', slot)
    if key not in imported:
        continue
    g = out[imported[key]]
    bb = g.boundingBox()
    cx = (bb[0] + bb[2]) / 2
    g.transform(psMat.translate(ACC_CENTER - cx, 0))
    g.width = 0
    accent_glyphs.add(g.glyphname)


# Dot and prime geometry.
def compose(uni, name, ref, offsets, adv):
    """Compose copies of a reference glyph at the given offsets."""
    gn = uname(uni) if uni is not None else name
    if uni is not None and uni in uni_owner:
        return None
    out.createChar(uni if uni is not None else -1, gn)
    g = out[gn]
    for (dx, dy) in offsets:
        g.addReference(ref, psMat.translate(dx, dy))
    g.width = round(adv)
    if uni is not None:
        uni_owner[uni] = gn
    return gn


if ('mit', 0x3A) in imported and ('syt', 0x01) in imported:
    # Read dot geometry from the local package; horizontal spacing uses math units.
    P = out[imported[('mit', 0x3A)]].width
    Cw = out[imported[('syt', 0x01)]].width
    per = imported[('mit', 0x3A)]
    cdo = imported[('syt', 0x01)]
    tfm_symbols = fonts['syt'][1]
    ellipsis_gap = _mu_to_units(Fraction(3, 1))
    compose(0x2026, None, per,
            [(0, 0), (P + ellipsis_gap, 0), (2 * (P + ellipsis_gap), 0)],
            3 * P + 2 * ellipsis_gap)
    compose(0x22EF, None, cdo,
            [(0, 0), (Cw + ellipsis_gap, 0), (2 * (Cw + ellipsis_gap), 0)],
            3 * Cw + 2 * ellipsis_gap)

    vstep = _pt_to_units(SOURCE_POLICY.dot_macros.vdots_step_pt, tfm_symbols)
    compose(0x22EE, None, per, [(0, 0), (0, vstep), (0, 2 * vstep)], P)

    diagonal_gap = _mu_to_units(SOURCE_POLICY.dot_macros.ddots_inner_mu)
    raises = tuple(_pt_to_units(x, tfm_symbols)
                   for x in SOURCE_POLICY.dot_macros.ddots_raises_pt)
    if len(raises) != 3:
        raise RuntimeError('local ddots policy must contain three raises')
    xs = [0, P + diagonal_gap, 2 * (P + diagonal_gap)]
    dadv = 3 * P + 2 * diagonal_gap
    compose(0x22F1, None, per, list(zip(xs, raises)), dadv)
    compose(0x22F0, None, per, list(zip(xs, reversed(raises))), dadv)

    # Center standalone dot glyphs on the local math axis.
    axis = _axis_height()
    for u in (0x22EE, 0x22F1, 0x22F0):
        if u not in uni_owner:
            continue
        g = out[uni_owner[u]]
        bb = g.boundingBox()
        g.transform(psMat.translate(0, axis - (bb[1] + bb[3]) / 2))
# Compose Word-compatible primes after importing optical script forms.


# Horizontal arrow assemblies use internal parts with trimmed connector bearings.
# Public outlines and advances remain unchanged.
ARROW_CONNECTOR = 200


def _trim_hconnector(src, suffix, connect_left=False, connect_right=False):
    """Create an unencoded assembly-only copy with connector sidebearings removed."""
    bits = ('L' if connect_left else '') + ('R' if connect_right else '')
    nm = f'{src}.hconn{bits}.{suffix}'
    if nm in out:
        return nm
    out.createChar(-1, nm)
    g = out[nm]
    g.addReference(src)
    g.unlinkRef()
    bb = g.boundingBox()
    xmin, _, xmax, _ = bb
    oldw = out[src].width
    if connect_left:
        g.transform(psMat.translate(-xmin, 0))
        oldw -= xmin
        xmax -= xmin
        xmin = 0
    if connect_right:
        # The right connector ends at actual ink, not at the source advance edge.
        g.width = round(xmax)
    else:
        g.width = round(oldw)
    if connect_left and connect_right:
        bb = g.boundingBox()
        if bb[0] != 0:
            g.transform(psMat.translate(-bb[0], 0))
            bb = g.boundingBox()
        g.width = max(1, round(bb[2]))
    return nm


def _resolve_harrow_ref(ref):
    if ref == 'Relbar':
        return imported.get(('syt', 0x48))
    if isinstance(ref, int):
        return uni_owner.get(ref)
    return None


def _arrow_component(src, idx, count, extender, suffix):
    left = idx > 0
    right = idx < count - 1
    gn = _trim_hconnector(src, suffix, left, right)
    if extender:
        # Both edges are straight connector material after trimming.
        conn = min(ARROW_CONNECTOR, max(100, out[gn].width // 3))
        return gn, 1, conn, conn, out[gn].width
    conn = min(ARROW_CONNECTOR, max(100, out[gn].width // 3))
    return gn, 0, (conn if left else 0), (conn if right else 0), out[gn].width


def _resolve_arrow_parts(part_spec, suffix):
    raw = []
    for kind, ref in part_spec:
        gn = _resolve_harrow_ref(ref)
        if gn is None:
            return None
        raw.append((gn, kind == 'E'))
    return [_arrow_component(gn, i, len(raw), ext, suffix)
            for i, (gn, ext) in enumerate(raw)]


def harrow_assembly(base_uni, part_spec):
    if base_uni not in uni_owner:
        return
    tups = _resolve_arrow_parts(part_spec, f'U{base_uni:04X}')
    if tups:
        out[uni_owner[base_uni]].horizontalComponents = tuple(tups)


# Arrow fills use fixed ends and an extender from the MTPro2 outlines.
_ARROW_SPECS = {
    0x2190: [('G', 0x2190), ('E', 0x2212), ('G', 0x2212)],
    0x2192: [('G', 0x2212), ('E', 0x2212), ('G', 0x2192)],
    0x2194: [('G', 0x2190), ('E', 0x2212), ('G', 0x2192)],
    0x21D0: [('G', 0x21D0), ('E', 'Relbar'), ('G', 'Relbar')],
    0x21D2: [('G', 'Relbar'), ('E', 'Relbar'), ('G', 0x21D2)],
    0x21D4: [('G', 0x21D0), ('E', 'Relbar'), ('G', 0x21D2)],
}
for _u, _spec in _ARROW_SPECS.items():
    harrow_assembly(_u, _spec)

# Mapsto uses dedicated short/long source glyphs, not an arbitrary-width assembly.
if 0x20D7 in uni_owner and 0x2192 in uni_owner and 0x2212 in uni_owner:
    vb = out[uni_owner[0x20D7]].boundingBox()
    ab = out[uni_owner[0x2192]].boundingBox()
    dy = round((vb[1] + vb[3]) / 2 - (ab[1] + ab[3]) / 2) + 25

    def accent_copy(src, suffix):
        nm = f'{src}.{suffix}'
        if nm in out:
            return nm
        out.createChar(-1, nm)
        g = out[nm]
        g.addReference(src, psMat.translate(0, dy))
        g.width = out[src].width
        g.unlinkRef()
        return nm

    if 0x20D6 not in uni_owner:
        src = uni_owner[0x20D7]
        nm = uname(0x20D6)
        out.createChar(0x20D6, nm)
        g = out[nm]
        g.addReference(src)
        g.unlinkRef()
        g.transform(psMat.scale(-1, 1))
        bb = g.boundingBox()
        g.transform(psMat.translate(vb[0] - bb[0], 0))
        g.width = 0
        uni_owner[0x20D6] = nm
        accent_glyphs.add(nm)

    shaft_src = uni_owner[0x2212]
    shaft = _trim_hconnector(shaft_src, 'vector.ex', True, True)
    shaft_acc = accent_copy(shaft, 'acc')
    shaft_conn = min(ARROW_CONNECTOR, max(100, out[shaft].width // 3))

    # Keep public U+20D7 fixed; private U+E287 carries the accent-height assembly.
    # Standard commands are not remapped to the private adapter.
    _widevec_cp = 0xE287
    _widevec_name = 'widevector.compat'
    if _widevec_name not in out:
        out.createChar(_widevec_cp, _widevec_name)
        _wg = out[_widevec_name]
        _wg.addReference(uni_owner[0x20D7])
        _wg.width = out[uni_owner[0x20D7]].width
        _wg.unlinkRef()
    uni_owner[_widevec_cp] = _widevec_name
    accent_glyphs.add(_widevec_name)

    # The right vector starts with its endpoint; shaft_acc supplies extra width.
    rend = accent_copy(uni_owner[0x2192], 'vector.end.acc')
    rconn = min(ARROW_CONNECTOR, max(100, out[rend].width // 3))
    out[_widevec_name].horizontalComponents = (
        (shaft_acc, 1, shaft_conn, shaft_conn, out[shaft_acc].width),
        (rend, 0, rconn, 0, out[rend].width),
    )

    # Left vector: same minimum width, mirrored assembly order.
    lend = accent_copy(uni_owner[0x2190], 'vector.end.acc')
    lconn = min(ARROW_CONNECTOR, max(100, out[lend].width // 3))
    out[uni_owner[0x20D6]].horizontalComponents = (
        (lend, 0, 0, lconn, out[lend].width),
        (shaft_acc, 1, shaft_conn, shaft_conn, out[shaft_acc].width),
    )


def stroke_band(gname, at_right=True):
    """Estimate the connector stroke band from outline points."""
    g = out[gname]
    xmin, ymin, xmax, ymax = g.boundingBox()
    edge = xmax if at_right else xmin
    ys = [pt.y for contour in g.foreground for pt in contour if abs(pt.x - edge) < 12]
    return (min(ys), max(ys)) if ys else (ymin, ymax)


def make_rule(name, y0, y1):
    out.createChar(-1, name)
    g = out[name]
    pen = g.glyphPen()
    w = 200
    pen.moveTo((0, y0))
    pen.lineTo((0, y1))
    pen.lineTo((w, y1))
    pen.lineTo((w, y0))
    pen.closePath()
    pen = None
    g.width = w
    return name


if 'exa' in fonts:
    _, exatfm, _ = fonts['exa']
    bld, brd, blu, bru = (piece(130), piece(131), piece(132), piece(133))
    if all([bld, brd, blu, bru]):
        # Standard braces use mt2exa corners and rules, separate from overcbrace designs.
        # Read the rule band from the local braceld TFM height.
        brace_rule_h = round(exatfm.chars[130]['ht'] * 1000)
        ext = make_rule('brace.hext', 0, brace_rule_h)

        def merge_hparts(left, right, name):
            if name in out:
                return name
            out.createChar(-1, name)
            g = out[name]
            wl = out[left].width
            g.addReference(left)
            g.addReference(right, psMat.translate(wl, 0))
            g.width = wl + out[right].width
            g.unlinkRef()
            return name

        # Merge cusp halves while preserving their source outlines.
        over_center = merge_hparts(bru, blu, 'brace.over.center')
        under_center = merge_hparts(brd, bld, 'brace.under.center')

        def shifted_copy(src, name, dy):
            if name in out:
                return name
            out.createChar(-1, name)
            g = out[name]
            g.addReference(src, psMat.translate(0, dy))
            g.width = out[src].width
            g.unlinkRef()
            return name

        # Set the top-accent origin using OpenType/Word conversion policy.
        _OVERBRACE_TARGET_YMIN = 539  # OpenType/Word migration policy
        over_ymin = min(out[q].boundingBox()[1] for q in (bld, ext, over_center, brd))
        over_dy = round(_OVERBRACE_TARGET_YMIN - over_ymin)
        over_left = shifted_copy(bld, 'brace.over.left', over_dy)
        over_ext = shifted_copy(ext, 'brace.over.ext', over_dy)
        over_center_shift = shifted_copy(over_center, 'brace.over.center.shift', over_dy)
        over_right = shifted_copy(brd, 'brace.over.right', over_dy)

        # Cap curved-part connectors at the local straight rule band minus tolerance.
        # Extenders expose their full rule width.
        brace_fixed_connector = max(
            0, brace_rule_h - CONNECTOR_PROFILE_TOLERANCE)
        for q in (bld, brd, blu, bru, over_left, over_center_shift,
                  over_right, over_center, under_center):
            connector_limits[q] = brace_fixed_connector
        connector_limits[ext] = out[ext].width
        connector_limits[over_ext] = out[over_ext].width
        brace_extenders = {ext, over_ext}

        for u, parts in [
                (0x23DE, [over_left, over_ext, over_center_shift, over_ext, over_right]),
                (0x23DF, [blu, ext, under_center, ext, bru])]:
            gn = uname(u)
            if gn not in out:
                out.createChar(u, gn)
            g = out[gn]
            # Build a small fallback; the assembly handles arbitrary widths.
            fixed = [q for q in parts if q != ext]
            x = 0
            for q in fixed:
                g.addReference(q, psMat.translate(x, 0))
                x += out[q].width
            g.width = x
            uni_owner[u] = gn
            horiz_variants[gn] = [gn]
            vert_assembly[('H', gn)] = [
                (q, 1 if q in brace_extenders else 0) for q in parts]

# TopAccent uses local family skewchar declarations; None means no skewchar.
SKEW = SOURCE_SKEW

topaccent = {}
for tag in tuple(SOURCE_SKEW):
    if tag not in fonts:
        continue
    _, tfm, _ = fonts[tag]
    sk = SKEW[tag]
    for (tg, slot), gname in list(imported.items()):
        if tg != tag or slot not in tfm.chars:
            continue
        w = tfm.chars[slot]['wd']
        ic = tfm.chars[slot].get('ic') or 0.0
        kern = tfm.kerns.get((slot, sk), 0.0) if sk is not None else 0.0
        # TeX centers over the accentee width plus CHARIC, then adds skew kern.
        topaccent[gname] = round(((w + ic) / 2 + kern) * 1000)
# Combining accents attach at the ink center.
for gname in accent_glyphs:
    topaccent[gname] = ACC_CENTER
# Other glyphs attach at the advance center.
for gname in list(imported.values()):
    if gname not in topaccent:
        g = out[gname]
        topaccent[gname] = g.width // 2

# MATH constants.
sy_fd = fonts['syt'][1].fontdimen
ex_fd = fonts['exa'][1].fontdimen
# Derive the display threshold from the local text/display summation sizes.
_op_text = fonts['exa'][1].chars.get(0x50)
_op_display = fonts['exa'][1].chars.get(0x58)
if not _op_text or not _op_display:
    raise SystemExit('local extension TFM lacks the summation size pair required for MATH policy')
_op_text_size = round((_op_text['ht'] + _op_text['dp']) * out.em)
_op_display_size = round((_op_display['ht'] + _op_display['dp']) * out.em)
_display_operator_min_height = (_op_text_size + _op_display_size) // 2

C = math_constants.compute(
    sy_fd, ex_fd,
    script_ratio=SCRIPT_RATIO,
    scriptscript_ratio=SCRIPTSCRIPT_RATIO,
    display_operator_min_height=_display_operator_min_height,
    quad=out.em,
)
ALL_MATH_SCALARS = dict(C)
MINOVL = C.pop('MinConnectorOverlap')

FF_NAMES = {'FractionNumDisplayStyleGapMin': 'FractionNumeratorDisplayStyleGapMin',
            'FractionDenomDisplayStyleGapMin': 'FractionDenominatorDisplayStyleGapMin'}
for k, v in C.items():
    try:
        setattr(out.math, FF_NAMES.get(k, k), int(v))
    except Exception as exc:
        print('math const fail', k, exc)
out.math.MinConnectorOverlap = MINOVL

# Per-glyph MATH data.
for gname, ta in topaccent.items():
    try:
        out[gname].topaccent = ta
    except Exception:
        pass


def glyph_size(gname):
    bb = out[gname].boundingBox()
    return bb[3] - bb[1]


for base, var in vert_variants.items():
    var2 = sorted(dict.fromkeys(var), key=glyph_size)
    if len(var2) > 1 or base in vert_assembly:
        out[base].verticalVariants = ' '.join(var2)
for base, var in horiz_variants.items():
    var2 = sorted(dict.fromkeys(var), key=lambda g: out[g].width)
    if len(var2) > 1:
        out[base].horizontalVariants = ' '.join(var2)


# Measure stable connector runs from flattened outline cross-sections.
# TFM recipes provide no overlap lengths.
def _flatten(gname, steps=8):
    polys = []
    for contour in out[gname].foreground:
        pts = []
        seq = [(p.x, p.y, p.on_curve) for p in contour]
        if not seq:
            continue
        seq.append(seq[0])
        i = 0
        while i < len(seq) - 1:
            x0, y0, on0 = seq[i]
            x1, y1, on1 = seq[i + 1]
            if on1:
                pts.append((x1, y1))
                i += 1
            else:
                ctrl = []
                j = i + 1
                while j < len(seq) and not seq[j][2]:
                    ctrl.append(seq[j][:2])
                    j += 1
                if j >= len(seq):
                    break
                x3, y3, _ = seq[j]
                for k in range(1, steps + 1):
                    t = k / steps
                    if len(ctrl) == 1:
                        cx, cy = ctrl[0]
                        xx = (1 - t)**2 * x0 + 2 * (1 - t) * t * cx + t * t * x3
                        yy = (1 - t)**2 * y0 + 2 * (1 - t) * t * cy + t * t * y3
                    else:
                        c1, c2 = ctrl[0], ctrl[-1]
                        xx = ((1 - t)**3 * x0 + 3 * (1 - t)**2 * t * \
                              c1[0] + 3 * (1 - t) * t * t * c2[0] + t**3 * x3)
                        yy = ((1 - t)**3 * y0 + 3 * (1 - t)**2 * t * \
                              c1[1] + 3 * (1 - t) * t * t * c2[1] + t**3 * y3)
                    pts.append((xx, yy))
                i = j
        if pts:
            polys.append(pts)
    return polys


def _profile(gname, vertical, n=64):
    polys = _flatten(gname)
    if not polys:
        return []
    bb = out[gname].boundingBox()
    lo, hi = (bb[1], bb[3]) if vertical else (bb[0], bb[2])
    if hi - lo <= 0:
        return []
    res = []
    for k in range(n):
        v = lo + (hi - lo) * (k + 0.5) / n
        xs = []
        for pts in polys:
            m = len(pts)
            for a in range(m):
                p, q = pts[a], pts[(a + 1) % m]
                pa, qa = (p[1], q[1]) if vertical else (p[0], q[0])
                if (pa <= v < qa) or (qa <= v < pa):
                    t = (v - pa) / (qa - pa)
                    pb, qb = (p[0], q[0]) if vertical else (p[1], q[1])
                    xs.append(pb + (qb - pb) * t)
        res.append((min(xs), max(xs)) if len(xs) >= 2 else None)
    return res


def connector_run(gname, vertical, at_end,
                  tol=CONNECTOR_PROFILE_TOLERANCE):
    prof = _profile(gname, vertical)
    if not prof:
        return 0
    bb = out[gname].boundingBox()
    span = (bb[3] - bb[1]) if vertical else (bb[2] - bb[0])
    step = span / len(prof)
    seq = list(reversed(prof)) if at_end else list(prof)
    ref = seq[0]
    if ref is None:
        return 0
    run = 0
    for cur in seq:
        if cur is None or abs(cur[0] - ref[0]) > tol or abs(cur[1] - ref[1]) > tol:
            break
        run += 1
    length = max(0, int(run * step))
    limit = connector_limits.get(gname)
    return min(length, limit) if limit is not None else length


def _norm_vpart(p):
    """Align vertical assembly parts to their ink bottom."""
    nm = f'{p}.vn'
    if nm not in out:
        bb = out[p].boundingBox()
        out.createChar(-1, nm)
        g = out[nm]
        g.addReference(p, psMat.translate(0, -bb[1]))
        g.width = out[p].width
        g.unlinkRef()
    return nm


def part_tuple(gname, is_ext, vertical=True):
    g = out[gname]
    if vertical:
        bb = g.boundingBox()
        full = round(bb[3] - bb[1])
    else:
        full = g.width
    start = connector_run(gname, vertical, False)
    end = connector_run(gname, vertical, True)
    return (gname, is_ext, start, end, full)


_runs = []
for _b, _p in vert_assembly.items():
    n = len(_p)
    vert = not isinstance(_b, tuple)
    for i, (p, e) in enumerate(_p):
        if i:
            _runs.append(connector_run(p, vert, False))
        if i < n - 1:
            _runs.append(connector_run(p, vert, True))
_ov = int(getattr(out.math, 'MinConnectorOverlap', 100) or 100)
if _runs and min(_runs) < _ov:
    out.math.MinConnectorOverlap = max(0, int(min(_runs)))
    print('MinConnectorOverlap ->', out.math.MinConnectorOverlap)

for base, parts in vert_assembly.items():
    if isinstance(base, tuple):  # Horizontal assemblies.
        _, gname = base
        # Only joining edges have connectors; outside fixed edges must have zero length.
        tups = []
        n = len(parts)
        for i, (p, e) in enumerate(parts):
            q = list(part_tuple(p, e, vertical=False))
            if i == 0:
                q[2] = 0              # StartConnectorLength
            if i == n - 1:
                q[3] = 0              # EndConnectorLength
            tups.append(tuple(q))
        out[gname].horizontalComponents = tuple(tups)
    else:
        # Cap end connectors at half the adjacent extender length.
        parts = [(_norm_vpart(p), e) for (p, e) in parts]
        tups = []
        n = len(parts)
        for i, (p, e) in enumerate(parts):
            bb = out[p].boundingBox()
            full = round(bb[3] - bb[1])
            start = 0 if i == 0 else connector_run(p, True, False)
            end = 0 if i == n - 1 else connector_run(p, True, True)
            tups.append((p, e, start, end, full))
        out[base].verticalComponents = tuple(tups)

# Extended shapes include larger variants, assembly parts, and display operators.
extended = set()
for base, var in vert_variants.items():
    extended.update(var[1:])
for base, parts in vert_assembly.items():
    if not isinstance(base, tuple):
        extended.update(p for (p, _) in parts)
# Mark the base integral family ExtendedShape for OpenType script/limit placement.
for _u in range(0x222B, 0x2234):
    if _u in uni_owner:
        extended.add(uni_owner[_u])
for gname in extended:
    try:
        out[gname].isExtendedShape = True
    except Exception:
        pass

# Optical script-size substitutions.
ssty_map = {}


def add_ssty(coretag, stag, sstag, table):
    if stag not in fonts:
        return
    for slot, (u, name) in table.items():
        key = (coretag, slot)
        if key not in imported:
            continue
        base = imported[key]
        alts = []
        for lvl, t in ((1, stag), (2, sstag)):
            if t not in fonts:
                continue
            g = import_glyph(t, slot, name=f'{base}.ssty{lvl}')
            if g:
                alts.append(g)
        if alts:
            ssty_map[base] = alts


add_ssty('mit', 'mit_s', 'mit_ss', U.MIT)
add_ssty('syt', 'syt_s', 'syt_ss', U.SYT)
add_ssty('ams', 'ams_s', 'ams_ss', U.AMSA)
add_ssty('bb', 'bb_s', 'bb_ss', U.alpha_map('bb'))
# Import option-family script sources so cv03..cv07 preserve optical designs.
for _core, _s, _ss in (
        ('bbd', 'bbd_s', 'bbd_ss'), ('bbi', 'bbi_s', 'bbi_ss'),
        ('hrb', 'hrb_s', 'hrb_ss'), ('hrbd', 'hrbd_s', 'hrbd_ss'),
        ('hbi', 'hbi_s', 'hbi_ss')):
    if _core not in fonts:
        continue
    for _slot, (_u, _nm) in U.alpha_map('bb').items():
        _base = import_glyph(_core, _slot, name=f'{_nm}.{_core}')
        if not _base:
            continue
        _alts = []
        for _lvl, _tag in ((1, _s), (2, _ss)):
            if _tag not in fonts:
                continue
            _g = import_glyph(_tag, _slot, name=f'{_base}.ssty{_lvl}')
            if _g:
                _alts.append(_g)
        if _alts:
            ssty_map[_base] = _alts
add_ssty('script', 'script_s', 'script_ss', U.alpha_map('script'))
add_ssty('frak', 'frak_s', 'frak_ss', U.alpha_map('frak'))
# Donor mathematical bold has no mt2mb* script substitutions; mbf is separate.
add_ssty('curly', 'curly_s', 'curly_ss', U.alpha_map('curly'))
add_ssty('bmit', 'bmit_s', 'bmit_ss', U.MIT)
add_ssty('bsyt', 'bsyt_s', 'bsyt_ss', U.SYT)

# Normalize script accents and use their own source-family skew kern.
for tag in ('syt_s', 'syt_ss'):
    for slot in ACCENT_SLOTS:
        key = (tag, slot)
        if key not in imported:
            continue
        g = out[imported[key]]
        bb = g.boundingBox()
        g.transform(psMat.translate(ACC_CENTER - (bb[0] + bb[2]) / 2, 0))
        g.width = 0
        g.topaccent = ACC_CENTER
        accent_glyphs.add(g.glyphname)
for tag in ('mit_s', 'mit_ss', 'syt_s', 'syt_ss', 'bmit_s', 'bmit_ss', 'bsyt_s', 'bsyt_ss',
            'bb_s', 'bb_ss', 'bbi_s', 'bbi_ss', 'bbd_s', 'bbd_ss',
            'hrb_s', 'hrb_ss', 'hrbd_s', 'hrbd_ss', 'hbi_s', 'hbi_ss',
            'script_s', 'script_ss', 'frak_s', 'frak_ss',
            'curly_s', 'curly_ss', 'bold_s', 'bold_ss'):
    if tag not in fonts:
        continue
    _, tfm, _ = fonts[tag]
    sk = SKEW[tag]
    for (tg, slot), gname in imported.items():
        if tg != tag or slot not in tfm.chars or gname in accent_glyphs:
            continue
        kern = tfm.kerns.get((slot, sk), 0.0) if sk is not None else 0.0
        try:
            w = tfm.chars[slot]['wd']
            ic = tfm.chars[slot].get('ic') or 0.0
            out[gname].topaccent = round(((w + ic) / 2 + kern) * 1000)
        except Exception:
            pass

# Word-compatible primes share local geometry, script ratios, and collision padding.
PRIME_SHIFT = None
PRIME_PADDING_EVIDENCE = None
if 0x2032 in uni_owner:
    xh_u = round(fonts['syt'][1].fontdimen[5] * 1000)
    SUP_SHIFT = round(fonts['syt'][1].fontdimen[14] * out.em)
    try:
        PRIME_PADDING_EVIDENCE = dict(_SOURCE_SNAPSHOT['geometry']['prime_padding'])
        PRIME_SHIFT = int(PRIME_PADDING_EVIDENCE['padding'])
    except Exception as exc:
        raise RuntimeError('local prime-padding source geometry is missing') from exc
    _script_scale = float(SCRIPT_RATIO)
    _scriptscript_scale = float(SCRIPTSCRIPT_RATIO)
    _targets = [uni_owner[0x2032]]
    if ('ams', 0x38) in imported:
        _targets.append(imported[('ams', 0x38)])
    for _base in _targets:
        _s1, _s2 = _base + '.ssty1', _base + '.ssty2'
        if _s1 not in out:
            # script design absent: scale and raise the base glyph.
            _g = out[_base]
            _g.transform(psMat.scale(_script_scale))
            _bb = _g.boundingBox()
            _g.transform(psMat.translate(PRIME_SHIFT, xh_u - _bb[1]))
            _g.width = round(_g.width)
            continue
        # base := local package script-size design scaled by the local script ratio
        out.selection.select(_s1)
        out.copy()
        out.selection.select(_base)
        out.paste()
        _g = out[_base]
        _g.transform(psMat.scale(_script_scale))
        _bb = _g.boundingBox()
        _g.transform(psMat.translate(PRIME_SHIFT, xh_u - _bb[1]))
        _g.width = round(_g.width)
        _base_y0 = out[_base].boundingBox()[1]
        # Reposition the first script form.
        _g1 = out[_s1]
        _b1 = _g1.boundingBox()
        _g1.transform(psMat.translate(0, (_base_y0 - SUP_SHIFT) / _script_scale - _b1[1]))
        # ssty2 := ssty1 rescaled by the local script/scriptscript ratio.
        if _s2 in out:
            out.selection.select(_s1)
            out.copy()
            out.selection.select(_s2)
            out.paste()
            _g2 = out[_s2]
            _g2.transform(psMat.scale(_script_scale / _scriptscript_scale))
            _b2 = _g2.boundingBox()
            _g2.transform(psMat.translate(
                0, (_base_y0 - SUP_SHIFT) / _scriptscript_scale - _b2[1]))
            _g2.width = round(_g2.width)
    # Compose repeated primes from the base.
    pr = uni_owner[0x2032]
    PW = out[pr].width
    if pr + '.ssty1' in out:
        # Use the scaled local script-design advance between primes.
        st = round(out[pr + '.ssty1'].width * _script_scale)
    else:
        st = round(PW - PRIME_SHIFT)
    compose(0x2033, None, pr, [(0, 0), (st, 0)], PW + st)
    compose(0x2034, None, pr, [(0, 0), (st, 0), (2 * st, 0)], PW + 2 * st)
    compose(0x2057, None, pr, [(0, 0), (st, 0), (2 * st, 0), (3 * st, 0)], PW + 3 * st)
    # Compose repeated script primes from their matching optical forms.
    for _lvl in (1, 2):
        _src = f'{pr}.ssty{_lvl}'
        if _src not in out:
            continue
        _stp = out[_src].width
        for _u, _n in ((0x2033, 2), (0x2034, 3), (0x2057, 4)):
            _base = uni_owner.get(_u)
            if not _base:
                continue
            _gn = f'{_base}.ssty{_lvl}'
            if _gn in out:
                continue
            out.createChar(-1, _gn)
            _gl = out[_gn]
            for _i in range(_n):
                _gl.addReference(_src, psMat.translate(_i * _stp, 0))
            _gl.width = _n * _stp
            ssty_map.setdefault(_base, []).append(_gn)
    # Ligate raw repeated primes to avoid repeating collision padding.
    # Pair adjustment covers shapers that skip the ligature; TeX scripts bypass it.
    out.addLookup('primelig', 'gsub_ligature', (),
                  (('ccmp', (('DFLT', ('dflt',)), ('latn', ('dflt',)),
                             ('math', ('dflt',)))),))
    out.addLookupSubtable('primelig', 'primelig-1')
    for _u, _n in ((0x2057, 4), (0x2034, 3), (0x2033, 2)):  # Match longer sequences first.
        _lig = uni_owner.get(_u)
        if _lig:
            out[_lig].addPosSub('primelig-1', tuple([pr] * _n))
    out.addLookup('primekern', 'gpos_pair', (),
                  (('kern', (('DFLT', ('dflt',)), ('latn', ('dflt',)),
                             ('math', ('dflt',)))),))
    out.addLookupSubtable('primekern', 'primekern-1')
    out[pr].addPosSub('primekern-1', pr, 0, 0, -PRIME_SHIFT, 0, 0, 0, 0, 0)
    print('prime family: base=%d..%d ssty1@%d ssty2@%d st=%d'
          % (out[pr].boundingBox()[1], out[pr].boundingBox()[3],
             out[pr + '.ssty1'].boundingBox()[1] if pr + '.ssty1' in out else -1,
             out[pr + '.ssty2'].boundingBox()[1] if pr + '.ssty2' in out else -1,
             st))

if ssty_map:
    out.addLookup('ssty', 'gsub_alternate', (),
                  (('ssty', (('DFLT', ('dflt',)), ('latn', ('dflt',)), ('math', ('dflt',)))),))
    out.addLookupSubtable('ssty', 'ssty-1')
    for base, alts in ssty_map.items():
        try:
            out[base].addPosSub('ssty-1', tuple(alts))
        except Exception:
            pass

# Dotless substitutions for italic i/j and upright i.
dtls_pairs = []
if 0x1D456 in uni_owner and 0x1D6A4 in uni_owner:
    dtls_pairs.append((uni_owner[0x1D456], uni_owner[0x1D6A4]))
if 0x1D457 in uni_owner and 0x1D6A5 in uni_owner:
    dtls_pairs.append((uni_owner[0x1D457], uni_owner[0x1D6A5]))
if 0x0069 in uni_owner and upright_dotless:
    dtls_pairs.append((uni_owner[0x0069], upright_dotless))
if bold_it_latin.get('i') and bold_dotless_i:
    dtls_pairs.append((bold_it_latin['i'], bold_dotless_i))
if bold_it_latin.get('j') and bold_dotless_j:
    dtls_pairs.append((bold_it_latin['j'], bold_dotless_j))
if dtls_pairs:
    out.addLookup('dtls', 'gsub_single', (),
                  (('dtls', (('DFLT', ('dflt',)), ('latn', ('dflt',)), ('math', ('dflt',)))),))
    out.addLookupSubtable('dtls', 'dtls-1')
    for base, sub in dtls_pairs:
        out[base].addPosSub('dtls-1', sub)

# Calligraphic salt maps curly to script.
curly_pairs = []
for slot, (u, name) in U.alpha_map('curly').items():
    key = ('curly', slot)
    if key in imported and ('script', slot) in imported:
        curly_pairs.append((imported[('script', slot)], imported[key]))
# Keep varnothing in cv02 so calligraphic salt cannot change it.
if curly_pairs:
    out.addLookup('salt', 'gsub_alternate', (),
                  (('salt', (('DFLT', ('dflt',)), ('latn', ('dflt',)), ('math', ('dflt',)))),))
    out.addLookupSubtable('salt', 'salt-1')
    for base, alt in curly_pairs:
        try:
            out[base].addPosSub('salt-1', (alt,))
        except Exception:
            pass

# Expose alternate codepoints for the same glyph.
for base_u, extra_u in [(0x007C, 0x2223), (0x2016, 0x2225), (0x1D715, 0x2202)]:
    if base_u in uni_owner and extra_u not in uni_owner:
        g = out[uni_owner[base_u]]
        g.altuni = ((g.altuni or ()) + ((extra_u, -1, 0),))
        uni_owner[extra_u] = g.glyphname

# Build cumulative spacing after all alphabet imports: hmtx keeps CHARWD,
# MATH keeps CHARIC, and GPOS adds ordinary TFM kern plus CHARIC(left).
# Exclude family skewchar-right pairs from ordinary kerning.

# cv01: swash z.
zalt_pairs = []
if ('mit', 180) in imported and 0x1D467 in uni_owner:
    zalt_pairs.append((uni_owner[0x1D467], imported[('mit', 180)]))
    for lvl, t in ((1, 'mit_s'), (2, 'mit_ss')):
        if t in fonts and 180 in fonts[t][1].chars:
            alt = import_glyph(t, 180, name=f'z.alt.ssty{lvl}')
            basek = (t, 0x7A)
            if alt and basek in imported:
                zalt_pairs.append((imported[basek], alt))
# cv03..cv07: blackboard and holey alphabet options.
for cvn, tag in (('cv03', 'bbd'), ('cv04', 'bbi'), ('cv05', 'hrb'),
                 ('cv06', 'hrbd'), ('cv07', 'hbi')):
    if tag not in fonts:
        continue
    pairs = []
    for slot, (u, nm) in U.alpha_map('bb').items():
        alt = import_glyph(tag, slot, name=f'{nm}.{tag}')
        if alt and u in uni_owner:
            base = uni_owner[u]
            pairs.append((base, alt))
            # Add script-form pairs for either shaping order: ssty then cv, or cv then ssty.
            for lvl in (1, 2):
                bb, aa = f'{base}.ssty{lvl}', f'{alt}.ssty{lvl}'
                if bb in out and aa in out:
                    pairs.append((bb, aa))
    if not pairs:
        continue
    out.addLookup(cvn, 'gsub_single', (),
                  ((cvn, (('DFLT', ('dflt',)), ('latn', ('dflt',)), ('math', ('dflt',)))),))
    out.addLookupSubtable(cvn, cvn + '-1')
    for base, alt in pairs:
        try:
            out[base].addPosSub(cvn + '-1', alt)
        except Exception:
            pass

# cv02: slashed-zero and circular empty-set forms.
if ('ams', 191) in imported and 0x2205 in uni_owner:
    out.addLookup('cv02', 'gsub_single', (),
                  (('cv02', (('DFLT', ('dflt',)), ('latn', ('dflt',)), ('math', ('dflt',)))),))
    out.addLookupSubtable('cv02', 'cv02-1')
    try:
        out[uni_owner[0x2205]].addPosSub('cv02-1', imported[('ams', 191)])
    except Exception:
        pass

if zalt_pairs:
    out.addLookup('cv01', 'gsub_single', (),
                  (('cv01', (('DFLT', ('dflt',)), ('latn', ('dflt',)), ('math', ('dflt',)))),))
    out.addLookupSubtable('cv01', 'cv01-1')
    for base, alt in zalt_pairs:
        try:
            out[base].addPosSub('cv01-1', alt)
        except Exception:
            pass


def with_ssty(pairs):
    """Extend substitution pairs with matching optical script forms."""
    res = []
    for b, a in pairs:
        if not b or not a:
            continue
        res.append((b, a))
        for lvl in (1, 2):
            bb, aa = f'{b}.ssty{lvl}', f'{a}.ssty{lvl}'
            if bb in out and aa in out:
                res.append((bb, aa))
    return res


def add_cv(tag, pairs):
    """Register a single-substitution character-variant feature."""
    pairs = [(b, a) for b, a in with_ssty(pairs) if b in out and a in out]
    if not pairs:
        return
    out.addLookup(tag, 'gsub_single', (),
                  ((tag, (('DFLT', ('dflt',)), ('latn', ('dflt',)),
                          ('math', ('dflt',)))),))
    out.addLookupSubtable(tag, tag + '-1')
    for base, alt in pairs:
        try:
            out[base].addPosSub(tag + '-1', alt)
        except Exception:
            pass
    print('%s: %d pairs' % (tag, len(pairs)))


# cv08: straight braces.
add_cv('cv08', [(uni_owner.get(0x007B), 'braceleft.straight'),
                (uni_owner.get(0x007D), 'braceright.straight')])

# cv09: AMS negated relations; defaults retain MTPro2 forms.
add_cv('cv09', [(uni_owner.get(u), imported.get(('ams', slot)))
                for u, slot in ((0x2241, 156), (0x2288, 170), (0x2289, 171))])

# cv10: variant subsetneq and supsetneq.
add_cv('cv10', [(uni_owner.get(u), imported.get(('ams', slot)))
                for u, slot in ((0x228A, 160), (0x228B, 161))])

# cv11: hbar and hslash.
add_cv('cv11', [(uni_owner.get(0x210F), imported.get(('syt', 175)))])

# cv12: slanted large operators.
add_cv('cv12', [(uni_owner.get(u), imported.get(('exa', slot)))
                for u, slot in ((0x2211, 160), (0x220F, 162), (0x2210, 164))])

# Provide Word/OMML spaces and invisible operators to prevent fallback.
BLANKS = {0x0020: 333, 0x00A0: 333, 0x2000: 500, 0x2001: 1000, 0x2002: 500,
          0x2003: 1000, 0x2004: 333, 0x2005: 250, 0x2006: 167, 0x2007: 500,
          0x2008: 250, 0x2009: 200, 0x200A: 100, 0x200B: 0, 0x202F: 200,
          0x205F: 222, 0x2061: 0, 0x2062: 0, 0x2063: 0, 0x2064: 0}
for u, w in BLANKS.items():
    if u in uni_owner:
        continue
    gn = 'space' if u == 0x0020 else uname(u)
    out.createChar(u, gn)
    out[gn].width = w
    uni_owner[u] = gn


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


# Allow text-only letterlike symbols, but reserve math-active primes.
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


# Limit donor additions to Latin/Common text; math ownership takes precedence.
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
for _kind in ('bb', 'script', 'frak', 'curly'):
    for _slot, (_u, _name) in U.alpha_map(_kind).items():
        if _u is not None:
            CANONICAL_FULL_ONLY_SOURCE_UNICODE.add(_u)

# Text-donor symbols used directly by Word math.
ROMAN_EXTRA = {'percent': 0x0025, 'ampersand': 0x0026, 'at': 0x0040,
               'underscore': 0x005F, 'asciitilde': 0x007E, 'numbersign': 0x0023,
               'dollar': 0x0024, 'degree': 0x00B0, 'fraction': 0x2044,
               'question': 0x003F, 'exclam': 0x0021}
if os.path.exists(ROMAN_REG):
    nf2 = fontforge.open(ROMAN_REG)
    _roman_extra_scale = float(out.em) / float(nf2.em)
    for src_name, u in ROMAN_EXTRA.items():
        if u in uni_owner or src_name not in nf2:
            continue
        if EDITION == 'lite' and u in CANONICAL_FULL_ONLY_SOURCE_UNICODE:
            continue
        nf2.selection.select(src_name)
        nf2.copy()
        gn = uname(u)
        out.createChar(u, gn)
        out.selection.select(gn)
        out.paste()
        if abs(_roman_extra_scale - 1.0) > 1e-12:
            out[gn].transform(psMat.scale(_roman_extra_scale))
        out[gn].width = round(nf2[src_name].width * _roman_extra_scale)
        uni_owner[u] = gn

    # Fill remaining text coverage without replacing existing math glyphs.
    todo = []
    for g in nf2.glyphs():
        u = g.unicode
        if u is None or u < 0x20 or u in uni_owner:
            continue
        if not _is_roman_text_extra(u):
            continue          # selectable donor must not add unrelated scripts
        if EDITION == 'lite' and u in CANONICAL_FULL_ONLY_SOURCE_UNICODE:
            continue          # Full-only MTPro2 semantic remains a hole in Lite
        if _is_math_range(u):
            continue  # Reserve math glyphs.
        if 0xE000 <= u <= 0xF8FF or u in (0xFEFF, 0xFFFD):
            continue  # Exclude private and special-use ranges.
        gn = uname(u)
        if gn in out:
            continue
        todo.append((g.glyphname, u, gn, g.width))
    for src_name, u, gn, w in todo:
        nf2.selection.select(src_name)
        nf2.unlinkReferences()  # Flatten references before copying outlines.
        nf2.selection.select(src_name)
        nf2.copy()
        out.createChar(u, gn)
        out.selection.select(gn)
        out.paste()
        if abs(_roman_extra_scale - 1.0) > 1e-12:
            out[gn].transform(psMat.scale(_roman_extra_scale))
        out[gn].width = round(w * _roman_extra_scale)
        uni_owner[u] = gn
    print('Roman donor: added %d chars' % len(todo))
    nf2.close()
# Compose proportion from two colons.
if 0x2237 not in uni_owner and 0x003A in uni_owner:
    c = uni_owner[0x003A]
    cw = out[c].width
    compose(0x2237, None, c, [(0, 0), (cw + 167, 0)], 2 * cw + 167)

# Expose private alternatives for Word, where cv/salt controls are unavailable.
PUA = 0xE000


def pua(gname):
    global PUA
    if gname not in out:
        return
    g = out[gname]
    if g.unicode == -1:
        g.unicode = PUA
    else:
        g.altuni = ((g.altuni or ()) + ((PUA, -1, 0),))
    PUA += 1


if ('mit', 180) in imported:
    pua(imported[('mit', 180)])                    # U+E000 z swash
if ('ams', 191) in imported:
    pua(imported[('ams', 191)])                    # U+E001 varnothing
PUA = 0xE010
for slot, (u, nm) in sorted(U.alpha_map('curly').items()):
    if ('curly', slot) in imported:
        pua(imported[('curly', slot)])             # U+E010.. curly
for base, tag in ((0xE100, 'bbd'), (0xE140, 'bbi'), (0xE180, 'hrb'),
                  (0xE1C0, 'hrbd'), (0xE200, 'hbi')):
    PUA = base
    for slot, (u, nm) in sorted(U.alpha_map('bb').items()):
        if (tag, slot) in imported:
            pua(imported[(tag, slot)])

# Keep private assignments fixed across editions; missing glyphs leave holes.
PUA_FIXED = {
    0xE23E: 'lhook',
    0xE23F: 'rhook',
    0xE240: 'varbeta.it',
    0xE241: 'vardelta.it',
    0xE242: 'upvardelta',
    0xE243: 'dbar.it',
    0xE244: 'updbar',
    0xE245: 'negationslash',
    0xE246: 'mapstochar',
    0xE247: 'tie.sy',
    0xE248: 'compose',
    0xE249: 'Relbar',
    0xE24A: 'wwbar',
    0xE24B: 'dotup.accent',
    0xE24C: 'ddotup.accent',
    0xE24D: 'smallint',
    0xE24E: 'wbar',
    0xE24F: 'what',
    0xE250: 'wtilde',
    0xE251: 'wcheck',
    0xE252: 'clubshaded',
    0xE253: 'spadeshaded',
    0xE254: 'dddotup.accent',
    0xE255: 'ddddotup.accent',
    0xE256: 'hslash',
    0xE257: 'simarrow',
    0xE258: 'varland',
    0xE259: 'contraction',
    0xE25A: 'circdashbullet',
    0xE25B: 'bulletdashcirc',
    0xE25C: 'braceleft.straight',
    0xE25D: 'braceright.straight',
    0xE25E: 'midshaft',
    0xE25F: 'rarrowhead',
    0xE260: 'larrowhead',
    0xE261: 'varpropto',
    0xE262: 'smallsmile',
    0xE263: 'smallfrown',
    0xE264: 'lvertneqq',
    0xE265: 'gvertneqq',
    0xE266: 'nleqslant',
    0xE267: 'ngeqslant',
    0xE268: 'npreceq',
    0xE269: 'nsucceq',
    0xE26A: 'nleqq',
    0xE26B: 'ngeqq',
    0xE26C: 'nsim.ams',
    0xE26D: 'varsubsetneq',
    0xE26E: 'varsupsetneq',
    0xE26F: 'nsubseteqq',
    0xE270: 'nsupseteqq',
    0xE271: 'varsubsetneqq',
    0xE272: 'varsupsetneqq',
    0xE273: 'nsubseteq.ams',
    0xE274: 'nsupseteq.ams',
    0xE275: 'nshortmid',
    0xE276: 'nshortparallel',
    0xE277: 'shortmid',
    0xE278: 'shortparallel',
    0xE279: 'thicksim',
    0xE27A: 'thickapprox',
    0xE27B: 'nsqsubset',
    0xE27C: 'nsqsupset',
    0xE27D: 'leadsto',
    0xE27E: 'undercurvearrowleft',
    0xE27F: 'undercurvearrowright',
    0xE280: 'capprod.big',
    0xE281: 'slsum',
    0xE282: 'slprod',
    0xE283: 'slcoprod',
    0xE284: 'varland.big',
    0xE285: 'ast.big',
    0xE286: 'wideoverbar.compat',
    0xE287: 'widevector.compat',
}
_pua_done = set()
_maxcp = 0xE23D
for _cp in sorted(PUA_FIXED):
    _maxcp = max(_maxcp, _cp)
    _nm = PUA_FIXED[_cp]
    if _nm in out and _nm not in _pua_done and out[_nm].unicode == _cp:
        _pua_done.add(_nm)
    elif _nm in out and _nm not in _pua_done and out[_nm].unicode == -1:
        out[_nm].unicode = _cp
        _pua_done.add(_nm)
    elif _nm in out and _nm not in _pua_done:
        out[_nm].altuni = ((out[_nm].altuni or ()) + ((_cp, -1, 0),))
        _pua_done.add(_nm)
PUA = _maxcp + 1
# Unencoded mapped glyphs are assigned deterministically after the fixed range,
# in source-table slot order.
for _tag, _table in (('mit', U.MIT), ('syt', U.SYT), ('ams', U.AMSA)):
    for _slot, _ent in sorted(_table.items()):
        _u, _nm = _ent[0], _ent[1]
        if _u is not None or not _nm:
            continue
        _g = imported.get((_tag, _slot))
        if _g and _g not in _pua_done and _g in out and out[_g].unicode == -1:
            pua(_g)
            _pua_done.add(_g)
for _slot in sorted(U.EXA_OPS):
    _u, _nm = U.EXA_OPS[_slot][0], U.EXA_OPS[_slot][1]
    if _u is not None or not _nm:
        continue
    _g = imported.get(('exa', _slot))
    if _g and _g not in _pua_done and _g in out and out[_g].unicode == -1:
        pua(_g)
        _pua_done.add(_g)
for _nm in ('braceleft.straight', 'braceright.straight'):
    if _nm in out and out[_nm].unicode == -1 and _nm not in _pua_done:
        pua(_nm)
        _pua_done.add(_nm)
print('PUA added: %d glyphs (U+E23E..U+%04X)' % (len(_pua_done), PUA - 1))

# PUA identities are part of the font contract; no TeX sidecar is generated.

# Metrics and output.
out.ascent, out.descent = 800, 200
# Use absolute FontForge metrics rather than offsets from the bounding box.
out.os2_typoascent_add = out.os2_typodescent_add = 0
out.hhea_ascent_add = out.hhea_descent_add = 0
out.os2_typoascent, out.os2_typodescent, out.os2_typolinegap = 806, -194, 200
out.hhea_ascent, out.hhea_descent, out.hhea_linegap = 806, -194, 200
out.os2_xheight = round(sy_fd[5] * 1000)
# Read cap height from the local math-italic TFM.
cap_h = (round(fonts['mit'][1].chars[0x41]['ht'] * out.em)
         if 0x41 in fonts['mit'][1].chars else None)
if cap_h:
    out.os2_capheight = cap_h
# Cover all outlines with Windows clipping bounds; USE_TYPO_METRICS controls spacing.
# Scan glyph bounds for compatibility across FontForge versions.
_ymin, _ymax = 0, 0
for _gl in out.glyphs():
    _bb = _gl.boundingBox()
    if _bb[1] == _bb[3] == 0 and _bb[0] == _bb[2] == 0:
        continue
    _ymin = min(_ymin, _bb[1])
    _ymax = max(_ymax, _bb[3])
out.os2_winascent = max(806, int(math.ceil(_ymax)))
out.os2_winascent_add = 0
out.os2_windescent = max(194, int(math.ceil(-_ymin)))
out.os2_windescent_add = 0
out.os2_use_typo_metrics = 1
print('usWinAscent=%d usWinDescent=%d (BBox %d..%d)'
      % (out.os2_winascent, out.os2_windescent, _ymin, _ymax))
out.os2_vendor = 'MTP2'
# Preserve the source trademark notice.
try:
    out.appendSFNTName('English (US)', 'Trademark',
                       'MathTime is a trademark of Publish or Perish, Inc.')
except Exception:
    pass
try:
    out.appendSFNTName('English (US)', 'Preferred Family', FAMILY)
    out.appendSFNTName('English (US)', 'Preferred Styles', STYLE)
except Exception:
    pass
out.os2_stylemap = 0x40
# Apply the selected embedding flag; license terms remain separate.
out.os2_fstype = FSTYPE
# finalize.py sets the Windows-compatible technical font version.

# Word math-italic nabla aliases the source nabla glyph.
if 0x2207 in uni_owner:
    _ng = out[uni_owner[0x2207]]
    _nabla_aliases = [0x1D6FB]
    for _u in _nabla_aliases:
        if _u not in uni_owner:
            _ng.altuni = (_ng.altuni or ()) + ((_u, -1, 0),)
            uni_owner[_u] = _ng.glyphname
            print('nabla alias U+%05X -> %s' % (_u, _ng.glyphname))

# Alias the fixed bar to U+0305 for Word.
if 0x0304 in uni_owner and 0x0305 not in uni_owner:
    _g = out[uni_owner[0x0304]]
    _g.altuni = (_g.altuni or ()) + ((0x0305, -1, 0),)
    uni_owner[0x0305] = uni_owner[0x0304]
    print('U+0305 (COMBINING OVERLINE) = %s' % uni_owner[0x0304])


# Finalize TopAccent and ordinary spacing after all source and alternate imports.
# Source roles, not nonzero IC alone, determine ordinary-character membership.
def _source_is_ordinary_left(tag, slot):
    return source_policy.is_ordinary_left(tag, slot)


if 'wideoverbar.compat' in out:
    accent_glyphs.add('wideoverbar.compat')
if 'widevector.compat' in out:
    accent_glyphs.add('widevector.compat')

# Finite source accents retain positive advance and attach at its center.
_source_fixed_accent_names = frozenset((
    # Normalized dot accents instead retain zero advance and ink-center attachment.
    'wbar', 'wwbar', 'what', 'wtilde', 'wcheck',
))
_source_fixed_accent_glyphs = set()
for _agn in _source_fixed_accent_names:
    if _agn in out:
        accent_glyphs.add(_agn)
        _source_fixed_accent_glyphs.add(_agn)

# Apply family skewchar policy after every source alphabet has been imported.
_source_topaccent_count = 0
for (_tag, _slot), _gname in sorted(imported.items()):
    if _tag not in SOURCE_SKEW or _tag not in fonts or _gname not in out:
        continue
    _tfm = fonts[_tag][1]
    if _slot not in _tfm.chars:
        continue
    if _gname in _source_fixed_accent_glyphs:
        _ta = out[_gname].width // 2
    elif _gname in accent_glyphs:
        _ta = ACC_CENTER
    else:
        _wd = _tfm.chars[_slot].get('wd') or 0.0
        _ic = _tfm.chars[_slot].get('ic') or 0.0
        _sk = SOURCE_SKEW[_tag]
        _skern = (_tfm.kerns.get((_slot, _sk), 0.0) or 0.0) if _sk is not None else 0.0
        _ta = round(((_wd + _ic) / 2 + _skern) * 1000)
    try:
        out[_gname].topaccent = int(_ta)
        _source_topaccent_count += 1
    except Exception:
        pass
# U+E286 uses positive-width bar coordinates; U+E287 uses zero-advance vector coordinates.
if 'wideoverbar.compat' in out:
    out['wideoverbar.compat'].topaccent = out['wideoverbar.compat'].width // 2
if 'widevector.compat' in out:
    out['widevector.compat'].topaccent = ACC_CENTER
print('source-family TopAccentAttachment:', _source_topaccent_count, 'glyph records')

# Serialize TFM kern alone; add_ordinary_ic_gpos.py adds the independent IC layer.
out.addLookup('kernL', 'gpos_pair', (),
              (('kern', (('DFLT', ('dflt',)), ('latn', ('dflt',)), ('math', ('dflt',)))),))
out.addLookupSubtable('kernL', 'kern-1')
_source_tfm_pair_contract = {}
_source_tfm_pair_count = 0


def _remember_source_tfm_pair(gl, gr, rec):
    global _source_tfm_pair_count
    key = (gl, gr)
    prev = _source_tfm_pair_contract.get(key)
    if prev is not None:
        if int(prev['xadvance']) != int(rec['xadvance']):
            raise RuntimeError('conflicting source TFM kern %s/%s: %+d vs %+d'
                               % (gl, gr, prev['xadvance'], rec['xadvance']))
        return
    _source_tfm_pair_contract[key] = rec
    out[gl].addPosSub('kern-1', gr, 0, 0, int(rec['xadvance']), 0, 0, 0, 0, 0)
    _source_tfm_pair_count += 1


for _tag in tuple(SOURCE_SKEW):
    if _tag not in fonts:
        continue
    _tfm = fonts[_tag][1]
    _sk = SOURCE_SKEW[_tag]
    for (_l, _r), _v in sorted(_tfm.kerns.items()):
        if _sk is not None and _r == _sk:
            continue
        _gl = imported.get((_tag, _l))
        _gr = imported.get((_tag, _r))
        if not _gl or not _gr or _gl not in out or _gr not in out:
            continue
        _k = round((_v or 0.0) * 1000)
        if not _k:
            continue
        _remember_source_tfm_pair(_gl, _gr, {
            'left': _gl, 'right': _gr, 'xadvance': int(_k),
            'tag': _tag, 'left_slot': int(_l), 'right_slot': int(_r),
            'skewchar': _sk,
            'formula': 'ordinary TFMkern(left,right)',
        })
print('ordinary source-TFM kern PairPos:', _source_tfm_pair_count)

# Builder source map used by independent post-serialization/audit tools.
_source_metric_contract = []
_ordinary_ic_left_by_glyph = {}
for (_tag, _slot), _gname in sorted(imported.items()):
    if _tag not in SOURCE_SKEW or _tag not in fonts or _gname not in out:
        continue
    _pfb, _tfm, _slots = fonts[_tag]
    if _slot not in _tfm.chars or _slot not in _slots:
        continue
    _srcname = _slots[_slot]
    _wd = round((_tfm.chars[_slot].get('wd') or 0.0) * 1000)
    _ic = round((_tfm.chars[_slot].get('ic') or 0.0) * 1000)
    _sk = SOURCE_SKEW[_tag]
    _skern = round(((_tfm.kerns.get((_slot, _sk), 0.0) or 0.0) if _sk is not None else 0.0) * 1000)
    # Recompute the exact target for the JSON record.
    if _gname in _source_fixed_accent_glyphs:
        _target_ta = int(out[_gname].width // 2)
    elif _gname in accent_glyphs:
        _target_ta = int(ACC_CENTER)
    else:
        _wd_f = _tfm.chars[_slot].get('wd') or 0.0
        _ic_f = _tfm.chars[_slot].get('ic') or 0.0
        _target_ta = round(((_wd_f + _ic_f) / 2
                            + ((_tfm.kerns.get((_slot, _sk), 0.0) or 0.0)
                               if _sk is not None else 0.0)) * 1000)
    try:
        _sbb = tuple(round(v) for v in _pfb[_srcname].boundingBox())
    except Exception:
        _sbb = None
    _rec = {
        'tag': _tag, 'slot': int(_slot), 'source_glyph': _srcname,
        'output_glyph': _gname, 'width': int(_wd),
        'italic_correction': int(_ic), 'skewchar': _sk,
        'skew_kern': int(_skern), 'topaccent_target': int(_target_ta),
        'ordinary_left': bool(_source_is_ordinary_left(_tag, _slot)),
        'normalized_combining_accent': bool(_gname in accent_glyphs
                                            and _gname not in _source_fixed_accent_glyphs),
        'fixed_source_accent': bool(_gname in _source_fixed_accent_glyphs),
        'source_bbox': _sbb,
    }
    _source_metric_contract.append(_rec)
    if _ic and _rec['ordinary_left']:
        _prev = _ordinary_ic_left_by_glyph.get(_gname)
        if _prev is not None and int(_prev['italic_correction']) != int(_ic):
            raise RuntimeError('conflicting ordinary IC for %s: %d vs %d'
                               % (_gname, _prev['italic_correction'], _ic))
        _ordinary_ic_left_by_glyph[_gname] = {
            'glyph': _gname, 'italic_correction': int(_ic),
            'tag': _tag, 'slot': int(_slot),
        }

# GDEF marks combining accents as marks and other glyphs as bases.
_mark = _base = 0
for _g in out.glyphs():
    _u = _g.unicode
    if _u == -1 and _g.altuni:
        _u = _g.altuni[0][0]
    if (_g.glyphname in accent_glyphs
            or (0x0300 <= _u <= 0x036F) or (0x20D0 <= _u <= 0x20F0)):
        _g.glyphclass = 'mark'
        _mark += 1
    else:
        _g.glyphclass = 'baseglyph'
        _base += 1
print('GDEF: mark %d / baseglyph %d' % (_mark, _base))

# Write the local source contract for independent post-serialization audits.
_source_contract_path = f'{ROOT}/build/generated/mtpro2-source-contract.json'
json.dump({
    'policy': (
        'MTPro2 original LaTeX source contract: hmtx=CHARWD; MATH IC=CHARIC; '
        'ordinary OpenType adjacency = CHARIC(left) + ordinary TFM kern(left,right), '
        'implemented as two cumulative GPOS lookups; missing TFM kern=0; '
        'per-family skewchar-right records excluded according to mtpro2.sty/umt2*.fd; '
        'scripts/primes/accents remain separate semantic paths; Word may segment '
        'math-class boundaries before GPOS.'
    ),
    'skewchar_by_tag': {k: SOURCE_SKEW[k] for k in SOURCE_SKEW if k in fonts},
    'source_font_by_tag': {k: SRC[k] for k in SOURCE_SKEW if k in fonts},
    'prime_padding': globals().get('PRIME_PADDING_EVIDENCE'),
    'records': _source_metric_contract,
    'ordinary_ic_lefts': [
        dict(v) for (_g, v) in sorted(_ordinary_ic_left_by_glyph.items())
    ],
    'tfm_kern_pairs': [
        dict(v) for (_key, v) in sorted(_source_tfm_pair_contract.items())
    ],
}, open(_source_contract_path, 'w', encoding='utf-8'),
    ensure_ascii=False, indent=2)
print('MTPro2 source contract:',
      len(_source_metric_contract), 'glyph records /',
      len(_ordinary_ic_left_by_glyph), 'ordinary nonzero-IC left glyphs /',
      len(_source_tfm_pair_contract), 'ordinary TFM kern pairs')

# The OpenType font is the unicode-math interface; no callback is generated.

# Serialize MinConnectorOverlap from the local connector geometry.
MINOVL = int(getattr(out.math, 'MinConnectorOverlap', MINOVL) or 0)
ALL_MATH_SCALARS['MinConnectorOverlap'] = MINOVL
_math_values_path = f'{ROOT}/build/generated/math-constants.json'
json.dump({'upm': out.em,
           'constants': dict(C),
           'MinConnectorOverlap': MINOVL,
           'provenance': math_constants.audit_payload(ALL_MATH_SCALARS)},
          open(_math_values_path, 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)

outpath = f'{OUTDIR}/{FONT_BASENAME}.otf'
out.generate(outpath, flags=('opentype',))

# Normalize structures that are safer to edit after FontForge generation.
_tools = os.path.dirname(os.path.abspath(__file__))
_system_python = os.environ.get('MTP2_SYSTEM_PYTHON', 'python3')


def _run_tool(script, *args):
    cmd = [_system_python, os.path.join(_tools, script)] + [str(x) for x in args]
    subprocess.run(cmd, check=True)


_run_tool('finalize.py', outpath, '--edition', EDITION,
          '--math-values', _math_values_path)
# Add the IC class lookup after serialization; it accumulates with TFM kern.
_run_tool('add_ordinary_ic_gpos.py', outpath, '--contract', _source_contract_path)

MAKE_TTF = '--no-ttf' not in sys.argv
if SUBSCRIPT_CORRECTION:
    _run_tool('mathkern.py', outpath)
else:
    print('MathKern: disabled (MTPro2 default = nosubscriptcorrection)')
if PRIME_SHIFT is not None:
    _run_tool('primectx.py', outpath, '--base-shift', PRIME_SHIFT)
print('generated', outpath, 'glyphs:', len([g for g in out.glyphs()]))
# Generate TrueType outlines for Word embedding; both formats retain OpenType MATH.
if MAKE_TTF:
    _run_tool('otf2ttf.py', outpath, outpath[:-4] + '.ttf')
