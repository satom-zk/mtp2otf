"""Native source faces, copied glyphs, and their Unicode/slot ownership.
"""

import os
from dataclasses import dataclass
from fractions import Fraction

import donors
import fontforge
import large_variant_policy as L
import mapping as U
import psMat
from outlines import native_font


@dataclass(frozen=True)
class AlphabetSources:
    upright_dotless_i: str | None
    upright_dotless_j: str
    bold_italic: dict
    bold_dotless_i: str | None
    bold_dotless_j: str | None


def uname(u):
    return "uni%04X" % u if u < 0x10000 else "u%05X" % u


# Prefix digit-leading names for Word font subsetting.
_DIGIT_NAME = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
)


def safe_gname(name):
    if name and name[0].isdigit():
        return _DIGIT_NAME[int(name[0])] + name[1:]
    return name


def _tfm_design_size(tfm):
    size = getattr(tfm, "design_size", None)
    if not size or size <= 0:
        raise RuntimeError("local TFM is missing a usable DESIGNSIZE")
    return Fraction(str(size))


class GlyphSources:
    """One font's source-slot and Unicode ownership; no CLI, paths or
    I/O.
    """

    def __init__(self, font, faces, rules, plan):
        self.font, self.faces, self.rules = font, faces, rules
        self.plan = {tag: set(slots) for tag, slots in plan["native"].items()}
        self.growth = plan["growth"]
        self.imported = {}
        self.variant_sources = {}
        self.source_requests = set()
        self.uni_owner = {}

    def axis_height(self):
        """Return the local MTPro2 math axis from the active symbol TFM.
        """
        return round(self.faces["syt"][1].fontdimen[22] * self.font.em)

    def pt_to_units(self, value, tfm):
        """Convert a package dimension in TeX points to output-font
        units.
        """
        return round(value / _tfm_design_size(tfm) * self.font.em)

    def mu_to_units(self, value):
        """Convert TeX math units to output-font units (one em is
        eighteen
        mu).
        """
        return round(value / 18 * self.font.em)

    def recenter_on_axis(self, gname):
        """Center delimiter variants on the math axis to bound Windows
        clipping metrics.
        """
        g = self.font[gname]
        bb = g.boundingBox()
        if bb == (0, 0, 0, 0):
            return
        dy = self.axis_height() - (bb[1] + bb[3]) / 2.0
        if abs(dy) >= 1:
            g.transform(psMat.translate(0, round(dy)))

    def import_glyph(
        self, tag, slot, name=None, unicode_=None, force_alt=False
    ):
        """Copy a source slot, or return its existing output glyph name.
        """
        key = (tag, slot)
        if slot not in self.plan.get(tag, set()):
            raise ValueError(
                f"unplanned source reference role={tag} slot={slot}"
            )
        self.source_requests.add(key)
        if key in self.imported:
            gname = self.imported[key]
            if (
                unicode_ is not None
                and unicode_ not in self.uni_owner
                and not force_alt
            ):
                g = self.font[gname]
                if g.unicode == -1:
                    g.unicode = unicode_
                    # Use codepoint-based names.
                    nn = uname(unicode_)
                    if nn not in self.font:
                        g.glyphname = nn
                        self.imported[key] = nn
                        gname = nn
                else:
                    self.font[gname].altuni = (
                        self.font[gname].altuni or ()
                    ) + ((unicode_, -1, 0),)
                self.uni_owner[unicode_] = gname
            return gname
        pfb, tfm, slots = self.faces[tag]
        if slot not in slots or slot not in tfm.chars:
            return None
        if unicode_ is not None and unicode_ in self.uni_owner:
            force_alt = True
            base = self.uni_owner[unicode_]
            unicode_ = None
            name = name or f"{base}.{tag}alt"
        if unicode_ is not None:
            gname = uname(unicode_)
            if (
                name
                and not name.startswith("uni")
                and not name.startswith("u1")
            ):
                # Prefer the canonical codepoint name.
                gname = uname(unicode_)
        else:
            gname = name or f"{tag}.{slot}"
        if gname in self.font:
            gname = f"{gname}.{tag}{slot}"
        gname = safe_gname(gname)
        pfb.selection.select(("encoding",), slot)
        pfb.copy()
        self.font.createChar(-1, gname)
        self.font.selection.select(gname)
        self.font.paste()
        g = self.font[gname]
        # Scale by the package-declared design size.
        scale = {"xxxl": 2.0, "exe": 2.0, "exf": 4.0, "exg": 8.0}.get(tag, 1.0)
        if scale != 1.0:
            g.transform(psMat.scale(scale))
        if tag in ("xl", "xxxl"):
            # PFB vertical placement assumes TeX-side raising; recenter
            # on the local math axis.
            bb = g.boundingBox()
            g.transform(
                psMat.translate(0, self.axis_height() - (bb[1] + bb[3]) / 2)
            )
        metric_slot = (
            self.growth["metric_references"].get(str(slot), slot)
            if tag == "exa"
            else slot
        )
        if metric_slot != slot:
            self.source_requests.add((tag, metric_slot))
        metrics = tfm.chars[metric_slot]
        _wd = metrics["wd"]
        _ic = metrics["ic"]
        if tag in ("exa", "xl", "xxxl") and _ic:
            # Include the slanted operator overhang in advance for
            # OpenType script placement.
            g.width = round((_wd + _ic) * 1000 * scale)
        else:
            g.width = round(_wd * 1000 * scale)
        if unicode_ is not None:
            g.unicode = unicode_
            self.uni_owner[unicode_] = gname
        ic = metrics["ic"]
        if ic:
            g.italicCorrection = round(ic * 1000 * scale)
        self.imported[key] = gname
        return gname

    def copy_donor_glyph(self, ffont, byuni, src_u, dst_u, dst_name=None):
        src_name = byuni.get(src_u)
        if src_name is None:
            raise RuntimeError("Roman donor missing U+%04X" % src_u)
        if dst_u is not None and dst_u in self.uni_owner:
            return self.uni_owner[dst_u]
        gn = dst_name or uname(dst_u)
        ffont.selection.select(src_name)
        ffont.copy()
        self.font.createChar(dst_u if dst_u is not None else -1, gn)
        self.font.selection.select(gn)
        self.font.paste()
        scale = float(self.font.em) / float(ffont.em)
        if abs(scale - 1.0) > 1e-12:
            self.font[gn].transform(psMat.scale(scale))
        self.font[gn].width = round(ffont[src_name].width * scale)
        if dst_u is not None:
            self.uni_owner[dst_u] = gn
        return gn

    def visible_contours(self, ffont, glyph):
        """Flatten references, then require closed, nonzero-area
        outlines.
        """
        ffont.selection.select(glyph.glyphname)
        ffont.unlinkReferences()
        contours = list(glyph.foreground)
        if not contours or any(not c.closed for c in contours):
            return None
        bounds = [c.boundingBox() for c in contours]
        if any(x1 <= x0 or y1 <= y0 for x0, y0, x1, y1 in bounds):
            return None
        return contours, bounds

    def regular_dotless_j(self, ffont, byuni):
        """Use this donor's encoded glyph, or remove its uniquely
        separated
        j dot.
        """
        source_u = 0x0237 if 0x0237 in byuni else 0x006A
        source_name = byuni.get(source_u)
        if source_name is None:
            raise RuntimeError(
                "Regular Roman donor has neither U+0237 nor U+006A"
            )
        source = ffont[source_name]
        visible = self.visible_contours(ffont, source)
        if visible is None:
            raise RuntimeError(
                "Regular Roman donor U+%04X has no valid visible outline"
                % source_u
            )
        contours, bounds = visible
        selected = None
        if source_u == 0x006A:
            if len(contours) != 2:
                raise RuntimeError(
                    "Regular Roman donor j dot is ambiguous: expected two "
                    "closed contours"
                )
            bodies = [
                i
                for i, (_, ymin, _, ymax) in enumerate(bounds)
                if ymin < 0 < ymax
            ]
            if len(bodies) != 1:
                raise RuntimeError(
                    "Regular Roman donor j body is not uniquely descending"
                )
            selected = bodies[0]
            dot = 1 - selected
            if bounds[dot][1] <= bounds[selected][3]:
                raise RuntimeError(
                    "Regular Roman donor j dot is not separated above body"
                )
        name = uname(0x0237)
        ffont.selection.select(source_name)
        ffont.copy()
        self.font.createChar(0x0237, name)
        self.font.selection.select(name)
        self.font.paste()
        if selected is not None:
            layer = fontforge.layer()
            layer.is_quadratic = source.foreground.is_quadratic
            layer += contours[selected]
            self.font[name].foreground = layer
        scale = float(self.font.em) / float(ffont.em)
        if abs(scale - 1.0) > 1e-12:
            self.font[name].transform(psMat.scale(scale))
        self.font[name].width = round(source.width * scale)
        self.uni_owner[0x0237] = name
        return name

    def alias_unicode(self, gname, u):
        old = self.uni_owner.get(u)
        if old is not None and old != gname:
            raise RuntimeError(
                "Unicode U+%04X already owned by %s, cannot alias %s"
                % (u, old, gname)
            )
        g = self.font[gname]
        if g.unicode == -1:
            g.unicode = u
        elif g.unicode != u:
            vals = list(g.altuni or ())
            if not any(a[0] == u for a in vals):
                vals.append((u, -1, 0))
                g.altuni = tuple(vals)
        self.uni_owner[u] = gname
        return gname

    def install_greek_aliases(self):
        groups = (
            ("Basic Greek", U.GREEK_LATIN_SHAPED_BASIC_ALIASES),
            (
                "Mathematical Italic Greek",
                U.GREEK_LATIN_SHAPED_MATH_ITALIC_ALIASES,
            ),
        )
        count = 0
        for label, table in groups:
            for target_cp, source_cp in table.items():
                source_glyph = self.uni_owner.get(source_cp)
                if source_glyph is None:
                    raise RuntimeError(
                        "%s alias source U+%04X missing for U+%04X"
                        % (label, source_cp, target_cp)
                    )
                self.alias_unicode(source_glyph, target_cp)
                count += 1
        if count != 30:
            raise RuntimeError(
                "Greek Latin-shaped alias contract expected 30 entries, "
                "got %d" % count
            )

    def piece(self, slot):
        name = U.EXA_PIECES.get(slot, f"exa.piece{slot}")
        return self.import_glyph("exa", slot, name=name)


