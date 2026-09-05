"""Parse tftopl property lists into TFM metrics and recipes."""
import re


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


FD_NAMES = {1: 'slant', 2: 'space', 3: 'stretch', 4: 'shrink', 5: 'xheight', 6: 'quad', 7: 'extraspace',
            8: 'num1', 9: 'num2', 10: 'num3', 11: 'denom1', 12: 'denom2', 13: 'sup1', 14: 'sup2', 15: 'sup3',
            16: 'sub1', 17: 'sub2', 18: 'supdrop', 19: 'subdrop', 20: 'delim1', 21: 'delim2', 22: 'axisheight'}
FD_NAMES_EX = {8: 'defaultrulethickness', 9: 'bigopspacing1', 10: 'bigopspacing2',
               11: 'bigopspacing3', 12: 'bigopspacing4', 13: 'bigopspacing5'}


class TFM:
    def __init__(self, plpath, kind='sy'):
        src = open(plpath).read()
        top = _parse(_tok(src))
        self.fontdimen = {}
        self.design_size = None  # TeX points; read from PL DESIGNSIZE
        self.chars = {}   # code -> dict(wd,ht,dp,ic,next,varchar)
        self.kerns = {}   # (left,right) -> amount
        self.ligs = {}
        for node in top:
            head = node[0]
            if head == 'DESIGNSIZE':
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
                        names.update({v.upper(): k for k, v in FD_NAMES_EX.items()})
                        idx = names.get(key)
                        if idx:
                            self.fontdimen[idx] = _num(sub[1:3])
            elif head == 'LIGTABLE':
                if any(isinstance(sub, list) and sub and sub[0] == 'SKIP'
                       for sub in node[1:]):
                    raise ValueError(
                        f'{plpath}: unsupported PL LIGTABLE SKIP; kerning not imported')
                labels = []
                for sub in node[1:]:
                    if not isinstance(sub, list):
                        continue
                    if sub[0] == 'LABEL':
                        labels.append(_charcode(sub[1], sub[2]))
                    elif sub[0] == 'KRN':
                        rc = _charcode(sub[1], sub[2])
                        amt = _num(sub[3:5])
                        for l in labels:
                            self.kerns[(l, rc)] = amt
                    elif sub[0] == 'LIG':
                        pass
                    elif sub[0] == 'STOP':
                        labels = []
            elif head == 'CHARACTER':
                code = _charcode(node[1], node[2])
                d = {'wd': 0.0, 'ht': 0.0, 'dp': 0.0, 'ic': 0.0, 'next': None, 'varchar': None}
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
                            if isinstance(p, list) and p[0] in ('TOP', 'MID', 'BOT', 'REP'):
                                vc[p[0]] = _charcode(p[1], p[2])
                        d['varchar'] = vc
                self.chars[code] = d

    def named_fd(self, kind):
        table = FD_NAMES if kind == 'sy' else dict(
            list(FD_NAMES.items())[:7] + list(FD_NAMES_EX.items()))
        return {table.get(i, f'p{i}'): v for i, v in self.fontdimen.items()}


if __name__ == '__main__':
    import sys, json
    t = TFM(sys.argv[1])
    print(json.dumps({'fd': t.fontdimen,
                      'nchars': len(t.chars),
                      'chains': {c: d['next'] for c, d in t.chars.items() if d['next'] is not None},
                      'varchars': {c: d['varchar'] for c, d in t.chars.items() if d['varchar']}},
                     indent=1))
