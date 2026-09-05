"""Map MTPro2 source slots to Unicode identities and glyph names.

Project-authored interoperability mappings use TeX and Unicode semantics.
TFM supplies variant chains and assemblies; None means intentionally unencoded.
"""


# Mathematical alphabet ranges.
def _range(base, letters):
    return {chr(ord('A') + i) if letters == 'U' else chr(ord('a') + i): base + i
            for i in range(26)}


MATH_IT_UC = _range(0x1D434, 'U')
MATH_IT_LC = _range(0x1D44E, 'l')
MATH_IT_LC['h'] = 0x210E
SCRIPT_UC = _range(0x1D49C, 'U')
SCRIPT_UC.update({'B': 0x212C, 'E': 0x2130, 'F': 0x2131, 'H': 0x210B,
                  'I': 0x2110, 'L': 0x2112, 'M': 0x2133, 'R': 0x211B})
SCRIPT_LC = _range(0x1D4B6, 'l')
SCRIPT_LC.update({'e': 0x212F, 'g': 0x210A, 'o': 0x2134})
FRAK_UC = _range(0x1D504, 'U')
FRAK_UC.update({'C': 0x212D, 'H': 0x210C, 'I': None, 'R': None, 'Z': 0x2128})
# Reserve U+2111/U+211C for mt2syt Im/Re; keep Fraktur I/R unencoded.
FRAK_LC = _range(0x1D51E, 'l')
BB_UC = _range(0x1D538, 'U')
BB_UC.update({'C': 0x2102, 'H': 0x210D, 'N': 0x2115, 'P': 0x2119,
              'Q': 0x211A, 'R': 0x211D, 'Z': 0x2124})
BB_LC = _range(0x1D552, 'l')
BOLD_UC = _range(0x1D400, 'U')
BOLD_LC = _range(0x1D41A, 'l')

GREEK_IT_LC = [  # OML slot order.
    0x1D6FC, 0x1D6FD, 0x1D6FE, 0x1D6FF, 0x1D716, 0x1D701, 0x1D702, 0x1D703,
    0x1D704, 0x1D705, 0x1D706, 0x1D707, 0x1D708, 0x1D709, 0x1D70B, 0x1D70C,
    0x1D70E, 0x1D70F, 0x1D710, 0x1D719, 0x1D712, 0x1D713, 0x1D714,          # ..omega
    0x1D700, 0x1D717, 0x1D71B, 0x1D71A, 0x1D70D, 0x1D711]  # Variant forms.
# mt2mit slot contract: 0-10 are italic; 0x7F/0x80-0x89 are upright.
GREEK_UP_UC = [0x1D6E4, 0x1D6E5, 0x1D6E9, 0x1D6EC, 0x1D6EF, 0x1D6F1, 0x1D6F4,
               0x1D6F6, 0x1D6F7, 0x1D6F9, 0x1D6FA]
GREEK_IT_UC = [0x0393, 0x0394, 0x0398, 0x039B, 0x039E, 0x03A0, 0x03A3,
               0x03A5, 0x03A6, 0x03A8]
GREEK_UP_LC = [  # Upright Greek source-slot order.
    0x03B1, 0x03B2, 0x03B3, 0x03B4, 0x03F5, 0x03B6, 0x03B7, 0x03B8,
    0x03B9, 0x03BA, 0x03BB, 0x03BC, 0x03BD, 0x03BE, 0x03C0, 0x03C1,
    0x03C3, 0x03C4, 0x03C5, 0x03D5, 0x03C7, 0x03C8, 0x03C9,
    0x03B5, 0x03D1, 0x03D6, 0x03F1, 0x03C2, 0x03C6]

# Latin-shaped Greek aliases share glyph IDs with the matching Latin style.
# Capital theta symbols share the corresponding Theta design.
GREEK_LATIN_SHAPED_BASIC_ALIASES = {
    0x0391: 0x0041,
    0x0392: 0x0042,
    0x0395: 0x0045,
    0x0396: 0x005A,
    0x0397: 0x0048,
    0x0399: 0x0049,
    0x039A: 0x004B,
    0x039C: 0x004D,
    0x039D: 0x004E,
    0x039F: 0x004F,
    0x03A1: 0x0050,
    0x03A4: 0x0054,
    0x03A7: 0x0058,
    0x03F4: 0x0398,
    0x03BF: 0x006F,
}

