"""Read effective TFM kerns as signed fix20 integers.

Execute each character's start/restart and mismatch skip chain. The first
command matching a right character wins, including a zero kern. Ligatures
and boundary programs are deliberately unsupported and rejected explicitly.
This helper does not change the project's PL/raw width or italic readers.
"""
from pathlib import Path
import struct


def read_kerns_fix20(path):
    data = Path(path).read_bytes()

    def invalid(reason):
        raise ValueError(f'{path}: invalid TFM: {reason}')

    if len(data) < 24:
        invalid('truncated size header')
    lf, lh, bc, ec, nw, nh, nd, ni, nl, nk, ne, np = struct.unpack(
        '>12H', data[:24]
    )
    nc = max(0, ec - bc + 1)
    if (bc > ec + 1 or ec > 255 or lh < 2 or min(nw, nh, nd, ni) == 0
            or lf != 6 + lh + nc + nw + nh + nd + ni + nl + nk + ne + np
            or len(data) != 4 * lf):
        invalid('inconsistent table sizes')
    char_start = 4 * (6 + lh)
    program_start = char_start + 4 * (nc + nw + nh + nd + ni)
    program = [tuple(data[i:i + 4])
               for i in range(program_start, program_start + 4 * nl, 4)]
    kern_start = program_start + 4 * nl
    kerns = struct.unpack(f'>{nk}i', data[kern_start:kern_start + 4 * nk])
    if program and (program[0][0] == 255 or program[-1][0] == 255):
        raise ValueError(f'{path}: unsupported TFM boundary program')
    result = {}
    for left in range(bc, ec + 1):
        width, _, it, start = data[char_start + 4 * (left - bc):
                                   char_start + 4 * (left - bc + 1)]
        if not width or it % 4 != 1:
            continue
        if start >= nl:
            invalid('lig/kern start outside program')
        if program[start][0] > 128:
            start = 256 * program[start][2] + program[start][3]
        seen = set()
        matched = set()
        index = start
        while True:
            if index >= nl or index in seen:
                invalid('out-of-range or cyclic lig/kern program')
            seen.add(index)
            skip, right, op, remainder = program[index]
            if skip <= 128 and right not in matched:
                matched.add(right)
                if op < 128:
                    raise ValueError(
                        f'{path}: unsupported TFM ligature at instruction {index}'
                    )
                ki = 256 * (op - 128) + remainder
                if ki >= nk:
                    invalid('kern index outside table')
                result[left, right] = kerns[ki]
            if skip >= 128:
                break
            index += skip + 1
    return result
