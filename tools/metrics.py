"""Parse tftopl property lists into TFM metrics and recipes."""

import re
from pathlib import Path
import struct


def apply_raw_alphabet_metrics(tfm, raw):
    """Overlay raw WD/IC/kern only for explicitly selected new alphabet
    roles.
    """
    source_chars = {
        int(slot): metrics for slot, metrics in raw['chars'].items()
    }
    if set(tfm.chars) != set(source_chars):
        raise ValueError('PL/raw TFM character coverage differs')
    for slot, metrics in source_chars.items():
        tfm.chars[slot]['wd'] = metrics['wd']
        tfm.chars[slot]['ic'] = metrics['ic']
    tfm.kerns = {
        (int(left), int(right)): value for left, right, value in raw['kerns']
    }


def _tok(s):
    # tokenize parens and atoms
    return re.findall(r'\(|\)|[^\s()]+', s)


def _parse(tokens):
    it = iter(tokens)

    def node():
        items = []
        for t in it:
            if t == '(':
                items.append(node())
            elif t == ')':
                return items
            else:
                items.append(t)
        return items

    top = []
    for t in it:
        if t == '(':
            top.append(node())
    return top


def _charcode(t, v):
    if t == 'O':
        return int(v, 8)
    if t == 'D':
        return int(v)
    if t == 'C':
        return ord(v)
    if t == 'H':
        return int(v, 16)
    raise ValueError((t, v))


def _num(items):
    # ['R', '0.5'] or ['D','8'] ...
    t, v = items[0], items[1]
    if t == 'R':
        return float(v)
    if t == 'D':
        return int(v)
    if t == 'O':
        return int(v, 8)
    raise ValueError(items)


FD_NAMES = {
    1: 'slant',
    2: 'space',
    3: 'stretch',
    4: 'shrink',
    5: 'xheight',
    6: 'quad',
    7: 'extraspace',
    8: 'num1',
    9: 'num2',
    10: 'num3',
    11: 'denom1',
    12: 'denom2',
    13: 'sup1',
    14: 'sup2',
    15: 'sup3',
    16: 'sub1',
    17: 'sub2',
    18: 'supdrop',
    19: 'subdrop',
    20: 'delim1',
    21: 'delim2',
    22: 'axisheight',
}
FD_NAMES_EX = {
    8: 'defaultrulethickness',
    9: 'bigopspacing1',
    10: 'bigopspacing2',
    11: 'bigopspacing3',
    12: 'bigopspacing4',
    13: 'bigopspacing5',
}


class TFM:
    def __init__(self, plpath):
        with open(plpath) as stream:
            src = stream.read()
        top = _parse(_tok(src))
        self.fontdimen = {}
        self.design_size = None  # TeX points; read from PL DESIGNSIZE
        self.chars = {}  # code -> dict(wd,ht,dp,ic,next,varchar)
        self.kerns = {}  # (left,right) -> amount
        for node in top:
            head = node[0]
            if head == 'BOUNDARYCHAR':
                raise ValueError(
                    f'{plpath}: unsupported PL boundary character'
                )
            elif head == 'DESIGNSIZE':
                self.design_size = float(_num(node[1:3]))
            elif head == 'FONTDIMEN':
                for sub in node[1:]:
                    if not isinstance(sub, list):
                        continue
                    key = sub[0]
                    if key == 'PARAMETER':
                        idx = _charcode(sub[1], sub[2])
                        self.fontdimen[idx] = _num(sub[3:5])
                    else:
                        names = {v.upper(): k for k, v in FD_NAMES.items()}
                        names.update(
                            {v.upper(): k for k, v in FD_NAMES_EX.items()}
                        )
                        idx = names.get(key)
                        if idx:
                            self.fontdimen[idx] = _num(sub[1:3])
            elif head == 'LIGTABLE':
                if any(
                    isinstance(sub, list) and sub and sub[0] == 'SKIP'
                    for sub in node[1:]
                ):
                    raise ValueError(
                        (
                            f'{plpath}: unsupported PL LIGTABLE SKIP; '
                            f'kerning not imported'
                        )
                    )
                labels = []
                for sub in node[1:]:
                    if not isinstance(sub, list):
                        continue
                    if sub[0] == 'LABEL':
                        if sub[1] == 'BOUNDARYCHAR':
                            raise ValueError(
                                f'{plpath}: unsupported PL boundary label'
                            )
                        labels.append(_charcode(sub[1], sub[2]))
                    elif sub[0] == 'KRN':
                        rc = _charcode(sub[1], sub[2])
                        amt = _num(sub[3:5])
                        for left in labels:
                            self.kerns.setdefault((left, rc), amt)
                    elif sub[0] == 'STOP':
                        labels = []
                    elif sub[0] != 'COMMENT':
                        raise ValueError(
                            f'{plpath}: unsupported PL LIGTABLE '
                            f'command {sub[0]}'
                        )
            elif head == 'CHARACTER':
                code = _charcode(node[1], node[2])
                d = {
                    'wd': 0.0,
                    'ht': 0.0,
                    'dp': 0.0,
                    'ic': 0.0,
                    'next': None,
                    'varchar': None,
                }
                for sub in node[3:]:
                    if not isinstance(sub, list):
                        continue
                    k = sub[0]
                    if k == 'CHARWD':
                        d['wd'] = _num(sub[1:3])
                    elif k == 'CHARHT':
                        d['ht'] = _num(sub[1:3])
                    elif k == 'CHARDP':
                        d['dp'] = _num(sub[1:3])
                    elif k == 'CHARIC':
                        d['ic'] = _num(sub[1:3])
                    elif k == 'NEXTLARGER':
                        d['next'] = _charcode(sub[1], sub[2])
                    elif k == 'VARCHAR':
                        vc = {}
                        for p in sub[1:]:
                            if isinstance(p, list) and p[0] in (
                                'TOP',
                                'MID',
                                'BOT',
                                'REP',
                            ):
                                vc[p[0]] = _charcode(p[1], p[2])
                        d['varchar'] = vc
                self.chars[code] = d