GREEK_LATIN_SHAPED_MATH_ITALIC_ALIASES = {
    0x1D6E2: MATH_IT_UC['A'],
    0x1D6E3: MATH_IT_UC['B'],
    0x1D6E6: MATH_IT_UC['E'],
    0x1D6E7: MATH_IT_UC['Z'],
    0x1D6E8: MATH_IT_UC['H'],
    0x1D6EA: MATH_IT_UC['I'],
    0x1D6EB: MATH_IT_UC['K'],
    0x1D6ED: MATH_IT_UC['M'],
    0x1D6EE: MATH_IT_UC['N'],
    0x1D6F0: MATH_IT_UC['O'],
    0x1D6F2: MATH_IT_UC['P'],
    0x1D6F3: 0x1D6E9,
    0x1D6F5: MATH_IT_UC['T'],
    0x1D6F8: MATH_IT_UC['X'],
    0x1D70A: MATH_IT_LC['o'],
}

# mt2mit
MIT = {}
for i, u in enumerate(GREEK_UP_UC):
    MIT[i] = (u, None)
for i, u in enumerate(GREEK_IT_LC):
    MIT[0x0B + i] = (u, None)
MIT.update({
    0x28: (0x21BC, None), 0x29: (0x21BD, None),
    0x2A: (0x21C0, None), 0x2B: (0x21C1, None),
    0x2C: (None, 'lhook'), 0x2D: (None, 'rhook'),
    0x2E: (0x0028, 'parenleft'), 0x2F: (0x0029, 'parenright'),  # 46,47
    0x3A: (0x002E, 'period'), 0x3B: (0x002C, 'comma'),
    0x3C: (0x003C, 'less'), 0x3D: (0x002F, 'slash'), 0x3E: (0x003E, 'greater'),
    0x3F: (0x22C6, 'star'), 0x40: (0x1D715, 'partialdiff'),
    0x5B: (0x266D, 'flat'), 0x5C: (0x266E, 'natural'), 0x5D: (0x266F, 'sharp'),
    0x5E: (0x2323, 'smile'), 0x5F: (0x2322, 'frown'), 0x60: (0x2113, 'ell'),
    0x7B: (0x1D6A4, 'imath.it'), 0x7C: (0x1D6A5, 'jmath.it'),
    0x7D: (0x2118, 'weierstrass'), 0x7E: (0x1D718, 'varkappa.it'),
    0x7F: (0x03A9, 'Omega.up'),
    0x8A: (0x0021, 'exclam'), 0x8B: (0x003F, 'question'),
    0x8C: (0x005B, 'bracketleft'), 0x8D: (0x005D, 'bracketright'),
    0x8E: (0x2020, 'dagger'), 0x8F: (0x2021, 'daggerdbl'),
    0x90: (0x00A7, 'section'), 0x91: (0x00B6, 'paragraph'),
    0xB0: (None, 'varbeta.it'), 0xB1: (0x03D0, 'upvarbeta'),
    0xB2: (None, 'vardelta.it'), 0xB3: (None, 'upvardelta'),
    0xB4: (None, 'z.alt'),
    0xB5: (None, 'dbar.it'), 0xB6: (None, 'updbar'),
})
for i in range(10):
    MIT[0x30 + i] = (0x30 + i, None)  # Default math digits.
for c in range(ord('A'), ord('Z') + 1):
    MIT[c] = (MATH_IT_UC[chr(c)], None)
for c in range(ord('a'), ord('z') + 1):
    MIT[c] = (MATH_IT_LC[chr(c)], None)
for i, u in enumerate(GREEK_IT_UC):
    MIT[0x80 + i] = (u, None)
for i, u in enumerate(GREEK_UP_LC):
    slot = 0x92 + i if i < 14 else 160 + (i - 14)
    MIT[slot] = (u, None)
MIT[0xAF] = (0x03F0, 'upvarkappa')            # 175