def import_core(sources, limits):
    LARGE_POLICY = limits.condition
    MAXVAR = limits.max_height
    fonts = sources.faces
    import_glyph = sources.import_glyph
    imported = sources.imported
    out = sources.font
    recenter_on_axis = sources.recenter_on_axis
    plan = [("mit", U.MIT), ("syt", U.SYT)]
    for tag, table in plan:
        if tag not in fonts:
            continue
        for slot, (u, name) in sorted(table.items()):
            import_glyph(tag, slot, name=name, unicode_=u)

    # Encode text operators; keep display variants in size order.
    # base glyph -> size-ordered variants, including the base
    op_variants = {}
    if "exa" in fonts:
        for slot, (u, name, dslot) in U.EXA_OPS.items():
            base = import_glyph("exa", slot, name=name, unicode_=u)
            if base is None:
                continue
            var = [base]
            d = import_glyph("exa", dslot, name=f"{base}.dsp")
            if d:
                var.append(d)
            # xl / XL / XXL / XXXL
            if name in U.XL_TABLE and "xl" in fonts:
                xl, XL, XXL, XXXL = U.XL_TABLE[name]
                for sz, (ftag, sl) in enumerate(
                    [("xl", xl), ("xl", XL), ("xl", XXL), ("xxxl", XXXL)]
                ):
                    if ftag not in fonts:
                        continue
                    sfx = [".xl", ".XL", ".XXL", ".XXXL"][sz]
                    # Compose the two source halves.
                    if isinstance(sl, tuple):
                        left = import_glyph(ftag, sl[0], name=f"{base}{sfx}.l")
                        r = import_glyph(ftag, sl[1], name=f"{base}{sfx}.r")
                        if left and r:
                            gn = f"{base}{sfx}"
                            out.createChar(-1, gn)
                            g = out[gn]
                            _scale = 2 if ftag == "xxxl" else 1
                            _pfb, _tfm, _slots = fonts[ftag]
                            _boxes = [
                                _pfb[_slots[q]].boundingBox() for q in sl
                            ]
                            _extent = (
                                max(b[3] for b in _boxes)
                                - min(b[1] for b in _boxes)
                            ) * _scale
                            _offsets = (
                                L.compound_reference_offsets(_boxes, _scale)
                                if (
                                    LARGE_POLICY == "source"
                                    and _extent > MAXVAR
                                )
                                else (0, 0)
                            )
                            g.addReference(
                                left, psMat.translate(0, _offsets[0])
                            )
                            g.addReference(
                                r,
                                psMat.translate(out[left].width, _offsets[1]),
                            )
                            g.width = out[left].width + out[r].width
                            var.append(gn)
                    else:
                        v = import_glyph(ftag, sl, name=f"{base}{sfx}")
                        if v:
                            var.append(v)
            # Limit fixed sizes to keep Windows
            # clipping bounds manageable.
            trimmed = [var[0]]
            for gn in var[1:]:
                bb = out[gn].boundingBox()
                if (
                    not L.exempt(LARGE_POLICY, u, "h", operator=True)
                    and MAXVAR
                    and bb[3] - bb[1] > MAXVAR
                ):
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
    if "ams" in fonts:
        for slot, (u, name) in sorted(U.AMSA.items()):
            import_glyph("ams", slot, name=name, unicode_=u)

    # Math alphabets.
    for tag, kind in [
        ("bb", "bb"),
        ("script", "script"),
        ("frak", "frak"),
        ("curly", "curly"),
        ("bscript", "bscript"),
        ("bfrak", "bfrak"),
    ]:
        if tag not in fonts:
            continue
        for slot, (u, name) in sorted(U.alpha_map(kind).items()):
            import_glyph(tag, slot, name=name, unicode_=u)
    return op_variants


