"""Native variant/assembly and composite geometry, in dependency order."""
from dataclasses import dataclass, field
from fractions import Fraction

import psMat

import uni_map as U
import large_variant_policy as L
from ff_sources import uname


@dataclass(frozen=True)
class VariantLimits:
    condition: str
    # Source also uses these caps for selected fallback branches.
    max_height: int = 5580
    max_width: int = 12000
    connector_tolerance: int = 8


@dataclass
class Variants:
    vertical: dict
    horizontal: dict
    assemblies: dict
    connector_limits: dict
    brace_fallbacks: set = field(default_factory=set)


@dataclass(frozen=True)
class Accents:
    glyphs: set
    slots: tuple
    center: int


def compose_glyph(sources, uni, name, ref, offsets, adv):
    """Compose copies of a reference glyph at the given offsets."""
    out, uni_owner = sources.font, sources.uni_owner
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


def build_variants(sources, limits, op_variants, geometry):
    LARGE_POLICY = limits.condition
    MAXVAR = limits.max_height
    MAXWIDTH = limits.max_width
    fonts = sources.faces
    import_glyph = sources.import_glyph
    imported = sources.imported
    out = sources.font
    piece = sources.piece
    recenter_on_axis = sources.recenter_on_axis
    uni_owner = sources.uni_owner

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

    vert_variants = {}     # base gname -> [gnames]
    vert_assembly = {}  # base -> [(glyph, extender)], bottom to top
    # Cap generic connector estimates with local source
    # geometry where needed.
    connector_limits = {}

    def build_vdelim(basespec, exastart, base_uni=None, base_name=None):
        tag, slot = basespec
        base = import_glyph(tag, slot, name=base_name, unicode_=base_uni)
        if base is None or 'exa' not in fonts:
            return
        _, tfm, _ = fonts['exa']
        seq, vc = exa_chain(exastart)
        var = [base]
        for c in seq:
            # A TeX VARCHAR slot selects an assembly,
            # not a fixed-size variant.
            is_terminal_piece = (
                bool(tfm.chars.get(c, {}).get('varchar'))
                or (
                    vc is not None and c == seq[-1]
                    and c in (vc.get('TOP'), vc.get('BOT'), vc.get('MID'))
                    and c != vc.get('REP')
                )
            )
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
                # Repeat-only recipes use the same glyph as fixed ends
                # and a central extender.
                rep = parts[0][0]
                parts = [(rep, 0), (rep, 1), (rep, 0)]
            if parts:
                vert_assembly[base] = parts

    for u, (bspec, ex0) in U.V_DELIMS.items():
        build_vdelim(bspec, ex0, base_uni=u)
    for nm, (bspec, ex0) in U.V_DELIMS_ALT.items():
        build_vdelim(bspec, ex0, base_name=nm)

    if LARGE_POLICY == 'source' and 'exa' in fonts:
        # Plain's moustaches are VARCHAR recipes. Their terminal glyphs
        # alone are incomplete; make independent, complete Unicode
        # roots from the raw ends.
        for cp, bottom_slot, top_slot in (
            (0x23B0, 140, 137), (0x23B1, 139, 138)
        ):
            bottom, top, rep = piece(bottom_slot), piece(top_slot), piece(141)
            root = uname(cp)
            out.createChar(cp, root)
            g = out[root]
            bb, tb = out[bottom].boundingBox(), out[top].boundingBox()
            # The lower source end's upper stem reach
            # supplies the join overlap.
            overlap = max(0, min(bb[3], tb[3] - tb[1]))
            g.addReference(bottom, psMat.translate(0, -bb[1]))
            g.addReference(
                top, psMat.translate(0, bb[3] - bb[1] - overlap - tb[1])
            )
            g.width = out[bottom].width
            g.unlinkRef()
            uni_owner[cp] = root
            vert_variants[root] = [root]
            vert_assembly[root] = [(bottom, 0), (rep, 1), (top, 0)]
        rep = piece(141)
        root = uname(0x23AA)
        out.createChar(0x23AA, root)
        out[root].addReference(rep)
        out[root].width = out[rep].width
        out[root].unlinkRef()
        uni_owner[0x23AA] = root
        vert_variants[root] = [root]
        vert_assembly[root] = [(rep, 0), (rep, 1), (rep, 0)]

        # The broken TFM NEXTLARGER paths for the eight morphed designs
        # are not followed. Import only their raw outlines/TFM
        # advances for fixed cv19.
        for slot in range(182, 190):
            if import_glyph('exa', slot, name=f'exa.morphed{slot}') is None:
                raise RuntimeError('missing morphed source exa:%d' % slot)

    vert_variants.update(op_variants)

    # Extend variant ladders from the
    # package-selected extension families.
    EXT_TAGS = ('exe', 'exf', 'exg')

    def chain_slots(tfm, start):
        """Follow the TFM NEXTLARGER chain."""
        out, seen, s = [], set(), start
        while s is not None and s in tfm.chars and s not in seen:
            seen.add(s)
            out.append(s)
            s = tfm.chars[s].get('next')
        if s is not None:
            raise ValueError('broken NEXTLARGER chain: %s' % s)
        return out

    def chain_heads(tfm):
        """Return slots with no incoming NEXTLARGER link."""
        targets = {
            c['next'] for c in tfm.chars.values() if c.get('next') is not None
        }
        return {s for s in tfm.chars if s not in targets}

    def extend_chain(base_gname, slot, table, size_key, identity=None):
        """Append an extension chain only when its head matches the base
        source.
        """
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
                # Compare height for vertical variants and advance
                # for horizontal variants.
                if size_key == 'h':
                    extent, cap = bb[3] - bb[1], MAXVAR
                else:
                    extent, cap = out[g].width, MAXWIDTH
                if (
                    not L.exempt(LARGE_POLICY, identity, size_key)
                    and cap
                    and extent > cap
                ):
                    # Discard oversized variants and import records.
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
                  (
                      lambda gn: out[gn].boundingBox()[3]
                      - out[gn].boundingBox()[1]
                  )
            head, rest = table[base_gname][0], table[base_gname][1:]
            table[base_gname] = [head] + sorted(rest, key=key)
        return added

    # Only extend matching chain heads; brackets, floors,
    # and ceilings have none.
    for u, (bspec, ex0) in U.V_DELIMS.items():
        if u not in uni_owner:
            continue
        base = uni_owner[u]
        extend_chain(base, ex0, vert_variants, 'h', identity=u)

    # Horizontal variants and brace assemblies.
    horiz_variants = {}
    for u, chain in U.H_CHAINS.items():
        gnames = []
        for tag, slot in chain:
            if tag not in fonts:
                continue
            g = import_glyph(
                tag, slot, unicode_=u if not gnames else None, name=None
                if not gnames else None
            )
            if g:
                gnames.append(g)
        if len(gnames) >= 1:
            horiz_variants[gnames[0]] = gnames

    # Keep public bar accents fixed. Private variants do not
    # remap standard commands.
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
                # The private finite bar keeps its advance and outline;
                # attachment is width/2.
                _wg.width = out[_bar_base].width
                _wg.unlinkRef()
            uni_owner[_widebar_cp] = _widebar_name
            horiz_variants[_widebar_name] = [_widebar_name] + _bar_chain[1:]
        horiz_variants.pop(_bar_base, None)

    # Extend only matching wide-accent chains. Equal slots can
    # have different semantics.
    _WIDE_ACCENT_EXTENSION = (0x0302, 0x0303, 0x030C)
    for u in _WIDE_ACCENT_EXTENSION:
        chain = U.H_CHAINS.get(u, ())
        if u not in uni_owner:
            continue
        exa_slots = [slot for (tag, slot) in chain if tag == 'exa']
        if exa_slots:
            extend_chain(
                uni_owner[u], exa_slots[0], horiz_variants, 'w', identity=u
            )

    # Use the designated mt2exf overparen
    # continuation at its source scale.
    if 0x23DC in uni_owner and 'exf' in fonts:
        base = uni_owner[0x23DC]
        extra = []
        for slot in range(177, 184):
            g = import_glyph('exf', slot, name=f'{base}.exf{slot}')
            if not g:
                continue
            if (
                not L.exempt(LARGE_POLICY, 0x23DC, 'w')
                and MAXWIDTH
                and out[g].width > MAXWIDTH
            ):
                imported.pop(('exf', slot), None)
                out.removeGlyph(out[g])
                continue
            extra.append(g)
        if extra:
            vals = horiz_variants.get(base, [base]) + extra
            # Deduplicate equal-width stages while preserving
            # the first source form.
            seen_w = set()
            dedup = []
            for gn in sorted(vals, key=lambda q: out[q].width):
                w = out[gn].width
                if w in seen_w:
                    continue
                seen_w.add(w)
                dedup.append(gn)
            horiz_variants[base] = dedup

        # Bridge the fixed overparen ladders with an assembly derived
        # from the local outline.

        def _make_overparen_parts():
            left = 'overparen.left.mt2'
            ext = 'overparen.ext.mt2'
            right = 'overparen.right.mt2'

            try:
                tpl = geometry['overparen_template']
                ops = tpl['path']
            except Exception as exc:
                raise RuntimeError(
                    'local overparen source geometry is missing'
                ) from exc
            expected_ops = (
                'moveTo', 'lineTo', 'curveTo', 'curveTo', 'lineTo', 'curveTo',
                'curveTo', 'closePath'
            )
            if tuple(rec.get('op') for rec in ops) != expected_ops:
                raise RuntimeError(
                    'unexpected local MTPro2 overparen contour topology'
                )

            def ipoints(i):
                pts = []
                for x, y in ops[i]['points']:
                    if round(x) != x or round(y) != y:
                        raise RuntimeError(
                            'non-integral local Type1 overparen coordinate'
                        )
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
                    'local overparen source contour is not the expected '
                    'symmetric-cap topology'
                )
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

    # widearc switches to exe:208 and exf/exg:177 in the original
    # package. The old overparen continuation is retained;
    # equal sizes stay distinct.
    if LARGE_POLICY == 'source' and 0x23DC in uni_owner:
        # Standalone \arc uses exa:195. Keep it outside the automatic
        # widearc construction; fixed_selectors exposes it as
        # the appended cv15 stage.
        if import_glyph('exa', 195, name='exa.arc195') is None:
            raise RuntimeError('source exa:195 missing')
        _base = uni_owner[0x23DC]
        for _tag, _head in (('exe', 208), ('exf', 177), ('exg', 177)):
            for _slot in chain_slots(fonts[_tag][1], _head):
                _g = import_glyph(_tag, _slot, name=f'{_base}.{_tag}{_slot}')
                if _g not in horiz_variants[_base]:
                    horiz_variants[_base].append(_g)
    return Variants(
        vert_variants, horiz_variants, vert_assembly, connector_limits
    )


