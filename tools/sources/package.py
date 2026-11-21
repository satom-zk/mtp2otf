"""Read declarations from mtpro2.sty and the .fd files."""

from __future__ import annotations

import re
from fractions import Fraction
from pathlib import Path

from errors import Error
from sources.types import FontShape, MathAccent, Package

ARG = r"\{([^}]*)\}"
FAMILY = re.compile(r"\\DeclareFontFamily" + ARG * 3)
SHAPE = re.compile(r"\\DeclareFontShape" + ARG * 6)
SYMBOL_FONT = re.compile(r"\\DeclareSymbolFont" + (ARG + r"\s*") * 4 + ARG)
ACCENT = re.compile(
    r"\\DeclareMathAccent\{\\\w+\}\s*\{\\math\w+\}\s*" + ARG + r"\s*" + ARG
)
# The extension fonts are loaded at multiples of the text size:
# \dimen@\f@size pt, then \font\X=file at \the\dimen@ and
# \multiply\dimen@\tw@ in turn.
LOADING = re.compile(
    r"(?P<reset>\\dimen@\\f@size\s*pt)"
    r"|(?P<double>\\multiply\\dimen@\\tw@)"
    r"|\\font(?P<command>\\\w+@?)=(?P<file>\w+)\s+at\s+\\the\\dimen@")
# The dot macros: \\vdots stacks dots \\baselineskip apart; \\ddots
# raises them and puts \\mkern between them.
VDOTS_STEP = re.compile(
    r"\\def\\vdots\{.*?\\baselineskip\s*([\d.]+)\\p@", re.DOTALL)
DDOTS = re.compile(r"\\def\\ddots\{(.*?)\}\s*\}", re.DOTALL)
RAISE = re.compile(r"\\raise\s*([\d.]*)\\p@")
MKERN = re.compile(r"\\mkern\s*([\d.]+)mu")
SKEWCHAR = re.compile(r"\\skewchar\s*\\font\s*=?\s*([\"']?[0-9A-Fa-f]+)")
SIZE = re.compile(
    r"<\s*(?:([\d.]*)\s*-\s*([\d.]*)|([\d.]+))\s*>\s*"
    r"(?:\w+\s*\*\s*)?(?:\[[^\]]*\]\s*)?([A-Za-z0-9]+)"
)


class PackageError(Error):
    pass


def _source(path) -> str:
    """Return the file's text without TeX comments."""
    text = Path(path).read_text(encoding="latin-1")
    return "\n".join(
        re.sub(r"(?<!\\)%.*", "", line) for line in text.splitlines()
    )


def _number(token: str) -> int:
    """Read a TeX integer constant: decimal, "hex or 'octal."""
    token = token.strip()
    if token.startswith('"'):
        return int(token[1:], 16)
    if token.startswith("'"):
        return int(token[1:], 8)
    return int(token)


def _sizes(spec: str) -> tuple:
    result = []
    for low, high, single, name in SIZE.findall(spec):
        if single:
            bounds = (Fraction(single), Fraction(single))
        else:
            bounds = (
                Fraction(low) if low else None,
                Fraction(high) if high else None,
            )
        result.append((bounds, name))
    return tuple(result)


def _skewchar(text: str) -> int | None:
    found = SKEWCHAR.search(text)
    return _number(found.group(1)) if found else None


def read_package(sty: str | Path, fds=()) -> Package:
    text = _source(sty)
    both = "\n".join([text] + [_source(path) for path in fds])

    def ratio(name: str) -> Fraction:
        found = re.search(r"\\def\\%s\{([\d.]+)\}" % name, text)
        if not found:
            raise PackageError(f"{sty}: \\{name} not found")
        return Fraction(found.group(1))

    family_skewchars = {}
    for encoding, family, code in FAMILY.findall(both):
        skewchar = _skewchar(code)
        if skewchar is not None:
            family_skewchars[(encoding, family)] = skewchar

    shapes = tuple(
        FontShape(
            encoding, family, series, shape, _sizes(spec), _skewchar(code)
        )
        for encoding, family, series, shape, spec, code in SHAPE.findall(both)
    )

    symbol_fonts = {}
    for name, *font in SYMBOL_FONT.findall(text):
        symbol_fonts.setdefault(name, tuple(font))

    accents = tuple(
        MathAccent(family.strip(), _number(slot))
        for family, slot in ACCENT.findall(text)
    )

    vdots = VDOTS_STEP.search(text)
    ddots = DDOTS.search(text)
    raises, gaps = (), ()
    if ddots:
        raises = tuple(Fraction(x or 1) for x in RAISE.findall(ddots[1]))
        # The kerns between the dots, not the ones outside them.
        gaps = tuple(Fraction(x) for x in MKERN.findall(ddots[1]))[1:-1]

    commands, scale = {}, None
    for found in LOADING.finditer(text):
        if found["reset"]:
            scale = 1
        elif found["double"] and scale is not None:
            scale *= 2
        elif found["command"] and scale is not None:
            commands[found["command"]] = (found["file"], scale)
    return Package(
        script_ratio=ratio("defaultscriptratio"),
        scriptscript_ratio=ratio("defaultscriptscriptratio"),
        family_skewchars=family_skewchars,
        shapes=shapes,
        accents=accents,
        symbol_fonts=symbol_fonts,
        commands=commands,
        vdots_step=Fraction(vdots[1]) if vdots else None,
        ddots_raises=raises,
        ddots_gaps=gaps,
    )
