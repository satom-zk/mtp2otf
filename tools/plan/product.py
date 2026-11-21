"""Names and fixed values of the product (design document, sections 1
and 9)."""

from pathlib import Path

# The version is kept in VERSION beside build.sh, which reads it too.
VERSION = (Path(__file__).resolve().parents[2]
           / "VERSION").read_text().strip()
VENDOR = "MTP2"
COPYRIGHT = (
    "Copyright (C) Publish or Perish, Inc. 2005.  Outlines from the "
    "MathTime(TM) Professional II Type1 fonts. Unofficial OpenType MATH "
    "conversion for the licensee's own use; redistribution of this font "
    "file is not permitted.")
TRADEMARK = "MathTime is a trademark of Publish or Perish, Inc."

# Line spacing after Latin Modern; not derived from the TFM files.
TYPO_ASCENDER = 806
TYPO_DESCENDER = -194
TYPO_LINE_GAP = 200

# Word needs these in the TrueType font (design document, section 9).
TRUETYPE_WIN_ASCENT = 2953
TRUETYPE_WIN_DESCENT = 2954


def names(lite):
    family = "MTPro2 Math Lite" if lite else "MTPro2 Math"
    postscript = family.replace(" ", "")
    return family, postscript