def build_accents_and_dots(sources):
    SOURCE_POLICY = sources.rules
    _axis_height = sources.axis_height
    _mu_to_units = sources.mu_to_units
    _pt_to_units = sources.pt_to_units
    compose = lambda *args: compose_glyph(sources, *args)
    fonts = sources.faces
    imported = sources.imported
    out = sources.font
    uni_owner = sources.uni_owner
    _NORMALIZED_ACCENT_MACROS = (
        'grave', 'acute', 'check', 'breve', 'bar', 'hat', 'dot', 'tilde',
        'ddot', 'mathring', 'vec', 'dotup', 'ddotup', 'dddot', 'ddddot',
        'dddotup', 'ddddotup',
    )
    try:
        ACCENT_SLOTS = [
            SOURCE_POLICY.accents[name].slot
            for name in _NORMALIZED_ACCENT_MACROS
        ]
    except KeyError as exc:
        raise RuntimeError(
            'required local MTPro2 accent declaration missing: %s'
            % exc.args[0]
        )
    accent_glyphs = set()
    ACC_CENTER = -(
        _axis_height() + round((fonts['exa'][1].fontdimen[8] * out.em) / 4)
    )
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

    if ('mit', 0x3A) in imported and ('syt', 0x01) in imported:
        # Read dot geometry from the local package; horizontal
        # spacing uses math units.
        P = out[imported[('mit', 0x3A)]].width
        Cw = out[imported[('syt', 0x01)]].width
        per = imported[('mit', 0x3A)]
        cdo = imported[('syt', 0x01)]
        tfm_symbols = fonts['syt'][1]
        ellipsis_gap = _mu_to_units(Fraction(3, 1))
        compose(
            0x2026, None, per,
            [(0, 0), (P + ellipsis_gap, 0), (2 * (P + ellipsis_gap), 0)],
            3 * P + 2 * ellipsis_gap
        )
        compose(
            0x22EF, None, cdo,
            [(0, 0), (Cw + ellipsis_gap, 0), (2 * (Cw + ellipsis_gap), 0)],
            3 * Cw + 2 * ellipsis_gap
        )

        vstep = _pt_to_units(
            SOURCE_POLICY.dot_macros.vdots_step_pt, tfm_symbols
        )
        compose(0x22EE, None, per, [(0, 0), (0, vstep), (0, 2 * vstep)], P)

        diagonal_gap = _mu_to_units(SOURCE_POLICY.dot_macros.ddots_inner_mu)
        raises = tuple(
            _pt_to_units(x, tfm_symbols)
            for x in SOURCE_POLICY.dot_macros.ddots_raises_pt
        )
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
    return Accents(accent_glyphs, tuple(ACCENT_SLOTS), ACC_CENTER)


