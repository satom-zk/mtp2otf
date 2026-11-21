"""The MATH table."""

from fontTools.otlLib.builder import buildMathTable


def build_math(font, plan, font_name):
    glyphs = [(font_name[glyph.name], glyph) for glyph in plan.glyphs]
    buildMathTable(
        font,
        constants=plan.constants,
        italicsCorrections={
            name: glyph.italic for name, glyph in glyphs if glyph.italic},
        topAccentAttachments={
            name: glyph.top_accent for name, glyph in glyphs
            if glyph.top_accent is not None},
        mathKerns={
            name: {"BottomRight": ([], [glyph.math_kern])}
            for name, glyph in glyphs if glyph.math_kern is not None},
        extendedShapes={font_name[name] for name in plan.extended_shapes},
        minConnectorOverlap=plan.min_connector_overlap,
        vertGlyphVariants=_variants(plan, font_name, "v"),
        horizGlyphVariants=_variants(plan, font_name, "h"),
        vertGlyphAssembly=_assemblies(plan, font_name, "v"),
        horizGlyphAssembly=_assemblies(plan, font_name, "h"),
    )


def _variants(plan, font_name, axis):
    return {
        font_name[c.root]: [
            (font_name[name], measure) for name, measure in c.variants]
        for c in plan.constructions if c.axis == axis and c.variants}


def _assemblies(plan, font_name, axis):
    # The italics correction of every assembly is 0.
    return {
        font_name[c.root]: [
            [(font_name[p.glyph], int(p.extender), p.start, p.end, p.full)
             for p in c.parts], 0]
        for c in plan.constructions if c.axis == axis and c.parts}