# mt2syt
SYT = {
    0x00: (0x2212, 'minus'), 0x01: (0x22C5, 'dotmath'), 0x02: (0x00D7, 'multiply'),
    0x03: (0x2217, 'asteriskmath'), 0x04: (0x00F7, 'divide'), 0x05: (0x22C4, 'diamondmath'),
    0x06: (0x00B1, 'plusminus'), 0x07: (0x2213, 'minusplus'),
    0x08: (0x2295, None), 0x09: (0x2296, None), 0x0A: (0x2297, None),
    0x0B: (0x2298, None), 0x0C: (0x2299, None), 0x0D: (0x25CB, 'circlebig'),
    0x0E: (0x2218, 'openbullet'), 0x0F: (0x2219, 'bullet'),
    0x10: (0x224D, 'equivasymptotic'), 0x11: (0x2261, 'equivalence'),
    0x12: (0x2286, None), 0x13: (0x2287, None), 0x14: (0x2264, None), 0x15: (0x2265, None),
    0x16: (0x2AAF, 'precedesequal'), 0x17: (0x2AB0, 'followsequal'),
    0x18: (0x223C, 'similar'), 0x19: (0x2248, 'approxequal'),
    0x1A: (0x2282, None), 0x1B: (0x2283, None), 0x1C: (0x226A, 'muchless'),
    0x1D: (0x226B, 'muchgreater'), 0x1E: (0x227A, 'precedes'), 0x1F: (0x227B, 'follows'),
    0x20: (0x2190, None), 0x21: (0x2192, None), 0x22: (0x2191, None), 0x23: (0x2193, None),
    0x24: (0x2194, None), 0x25: (0x2197, None), 0x26: (0x2198, None), 0x27: (0x2243, None),
    0x28: (0x21D0, None), 0x29: (0x21D2, None), 0x2A: (0x21D1, None), 0x2B: (0x21D3, None),
    0x2C: (0x21D4, None), 0x2D: (0x2196, None), 0x2E: (0x2199, None), 0x2F: (0x221D, None),
    0x30: (0x2032, 'prime'), 0x31: (0x221E, 'infinity'),
    0x32: (0x2208, 'element'), 0x33: (0x220B, 'owner'),
    0x34: (0x25B3, 'triangle'), 0x35: (0x25BD, 'triangleinv'),
    0x36: (None, 'negationslash'), 0x37: (None, 'mapstochar'),
    0x38: (0x2200, 'universal'), 0x39: (0x2203, 'existential'),
    0x3A: (0x00AC, 'logicalnot'), 0x3B: (0x2205, 'emptyset'),
    0x3C: (0x211C, 'Rfraktur'), 0x3D: (0x2111, 'Ifraktur'),
    0x3E: (0x22A4, 'top'), 0x3F: (0x22A5, 'perpendicular'),
    0x40: (0x2135, 'aleph'),
    # MTPro2-specific symbol slots.
    0x41: (None, 'tie.sy'),
    0x42: (None, 'compose'),  # Small composition circle.
    0x43: (0x002B, 'plus'), 0x44: (0x003D, 'equal'),
    0x45: (0x20D7, 'vec.accent'),
    # mtpro2.sty: \triangleright=symbols@70, \triangleleft=symbols@71
    0x46: (0x25B7, 'triangleright'), 0x47: (0x25C1, 'triangleleft'),
    0x48: (None, 'Relbar'), 0x49: (0x003B, 'semicolon'),
    0x4A: (0x0300, 'grave.accent'), 0x4B: (0x0301, 'acute.accent'),
    0x4C: (0x030C, 'check.accent'), 0x4D: (0x0306, 'breve.accent'),
    0x4E: (0x0304, 'bar.accent'), 0x4F: (0x0302, 'hat.accent'),
    0x50: (0x0307, 'dot.accent'), 0x51: (0x0303, 'tilde.accent'),
    0x52: (0x0308, 'ddot.accent'), 0x53: (None, 'wwbar'),
    0x54: (None, 'dotup.accent'), 0x55: (None, 'ddotup.accent'),
    0x56: (0x030A, 'ring.accent'), 0x57: (0x003A, 'colon'),
    0x58: (0x2216, 'setdif'), 0x59: (0x228D, 'cupprod'), 0x5A: (0x2A40, 'capprod'),
    0x5B: (0x222A, 'union'), 0x5C: (0x2229, 'intersection'),
    0x5D: (0x228E, 'unionmulti'), 0x5E: (0x2227, 'logicaland'), 0x5F: (0x2228, 'logicalor'),
    0x60: (0x22A2, 'turnstileleft'), 0x61: (0x22A3, 'turnstileright'),
    0x62: (0x230A, 'floorleft'), 0x63: (0x230B, 'floorright'),
    0x64: (0x2308, 'ceilingleft'), 0x65: (0x2309, 'ceilingright'),
    0x66: (0x007B, 'braceleft'), 0x67: (0x007D, 'braceright'),
    0x68: (0x27E8, 'angbracketleft'), 0x69: (0x27E9, 'angbracketright'),
    0x6A: (0x007C, 'bar'), 0x6B: (0x2016, 'bardbl'),
    0x6C: (0x2195, 'arrowupdn'), 0x6D: (0x21D5, 'arrowdblupdn'),
    0x6E: (0x005C, 'backslash'), 0x6F: (0x2240, 'wreathproduct'),
    0x70: (0x221A, 'radical'), 0x71: (0x2A3F, 'coproduct.small'),
    0x72: (0x2207, 'nabla'), 0x73: (None, 'smallint'),
    0x74: (0x2294, 'unionsq'), 0x75: (0x2293, 'intersectionsq'),
    0x76: (0x2291, 'subsetsqequal'), 0x77: (0x2292, 'supersetsqequal'),
    0x78: (None, 'wbar'), 0x79: (None, 'what'), 0x7A: (None, 'wtilde'), 0x7B: (None, 'wcheck'),
    0x7C: (0x2663, 'club'), 0x7D: (0x2662, 'diamond'),
    0x7E: (0x2661, 'heart'), 0x7F: (0x2660, 'spade'),
    0x80: (0x2667, 'clubopen'), 0x81: (None, 'clubshaded'),
    0x82: (0x2664, 'spadeopen'), 0x83: (None, 'spadeshaded'),
    0x84: (0x210F, 'hbar'), 0x85: (0x2209, 'notelement'),
    0x86: (0x2220, 'angle'), 0x87: (0x2250, 'doteq'),
    0x88: (0x22A7, 'models'),  # models uses U+22A7; vDash uses U+22A8.
    0x89: (0x22C8, 'bowtie'), 0x8A: (0x2245, 'congruent'),
    0x8B: (0x21A9, None), 0x8C: (0x21AA, None), 0x8D: (0x27F5, None), 0x8E: (0x27F6, None),
    0x8F: (0x27F8, None), 0x90: (0x27F9, None), 0x91: (0x21A6, 'mapsto'),
    0x92: (0x27FC, None), 0x93: (0x27F7, None), 0x94: (0x27FA, None),
    0x95: (0x21CC, None),
    0x96: (0x226E, None), 0x97: (0x2270, None), 0x98: (0x2280, None), 0x99: (0x22E0, None),
    0x9A: (0x2284, None), 0x9B: (0x2288, None), 0x9C: (0x22E2, None), 0x9D: (0x226F, None),
    0x9E: (0x2271, None), 0x9F: (0x2281, None),
    160: (0x22E1, None), 161: (0x2285, None), 162: (0x2289, None), 163: (0x22E3, None),
    164: (0x2260, 'notequal'), 165: (0x2262, None), 166: (0x2241, None), 167: (0x2244, None),
    168: (0x2249, None), 169: (0x2247, None), 170: (0x226D, None),
    171: (0x20DB, 'dddot.accent'), 172: (0x20DC, 'ddddot.accent'),
    173: (None, 'dddotup.accent'), 174: (None, 'ddddotup.accent'),
    175: (None, 'hslash'), 176: (None, 'simarrow'), 177: (0x03DD, 'digamma'),
    178: (None, 'varland'), 179: (None, 'contraction'),
    180: (0x2254, 'coloneq'), 181: (0x2255, 'eqcolon'), 182: (0x2259, 'hateq'),
    183: (None, 'circdashbullet'), 184: (None, 'bulletdashcirc'),
    185: (None, 'braceleft.straight'), 186: (None, 'braceright.straight'),
}