def build_arrows_and_braces(sources, limits, variants, accents):
    CONNECTOR_PROFILE_TOLERANCE = limits.connector_tolerance
    LARGE_POLICY = limits.condition
    accent_glyphs = accents.glyphs
    connector_limits = variants.connector_limits
    fonts = sources.faces
    horiz_variants = variants.horizontal
    import_glyph = sources.import_glyph
    imported = sources.imported
    out = sources.font
    piece = sources.piece
    uni_owner = sources.uni_owner
    vert_assembly = variants.assemblies
    ARROW_CONNECTOR = 200

    def _trim_hconnector(src, suffix, connect_left=False, connect_right=False):
        """Create an unencoded assembly-only copy with connector
        sidebearings removed.
        """
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
            # The right connector ends at actual ink, not at
            # the source advance edge.
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
        return gn, 0, (
            conn if left else 0
        ), (conn if right else 0), out[gn].width

    def _resolve_arrow_parts(part_spec, suffix):
        raw = []
        for kind, ref in part_spec:
            gn = _resolve_harrow_ref(ref)
            if gn is None:
                return None
            raw.append((gn, kind == 'E'))
        return [
            _arrow_component(gn, i, len(raw), ext, suffix)
            for i, (gn, ext) in enumerate(raw)
        ]

    def harrow_assembly(base_uni, part_spec):
        if base_uni not in uni_owner:
            return
        tups = _resolve_arrow_parts(part_spec, f'U{base_uni:04X}')
        if tups:
            out[uni_owner[base_uni]].horizontalComponents = tuple(tups)

    # Arrow fills use fixed ends and an extender
    # from the MTPro2 outlines.
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

    # Mapsto uses dedicated short/long source glyphs, not an
    # arbitrary-width assembly.
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

        # Keep public U+20D7 fixed; private U+E287 carries the
        # accent-height assembly. Standard commands are not remapped
        # to the private adapter.
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

        # The right vector starts with its endpoint;
        # shaft_acc supplies extra width.
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
            # Standard braces use mt2exa corners and rules, separate
            # from overcbrace designs. Read the rule band from the
            # local braceld TFM height.
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

            _OVERBRACE_TARGET_YMIN = 539  # OpenType/Word migration policy
            over_ymin = min(
                out[q].boundingBox()[1] for q in (bld, ext, over_center, brd)
            )
            over_dy = round(_OVERBRACE_TARGET_YMIN - over_ymin)
            over_left = shifted_copy(bld, 'brace.over.left', over_dy)
            over_ext = shifted_copy(ext, 'brace.over.ext', over_dy)
            over_center_shift = shifted_copy(
                over_center, 'brace.over.center.shift', over_dy
            )
            over_right = shifted_copy(brd, 'brace.over.right', over_dy)

            # Cap curved-part connectors at the local straight rule band
            # minus tolerance. Extenders expose their full rule width.
            brace_fixed_connector = max(
                0, brace_rule_h - CONNECTOR_PROFILE_TOLERANCE
            )
            for q in (
                bld, brd, blu, bru, over_left, over_center_shift, over_right,
                over_center, under_center
            ):
                connector_limits[q] = brace_fixed_connector
            connector_limits[ext] = out[ext].width
            connector_limits[over_ext] = out[over_ext].width
            brace_extenders = {ext, over_ext}

            for u, parts in [
                (
                    0x23DE,
                    [
                        over_left, over_ext, over_center_shift, over_ext,
                        over_right
                    ]
                ),
                (0x23DF, [blu, ext, under_center, ext, bru])
            ]:
                gn = uname(u)
                if gn not in out:
                    out.createChar(u, gn)
                g = out[gn]
                # Build a small fallback; the assembly
                # handles arbitrary widths.
                fixed = [q for q in parts if q != ext]
                x = 0
                for q in fixed:
                    g.addReference(q, psMat.translate(x, 0))
                    x += out[q].width
                g.width = x
                uni_owner[u] = gn
                horiz_variants[gn] = [gn]
                vert_assembly[('H', gn)] = [
                    (q, 1 if q in brace_extenders else 0) for q in parts
                ]

            if LARGE_POLICY == 'source':
                # Plain's dedicated middle pieces have a different
                # advance from the ordinary two-half cusp. Keep the
                # new assemblies isolated.
                for cp, middle_slot, source_parts, shift in (
                    (0x23DE, 135, (bld, ext, None, ext, brd), over_dy),
                    (0x23DF, 134, (blu, ext, None, ext, bru), 0)
                ):
                    middle = piece(middle_slot)
                    if middle is None:
                        raise RuntimeError(
                            'missing plain brace middle exa:%d' % middle_slot
                        )
                    label = 'over' if cp == 0x23DE else 'under'
                    # Translate each overbrace part by the ordinary
                    # brace's documented baseline offset;
                    # no contour is reshaped.

                    def plain_part(source, suffix):
                        return shifted_copy(
                            source, 'brace.plain.' + label + '.' + suffix,
                            shift
                        )
                    parts = [
                        plain_part(
                            q, 'left' if i==0 else 'right'
                            if i==4 else 'middle' if i==2 else 'ext'
                        )
                        for i, q in enumerate(source_parts) if q is not None
                    ]
                    center = plain_part(middle, 'middle')
                    left, rule, right = parts[0], parts[1], parts[-1]
                    root = 'brace.plain.' + label
                    out.createChar(-1, root)
                    g = out[root]
                    x = 0
                    for q in (left, center, right):
                        g.addReference(q, psMat.translate(x, 0))
                        x += out[q].width
                    g.width = x
                    g.unlinkRef()
                    # Bound the original 116-unit joining rule by the
                    # measured edge profile of each source piece.
                    for q in (left, center, right):
                        connector_limits[q] = max(
                            0, brace_rule_h - CONNECTOR_PROFILE_TOLERANCE
                        )
                    connector_limits[rule] = out[rule].width
                    vert_assembly[('H', root)] = [
                        (left, 0), (rule, 1), (center, 0), (rule, 1),
                        (right, 0)
                    ]

    # Original overcbrace/undercbrace select these complete designs by
    # width. Preserve the original fallback glyph and construction. The
    # source Unicode entrance uses the smallest dedicated glyph, so
    # fallback cannot exceed the first fixed variant. Names continue to
    # identify the original source import.
    _source_brace_fallbacks = set()
    if LARGE_POLICY == 'source':
        for _cp, _series in (
            (
                0x23DF,
                (('exe', 144, 160), ('exf', 144, 155), ('exg', 144, 149))
            ),
            (
                0x23DE,
                (('exe', 176, 192), ('exf', 160, 171), ('exg', 160, 165))
            )
        ):
            _base = uni_owner[_cp]
            for _tag, _first, _last in _series:
                for _slot in range(_first, _last + 1):
                    _gn = import_glyph(
                        _tag, _slot, name=f'{_base}.curly.{_tag}{_slot}'
                    )
                    if _gn is None:
                        raise ValueError(
                            'missing dedicated curly brace %s:%d'
                            % (_tag, _slot)
                        )
                    # Adopt the existing public overbrace baseline
                    # convention; underbraces keep the
                    # scaled source baseline.
                    if _cp == 0x23DE:
                        _bb = out[_gn].boundingBox()
                        out[_gn].transform(
                            psMat.translate(0, round(539 - _bb[1]))
                        )
                    horiz_variants[_base].append(_gn)
            _source_brace_fallbacks.add(_base)
            _new_base = imported[(_series[0][0], _series[0][1])]
            out[_base].unicode = -1
            out[_new_base].unicode = _cp
            uni_owner[_cp] = _new_base
            horiz_variants[_new_base] = horiz_variants[_base][1:]
            vert_assembly[('H', _new_base)] = list(vert_assembly[('H', _base)])
    variants.brace_fallbacks = _source_brace_fallbacks


