"""Native optical routes, MATH/spacing and final metric boundaries."""

import mapping as U
import large_variant_policy as L
import math_constants
import positioning
from compatibility_metrics import assign_windows
from constructions import compose_glyph


def install_initial_math(sources, accents):
    ACC_CENTER = accents.center
    SCRIPTSCRIPT_RATIO = sources.rules.scriptscript_ratio
    SCRIPT_RATIO = sources.rules.script_ratio
    SOURCE_SKEW = dict(sources.rules.skewchar_by_tag)
    accent_glyphs = accents.glyphs
    fonts = sources.faces
    imported = sources.imported
    out = sources.font
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
            # TeX centers over the accentee width plus
            # CHARIC, then adds skew kern.
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
    # Only mapped operator pairs define this threshold. The catalog/plan
    # already preflight both slots; unrelated NEXTLARGER chains are
    # excluded.
    operator_sizes = [
        tuple(
            fonts['exa'][1].chars[slot]['ht']
            + fonts['exa'][1].chars[slot]['dp']
            for slot in (text, display)
        )
        for text, (_, _, display) in U.EXA_OPS.items()
    ]

    C = math_constants.compute(
        sy_fd,
        ex_fd,
        script_sy=fonts['syt_s'][1].fontdimen,
        script_ratio=SCRIPT_RATIO,
        scriptscript_ratio=SCRIPTSCRIPT_RATIO,
        operator_sizes=operator_sizes,
        cap_height=fonts['mit'][1].chars[0x41]['ht'],
        quad=out.em,
    )
    MINOVL = C.pop('MinConnectorOverlap')

    FF_NAMES = {
        'FractionNumDisplayStyleGapMin': 'FractionNumeratorDisplayStyleGapMin',
        'FractionDenomDisplayStyleGapMin': (
            'FractionDenominatorDisplayStyleGapMin'
        ),
    }
    for k, v in C.items():
        try:
            setattr(out.math, FF_NAMES.get(k, k), int(v))
        except AttributeError as exc:
            # Only these scalars are restored from
            # the snapshot by font_geometry.
            if k not in (
                'ScriptPercentScaleDown',
                'ScriptScriptPercentScaleDown',
                'SpaceAfterScript',
            ):
                raise ValueError(f'MATH constant {k}: {exc}') from exc
        except Exception as exc:
            raise ValueError(f'MATH constant {k}: {exc}') from exc
    out.math.MinConnectorOverlap = MINOVL

    # Per-glyph MATH data.
    for gname, ta in topaccent.items():
        try:
            out[gname].topaccent = ta
        except Exception as exc:
            raise ValueError(f'TopAccent {gname}: {exc}') from exc
    return C, MINOVL


def assign_private_codepoints(sources):
    alias_unicode = sources.alias_unicode

    def compose(*args):
        return compose_glyph(sources, *args)

    imported = sources.imported
    out = sources.font
    uni_owner = sources.uni_owner
    alias_unicode(uni_owner[0x003A], 0x2236)

    # Compose proportion from two colons.
    if 0x2237 not in uni_owner and 0x003A in uni_owner:
        c = uni_owner[0x003A]
        cw = out[c].width
        compose(0x2237, None, c, [(0, 0), (cw + 167, 0)], 2 * cw + 167)

    # Expose private alternatives for Word, where cv/salt
    # controls are unavailable.
    PUA = 0xE000

    def pua(gname):
        nonlocal PUA
        if gname not in out:
            return
        g = out[gname]
        if g.unicode == -1:
            g.unicode = PUA
        else:
            g.altuni = (g.altuni or ()) + ((PUA, -1, 0),)
        PUA += 1

    if ('mit', 180) in imported:
        pua(imported[('mit', 180)])  # U+E000 z swash
    if ('ams', 191) in imported:
        pua(imported[('ams', 191)])  # U+E001 varnothing
    PUA = 0xE010
    for slot, (u, nm) in sorted(U.alpha_map('curly').items()):
        if ('curly', slot) in imported:
            pua(imported[('curly', slot)])  # U+E010.. curly
    for base, tag in (
        (0xE100, 'bbd'),
        (0xE140, 'bbi'),
        (0xE180, 'hrb'),
        (0xE1C0, 'hrbd'),
        (0xE200, 'hbi'),
    ):
        PUA = base
        for slot, (u, nm) in sorted(U.alpha_map('bb').items()):
            if (tag, slot) in imported:
                pua(imported[(tag, slot)])

    # Keep private assignments fixed across editions;
    # missing glyphs leave holes.
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
            out[_nm].altuni = (out[_nm].altuni or ()) + ((_cp, -1, 0),)
            _pua_done.add(_nm)
    PUA = _maxcp + 1
    # Unencoded mapped glyphs are assigned deterministically after the
    # fixed range, in source-table slot order.
    for _tag, _table in (('mit', U.MIT), ('syt', U.SYT), ('ams', U.AMSA)):
        for _slot, _ent in sorted(_table.items()):
            _u, _nm = _ent[0], _ent[1]
            if _u is not None or not _nm:
                continue
            _g = imported.get((_tag, _slot))
            if (
                _g
                and _g not in _pua_done
                and _g in out
                and out[_g].unicode == -1
            ):
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


