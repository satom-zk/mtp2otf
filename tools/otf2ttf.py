#!/usr/bin/env python3
"""Convert CFF outlines to quadratic TrueType outlines for Word embedding.

Preserve MATH, GSUB, GPOS, and cmap. Usage: otf2ttf.py in.otf out.ttf [error].
"""
import sys
from fontTools.ttLib import TTFont, newTable
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen


def convert(src, dst, tolerance=0.6):
    f = TTFont(src)
    upem = f['head'].unitsPerEm
    glyphset = f.getGlyphSet()
    order = f.getGlyphOrder()

    glyf = newTable('glyf')
    glyf.glyphOrder = order
    glyf.glyphs = {}
    for name in order:
        pen = TTGlyphPen(None)
        cu2qu = Cu2QuPen(pen, tolerance * upem / 1000.0, reverse_direction=True)
        glyphset[name].draw(cu2qu)
        g = pen.glyph()
        g.recalcBounds(glyf)
        glyf.glyphs[name] = g

    f['glyf'] = glyf
    f['loca'] = newTable('loca')

    maxp = f['maxp']
    maxp.tableVersion = 0x00010000
    for attr, val in (('maxZones', 1), ('maxTwilightPoints', 0),
                      ('maxStorage', 0), ('maxFunctionDefs', 0),
                      ('maxInstructionDefs', 0), ('maxStackElements', 0),
                      ('maxSizeOfInstructions', 0), ('maxComponentElements', 0),
                      ('maxComponentDepth', 0)):
        setattr(maxp, attr, val)
    maxp.recalc(f)

    head = f['head']
    head.indexToLocFormat = 0
    head.glyphDataFormat = 0

    post = f['post']
    post.formatType = 3.0   # final TTF does not require PostScript glyph names
    for attr in ('extraNames', 'mapping', 'glyphOrder'):
        if hasattr(post, attr):
            delattr(post, attr)

    del f['CFF ']
    if 'VORG' in f:
        del f['VORG']

    f.sfntVersion = '\000\001\000\000'
    f.save(dst)
    print(f'{dst} written (glyphs {len(order)})')


if __name__ == '__main__':
    tol = float(sys.argv[3]) if len(sys.argv) > 3 else 0.6
    convert(sys.argv[1], sys.argv[2], tol)