def install_variant_geometry(sources, limits, variants):
    CONNECTOR_PROFILE_TOLERANCE = limits.connector_tolerance
    LARGE_POLICY = limits.condition
    _source_brace_fallbacks = variants.brace_fallbacks
    connector_limits = variants.connector_limits
    horiz_variants = variants.horizontal
    out = sources.font
    uni_owner = sources.uni_owner
    vert_assembly = variants.assemblies
    vert_variants = variants.vertical

    def glyph_size(gname):
        bb = out[gname].boundingBox()
        return bb[3] - bb[1]

    for base, var in vert_variants.items():
        var2 = sorted(dict.fromkeys(var), key=glyph_size)
        if len(var2) > 1 or base in vert_assembly:
            out[base].verticalVariants = ' '.join(var2)
    for base, var in horiz_variants.items():
        var2 = sorted(
            dict.fromkeys(var),
            key=(lambda g: out[g].boundingBox()[2] - out[g].boundingBox()[0])
            if LARGE_POLICY == 'source' else (lambda g: out[g].width)
        )
        if base in _source_brace_fallbacks:
            # The legacy brace base is an assembly fallback, not a fixed
            # variant. Keep its outline, but do not interleave that
            # generic design with curly forms.
            var2 = [g for g in var2 if g != base]
        if len(var2) > 1:
            out[base].horizontalVariants = ' '.join(var2)

    # Measure stable connector runs from flattened outline
    # cross-sections. TFM recipes provide no overlap lengths.

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
                x0, y0, _ = seq[i]
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
                            xx = (
                                (1 - t)**2
                                * x0 + 2 * (1 - t) * t * cx + t
                                * t * x3
                            )
                            yy = (
                                (1 - t)**2
                                * y0 + 2 * (1 - t) * t * cy + t
                                * t * y3
                            )
                        else:
                            c1, c2 = ctrl[0], ctrl[-1]
                            xx = ((1 - t)**3 * x0 + 3 * (1 - t)**2 * t * \
                                  c1[0]
                                  + 3 * (1 - t) * t * t * c2[0] + t ** 3
                                  * x3)
                            yy = ((1 - t)**3 * y0 + 3 * (1 - t)**2 * t * \
                                  c1[1]
                                  + 3 * (1 - t) * t * t * c2[1] + t ** 3
                                  * y3)
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

    def connector_run(
        gname, vertical, at_end, tol=CONNECTOR_PROFILE_TOLERANCE
    ):
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
            if (
                cur is None
                or abs(cur[0] - ref[0]) > tol
                or abs(cur[1] - ref[1]) > tol
            ):
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
            if i or e:
                _runs.append(connector_run(p, vert, False))
            if i < n - 1 or e:
                _runs.append(connector_run(p, vert, True))
    _ov = int(getattr(out.math, 'MinConnectorOverlap', 100) or 100)
    if _runs and min(_runs) < _ov:
        out.math.MinConnectorOverlap = max(0, int(min(_runs)))

    for base, parts in vert_assembly.items():
        if isinstance(base, tuple):  # Horizontal assemblies.
            _, gname = base
            # Only joining edges have connectors; outside fixed edges
            # must have zero length.
            tups = []
            n = len(parts)
            for i, (p, e) in enumerate(parts):
                q = list(part_tuple(p, e, vertical=False))
                if i == 0 and not e:
                    q[2] = 0              # StartConnectorLength
                if i == n - 1 and not e:
                    q[3] = 0              # EndConnectorLength
                tups.append(tuple(q))
            out[gname].horizontalComponents = tuple(tups)
        else:
            # Extenders need both connectors even
            # at an assembly boundary.
            parts = [(_norm_vpart(p), e) for (p, e) in parts]
            tups = []
            n = len(parts)
            for i, (p, e) in enumerate(parts):
                bb = out[p].boundingBox()
                full = round(bb[3] - bb[1])
                start = (
                    0 if i == 0 and not e else connector_run(p, True, False)
                )
                end = (
                    0 if i == n - 1 and not e else connector_run(p, True, True)
                )
                tups.append((p, e, start, end, full))
            out[base].verticalComponents = tuple(tups)

    # Extended shapes include larger variants, assembly parts,
    # and display operators.
    extended = set()
    for base, var in vert_variants.items():
        extended.update(var[1:])
    for base, parts in vert_assembly.items():
        if not isinstance(base, tuple):
            extended.update(p for (p, _) in parts)
    # Mark the base integral family ExtendedShape for OpenType
    # script/limit placement.
    for _u in range(0x222B, 0x2234):
        if _u in uni_owner:
            extended.add(uni_owner[_u])
    for gname in extended:
        try:
            out[gname].isExtendedShape = True
        except Exception as exc:
            raise ValueError(f'ExtendedShape {gname}: {exc}') from exc