def import_roman(sources, regular, bold):
    _copy_donor_glyph = sources.copy_donor_glyph
    _regular_dotless_j = sources.regular_dotless_j
    out = sources.font
    ROMAN_REG, ROMAN_BOLD = str(regular), str(bold)
    upright_dotless = None
    with native_font(ROMAN_REG) as _nf_reg:
        _nr = donors.unicode_map(_nf_reg)
        for _u in list(range(0x41, 0x5B)) + list(range(0x61, 0x7B)):
            _copy_donor_glyph(_nf_reg, _nr, _u, _u)
        # dotless i is used internally by dtls. Prefer the
        # encoded U+0131 if present.
        if 0x0131 in _nr:
            upright_dotless = _copy_donor_glyph(
                _nf_reg, _nr, 0x0131, None, "i.dotless"
            )
        elif "dotlessi" in _nf_reg:
            _nf_reg.selection.select("dotlessi")
            _nf_reg.copy()
            out.createChar(-1, "i.dotless")
            out.selection.select("i.dotless")
            out.paste()
            _roman_reg_scale = float(out.em) / float(_nf_reg.em)
            if abs(_roman_reg_scale - 1.0) > 1e-12:
                out["i.dotless"].transform(psMat.scale(_roman_reg_scale))
            out["i.dotless"].width = round(
                _nf_reg["dotlessi"].width * _roman_reg_scale
            )
            upright_dotless = "i.dotless"
        upright_dotless_j = _regular_dotless_j(_nf_reg, _nr)

    with native_font(ROMAN_BOLD) as _nf_bold:
        _nb = donors.unicode_map(_nf_bold)
        # Unicode Mathematical Bold Latin and digits follow
        # \mathbf / rmdefault bold.
        for _i, _u in enumerate(range(0x41, 0x5B)):
            _copy_donor_glyph(_nf_bold, _nb, _u, 0x1D400 + _i)
        for _i, _u in enumerate(range(0x61, 0x7B)):
            _copy_donor_glyph(_nf_bold, _nb, _u, 0x1D41A + _i)
        for _i, _u in enumerate(range(0x30, 0x3A)):
            _copy_donor_glyph(_nf_bold, _nb, _u, 0x1D7CE + _i)
    return upright_dotless, upright_dotless_j


