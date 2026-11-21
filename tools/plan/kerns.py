"""Kerning (design document, section 4.4)."""

from collections import defaultdict

from plan.metrics import tfm_char, units


def plan_kerns(design, sources, glyphs):
    """Copy the TFM kerns to every pair of glyphs made from the slots."""
    by_slot = defaultdict(list)
    for glyph in glyphs:
        if glyph.origin:
            by_slot[glyph.origin].append(glyph.name)
    kerns = {}
    for (source, slot), lefts in by_slot.items():
        scale = design.role_of(source).scale
        skew = sources.package.skewchar(source)
        char = tfm_char(design, sources, source, slot)
        for right_slot, kern in char.kerns.items():
            # A kern with the skew character positions accents.
            if right_slot == skew or not units(kern * scale):
                continue
            for right in by_slot.get((source, right_slot), ()):
                for left in lefts:
                    kerns[left, right] = units(kern * scale)
    return kerns
