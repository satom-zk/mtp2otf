#!/usr/bin/env python3
"""Convert CFF outlines to quadratic TrueType outlines for Word
embedding.

Preserve MATH, GSUB, GPOS, and cmap. Usage: otf2ttf.py in.otf out.ttf
[tolerance].
"""

from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from large_variant_policy import field_range


def convert(
    src,
    dst,
    tolerance=0.6,
    windows_policy=None,
    edition=None,
    input_manifest=None,
):
    if windows_policy:
        from windows_metrics import provenance_errors, read

        policy = read(windows_policy)
        failures = provenance_errors(policy, edition, input_manifest, src)
        if failures:
            raise ValueError("; ".join(failures))
    with TTFont(src) as f:
        upem = f["head"].unitsPerEm
        glyphset = f.getGlyphSet()
        order = f.getGlyphOrder()

        glyf = newTable("glyf")
        glyf.glyphOrder = order
        glyf.glyphs = {}
        for name in order:
            pen = TTGlyphPen(None)
            cu2qu = Cu2QuPen(
                pen, tolerance * upem / 1000.0, reverse_direction=True
            )
            glyphset[name].draw(cu2qu)
            g = pen.glyph()
            g.recalcBounds(glyf)
            for x, y in g.coordinates if hasattr(g, "coordinates") else ():
                field_range(name + ".quadratic.x", x, -32768, 32767)
                field_range(name + ".quadratic.y", y, -32768, 32767)
            glyf.glyphs[name] = g

        f["glyf"] = glyf
        f["loca"] = newTable("loca")

        maxp = f["maxp"]
        maxp.tableVersion = 0x00010000
        for attr, val in (
            ("maxZones", 1),
            ("maxTwilightPoints", 0),
            ("maxStorage", 0),
            ("maxFunctionDefs", 0),
            ("maxInstructionDefs", 0),
            ("maxStackElements", 0),
            ("maxSizeOfInstructions", 0),
            ("maxComponentElements", 0),
            ("maxComponentDepth", 0),
        ):
            setattr(maxp, attr, val)
        maxp.recalc(f)

        head = f["head"]
        head.indexToLocFormat = 0
        head.glyphDataFormat = 0

        post = f["post"]
        # Final TTF does not require PostScript glyph names.
        post.formatType = 3.0
        for attr in ("extraNames", "mapping", "glyphOrder"):
            if hasattr(post, attr):
                delattr(post, attr)

        del f["CFF "]
        if "VORG" in f:
            del f["VORG"]

        f.sfntVersion = "\000\001\000\000"
        if windows_policy:
            from windows_metrics import errors

            bbox = [
                getattr(f["head"], n) for n in ("xMin", "yMin", "xMax", "yMax")
            ]
            if (
                max(
                    abs(a - b)
                    for a, b in zip(bbox, policy["source_head_bbox"])
                )
                > 1
            ):
                raise ValueError(
                    "quadratic conversion changes source bbox beyond "
                    "rounding tolerance"
                )
            f["OS/2"].usWinAscent, f["OS/2"].usWinDescent = policy["Windows"]
        f.save(dst)
    if windows_policy:
        from windows_metrics import sha

        with TTFont(dst) as actual:
            policy["source_ttf_head_bbox"] = [
                getattr(actual["head"], n)
                for n in ("xMin", "yMin", "xMax", "yMax")
            ]
            policy["target_ttf_sha256"] = sha(dst)
            failures = errors(
                actual,
                policy,
                "source",
                font_path=dst,
                edition=edition,
                manifest=input_manifest,
                source_path=src,
            )
            if failures:
                raise ValueError("; ".join(failures))
        from diagnostics import write_contract

        write_contract(windows_policy, policy)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("tolerance", nargs="?", type=float, default=0.6)
    parser.add_argument("--windows-policy")
    parser.add_argument("--edition", choices=("full", "lite"))
    parser.add_argument("--input-manifest")
    args = parser.parse_args()
    convert(
        args.src,
        args.dst,
        args.tolerance,
        args.windows_policy,
        args.edition,
        args.input_manifest,
    )