def read_kerns_fix20(path):
    """Read effective TFM kerns as signed fix20 integers.

    Execute each character's start/restart and mismatch skip chain. The
    first matching command wins, including a zero kern.
    Ligatures and boundary programs are deliberately unsupported and
    rejected explicitly. This helper does not change the project's
    PL/raw width or italic readers.
    """
    data = Path(path).read_bytes()

    def invalid(reason):
        raise ValueError(f'{path}: invalid TFM: {reason}')

    if len(data) < 24:
        invalid('truncated size header')
    lf, lh, bc, ec, nw, nh, nd, ni, nl, nk, ne, np = struct.unpack(
        '>12H', data[:24]
    )
    nc = max(0, ec - bc + 1)
    if (
        bc > ec + 1
        or ec > 255
        or lh < 2
        or min(nw, nh, nd, ni) == 0
        or lf != 6 + lh + nc + nw + nh + nd + ni + nl + nk + ne + np
        or len(data) != 4 * lf
    ):
        invalid('inconsistent table sizes')
    char_start = 4 * (6 + lh)
    program_start = char_start + 4 * (nc + nw + nh + nd + ni)
    program = [
        tuple(data[i:i + 4])
        for i in range(program_start, program_start + 4 * nl, 4)
    ]
    kern_start = program_start + 4 * nl
    kerns = struct.unpack(f'>{nk}i', data[kern_start:kern_start + 4 * nk])
    if program and (program[0][0] == 255 or program[-1][0] == 255):
        raise ValueError(f'{path}: unsupported TFM boundary program')
    result = {}
    for left in range(bc, ec + 1):
        width, _, it, start = data[
            char_start + 4 * (left - bc):char_start + 4 * (left - bc + 1)
        ]
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
                        f'{path}: unsupported TFM ligature '
                        f'at instruction {index}'
                    )
                ki = 256 * (op - 128) + remainder
                if ki >= nk:
                    invalid('kern index outside table')
                result[left, right] = kerns[ki]
            if skip >= 128:
                break
            index += skip + 1
    return result


def raw_alphabet_metrics(path):
    """Read exact binary TFM fractions into a local JSON-safe snapshot.
    """
    from fontTools.tfmLib import TFM

    tfm = TFM(str(path))
    return {
        'chars': {
            str(slot): {
                'wd': char.get('width', 0),
                'ic': char.get('italic', 0),
            }
            for slot, char in tfm.chars.items()
        },
        'kerns': [
            [left, right, value / (1 << 20)]
            for (left, right), value in read_kerns_fix20(path).items()
        ],
    }


def read_pl(path, pl_path, *, run=None):
    """Interpret tftopl once per role, preserving PL order and rounding.
    """
    import subprocess

    command = ['tftopl', str(path), str(pl_path)]
    if run is None:
        subprocess.run(command, check=True)
    else:
        run('tftopl ' + str(path), command)
    return TFM(pl_path)


def to_data(tfm):
    return dict(
        fontdimen=list(tfm.fontdimen.items()),
        design_size=tfm.design_size,
        chars=list(tfm.chars.items()),
        kerns=[[left, r, v] for (left, r), v in tfm.kerns.items()],
    )


def from_data(data):
    tfm = TFM.__new__(TFM)
    tfm.fontdimen = {int(k): v for k, v in data['fontdimen']}
    tfm.design_size = data['design_size']
    tfm.chars = {int(k): v for k, v in data['chars']}
    tfm.kerns = {(int(left), int(r)): v for left, r, v in data['kerns']}
    return tfm


def read_raw(path):
    """Keep the existing binary parser for post-native original
    additions.
    """
    from fontTools.tfmLib import TFM as RawTFM

    return RawTFM(str(path))