def assign_metrics(sources, *, cap_height):
    out = sources.font
    sy_fd = sources.faces['syt'][1].fontdimen
    out.ascent, out.descent = 800, 200
    # Use absolute FontForge metrics rather than offsets
    # from the bounding box.
    out.os2_typoascent_add = out.os2_typodescent_add = 0
    out.hhea_ascent_add = out.hhea_descent_add = 0
    out.os2_typoascent, out.os2_typodescent, out.os2_typolinegap = (
        806,
        -194,
        200,
    )
    out.hhea_ascent, out.hhea_descent, out.hhea_linegap = 806, -194, 200
    out.os2_xheight = round(sy_fd[5] * 1000)
    # Reuse the source cap height already converted for MATH.
    out.os2_capheight = cap_height
    # Cover all outlines with Windows clipping bounds; USE_TYPO_METRICS
    # controls spacing. Scan glyph bounds for compatibility
    # across FontForge versions.
    _bounds_y = assign_windows(out)
    return _bounds_y


def finish_source_features(
    sources, limits, accents, variants, *, prime_accents
):
    ACC_CENTER = accents.center
    FAMILY = sources.font.familyname
    FSTYPE = 8
    LARGE_POLICY = limits.condition
    MAXWIDTH = limits.max_width
    SOURCE_SKEW = dict(sources.rules.skewchar_by_tag)
    STYLE = 'Regular'
    accent_glyphs = accents.glyphs
    fonts = sources.faces
    horiz_variants = variants.horizontal
    imported = sources.imported
    out = sources.font
    uni_owner = sources.uni_owner
    out.os2_use_typo_metrics = 1
    out.os2_vendor = 'MTP2'
    # Preserve the source trademark notice.
    try:
        out.appendSFNTName(
            'English (US)',
            'Trademark',
            ('MathTime is a trademark of Publish or ' 'Perish, Inc.'),
        )
    except Exception as exc:
        raise ValueError(f'name Trademark: {exc}') from exc
    try:
        out.appendSFNTName('English (US)', 'Preferred Family', FAMILY)
        out.appendSFNTName('English (US)', 'Preferred Styles', STYLE)
    except Exception as exc:
        raise ValueError(
            f'name Preferred Family/Preferred Styles: {exc}'
        ) from exc
    out.os2_stylemap = 0x40
    # Apply the selected embedding flag; license terms remain separate.
    out.os2_fstype = FSTYPE
    # font_geometry.py sets the Windows-compatible technical font
    # version.

    # Word math-italic nabla aliases the source nabla glyph.
    if 0x2207 in uni_owner:
        _ng = out[uni_owner[0x2207]]
        _nabla_aliases = [0x1D6FB]
        for _u in _nabla_aliases:
            if _u not in uni_owner:
                _ng.altuni = (_ng.altuni or ()) + ((_u, -1, 0),)
                uni_owner[_u] = _ng.glyphname

    # Alias the fixed bar to U+0305 for Word.
    if 0x0304 in uni_owner and 0x0305 not in uni_owner:
        _g = out[uni_owner[0x0304]]
        _g.altuni = (_g.altuni or ()) + ((0x0305, -1, 0),)
        uni_owner[0x0305] = uni_owner[0x0304]

    # Finalize TopAccent and original pair kerning after all source
    # and alternate imports. MATH italic corrections remain independent.

    if 'wideoverbar.compat' in out:
        accent_glyphs.add('wideoverbar.compat')
    if 'widevector.compat' in out:
        accent_glyphs.add('widevector.compat')

    # Finite source accents retain positive advance
    # and attach at its center.
    _source_fixed_accent_names = frozenset(
        (
            # Normalized dot accents instead retain zero advance and
            # ink-center attachment.
            'wbar',
            'wwbar',
            'what',
            'wtilde',
            'wcheck',
        )
    )
    _source_fixed_accent_glyphs = set()
    for _agn in _source_fixed_accent_names:
        if _agn in out:
            accent_glyphs.add(_agn)
            _source_fixed_accent_glyphs.add(_agn)

    # Apply family skewchar policy after every source
    # alphabet has been imported.
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
            _skern = (
                (_tfm.kerns.get((_slot, _sk), 0.0) or 0.0)
                if _sk is not None
                else 0.0
            )
            _ta = round(((_wd + _ic) / 2 + _skern) * 1000)
        try:
            out[_gname].topaccent = int(_ta)
        except Exception as exc:
            raise ValueError(f'TopAccent {_gname}: {exc}') from exc
    # U+E286 uses positive-width bar coordinates; U+E287 uses
    # zero-advance vector coordinates.
    if 'wideoverbar.compat' in out:
        out['wideoverbar.compat'].topaccent = (
            out['wideoverbar.compat'].width // 2
        )
    if 'widevector.compat' in out:
        out['widevector.compat'].topaccent = ACC_CENTER

    positioning.install_source_kerns(sources)

    if LARGE_POLICY == 'source':
        for _cp in L.HORIZONTAL:
            _forms = horiz_variants.get(uni_owner.get(_cp), ())
            for _gn in _forms if _cp in (0x23DE, 0x23DF) else _forms[1:]:
                _new = (
                    _cp in (0x23DE, 0x23DF)
                    or out[_gn].width > MAXWIDTH
                    or (
                        _cp == 0x23DC
                        and any('.' + t in _gn for t in ('exe', 'exg'))
                    )
                )
                if _new and _gn not in accent_glyphs:
                    out[_gn].topaccent = out[_gn].width // 2

    # Normal Unicode primes use the scaled source-S attachment. Their
    # old T-size source attachment must not overwrite this
    # transformation.
    for name, value in prime_accents.items():
        out[name].topaccent = value

    # GDEF marks combining accents as marks and other glyphs as bases.
    for _g in out.glyphs():
        _u = _g.unicode
        if _u == -1 and _g.altuni:
            _u = _g.altuni[0][0]
        if (
            _g.glyphname in accent_glyphs
            or (0x0300 <= _u <= 0x036F)
            or (0x20D0 <= _u <= 0x20F0)
        ):
            _g.glyphclass = 'mark'
        else:
            _g.glyphclass = 'baseglyph'


def check_native_ranges(sources):
    out = sources.font
    for _g in out.glyphs():
        for _p in [p for c in _g.foreground for p in c]:
            L.field_range(_g.glyphname + '.x', _p.x, -32768, 32767)
            L.field_range(_g.glyphname + '.y', _p.y, -32768, 32767)
        for _i, _v in enumerate(_g.boundingBox()):
            L.field_range(_g.glyphname + '.bbox[%d]' % _i, _v, -32768, 32767)
        L.field_range(_g.glyphname + '.advance', _g.width, 0, 65535)
