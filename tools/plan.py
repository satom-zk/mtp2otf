"""Plan required source references and construction dependencies.

Mapping owns semantic slots. TFM supplies chain/assembly relationships.
Encoding and CharStrings establish presence without substituting slots.
"""

from dataclasses import dataclass, field
import json

import mapping as U
import donors


@dataclass
class GenerationPlan:
    native: dict
    originals: dict
    routes: list
    coverage: str
    alternate_rows: list = field(default_factory=list, repr=False)

    def to_data(self):
        return dict(
            native={t: sorted(s) for t, s in self.native.items()},
            originals={t: sorted(s) for t, s in self.originals.items()},
            routes=self.routes,
            donor_coverage=self.coverage,
        )


def create(catalog, coverage):
    native, post, routes = {}, {}, []
    ledger = []

    def add(tag, slots, target=native):
        if tag in catalog.faces:
            target.setdefault(tag, set()).update(slots)

    def optical(tag, table):
        for suffix in ['', '_s', '_ss']:
            add(tag + suffix, table)

    for tag, table in [('mit', U.MIT), ('syt', U.SYT), ('ams', U.AMSA)]:
        optical(tag, table)
    for tag, kind in [
        ('bb', 'bb'),
        ('script', 'script'),
        ('frak', 'frak'),
        ('curly', 'curly'),
        ('bscript', 'bscript'),
        ('bfrak', 'bfrak'),
        ('bbd', 'bb'),
        ('bbi', 'bb'),
        ('hrb', 'bb'),
        ('hrbd', 'bb'),
        ('hbi', 'bb'),
    ]:
        optical(tag, U.alpha_map(kind))
    optical('bmit', U.bold_source_slots())
    optical(
        'bsyt', [slot for slot, (cp, name) in U.SYT.items() if cp == 0x2207]
    )
    for slot, (cp, name, display) in U.EXA_OPS.items():
        add('exa', [slot, display])
        if name in U.XL_TABLE:
            for tag, s in zip(['xl', 'xl', 'xl', 'xxxl'], U.XL_TABLE[name]):
                add(tag, s if isinstance(s, tuple) else [s])
    starts = []
    for cp, (base, start) in list(U.V_DELIMS.items()) + list(
        U.V_DELIMS_ALT.items()
    ):
        add(base[0], [base[1]])
        add('exa', [start])
        starts.append(('exa', start))
        if cp in U.V_DELIMS:
            for tag in ['exe', 'exf', 'exg']:
                chars = catalog.faces[tag].tfm.chars
                targets = {
                    v['next']
                    for v in chars.values()
                    if v.get('next') is not None
                }
                if start in chars and start not in targets:
                    starts.append((tag, start))
                    add(tag, [start])
    for cp, chain in U.H_CHAINS.items():
        for tag, slot in chain:
            add(tag, [slot])
        if cp in [0x302, 0x303, 0x30C]:
            exa = [s for t, s in chain if t == 'exa']
            if exa:
                for tag in ['exe', 'exf', 'exg']:
                    chars = catalog.faces[tag].tfm.chars
                    targets = {
                        v['next']
                        for v in chars.values()
                        if v.get('next') is not None
                    }
                    if exa[0] in chars and exa[0] not in targets:
                        starts.append((tag, exa[0]))
                        add(tag, [exa[0]])
    add('exa', U.SOURCE_BRACE_PIECES + U.SOURCE_MORPHED_SLOTS + (195,))
    add('exf', U.SOURCE_OVERPAREN_CONTINUATION)
    for tag, start in U.SOURCE_WIDEARC_CHAINS:
        add(tag, [start])
        starts.append((tag, start))
    for cp, series in U.SOURCE_BRACE_SERIES:
        for tag, first, last in series:
            add(tag, range(first, last + 1))
    # Native chains include their original VARCHAR components.
    # Keep cycle/error checks.
    for tag, start in starts:
        chars = catalog.faces[tag].tfm.chars
        slot = start
        seen = set()
        while slot is not None and slot in chars and slot not in seen:
            seen.add(slot)
            add(tag, [slot])
            v = chars[slot]
            if v.get('varchar'):
                add(tag, v['varchar'].values())
            slot = v.get('next')
        if slot is not None and slot not in chars:
            # Keep the missing target in the required set for joint
            # preflight.
            add(tag, [slot])
        elif slot is not None:
            raise ValueError(
                f'plan {catalog.faces[tag].stem}.tfm role={tag} slot={slot}: '
                'broken NEXTLARGER chain'
            )
    # Independent original-source additions intentionally use binary
    # metrics.
    import source_glyphs as additions

    for row in additions.bold_identities():
        add(row['source_role'], [row['source_slot']], post)
    if catalog.edition == 'full':
        for role in ['ams', 'ams_s', 'ams_ss']:
            add(role, [88, 122, 85, 114], post)
        ledger = U.load_alternates(U.ALTERNATE_PATH)['rows']
        for row in ledger:
            routes.append(row['semantic_id'])
            for style in row['source_styles']:
                alt = style['alternate']
                add(alt['tag'], [alt['slot']], post)
                if alt['font'] != U.SOURCE_FONTS[alt['tag']]:
                    raise ValueError('plan alternate source family mismatch')
                if (
                    alt['accent_calibration']['skewchar']
                    != catalog.declarations.skewchar_by_tag[alt['tag']]
                ):
                    raise ValueError('plan alternate skew policy mismatch')
    return GenerationPlan(native, post, routes, coverage, ledger)