def import_bold_and_aliases(sources, upright_dotless_i, upright_dotless_j):
    _install_greek_latin_shaped_aliases = sources.install_greek_aliases
    alias_unicode = sources.alias_unicode
    fonts = sources.faces
    import_glyph = sources.import_glyph
    uni_owner = sources.uni_owner
    _install_greek_latin_shaped_aliases()

    _MIT_CP_SLOT = {
        u: slot for slot, (u, _name) in U.MIT.items() if u is not None
    }
    _SYT_CP_SLOT = {
        u: slot for slot, (u, _name) in U.SYT.items() if u is not None
    }

    def bmit_cp(source_cp, target_cp, name=None):
        slot = _MIT_CP_SLOT.get(source_cp)
        if slot is None:
            raise RuntimeError(
                "mt2bmit source mapping missing U+%04X" % source_cp
            )
        return import_glyph("bmit", slot, name=name, unicode_=target_cp)

    bold_it_latin = {}
    bold_dotless_i = None
    bold_dotless_j = None
    # Lite has donor bold Latin/digits, but no
    # synthesized Full-only bold math.
    if "bmit" in fonts and "bsyt" in fonts:
        # Mathematical Bold Italic Latin U+1D468..U+1D49B.
        bold_it_latin = {}
        for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
            g = import_glyph("bmit", ord("A") + i, unicode_=0x1D468 + i)
            bold_it_latin[ch] = g
        for i, ch in enumerate("abcdefghijklmnopqrstuvwxyz"):
            g = import_glyph("bmit", ord("a") + i, unicode_=0x1D482 + i)
            bold_it_latin[ch] = g

        # Keep bold dotless forms unencoded; public dotless
        # codepoints belong to italic.
        bold_dotless_i = import_glyph("bmit", 0x7B, name="u1D48A.dotless")
        bold_dotless_j = import_glyph("bmit", 0x7C, name="u1D48B.dotless")

        # Greek uppercase order in the Unicode
        # Mathematical Alphanumeric block.
        greek_cap_names = [
            "ALPHA",
            "BETA",
            "GAMMA",
            "DELTA",
            "EPSILON",
            "ZETA",
            "ETA",
            "THETA",
            "IOTA",
            "KAPPA",
            "LAMDA",
            "MU",
            "NU",
            "XI",
            "OMICRON",
            "PI",
            "RHO",
            "THETA SYMBOL",
            "SIGMA",
            "TAU",
            "UPSILON",
            "PHI",
            "CHI",
            "PSI",
            "OMEGA",
        ]
        basic_cap = {
            "ALPHA": 0x0391,
            "BETA": 0x0392,
            "GAMMA": 0x0393,
            "DELTA": 0x0394,
            "EPSILON": 0x0395,
            "ZETA": 0x0396,
            "ETA": 0x0397,
            "THETA": 0x0398,
            "IOTA": 0x0399,
            "KAPPA": 0x039A,
            "LAMDA": 0x039B,
            "MU": 0x039C,
            "NU": 0x039D,
            "XI": 0x039E,
            "OMICRON": 0x039F,
            "PI": 0x03A0,
            "RHO": 0x03A1,
            "SIGMA": 0x03A3,
            "TAU": 0x03A4,
            "UPSILON": 0x03A5,
            "PHI": 0x03A6,
            "CHI": 0x03A7,
            "PSI": 0x03A8,
            "OMEGA": 0x03A9,
        }
        latin_visual = {
            "ALPHA": "A",
            "BETA": "B",
            "EPSILON": "E",
            "ZETA": "Z",
            "ETA": "H",
            "IOTA": "I",
            "KAPPA": "K",
            "MU": "M",
            "NU": "N",
            "OMICRON": "O",
            "RHO": "P",
            "TAU": "T",
            "CHI": "X",
        }

        # Use mt2bmit for non-Latin-shaped bold Greek and
        # Latin aliases for the rest.
        bold_greek = {}
        for idx, name in enumerate(greek_cap_names):
            tgt = 0x1D6A8 + idx
            if name == "THETA SYMBOL":
                g = bold_greek["THETA"]
                alias_unicode(g, tgt)
            elif basic_cap[name] in _MIT_CP_SLOT:
                g = bmit_cp(basic_cap[name], tgt)
            else:
                g = uni_owner[0x1D400 + (ord(latin_visual[name]) - ord("A"))]
                alias_unicode(g, tgt)
            bold_greek[name] = g

        # Genuine bold nabla from mt2bsyt; upright and italic
        # mathematical nabla share it.
        _bsnabla_slot = _SYT_CP_SLOT.get(0x2207)
        if _bsnabla_slot is None:
            raise RuntimeError("mt2bsyt nabla source missing")
        bold_nabla = import_glyph("bsyt", _bsnabla_slot, unicode_=0x1D6C1)
        alias_unicode(bold_nabla, 0x1D735)

        small_order = [
            ("ALPHA", 0x03B1),
            ("BETA", 0x03B2),
            ("GAMMA", 0x03B3),
            ("DELTA", 0x03B4),
            ("EPSILON", 0x03B5),
            ("ZETA", 0x03B6),
            ("ETA", 0x03B7),
            ("THETA", 0x03B8),
            ("IOTA", 0x03B9),
            ("KAPPA", 0x03BA),
            ("LAMDA", 0x03BB),
            ("MU", 0x03BC),
            ("NU", 0x03BD),
            ("XI", 0x03BE),
            ("OMICRON", 0x03BF),
            ("PI", 0x03C0),
            ("RHO", 0x03C1),
            ("FINAL SIGMA", 0x03C2),
            ("SIGMA", 0x03C3),
            ("TAU", 0x03C4),
            ("UPSILON", 0x03C5),
            ("PHI", 0x03C6),
            ("CHI", 0x03C7),
            ("PSI", 0x03C8),
            ("OMEGA", 0x03C9),
        ]
        for idx, (_name, source_cp) in enumerate(small_order):
            tgt = 0x1D6C2 + idx
            if source_cp in _MIT_CP_SLOT:
                bmit_cp(source_cp, tgt)
            else:  # Greek omicron has the Latin o design.
                alias_unicode(uni_owner[0x1D41A + (ord("o") - ord("a"))], tgt)

        # Bold partial differential and upright variant Greek symbols.
        bold_partial = bmit_cp(0x1D715, 0x1D6DB)
        for i, source_cp in enumerate(
            (0x03F5, 0x03D1, 0x03F0, 0x03D5, 0x03F1, 0x03D6)
        ):
            bmit_cp(source_cp, 0x1D6DC + i)

        # Mathematical Bold Italic Greek U+1D71C..U+1D755.
        italic_cap_regular = {
            "GAMMA": 0x1D6E4,
            "DELTA": 0x1D6E5,
            "THETA": 0x1D6E9,
            "LAMDA": 0x1D6EC,
            "XI": 0x1D6EF,
            "PI": 0x1D6F1,
            "SIGMA": 0x1D6F4,
            "UPSILON": 0x1D6F6,
            "PHI": 0x1D6F7,
            "PSI": 0x1D6F9,
            "OMEGA": 0x1D6FA,
        }
        bold_it_greek = {}
        for idx, name in enumerate(greek_cap_names):
            tgt = 0x1D71C + idx
            if name == "THETA SYMBOL":
                g = bold_it_greek["THETA"]
                alias_unicode(g, tgt)
            elif name in italic_cap_regular:
                g = bmit_cp(italic_cap_regular[name], tgt)
            else:
                g = bold_it_latin[latin_visual[name]]
                alias_unicode(g, tgt)
            bold_it_greek[name] = g

        reg_it_small = [
            0x1D6FC,
            0x1D6FD,
            0x1D6FE,
            0x1D6FF,
            0x1D700,
            0x1D701,
            0x1D702,
            0x1D703,
            0x1D704,
            0x1D705,
            0x1D706,
            0x1D707,
            0x1D708,
            0x1D709,
            0x1D70A,
            0x1D70B,
            0x1D70C,
            0x1D70D,
            0x1D70E,
            0x1D70F,
            0x1D710,
            0x1D711,
            0x1D712,
            0x1D713,
            0x1D714,
        ]
        for i, source_cp in enumerate(reg_it_small):
            tgt = 0x1D736 + i
            if source_cp in _MIT_CP_SLOT:
                bmit_cp(source_cp, tgt)
            else:  # mathematical italic omicron = Latin italic o
                alias_unicode(bold_it_latin["o"], tgt)
        alias_unicode(bold_partial, 0x1D74F)
        for i, source_cp in enumerate(
            (0x1D716, 0x1D717, 0x1D718, 0x1D719, 0x1D71A, 0x1D71B)
        ):
            bmit_cp(source_cp, 0x1D750 + i)
    return AlphabetSources(
        upright_dotless_i,
        upright_dotless_j,
        bold_it_latin,
        bold_dotless_i,
        bold_dotless_j,
    )