# Encode text-size operators; name delimiter variants and parts from TFM recipes.
EXA_OPS = {   # slot(text): (unicode, name, display slot)
    0x50: (0x2211, 'summation', 0x58),
    0x51: (0x220F, 'product', 0x59),
    0x60: (0x2210, 'coproduct', 0x61),
    0x52: (0x222B, 'integral', 0x5A),
    0x48: (0x222E, 'contintegral', 0x49),
    0x4A: (0x2A00, 'circledot', 0x4B),
    0x4C: (0x2A01, 'circleplus', 0x4D),
    0x4E: (0x2A02, 'circlemultiply', 0x4F),
    0x53: (0x22C3, 'union.big', 0x5B),
    0x54: (0x22C2, 'intersection.big', 0x5C),
    0x55: (0x2A04, 'unionmulti.big', 0x5D),
    0x56: (0x22C0, 'logicaland.big', 0x5E),
    0x57: (0x22C1, 'logicalor.big', 0x5F),
    0x46: (0x2A06, 'unionsq.big', 0x47),
    146: (0x222C, 'iint', 147),
    148: (0x222D, 'iiint', 149),
    150: (0x222F, 'oiint', 151),
    152: (0x2230, 'oiiint', 153),
    154: (0x2232, 'cwoint', 155),
    156: (0x2233, 'awoint', 157),
    158: (0x2231, 'cwint', 159),
    142: (0x2A03, 'cupprod.big', 143),
    144: (None, 'capprod.big', 145),
    160: (None, 'slsum', 161),
    162: (None, 'slprod', 163),
    164: (None, 'slcoprod', 165),
    166: (None, 'varland.big', 167),
    168: (None, 'ast.big', 169),
    170: (0x2A0D, 'barint', 171),
    172: (0x2A0F, 'slashint', 173),
}
# Additional operator sizes: operator name -> source slots.
XL_TABLE = {  # name: (xl_slot(mt2xl 96..), XL(mt2xl 0..), XXL(mt2xl 48..), XXXL(mt2xxxl))
    'circledot': (96, 0, 48, 0),
    'circleplus': (97, 1, 49, 1),
    'circlemultiply': (98, 2, 50, 2),
    'unionsq.big': (99, 3, 51, 3),
    'union.big': (100, 4, 52, 4),
    'intersection.big': (101, 5, 53, 5),
    'unionmulti.big': (102, 6, 54, 6),
    'logicaland.big': (103, 7, 55, 7),
    'logicalor.big': (104, 8, 56, 8),
    'summation': (105, 9, 57, 9),
    'product': (106, 10, 58, 10),
    'coproduct': (107, 11, 59, 11),
    'integral': (108, 12, 60, 12),
    'contintegral': (109, 13, 61, 13),
    'cupprod.big': (110, 14, (62, 64), (14, 16)),
    'capprod.big': (111, 15, (63, 65), (15, 17)),
    'cwoint': (112, 16, 66, 18),
    'awoint': (113, 17, 67, 19),
    'cwint': (114, 18, 68, 20),
    'iint': (115, 19, 69, 21),
    'iiint': (116, 20, 70, 22),
    'oiint': (117, 21, 71, 23),
    'oiiint': (118, 22, 72, 24),
    'slsum': (119, 23, 73, 25),
    'slprod': (120, 24, 74, 26),
    'slcoprod': (121, 25, 75, 27),
    'varland.big': (122, 26, 76, (28, 29)),
    'ast.big': (123, 27, 77, 30),
    'barint': (124, 28, 78, 31),
    'slashint': (125, 29, 79, 32),
}