def build_word_primes(sources, ssty_map, geometry):
    SCRIPT_RATIO = sources.rules.script_ratio
    compose = lambda *args: compose_glyph(sources, *args)
    fonts = sources.faces
    imported = sources.imported
    out = sources.font
    uni_owner = sources.uni_owner
    PRIME_SHIFT = None
    PRIME_PADDING_EVIDENCE = None
    if 0x2032 in uni_owner:
        xh_u = round(fonts['syt'][1].fontdimen[5] * 1000)
        SUP_SHIFT = round(fonts['syt'][1].fontdimen[14] * out.em)
        try:
            PRIME_PADDING_EVIDENCE = dict(geometry['prime_padding'])
            PRIME_SHIFT = int(PRIME_PADDING_EVIDENCE['padding'])
        except Exception as exc:
            raise RuntimeError(
                'local prime-padding source geometry is missing'
            ) from exc
        _script_scale = float(SCRIPT_RATIO)
        _targets = [uni_owner[0x2032]]
        if ('ams', 0x38) in imported:
            _targets.append(imported[('ams', 0x38)])
        for _base in _targets:
            _s1 = _base + '.ssty1'
            if _s1 not in out:
                # script design absent: scale and raise the base glyph.
                _g = out[_base]
                _g.transform(psMat.scale(_script_scale))
                _bb = _g.boundingBox()
                _g.transform(psMat.translate(PRIME_SHIFT, xh_u - _bb[1]))
                _g.width = round(_g.width)
                continue
            # base := local package script-size design scaled by
            # the local script ratio
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
            _g1 = out[_s1]
            _b1 = _g1.boundingBox()
            _g1.transform(
                psMat.translate(
                    0, (_base_y0 - SUP_SHIFT) / _script_scale - _b1[1]
                )
            )
            # Keep the native scriptscript outline and
            # metrics imported by add_ssty.
        pr = uni_owner[0x2032]
        PW = out[pr].width
        if pr + '.ssty1' in out:
            # Use the scaled local script-design advance between primes.
            st = round(out[pr + '.ssty1'].width * _script_scale)
        else:
            st = round(PW - PRIME_SHIFT)
        compose(0x2033, None, pr, [(0, 0), (st, 0)], PW + st)
        compose(0x2034, None, pr, [(0, 0), (st, 0), (2 * st, 0)], PW + 2 * st)
        compose(
            0x2057, None, pr, [(0, 0), (st, 0), (2 * st, 0), (3 * st, 0)],
            PW + 3 * st
        )
        # Compose repeated script primes from their
        # matching optical forms.
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
        # Ligate raw repeated primes to avoid repeating collision
        # padding. Pair adjustment covers shapers that skip the
        # ligature; TeX scripts bypass it.
        out.addLookup(
            'primelig', 'gsub_ligature', (),
            (
                (
                    'ccmp',
                    (
                        ('DFLT', ('dflt',)), ('latn', ('dflt',)),
                        ('math', ('dflt',))
                    )
                ),
            )
        )
        out.addLookupSubtable('primelig', 'primelig-1')
        for _u, _n in (
            (0x2057, 4), (0x2034, 3), (0x2033, 2)
        ):  # Match longer sequences first.
            _lig = uni_owner.get(_u)
            if _lig:
                out[_lig].addPosSub('primelig-1', tuple([pr] * _n))
        out.addLookup(
            'primekern', 'gpos_pair', (),
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
        out.addLookupSubtable('primekern', 'primekern-1')
        out[pr].addPosSub('primekern-1', pr, 0, 0, -PRIME_SHIFT, 0, 0, 0, 0, 0)
    return PRIME_SHIFT