def import_remaining_roman(sources, regular, edition, coverage, spec):
    DONOR_COVERAGE = coverage
    EDITION = edition
    PUBLIC_SPEC = spec
    ROMAN_REG = str(regular)
    out = sources.font
    uni_owner = sources.uni_owner
    for u, w in U.BLANKS.items():
        if u in uni_owner:
            continue
        gn = "space" if u == 0x0020 else uname(u)
        out.createChar(u, gn)
        out[gn].width = w
        uni_owner[u] = gn

    if os.path.exists(ROMAN_REG):
        with native_font(ROMAN_REG) as nf2:
            _roman_extra_scale = float(out.em) / float(nf2.em)
            for src_name, u in donors.ROMAN_EXTRA.items():
                if u in uni_owner or src_name not in nf2:
                    continue
                if (
                    EDITION == "lite"
                    and u in donors.CANONICAL_FULL_ONLY_SOURCE_UNICODE
                ):
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

            # Fill remaining text coverage without
            # replacing existing math glyphs.
            todo = donors.text_candidates(
                nf2,
                uni_owner,
                {g.glyphname for g in out.glyphs()},
                EDITION,
                DONOR_COVERAGE,
                PUBLIC_SPEC,
                {r[0] for g in out.glyphs() for r in (g.references or ())},
            )
            for src_name, u, gn, w in todo:
                nf2.selection.select(src_name)
                nf2.unlinkReferences()
                nf2.selection.select(src_name)
                nf2.copy()
                out.createChar(u, gn)
                out.selection.select(gn)
                out.paste()
                if abs(_roman_extra_scale - 1.0) > 1e-12:
                    out[gn].transform(psMat.scale(_roman_extra_scale))
                out[gn].width = round(w * _roman_extra_scale)
                uni_owner[u] = gn


