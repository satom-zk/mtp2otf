"""Read TeX font metric files.

All dimensions are kept as exact fractions of the design size.
"""

from __future__ import annotations

import struct
from fractions import Fraction
from pathlib import Path

from errors import Error
from sources.types import Tfm, TfmChar

FIX = 1 << 20


class TfmError(Error):
    pass


def _fix(word: bytes) -> Fraction:
    return Fraction(struct.unpack(">i", word)[0], FIX)


def read_tfm(path: str | Path) -> Tfm:
    data = Path(path).read_bytes()
    if len(data) < 24:
        raise TfmError(f"{path}: too short")
    lf, lh, bc, ec, nw, nh, nd, ni, nl, nk, ne, np = struct.unpack(
        ">12H", data[:24]
    )
    count = ec - bc + 1 if ec >= bc else 0
    words = 6 + lh + count + nw + nh + nd + ni + nl + nk + ne + np
    if lf * 4 != len(data) or lf != words:
        raise TfmError(f"{path}: inconsistent lengths")

    pos = 24

    def take(words: int) -> list:
        nonlocal pos
        end = pos + 4 * words
        chunk = [data[i:i + 4] for i in range(pos, end, 4)]
        pos = end
        return chunk

    header = take(lh)
    info = take(count)
    widths = [_fix(w) for w in take(nw)]
    heights = [_fix(w) for w in take(nh)]
    depths = [_fix(w) for w in take(nd)]
    italics = [_fix(w) for w in take(ni)]
    ligkern = take(nl)
    kerns = [_fix(w) for w in take(nk)]
    exten = take(ne)
    params = tuple(_fix(w) for w in take(np))

    if nl and (ligkern[0][0] == 255 or ligkern[-1][0] == 255):
        raise TfmError(f"{path}: boundary characters are not supported")

    def kern_program(start: int) -> dict:
        i = start
        if ligkern[i][0] > 128:
            i = 256 * ligkern[i][2] + ligkern[i][3]
        result = {}
        while True:
            skip, nxt, op, rem = ligkern[i]
            if skip <= 128:
                if op < 128:
                    raise TfmError(f"{path}: ligatures are not supported")
                result.setdefault(nxt, kerns[256 * (op - 128) + rem])
            if skip >= 128:
                return result
            i += skip + 1

    chars = {}
    for offset, word in enumerate(info):
        wi, hd, it, rem = word
        if wi == 0:
            continue
        tag = it & 3
        code_kerns, larger, recipe = {}, None, None
        if tag == 1:
            code_kerns = kern_program(rem)
        elif tag == 2:
            larger = rem
        elif tag == 3:
            # A zero byte means "no piece" for top, mid and bot.
            top, mid, bot, rep = exten[rem]
            recipe = (top or None, mid or None, bot or None, rep)
        chars[bc + offset] = TfmChar(
            width=widths[wi],
            height=heights[hd >> 4],
            depth=depths[hd & 15],
            italic=italics[it >> 2],
            kerns=code_kerns,
            next_larger=larger,
            extensible=recipe,
        )

    return Tfm(
        checksum=struct.unpack(">I", header[0])[0] if lh > 0 else 0,
        design_size=_fix(header[1]) if lh > 1 else Fraction(10),
        params=params,
        chars=chars,
    )
