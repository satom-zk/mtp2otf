"""Native optical routes, MATH/spacing and final metric boundaries."""
import psMat

import uni_map as U
import source_policy
import large_variant_policy as L
import math_constants
from compatibility_metrics import assign_windows
from ff_constructions import compose_glyph


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
    # Derive the display threshold from the local
    # text/display summation sizes.
    _op_text = fonts['exa'][1].chars.get(0x50)
    _op_display = fonts['exa'][1].chars.get(0x58)
    if not _op_text or not _op_display:
        raise SystemExit(
            'local extension TFM lacks the summation size pair required for '
            'MATH policy'
        )
    _op_text_size = round((_op_text['ht'] + _op_text['dp']) * out.em)
    _op_display_size = round((_op_display['ht'] + _op_display['dp']) * out.em)
    _display_operator_min_height = (_op_text_size + _op_display_size) // 2

    C = math_constants.compute(
        sy_fd, ex_fd, script_sy=fonts['syt_s'][1].fontdimen,
        script_ratio=SCRIPT_RATIO, scriptscript_ratio=SCRIPTSCRIPT_RATIO,
        display_operator_min_height=_display_operator_min_height, quad=out.em,
    )
    MINOVL = C.pop('MinConnectorOverlap')

    FF_NAMES = {
        'FractionNumDisplayStyleGapMin': 'FractionNumeratorDisplayStyleGapMin',
        'FractionDenomDisplayStyleGapMin': (
            'FractionDenominatorDisplayStyleGapMin'
        )
    }
    for k, v in C.items():
        try:
            setattr(out.math, FF_NAMES.get(k, k), int(v))
        except AttributeError as exc:
            # Only these scalars are restored from
            # the snapshot by finalize.
            if k not in (
                'ScriptPercentScaleDown', 'ScriptScriptPercentScaleDown',
                'SpaceAfterScript'
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
                g = import_glyph(t, slot, name=f'{base}.ssty{lvl}')
                if g:
                    alts.append(g)
            if alts:
                ssty_map[base] = alts

    add_ssty('mit', 'mit_s', 'mit_ss', U.MIT)
    add_ssty('syt', 'syt_s', 'syt_ss', U.SYT)
    add_ssty('ams', 'ams_s', 'ams_ss', U.AMSA)
    add_ssty('bb', 'bb_s', 'bb_ss', U.alpha_map('bb'))
    # Import option-family script sources so cv03..cv07
    # preserve optical designs.
    for _core, _s, _ss in (
        ('bbd', 'bbd_s', 'bbd_ss'), ('bbi', 'bbi_s', 'bbi_ss'),
        ('hrb', 'hrb_s', 'hrb_ss'), ('hrbd', 'hrbd_s', 'hrbd_ss'),
        ('hbi', 'hbi_s', 'hbi_ss')
    ):
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
    add_ssty('bscript', 'bscript_s', 'bscript_ss', U.alpha_map('bscript'))
    add_ssty('bfrak', 'bfrak_s', 'bfrak_ss', U.alpha_map('bfrak'))
    # Donor mathematical bold has no mt2mb* script
    # substitutions; mbf is separate.
    add_ssty('curly', 'curly_s', 'curly_ss', U.alpha_map('curly'))
    add_ssty('bmit', 'bmit_s', 'bmit_ss', U.MIT)
    add_ssty('bsyt', 'bsyt_s', 'bsyt_ss', U.SYT)

    # Normalize script accents and use their own
    # source-family skew kern.
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
    for tag in (
        'mit_s', 'mit_ss', 'syt_s', 'syt_ss', 'bmit_s', 'bmit_ss', 'bsyt_s',
        'bsyt_ss', 'bb_s', 'bb_ss', 'bbi_s', 'bbi_ss', 'bbd_s', 'bbd_ss',
        'hrb_s', 'hrb_ss', 'hrbd_s', 'hrbd_ss', 'hbi_s', 'hbi_ss', 'script_s',
        'script_ss', 'frak_s', 'frak_ss', 'bscript_s', 'bscript_ss', 'bfrak_s',
        'bfrak_ss', 'curly_s', 'curly_ss', 'bold_s', 'bold_ss'
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
                w = tfm.chars[slot]['wd']
                ic = tfm.chars[slot].get('ic') or 0.0
                out[gname].topaccent = round(((w + ic) / 2 + kern) * 1000)
            except Exception as exc:
                raise ValueError(f'TopAccent {gname}: {exc}') from exc
    return ssty_map


def install_optical_routes(sources, ssty_map, alphabet):
    bold_dotless_i = alphabet.bold_dotless_i
    bold_dotless_j = alphabet.bold_dotless_j
    bold_it_latin = alphabet.bold_italic
    fonts = sources.faces
    import_glyph = sources.import_glyph
    imported = sources.imported
    out = sources.font
    uni_owner = sources.uni_owner
    upright_dotless = alphabet.upright_dotless_i
    upright_dotless_j = alphabet.upright_dotless_j
    if ssty_map:
        out.addLookup(
            'ssty', 'gsub_alternate', (),
            (
                (
                    'ssty',
                    (
                        ('DFLT', ('dflt',)), ('latn', ('dflt',)),
                        ('math', ('dflt',))
                    )
                ),
            )
        )
        out.addLookupSubtable('ssty', 'ssty-1')
        for base, alts in ssty_map.items():
            try:
                out[base].addPosSub('ssty-1', tuple(alts))
            except Exception as exc:
                raise ValueError(f'ssty glyph {base}: {exc}') from exc

    # Dotless substitutions for italic i/j and upright i/j.
    dtls_pairs = []
    if 0x1D456 in uni_owner and 0x1D6A4 in uni_owner:
        dtls_pairs.append((uni_owner[0x1D456], uni_owner[0x1D6A4]))
    if 0x1D457 in uni_owner and 0x1D6A5 in uni_owner:
        dtls_pairs.append((uni_owner[0x1D457], uni_owner[0x1D6A5]))
    if 0x0069 in uni_owner and upright_dotless:
        dtls_pairs.append((uni_owner[0x0069], upright_dotless))
    if 0x006A in uni_owner:
        dtls_pairs.append((uni_owner[0x006A], upright_dotless_j))
    if bold_it_latin.get('i') and bold_dotless_i:
        dtls_pairs.append((bold_it_latin['i'], bold_dotless_i))
    if bold_it_latin.get('j') and bold_dotless_j:
        dtls_pairs.append((bold_it_latin['j'], bold_dotless_j))
    if dtls_pairs:
        out.addLookup(
            'dtls', 'gsub_single', (),
            (
                (
                    'dtls',
                    (
                        ('DFLT', ('dflt',)), ('latn', ('dflt',)),
                        ('math', ('dflt',))
                    )
                ),
            )
        )
        out.addLookupSubtable('dtls', 'dtls-1')
        for base, sub in dtls_pairs:
            out[base].addPosSub('dtls-1', sub)

    # Calligraphic salt maps Script to Curly.
    curly_pairs = []
    for slot, (u, name) in U.alpha_map('curly').items():
        key = ('curly', slot)
        if key in imported and ('script', slot) in imported:
            curly_pairs.append((imported[('script', slot)], imported[key]))
    # Keep varnothing in cv02 so calligraphic salt cannot change it.
    if curly_pairs:
        out.addLookup(
            'salt', 'gsub_alternate', (),
            (
                (
                    'salt',
                    (
                        ('DFLT', ('dflt',)), ('latn', ('dflt',)),
                        ('math', ('dflt',))
                    )
                ),
            )
        )
        out.addLookupSubtable('salt', 'salt-1')
        for base, alt in curly_pairs:
            try:
                out[base].addPosSub('salt-1', (alt,))
            except Exception as exc:
                raise ValueError(f'salt glyph {base}: {exc}') from exc

    # Expose alternate codepoints for the same glyph.
    for base_u, extra_u in [
        (0x007C, 0x2223), (0x2016, 0x2225), (0x1D715, 0x2202)
    ]:
        if base_u in uni_owner and extra_u not in uni_owner:
            g = out[uni_owner[base_u]]
            g.altuni = ((g.altuni or ()) + ((extra_u, -1, 0),))
            uni_owner[extra_u] = g.glyphname

    # Build cumulative spacing after all alphabet imports: hmtx keeps
    # CHARWD, MATH keeps CHARIC, and GPOS adds ordinary TFM kern plus
    # CHARIC(left). Exclude family skewchar-right pairs
    # from ordinary kerning.

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
    for cvn, tag in (
        ('cv03', 'bbd'), ('cv04', 'bbi'), ('cv05', 'hrb'), ('cv06', 'hrbd'),
        ('cv07', 'hbi')
    ):
        if tag not in fonts:
            continue
        pairs = []
        for slot, (u, nm) in U.alpha_map('bb').items():
            alt = import_glyph(tag, slot, name=f'{nm}.{tag}')
            if alt and u in uni_owner:
                base = uni_owner[u]
                pairs.append((base, alt))
                # Add script-form pairs for either shaping order: ssty
                # then cv, or cv then ssty.
                for lvl in (1, 2):
                    bb, aa = f'{base}.ssty{lvl}', f'{alt}.ssty{lvl}'
                    if bb in out and aa in out:
                        pairs.append((bb, aa))
        if not pairs:
            continue
        out.addLookup(
            cvn, 'gsub_single', (),
            (
                (
                    cvn,
                    (
                        ('DFLT', ('dflt',)), ('latn', ('dflt',)),
                        ('math', ('dflt',))
                    )
                ),
            )
        )
        out.addLookupSubtable(cvn, cvn + '-1')
        for base, alt in pairs:
            try:
                out[base].addPosSub(cvn + '-1', alt)
            except Exception as exc:
                raise ValueError(f'{cvn} glyph {base}: {exc}') from exc

    # cv02: slashed-zero and circular empty-set forms.
    if ('ams', 191) in imported and 0x2205 in uni_owner:
        out.addLookup(
            'cv02', 'gsub_single', (),
            (
                (
                    'cv02',
                    (
                        ('DFLT', ('dflt',)), ('latn', ('dflt',)),
                        ('math', ('dflt',))
                    )
                ),
            )
        )
        out.addLookupSubtable('cv02', 'cv02-1')
        try:
            out[uni_owner[0x2205]].addPosSub('cv02-1', imported[('ams', 191)])
        except Exception as exc:
            raise ValueError(f'cv02 glyph {uni_owner[0x2205]}: {exc}') from exc

    if zalt_pairs:
        out.addLookup(
            'cv01', 'gsub_single', (),
            (
                (
                    'cv01',
                    (
                        ('DFLT', ('dflt',)), ('latn', ('dflt',)),
                        ('math', ('dflt',))
                    )
                ),
            )
        )
        out.addLookupSubtable('cv01', 'cv01-1')
        for base, alt in zalt_pairs:
            try:
                out[base].addPosSub('cv01-1', alt)
            except Exception as exc:
                raise ValueError(f'cv01 glyph {base}: {exc}') from exc

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
        out.addLookup(
            tag, 'gsub_single', (),
            (
                (
                    tag,
                    (
                        ('DFLT', ('dflt',)), ('latn', ('dflt',)),
                        ('math', ('dflt',))
                    )
                ),
            )
        )
        out.addLookupSubtable(tag, tag + '-1')
        for base, alt in pairs:
            try:
                out[base].addPosSub(tag + '-1', alt)
            except Exception as exc:
                raise ValueError(f'{tag} glyph {base}: {exc}') from exc

    # cv08: straight braces.
    add_cv(
        'cv08',
        [
            (uni_owner.get(0x007B), 'braceleft.straight'),
            (uni_owner.get(0x007D), 'braceright.straight')
        ]
    )

    # cv09: AMS negated relations; defaults retain MTPro2 forms.
    add_cv(
        'cv09',
        [
            (uni_owner.get(u), imported.get(('ams', slot)))
            for u, slot in ((0x2241, 156), (0x2288, 170), (0x2289, 171))
        ]
    )

    # cv10: variant subsetneq and supsetneq.
    add_cv(
        'cv10',
        [
            (uni_owner.get(u), imported.get(('ams', slot)))
            for u, slot in ((0x228A, 160), (0x228B, 161))
        ]
    )

    # cv11: hbar and hslash.
    add_cv('cv11', [(uni_owner.get(0x210F), imported.get(('syt', 175)))])

    # cv12: slanted large operators.
    add_cv(
        'cv12',
        [
            (uni_owner.get(u), imported.get(('exa', slot)))
            for u, slot in ((0x2211, 160), (0x220F, 162), (0x2210, 164))
        ]
    )


def assign_private_codepoints(sources):
    alias_unicode = sources.alias_unicode
    compose = lambda *args: compose_glyph(sources, *args)
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
    for base, tag in (
        (0xE100, 'bbd'), (0xE140, 'bbi'), (0xE180, 'hrb'), (0xE1C0, 'hrbd'),
        (0xE200, 'hbi')
    ):
        PUA = base
        for slot, (u, nm) in sorted(U.alpha_map('bb').items()):
            if (tag, slot) in imported:
                pua(imported[(tag, slot)])

    # Keep private assignments fixed across editions;
    # missing glyphs leave holes.
    PUA_FIXED = {
        0xE23E: 'lhook', 0xE23F: 'rhook', 0xE240: 'varbeta.it',
        0xE241: 'vardelta.it', 0xE242: 'upvardelta', 0xE243: 'dbar.it',
        0xE244: 'updbar', 0xE245: 'negationslash', 0xE246: 'mapstochar',
        0xE247: 'tie.sy', 0xE248: 'compose', 0xE249: 'Relbar', 0xE24A: 'wwbar',
        0xE24B: 'dotup.accent', 0xE24C: 'ddotup.accent', 0xE24D: 'smallint',
        0xE24E: 'wbar', 0xE24F: 'what', 0xE250: 'wtilde', 0xE251: 'wcheck',
        0xE252: 'clubshaded', 0xE253: 'spadeshaded', 0xE254: 'dddotup.accent',
        0xE255: 'ddddotup.accent', 0xE256: 'hslash', 0xE257: 'simarrow',
        0xE258: 'varland', 0xE259: 'contraction', 0xE25A: 'circdashbullet',
        0xE25B: 'bulletdashcirc', 0xE25C: 'braceleft.straight',
        0xE25D: 'braceright.straight', 0xE25E: 'midshaft',
        0xE25F: 'rarrowhead', 0xE260: 'larrowhead', 0xE261: 'varpropto',
        0xE262: 'smallsmile', 0xE263: 'smallfrown', 0xE264: 'lvertneqq',
        0xE265: 'gvertneqq', 0xE266: 'nleqslant', 0xE267: 'ngeqslant',
        0xE268: 'npreceq', 0xE269: 'nsucceq', 0xE26A: 'nleqq', 0xE26B: 'ngeqq',
        0xE26C: 'nsim.ams', 0xE26D: 'varsubsetneq', 0xE26E: 'varsupsetneq',
        0xE26F: 'nsubseteqq', 0xE270: 'nsupseteqq', 0xE271: 'varsubsetneqq',
        0xE272: 'varsupsetneqq', 0xE273: 'nsubseteq.ams',
        0xE274: 'nsupseteq.ams', 0xE275: 'nshortmid', 0xE276: 'nshortparallel',
        0xE277: 'shortmid', 0xE278: 'shortparallel', 0xE279: 'thicksim',
        0xE27A: 'thickapprox', 0xE27B: 'nsqsubset', 0xE27C: 'nsqsupset',
        0xE27D: 'leadsto', 0xE27E: 'undercurvearrowleft',
        0xE27F: 'undercurvearrowright', 0xE280: 'capprod.big', 0xE281: 'slsum',
        0xE282: 'slprod', 0xE283: 'slcoprod', 0xE284: 'varland.big',
        0xE285: 'ast.big', 0xE286: 'wideoverbar.compat',
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


def assign_metrics(sources):
    fonts = sources.faces
    out = sources.font
    sy_fd = sources.faces['syt'][1].fontdimen
    out.ascent, out.descent = 800, 200
    # Use absolute FontForge metrics rather than offsets
    # from the bounding box.
    out.os2_typoascent_add = out.os2_typodescent_add = 0
    out.hhea_ascent_add = out.hhea_descent_add = 0
    out.os2_typoascent, out.os2_typodescent, out.os2_typolinegap = (
        806, -194, 200
    )
    out.hhea_ascent, out.hhea_descent, out.hhea_linegap = 806, -194, 200
    out.os2_xheight = round(sy_fd[5] * 1000)
    # Read cap height from the local math-italic TFM.
    cap_h = (
        round(fonts['mit'][1].chars[0x41]['ht'] * out.em)
        if 0x41 in fonts['mit'][1].chars else None
    )
    if cap_h:
        out.os2_capheight = cap_h
    # Cover all outlines with Windows clipping bounds; USE_TYPO_METRICS
    # controls spacing. Scan glyph bounds for compatibility
    # across FontForge versions.
    _bounds_y = assign_windows(out)
    return _bounds_y


def finish_source_features(sources, limits, accents, variants):
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
            'English (US)', 'Trademark',
            ('MathTime is a trademark of Publish or ' 'Perish, Inc.')
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
    # finalize.py sets the Windows-compatible technical font version.

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

    # Finalize TopAccent and ordinary spacing after all source and
    # alternate imports. Source roles, not nonzero IC alone, determine
    # ordinary-character membership.

    def _source_is_ordinary_left(tag, slot):
        return source_policy.is_ordinary_left(tag, slot)

    if 'wideoverbar.compat' in out:
        accent_glyphs.add('wideoverbar.compat')
    if 'widevector.compat' in out:
        accent_glyphs.add('widevector.compat')

    # Finite source accents retain positive advance
    # and attach at its center.
    _source_fixed_accent_names = frozenset((
        # Normalized dot accents instead retain zero advance and
        # ink-center attachment.
        'wbar', 'wwbar', 'what', 'wtilde', 'wcheck',
    ))
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
                _tfm.kerns.get((_slot, _sk), 0.0) or 0.0
            ) if _sk is not None else 0.0
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

    # Serialize TFM kern alone; add_ordinary_ic_gpos.py adds
    # the independent IC layer.
    out.addLookup(
        'kernL', 'gpos_pair', (),
        (
            (
                'kern',
                (
                    ('DFLT', ('dflt',)), ('latn', ('dflt',)),
                    ('math', ('dflt',))
                )
            ),
        )
    )
    out.addLookupSubtable('kernL', 'kern-1')
    _source_tfm_pairs = {}

    def _remember_source_tfm_pair(gl, gr, xadvance):
        key = (gl, gr)
        previous = _source_tfm_pairs.get(key)
        if previous is not None:
            if previous != xadvance:
                raise RuntimeError(
                    'conflicting source TFM kern %s/%s: %+d vs %+d' % (
                        gl, gr, previous, xadvance
                    )
                )
            return
        _source_tfm_pairs[key] = xadvance
        out[gl].addPosSub('kern-1', gr, 0, 0, xadvance, 0, 0, 0, 0, 0)

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
            _remember_source_tfm_pair(_gl, _gr, int(_k))

    # Only ordinary IC values cross the process
    # boundary to the GPOS producer.
    _ordinary_ic_left_by_glyph = {}
    for (_tag, _slot), _gname in sorted(imported.items()):
        if _tag not in SOURCE_SKEW or _tag not in fonts or _gname not in out:
            continue
        _pfb, _tfm, _slots = fonts[_tag]
        if _slot not in _tfm.chars or _slot not in _slots:
            continue
        _ic = round((_tfm.chars[_slot].get('ic') or 0.0) * 1000)
        if _ic and _source_is_ordinary_left(_tag, _slot):
            _previous = _ordinary_ic_left_by_glyph.get(_gname)
            if _previous is not None and _previous != int(_ic):
                raise RuntimeError(
                    'conflicting ordinary IC for %s: %d vs %d' % (
                        _gname, _previous, _ic
                    )
                )
            _ordinary_ic_left_by_glyph[_gname] = int(_ic)

    if LARGE_POLICY == 'source':
        for _cp in L.HORIZONTAL:
            _forms = horiz_variants.get(uni_owner.get(_cp), ())
            for _gn in (_forms if _cp in (0x23DE, 0x23DF) else _forms[1:]):
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
    return _ordinary_ic_left_by_glyph


def check_native_ranges(sources):
    out = sources.font
    for _g in out.glyphs():
        for _p in [p for c in _g.foreground for p in c]:
            L.field_range(_g.glyphname + '.x', _p.x, -32768, 32767)
            L.field_range(_g.glyphname + '.y', _p.y, -32768, 32767)
        for _i, _v in enumerate(_g.boundingBox()):
            L.field_range(_g.glyphname + '.bbox[%d]' % _i, _v, -32768, 32767)
        L.field_range(_g.glyphname + '.advance', _g.width, 0, 65535)