def check_minimal_supply(sources, spec, alphabet):
    PUBLIC_SPEC = spec
    out = sources.font
    uni_owner = sources.uni_owner
    upright_dotless = alphabet.upright_dotless_i
    if PUBLIC_SPEC is not None:
        _public_observed = {}
        for _rule in PUBLIC_SPEC["roots"]:
            _u = _rule["output_unicode"]
            if _u not in uni_owner:
                continue
            _g = out[uni_owner[_u]]
            _bb = _g.boundingBox()
            _public_observed[_u] = {
                "visible": _bb[2] > _bb[0] and _bb[3] > _bb[1],
                "advance": _g.width,
            }
        _names = {g.glyphname for g in out.glyphs()}
        _dependencies = {
            r[0] for g in out.glyphs() for r in (g.references or ())
        }
        _internal = {
            "i.dotless": bool(
                upright_dotless
                and upright_dotless in _names
                and (
                    out[upright_dotless].boundingBox()[2]
                    > out[upright_dotless].boundingBox()[0]
                )
            )
        }
        donors.validate_outputs(
            PUBLIC_SPEC, _public_observed, _internal, _dependencies, _names
        )


def import_optical_forms(sources, accents):
    ACCENT_SLOTS = accents.slots
    ACC_CENTER = accents.center
    SKEW = dict(sources.rules.skewchar_by_tag)
    accent_glyphs = accents.glyphs
    fonts = sources.faces
    import_glyph = sources.import_glyph
    imported = sources.imported
    out = sources.font
    ssty_map = {}

    def add_ssty(coretag, stag, sstag, table):
        if stag not in fonts:
            return
        for slot in table:
            key = (coretag, slot)
            if key not in imported:
                continue
            base = imported[key]
            alts = []
            for lvl, t in ((1, stag), (2, sstag)):
                if t not in fonts:
                    continue
                g = import_glyph(t, slot, name=f"{base}.ssty{lvl}")
                if g:
                    alts.append(g)
            if alts:
                ssty_map[base] = alts

    add_ssty("mit", "mit_s", "mit_ss", U.MIT)
    add_ssty("syt", "syt_s", "syt_ss", U.SYT)
    add_ssty("ams", "ams_s", "ams_ss", U.AMSA)
    add_ssty("bb", "bb_s", "bb_ss", U.alpha_map("bb"))
    # Import Blackboard option-family optical sources for cv33/cv34.
    for _core, _s, _ss in (
        ("bbd", "bbd_s", "bbd_ss"),
        ("bbi", "bbi_s", "bbi_ss"),
        ("hrb", "hrb_s", "hrb_ss"),
        ("hrbd", "hrbd_s", "hrbd_ss"),
        ("hbi", "hbi_s", "hbi_ss"),
    ):
        if _core not in fonts:
            continue
        for _slot, (_u, _nm) in U.alpha_map("bb").items():
            _base = import_glyph(_core, _slot, name=f"{_nm}.{_core}")
            if not _base:
                continue
            _alts = []
            for _lvl, _tag in ((1, _s), (2, _ss)):
                if _tag not in fonts:
                    continue
                _g = import_glyph(_tag, _slot, name=f"{_base}.ssty{_lvl}")
                if _g:
                    _alts.append(_g)
            if _alts:
                ssty_map[_base] = _alts
    add_ssty("script", "script_s", "script_ss", U.alpha_map("script"))
    add_ssty("frak", "frak_s", "frak_ss", U.alpha_map("frak"))
    add_ssty("bscript", "bscript_s", "bscript_ss", U.alpha_map("bscript"))
    add_ssty("bfrak", "bfrak_s", "bfrak_ss", U.alpha_map("bfrak"))
    # Donor mathematical bold has no mt2mb* script
    # substitutions; mbf is separate.
    add_ssty("curly", "curly_s", "curly_ss", U.alpha_map("curly"))
    add_ssty("bmit", "bmit_s", "bmit_ss", U.MIT)
    add_ssty("bsyt", "bsyt_s", "bsyt_ss", U.SYT)

    # Normalize script accents and use their own
    # source-family skew kern.
    for tag in ("syt_s", "syt_ss"):
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
    for tag in (
        "mit_s",
        "mit_ss",
        "syt_s",
        "syt_ss",
        "bmit_s",
        "bmit_ss",
        "bsyt_s",
        "bsyt_ss",
        "bb_s",
        "bb_ss",
        "bbi_s",
        "bbi_ss",
        "bbd_s",
        "bbd_ss",
        "hrb_s",
        "hrb_ss",
        "hrbd_s",
        "hrbd_ss",
        "hbi_s",
        "hbi_ss",
        "script_s",
        "script_ss",
        "frak_s",
        "frak_ss",
        "bscript_s",
        "bscript_ss",
        "bfrak_s",
        "bfrak_ss",
        "curly_s",
        "curly_ss",
        "bold_s",
        "bold_ss",
    ):
        if tag not in fonts:
            continue
        _, tfm, _ = fonts[tag]
        sk = SKEW[tag]
        for (tg, slot), gname in imported.items():
            if tg != tag or slot not in tfm.chars or gname in accent_glyphs:
                continue
            kern = tfm.kerns.get((slot, sk), 0.0) if sk is not None else 0.0
            try:
                w = tfm.chars[slot]["wd"]
                ic = tfm.chars[slot].get("ic") or 0.0
                out[gname].topaccent = round(((w + ic) / 2 + kern) * 1000)
            except Exception as exc:
                raise ValueError(f"TopAccent {gname}: {exc}") from exc
    return ssty_map