# Vertical delimiters: codepoint -> (base source, extension chain head).
V_DELIMS = {
    0x0028: (('mit', 46), 0x00), 0x0029: (('mit', 47), 0x01),
    0x005B: (('mit', 140), 0x02), 0x005D: (('mit', 141), 0x03),
    0x230A: (('syt', 0x62), 0x04), 0x230B: (('syt', 0x63), 0x05),
    0x2308: (('syt', 0x64), 0x06), 0x2309: (('syt', 0x65), 0x07),
    0x007B: (('syt', 0x66), 0x08), 0x007D: (('syt', 0x67), 0x09),
    0x27E8: (('syt', 0x68), 0x0A), 0x27E9: (('syt', 0x69), 0x0B),
    0x007C: (('syt', 0x6A), 0x0C), 0x2016: (('syt', 0x6B), 0x0D),
    0x002F: (('mit', 0x3D), 0x0E), 0x005C: (('syt', 0x6E), 0x0F),
    0x2191: (('syt', 0x22), 0x78), 0x2193: (('syt', 0x23), 0x79),
    0x2195: (('syt', 0x6C), 0x3F),
    0x21D1: (('syt', 0x2A), 0x7E), 0x21D3: (('syt', 0x2B), 0x7F),
    0x21D5: (('syt', 0x6D), 0x77),
    0x221A: (('syt', 0x70), 0x70),
}
# Straight-brace alternatives use their dedicated source chain heads.
V_DELIMS_ALT = {
    'braceleft.straight': (('syt', 185), 0xAE),
    'braceright.straight': (('syt', 186), 0xAF),
}