def source_status(face, slot, chars):
    """Check presence using dictionaries/metrics already read."""
    encoding = face.font['Encoding']
    name = encoding[slot] if 0 <= slot < len(encoding) else None
    present = name is not None and name in face.font['CharStrings']
    return dict(
        encoding_name=name,
        charstring_present=present,
        pfb_usable=bool(name and name != '.notdef' and present),
        tfm_valid=slot in chars,
    )


def check_sources(catalog, generation, coverage, *, log=None):
    missing = []
    for phase, table in [
        ('native', generation.native),
        ('original additions', generation.originals),
    ]:
        for role, slots in table.items():
            face = catalog.faces[role]
            if phase == 'original additions':
                if tuple(face.font['FontMatrix']) != (
                    0.001,
                    0,
                    0,
                    0.001,
                    0,
                    0,
                ):
                    raise ValueError(
                        f'preflight {face.pfb_path.name} role={role}: '
                        'unsupported FontMatrix'
                    )
                chars = face.raw_metrics().chars
            else:
                chars = face.tfm.chars
            for slot in sorted(slots):
                status = source_status(face, slot, chars)
                if status['pfb_usable'] and status['tfm_valid']:
                    continue
                record = dict(
                    phase=phase,
                    role=role,
                    pfb_file=str(face.pfb_path),
                    tfm_file=str(face.tfm_path),
                    slot=slot,
                    slot_hex=f'0x{slot:02X}',
                    **status,
                )
                # Reuse the small ledger already read by create.
                # No reverse index is needed.
                for row in generation.alternate_rows:
                    for style in row['source_styles']:
                        alt = style['alternate']
                        if alt['tag'] == role and alt['slot'] == slot:
                            record.setdefault('semantic_sources', []).append(
                                dict(
                                    semantic_id=row['semantic_id'],
                                    style=style['style'],
                                )
                            )
                missing.append(record)
                if log is not None:
                    log.write(
                        'required source missing: ' + json.dumps(record) + '\n'
                    )
                    log.flush()
    if missing:
        first = missing[0]
        raise ValueError(
            f'{len(missing)} required source reference(s) missing; first: '
            f'{first["phase"]} role={first["role"]} '
            f'slot={first["slot"]} ({first["slot_hex"]})'
        )
    for role in ['bold', 'bold_s', 'bold_ss']:
        if catalog.declarations.skewchar_by_tag.get(role) != 32:
            raise ValueError(
                f'preflight role={role}: mbf source/skewchar role mismatch'
            )
    donors.check_supply(catalog.donors, coverage)
