"""Assemble the font plan."""

import unicodedata

from outline import moved
from plan import names, product
from plan.constants import MIN_CONNECTOR_OVERLAP, plan_constants
from plan.constructed import ConstructedMaker
from plan.features import name_edges, plan_features, reachable, substitutions
from plan.glyphs import NOTDEF, GlyphMaker, PlanError, encoded_glyphs
from plan.kerns import plan_kerns
from plan.stretch import StretchPlanner
from plan.types import Glyph, Plan


def make_plan(design, sources, lite=False):
    maker = GlyphMaker(design, sources)
    constants = plan_constants(design, sources)
    builder = ConstructedMaker(design, sources, maker, constants)

    def available(name):
        return builder.available(name, lite)

    key = reachable(design, lite, available)
    encoded, slots = encoded_glyphs(design, maker, lite)
    glyphs = {glyph.name: glyph for glyph in encoded}
    glyph_names = {
        ("codepoint", names.primary(glyph.codepoints)): glyph.name
        for glyph in encoded}
    builder.glyph_of = lambda ref: glyphs[glyph_names[key(ref)]]
    builder.glyphs = glyphs

    constructed = []
    for item in design.constructed.values():
        if item.codepoints and available(item.name):
            name = names.base_name(item.codepoints)
            constructed.append(_constructed(
                builder, maker, item.name, name, item.codepoints))
    encoded += constructed
    encoded.sort(key=lambda glyph: names.primary(glyph.codepoints))
    glyphs.update((glyph.name, glyph) for glyph in constructed)
    glyph_names.update(
        (("codepoint", names.primary(glyph.codepoints)), glyph.name)
        for glyph in constructed)

    # Glyphs without code points exist because a feature or a stretch
    # series refers to them; they are named after the glyphs they are
    # reached from.
    rows = substitutions(design, key)
    derived = names.derived_names(
        dict(glyph_names), name_edges(design, key, rows))
    used = {k for _, _, inputs, output in rows for k in inputs + (output,)}
    for item in design.stretch:
        if item.kind == "variant":
            used.update(key(ref) for ref in (item.root, item.glyph))
    used.discard(None)
    bare = sorted(
        (derived[k], k) for k in used
        if k not in glyph_names and k in derived)
    if len({name for name, _ in bare}) != len(bare):
        raise PlanError("two glyphs share a derived name")
    glyph_names.update((k, name) for name, k in bare)

    made = []
    # Slots first: some constructed glyphs are drawn from them.
    for name, k in sorted(bare, key=lambda item: item[1][0] != "slot"):
        if k[0] == "slot":
            role = design.roles[k[1]]
            glyph = maker.from_slot(role.text, k[2], name, placed=True)
            slots[name] = (role.name, k[2])
        else:
            glyph = _constructed(builder, maker, k[1], name)
        made.append(glyph)
        glyphs[name] = glyph

    optical = builder.optical
    for name, (role, slot) in sorted(slots.items()):
        role = design.roles[role]
        if role.script:
            sizes = maker.optical_sizes(role, slot, name)
            optical[name] = tuple(glyph.name for glyph in sizes)
            made += sizes
            glyphs.update((glyph.name, glyph) for glyph in sizes)
    for item in design.constructed.values():
        k = ("codepoint", names.primary(item.codepoints)) \
            if item.codepoints else ("name", item.name)
        if k not in glyph_names or not available(item.name):
            continue
        sizes = _smaller(builder, maker, item.name, glyph_names[k])
        if sizes:
            optical[glyph_names[k]] = tuple(glyph.name for glyph in sizes)
            made += sizes
            glyphs.update((glyph.name, glyph) for glyph in sizes)

    planner = StretchPlanner(
        design, maker, builder, key, glyph_names, glyphs, optical,
        constants)
    constructions, extended = planner.plan()
    made += planner.new

    made.sort(key=lambda glyph: names.order_key(glyph.name))
    ordered = (NOTDEF,) + tuple(encoded) + tuple(made)
    family, postscript = product.names(lite)
    return Plan(
        family=family,
        postscript_name=postscript,
        version=product.VERSION,
        glyphs=ordered,
        # Only the dictionaries of glyphs in the font (glyphs drawn
        # only to measure others also made dictionaries).
        hints={key: value for key, value in maker.hints.items()
               if any(glyph.hints == key for glyph in ordered)},
        features=plan_features(design, rows, glyph_names, optical),
        kerns=plan_kerns(design, sources, ordered),
        constructions=constructions,
        extended_shapes=extended,
        constants=constants,
        min_connector_overlap=MIN_CONNECTOR_OVERLAP,
        marks=_marks(maker, encoded, optical),
        x_height=constants["AccentBaseHeight"],
        cap_height=constants["FlattenedAccentBaseHeight"],
    )


def _marks(maker, encoded, optical):
    """GDEF marks (design document, section 8.3): combining characters
    and the accents of the symbols font, in every optical size."""
    marks = set()
    for glyph in encoded:
        combining = any(
            unicodedata.category(chr(c)) == "Mn" for c in glyph.codepoints)
        accent = glyph.origin and glyph.origin[0] == maker.accent_source \
            and glyph.origin[1] in maker.accents
        if combining or accent:
            marks.add(glyph.name)
            marks.update(optical.get(glyph.name, ()))
    return frozenset(marks)


def _constructed(builder, maker, item, name, codepoints=()):
    """A constructed glyph, placed like the glyphs of its series."""
    glyph = builder.raw(item)
    rise = maker.placement.rise(item, glyph.outline)
    return Glyph(
        name, codepoints, glyph.advance, moved(glyph.outline, 0, rise),
        top_accent=glyph.top_accent, source=glyph.source,
        transform=(1, 0, rise))


def _smaller(builder, maker, item, name):
    """Script and scriptscript forms of a constructed glyph."""
    source = builder.optical_sources(item)
    suffixes = (names.SCRIPT, names.SCRIPTSCRIPT)
    if source:
        role, slot = source
        return maker.optical_sizes(role, slot, name)
    forms = [builder.raw(item, size) for size in (1, 2)]
    if None in forms:
        return ()
    return tuple(
        Glyph(name + suffix, (), glyph.advance, glyph.outline,
              top_accent=glyph.top_accent, source=glyph.source)
        for glyph, suffix in zip(forms, suffixes))