# Horizontal variants in ascending size order.
H_CHAINS = {
    0x0302: [('syt', 0x4F), ('syt', 0x79), ('exa', 98), ('exa', 99), ('exa', 100), ('exa', 128)],
    0x0303: [('syt', 0x51), ('syt', 0x7A), ('exa', 101), ('exa', 102), ('exa', 103), ('exa', 129)],
    0x030C: [('syt', 0x4C), ('syt', 0x7B), ('exa', 122), ('exa', 123), ('exa', 124), ('exa', 125)],
    0x0304: [('syt', 0x4E), ('syt', 0x78), ('syt', 0x53)],
    # Include long arrows as horizontal variants.
    0x2190: [('syt', 0x20), ('syt', 0x8D)],
    0x2192: [('syt', 0x21), ('syt', 0x8E)],
    0x2194: [('syt', 0x24), ('syt', 0x93)],
    0x21D0: [('syt', 0x28), ('syt', 0x8F)],
    0x21D2: [('syt', 0x29), ('syt', 0x90)],
    0x21D4: [('syt', 0x2C), ('syt', 0x94)],
    0x21A6: [('syt', 0x91), ('syt', 0x92)],
    0x23DC: [('exa', 190), ('exa', 191), ('exa', 192), ('exa', 193), ('exa', 194)],
}
# Named extension parts for TFM recipe references.
EXA_PIECES = {
    130: 'braceld', 131: 'bracerd', 132: 'bracelu', 133: 'braceru',
    117: 'radical.ex', 118: 'radical.tp',
    63: 'vertex.single', 119: 'vertex.double',
    120: 'arrowup.big', 121: 'arrowdown.big',
    126: 'arrowdblup.big', 127: 'arrowdbldown.big',
    136: 'braceleft.ex',
    48: 'parenleft.tp', 49: 'parenright.tp',
    64: 'parenleft.bt', 65: 'parenright.bt',
    66: 'parenleft.ex', 67: 'parenright.ex',
    50: 'bracketleft.tp', 51: 'bracketright.tp',
    52: 'bracketleft.bt', 53: 'bracketright.bt',
    54: 'bracketleft.ex', 55: 'bracketright.ex',
    56: 'braceleft.tp', 57: 'braceright.tp',
    58: 'braceleft.bt', 59: 'braceright.bt',
    60: 'braceleft.mid', 61: 'braceright.mid',
    62: 'braceright.ex', 116: 'radical.bt',
    134: 'cupprod.lhalf', 135: 'cupprod.rhalf',
}