def build_primes(sources, ssty_map):
    """Use original S/SS primes; derive same-line forms from the S
    design.

    Placement of superscripts and preceding-character IC belongs to the
    engine. The returned attachments override only the transformed T
    forms.
    """
    from constructions import compose_glyph

    out, imported, owners = sources.font, sources.imported, sources.uni_owner
    ratio = sources.rules.script_ratio
    scale = float(ratio)
    shift = round(sources.faces["syt"][1].fontdimen[13] * out.em)
    accents = {}
    targets = [("syt", 48, owners[0x2032])]
    if ("ams", 56) in imported:
        targets.append(("ams", 56, imported[("ams", 56)]))
    for tag, slot, base in targets:
        script = base + ".ssty1"
        tfm = sources.faces[tag + "_s"][1]
        width = round(tfm.chars[slot]["wd"] * out.em)
        italic = round((tfm.chars[slot].get("ic") or 0) * out.em)
        out.selection.select(script)
        out.copy()
        out.selection.select(base)
        out.paste()
        out[base].transform((scale, 0, 0, scale, 0, shift))
        out[base].width = round(ratio * width)
        # These source primes have centered attachment and no skew pair.
        accents[base] = round(ratio * Fraction(width + italic, 2))

    prime = owners[0x2032]
    source_width = round(sources.faces["syt_s"][1].chars[48]["wd"] * out.em)
    for cp, count in ((0x2033, 2), (0x2034, 3), (0x2057, 4)):
        # Keep fractional positions through composition; round total
        # width
        # once, rather than accumulating rounded single-prime advances.
        offsets = [(float(i * ratio * source_width), 0) for i in range(count)]
        compose_glyph(
            sources,
            cp,
            None,
            prime,
            offsets,
            round(count * ratio * source_width),
        )
        base = owners[cp]
        for level, role in ((1, "syt_s"), (2, "syt_ss")):
            original = prime + ".ssty" + str(level)
            width = round(sources.faces[role][1].chars[48]["wd"] * out.em)
            name = base + ".ssty" + str(level)
            out.createChar(-1, name)
            glyph = out[name]
            for i in range(count):
                glyph.addReference(original, psMat.translate(i * width, 0))
            glyph.width = count * width
            ssty_map.setdefault(base, []).append(name)

    # Preserve raw-prime ccmp ligatures, longest sequence first. There
    # is
    # no padding to cancel with a dedicated prime-prime GPOS adjustment.
    out.addLookup(
        "primelig",
        "gsub_ligature",
        (),
        (
            (
                "ccmp",
                (
                    ("DFLT", ("dflt",)),
                    ("latn", ("dflt",)),
                    ("math", ("dflt",)),
                ),
            ),
        ),
    )
    out.addLookupSubtable("primelig", "primelig-1")
    for cp, count in ((0x2057, 4), (0x2034, 3), (0x2033, 2)):
        out[owners[cp]].addPosSub("primelig-1", tuple([prime] * count))
    return accents
