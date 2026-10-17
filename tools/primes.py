"""Original S/SS prime geometry and ccmp sequences."""

from fractions import Fraction

import psMat

from constructions import compose_glyph


def build_primes(sources, ssty_map):
    """Use original S/SS primes; derive same-line forms from the S
    design.

    Placement of superscripts and preceding-character IC belongs to the
    engine. The returned attachments override only the transformed T
    forms.
    """
    out, imported, owners = sources.font, sources.imported, sources.uni_owner
    ratio = sources.rules.script_ratio
    scale = float(ratio)
    shift = round(sources.faces['syt'][1].fontdimen[13] * out.em)
    accents = {}
    targets = [('syt', 48, owners[0x2032])]
    if ('ams', 56) in imported:
        targets.append(('ams', 56, imported[('ams', 56)]))
    for tag, slot, base in targets:
        script = base + '.ssty1'
        tfm = sources.faces[tag + '_s'][1]
        width = round(tfm.chars[slot]['wd'] * out.em)
        italic = round((tfm.chars[slot].get('ic') or 0) * out.em)
        out.selection.select(script)
        out.copy()
        out.selection.select(base)
        out.paste()
        out[base].transform((scale, 0, 0, scale, 0, shift))
        out[base].width = round(ratio * width)
        # These source primes have centered attachment and no skew pair.
        accents[base] = round(ratio * Fraction(width + italic, 2))

    prime = owners[0x2032]
    source_width = round(sources.faces['syt_s'][1].chars[48]['wd'] * out.em)
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
        for level, role in ((1, 'syt_s'), (2, 'syt_ss')):
            original = prime + '.ssty' + str(level)
            width = round(sources.faces[role][1].chars[48]['wd'] * out.em)
            name = base + '.ssty' + str(level)
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
        'primelig',
        'gsub_ligature',
        (),
        (
            (
                'ccmp',
                (
                    ('DFLT', ('dflt',)),
                    ('latn', ('dflt',)),
                    ('math', ('dflt',)),
                ),
            ),
        ),
    )
    out.addLookupSubtable('primelig', 'primelig-1')
    for cp, count in ((0x2057, 4), (0x2034, 3), (0x2033, 2)):
        out[owners[cp]].addPosSub('primelig-1', tuple([prime] * count))
    return accents
