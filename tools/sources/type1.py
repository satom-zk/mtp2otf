"""Read Type 1 fonts through AFDKO's tx.

tx converts Type 1 to CFF without changing coordinates, widths or hints.
"""

from __future__ import annotations

import io
import subprocess
import tempfile
from pathlib import Path

from fontTools.cffLib import CFFFontSet
from fontTools.encodings.StandardEncoding import StandardEncoding
from fontTools.pens.recordingPen import RecordingPen

from errors import Error
from sources.types import Type1Font, Type1Glyph

PRIVATE_KEYS = (
    "BlueValues",
    "OtherBlues",
    "FamilyBlues",
    "FamilyOtherBlues",
    "BlueScale",
    "BlueShift",
    "BlueFuzz",
    "StdHW",
    "StdVW",
    "StemSnapH",
    "StemSnapV",
    "ForceBold",
    "LanguageGroup",
)


class Type1Error(Error):
    pass


def outline_from_pen(value) -> tuple:
    """Convert RecordingPen output into closed contours."""
    contours, current = [], None
    for op, points in value:
        if op == "moveTo":
            if current:
                contours.append(tuple(current))
            current = [("move", tuple(points[0]))]
        elif op == "lineTo":
            current.append(("line", tuple(points[0])))
        elif op == "curveTo":
            current.append(("curve",) + tuple(tuple(p) for p in points))
        elif op in ("closePath", "endPath"):
            if current:
                contours.append(tuple(current))
            current = None
        else:
            raise Type1Error(f"unexpected outline operator {op}")
    if current:
        contours.append(tuple(current))
    return tuple(contours)


def load_cff(data: bytes):
    fontset = CFFFontSet()
    fontset.decompile(io.BytesIO(data), None)
    return fontset


STEM_OPERATORS = (
    "hstem",
    "vstem",
    "hstemhm",
    "vstemhm",
    "hintmask",
    "cntrmask",
)


def charstring_parts(charstring, private) -> tuple:
    """Return (width, program without the width operand).

    A Type 2 charstring carries its width as an extra leading operand
    of the first operator.
    """
    charstring.decompile()
    program = list(charstring.program)
    count = 0
    while count < len(program) and not isinstance(program[count], str):
        count += 1
    first = program[count] if count < len(program) else "endchar"
    has_width = (
        (first in STEM_OPERATORS and count % 2 == 1)
        or (first == "rmoveto" and count == 3)
        or (first in ("hmoveto", "vmoveto") and count == 2)
        or (first == "endchar" and count in (1, 5))
    )
    if has_width:
        return private.nominalWidthX + program[0], tuple(program[1:])
    return private.defaultWidthX, tuple(program)


def read_type1(path: str | Path) -> Type1Font:
    path = Path(path)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "font.cff"
        run = subprocess.run(
            ["tx", "-cff", "+b", str(path), str(out)],
            capture_output=True,
            text=True,
        )
        if run.returncode != 0 or not out.exists():
            raise Type1Error(f"tx failed for {path}: {run.stderr.strip()}")
        fontset = load_cff(out.read_bytes())
    if len(fontset.fontNames) != 1:
        raise Type1Error(f"{path}: expected a single font")
    top = fontset.topDictIndex[0]
    if fontset.GlobalSubrs or getattr(top.Private, "Subrs", None):
        fontset.desubroutinize()
    private = top.Private
    strings = top.CharStrings
    glyphs = {}
    for name in top.charset:
        charstring = strings[name]
        width, program = charstring_parts(charstring, private)
        pen = RecordingPen()
        charstring.draw(pen)
        glyphs[name] = Type1Glyph(
            name=name,
            width=width,
            program=program,
            outline=outline_from_pen(pen.value),
        )
    encoding = top.Encoding
    if encoding == "StandardEncoding":
        encoding = StandardEncoding
    elif isinstance(encoding, str):
        raise Type1Error(f"{path}: unsupported encoding {encoding}")
    slots = {
        code: name
        for code, name in enumerate(encoding)
        if name != ".notdef" and name in glyphs
    }
    hints = {
        key: private.rawDict[key]
        for key in PRIVATE_KEYS
        if key in private.rawDict
    }
    return Type1Font(
        font_name=fontset.fontNames[0],
        encoding=slots,
        glyphs=glyphs,
        private=hints,
    )