# mt2syat (AMSa)
AMSA = {  # slot: (unicode, name)
    0x00: (0x22A1, 'boxdot'), 0x01: (0x229E, 'boxplus'), 0x02: (0x22A0, 'boxtimes'),
    0x03: (0x25A1, 'square'), 0x04: (0x25A0, 'blacksquare'), 0x05: (0x2B1D, 'centerdot'),
    0x06: (0x25CA, 'lozenge'), 0x07: (0x29EB, 'blacklozenge'),
    0x08: (0x21BB, 'circlearrowright'), 0x09: (0x21BA, 'circlearrowleft'),
    0x0B: (0x21CB, 'leftrightharpoons'), 0x0C: (0x229F, 'boxminus'),
    0x0D: (0x22A9, 'Vdash'), 0x0E: (0x22AA, 'Vvdash'), 0x0F: (0x22A8, 'vDash'),   # \vDash=AMSa@15
    0x10: (0x21A0, 'twoheadrightarrow'), 0x11: (0x219E, 'twoheadleftarrow'),
    0x12: (0x21C7, 'leftleftarrows'), 0x13: (0x21C9, 'rightrightarrows'),
    0x14: (0x21C8, 'upuparrows'), 0x15: (0x21CA, 'downdownarrows'),
    0x16: (0x21BE, 'upharpoonright'), 0x17: (0x21C2, 'downharpoonright'),
    0x18: (0x21BF, 'upharpoonleft'), 0x19: (0x21C3, 'downharpoonleft'),
    0x1A: (0x21A3, 'rightarrowtail'), 0x1B: (0x21A2, 'leftarrowtail'),
    0x1C: (0x21C6, 'leftrightarrows'), 0x1D: (0x21C4, 'rightleftarrows'),
    0x1E: (0x21B0, 'Lsh'), 0x1F: (0x21B1, 'Rsh'),
    0x20: (0x21DD, 'rightsquigarrow'), 0x21: (0x21AD, 'leftrightsquigarrow'),
    0x22: (0x21AB, 'looparrowleft'), 0x23: (0x21AC, 'looparrowright'),
    0x24: (0x2257, 'circeq'), 0x25: (0x227F, 'succsim'),
    0x26: (0x2273, 'gtrsim'), 0x27: (0x2A86, 'gtrapprox'),
    0x28: (0x22B8, 'multimap'), 0x29: (0x2234, 'therefore'), 0x2A: (0x2235, 'because'),
    0x2B: (0x2251, 'doteqdot'), 0x2C: (0x225C, 'triangleq'),
    0x2D: (0x227E, 'precsim'), 0x2E: (0x2272, 'lesssim'), 0x2F: (0x2A85, 'lessapprox'),
    0x30: (0x2A95, 'eqslantless'), 0x31: (0x2A96, 'eqslantgtr'),
    0x32: (0x22DE, 'curlyeqprec'), 0x33: (0x22DF, 'curlyeqsucc'),
    0x34: (0x227C, 'preccurlyeq'), 0x35: (0x2266, 'leqq'), 0x36: (0x2A7D, 'leqslant'),
    0x37: (0x2276, 'lessgtr'), 0x38: (0x2035, 'backprime'), 0x39: (None, 'midshaft'),
    0x3A: (0x2253, 'risingdotseq'), 0x3B: (0x2252, 'fallingdotseq'),
    0x3C: (0x227D, 'succcurlyeq'), 0x3D: (0x2267, 'geqq'), 0x3E: (0x2A7E, 'geqslant'),
    0x3F: (0x2277, 'gtrless'),
    0x40: (0x228F, 'sqsubset'), 0x41: (0x2290, 'sqsupset'),
    0x42: (0x22B3, 'vartriangleright'), 0x43: (0x22B2, 'vartriangleleft'),
    0x44: (0x22B5, 'trianglerighteq'), 0x45: (0x22B4, 'trianglelefteq'),
    0x46: (0x2605, 'bigstar'), 0x47: (0x226C, 'between'),
    0x48: (0x25BE, 'blacktriangledown'),  # Use the AMS family for all triangle directions.
    0x49: (0x25B6, 'blacktriangleright'),
    0x4A: (0x25C0, 'blacktriangleleft'), 0x4B: (None, 'rarrowhead'), 0x4C: (None, 'larrowhead'),
    0x4D: (0x25B5, 'vartriangle'), 0x4E: (0x25B4, 'blacktriangle'),
    0x4F: (0x25BF, 'triangledown.small'),
    0x50: (0x2256, 'eqcirc'), 0x51: (0x22DA, 'lesseqgtr'), 0x52: (0x22DB, 'gtreqless'),
    0x53: (0x2A8B, 'lesseqqgtr'), 0x54: (0x2A8C, 'gtreqqless'),
    0x56: (0x21DB, 'Rrightarrow'), 0x57: (0x21DA, 'Lleftarrow'),
    0x59: (0x22BB, 'veebar'), 0x5A: (0x22BC, 'barwedge'), 0x5B: (0x2A5E, 'doublebarwedge'),
    0x5D: (0x2221, 'measuredangle'), 0x5E: (0x2222, 'sphericalangle'),
    0x5F: (None, 'varpropto'),
    0x60: (None, 'smallsmile'), 0x61: (None, 'smallfrown'),
    0x62: (0x22D0, 'Subset'), 0x63: (0x22D1, 'Supset'),
    0x64: (0x22D3, 'Cup'), 0x65: (0x22D2, 'Cap'),
    0x66: (0x22CF, 'curlywedge'), 0x67: (0x22CE, 'curlyvee'),
    0x68: (0x22CB, 'leftthreetimes'), 0x69: (0x22CC, 'rightthreetimes'),
    0x6A: (0x2AC5, 'subseteqq'), 0x6B: (0x2AC6, 'supseteqq'),
    0x6C: (0x224F, 'bumpeq'), 0x6D: (0x224E, 'Bumpeq'),
    0x6E: (0x22D8, 'lll'), 0x6F: (0x22D9, 'ggg'),
    0x70: (0x231C, 'ulcorner'), 0x71: (0x231D, 'urcorner'),
    0x73: (0x24C8, 'circledS'), 0x74: (0x22D4, 'pitchfork'), 0x75: (0x2214, 'dotplus'),
    0x76: (0x223D, 'backsim'), 0x77: (0x22CD, 'backsimeq'),
    0x78: (0x231E, 'llcorner'), 0x79: (0x231F, 'lrcorner'),
    0x7B: (0x2201, 'complement'), 0x7C: (0x22BA, 'intercal'),
    0x7D: (0x229A, 'circledcirc'), 0x7E: (0x229B, 'circledast'), 0x7F: (0x229D, 'circleddash'),
    0x80: (None, 'lvertneqq'), 0x81: (None, 'gvertneqq'),
    0x88: (0x2268, 'lneqq'), 0x89: (0x2269, 'gneqq'),
    0x8A: (None, 'nleqslant'), 0x8B: (None, 'ngeqslant'),
    0x8C: (0x2A87, 'lneq'), 0x8D: (0x2A88, 'gneq'),
    0x8E: (None, 'npreceq'), 0x8F: (None, 'nsucceq'),
    0x90: (0x22E8, 'precnsim'), 0x91: (0x22E9, 'succnsim'),
    0x92: (0x22E6, 'lnsim'), 0x93: (0x22E7, 'gnsim'),
    0x94: (None, 'nleqq'), 0x95: (None, 'ngeqq'),
    0x96: (0x2AB5, 'precneqq'), 0x97: (0x2AB6, 'succneqq'),
    0x98: (0x2AB9, 'precnapprox'), 0x99: (0x2ABA, 'succnapprox'),
    0x9A: (0x2A89, 'lnapprox'), 0x9B: (0x2A8A, 'gnapprox'),
    0x9C: (None, 'nsim.ams'),
    0x9E: (0x27CB, 'diagup'), 0x9F: (0x27CD, 'diagdown'),
    # Encode subsetneq/supsetneq; expose alternate forms through cv features.
    160: (None, 'varsubsetneq'), 161: (None, 'varsupsetneq'),
    162: (None, 'nsubseteqq'), 163: (None, 'nsupseteqq'),
    164: (0x2ACB, 'subsetneqq'), 165: (0x2ACC, 'supsetneqq'),
    166: (None, 'varsubsetneqq'), 167: (None, 'varsupsetneqq'),
    168: (0x228A, 'subsetneq'), 169: (0x228B, 'supsetneq'),
    170: (None, 'nsubseteq.ams'), 171: (None, 'nsupseteq.ams'),
    172: (0x2226, 'nparallel'), 173: (0x2224, 'nmid'),
    174: (None, 'nshortmid'), 175: (None, 'nshortparallel'),
    176: (0x22AC, 'nvdash'), 177: (0x22AE, 'nVdash'),
    178: (0x22AD, 'nvDash'), 179: (0x22AF, 'nVDash'),
    180: (0x22ED, 'ntrianglerighteq'), 181: (0x22EC, 'ntrianglelefteq'),
    182: (0x22EA, 'ntriangleleft'), 183: (0x22EB, 'ntriangleright'),
    184: (0x219A, 'nleftarrow'), 185: (0x219B, 'nrightarrow'),
    186: (0x21CD, 'nLeftarrow'), 187: (0x21CF, 'nRightarrow'),
    188: (0x21CE, 'nLeftrightarrow'), 189: (0x21AE, 'nleftrightarrow'),
    190: (0x22C7, 'divideontimes'), 191: (None, 'varnothing'),
    192: (0x2204, 'nexists'),
    193: (0x2132, 'Finv'), 194: (0x2141, 'Game'), 195: (0x2127, 'mho'),
    196: (0x00F0, 'eth'), 197: (0x2242, 'eqsim'),
    198: (0x2136, 'beth'), 199: (0x2137, 'gimel'), 200: (0x2138, 'daleth'),
    201: (0x22D6, 'lessdot'), 202: (0x22D7, 'gtrdot'),
    203: (0x22C9, 'ltimes'), 204: (0x22CA, 'rtimes'),
    205: (None, 'shortmid'), 206: (None, 'shortparallel'),
    207: (None, 'thicksim'), 208: (None, 'thickapprox'),
    209: (0x224A, 'approxeq'), 210: (0x2AB8, 'succapprox'), 211: (0x2AB7, 'precapprox'),
    212: (0x21B6, 'curvearrowleft'), 213: (0x21B7, 'curvearrowright'),
    214: (0x03F6, 'backepsilon'),
    215: (None, 'nsqsubset'), 216: (None, 'nsqsupset'),
    219: (0x21E0, 'dashleftarrow'), 220: (0x21E2, 'dashrightarrow'),
    221: (None, 'leadsto'), 222: (0x25C7, 'Diamond'),
    223: (0x21C5, 'updownarrows'),   # "DF
    224: (0x21F5, 'downuparrows'),
    225: (0x296E, 'updownharpoons'), 226: (0x296F, 'downupharpoons'),
    227: (0x2963, 'upupharpoons'), 228: (0x2965, 'downdownharpoons'),
    229: (None, 'undercurvearrowleft'), 230: (None, 'undercurvearrowright'),
}


# Alphabet mappings.
def alpha_map(kind):
    """kind: bb / script / frak / bold / curly"""
    out = {}
    tables = {
        'bb': (BB_UC, BB_LC, 0x1D7D8, '.bb'),
        'script': (SCRIPT_UC, SCRIPT_LC, None, '.scr'),
        'frak': (FRAK_UC, FRAK_LC, None, '.frak'),
        'bold': (BOLD_UC, BOLD_LC, 0x1D7CE, '.bf'),
        'curly': ({c: None for c in SCRIPT_UC}, {c: None for c in SCRIPT_LC}, None, '.curly'),
    }
    uc, lc, dig, sfx = tables[kind]
    for c in range(ord('A'), ord('Z') + 1):
        u = uc[chr(c)]
        out[c] = (u, chr(c) + sfx)
    for c in range(ord('a'), ord('z') + 1):
        u = lc[chr(c)]
        out[c] = (u, chr(c) + sfx)
    if dig is not None:
        for i in range(10):
            out[0x30 + i] = (dig + i, chr(0x30 + i) + sfx)
    return out
