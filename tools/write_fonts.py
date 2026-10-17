"""Own system-Python OpenType editing and its final serialization."""

from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import tempfile

from fontTools.ttLib import TTFont

import font_geometry
import source_glyphs
import fixed_selectors
from contract_io import verify_contract
from mapping import load_alternates


@contextmanager
def stage(label):
    """Preserve the failing edit's identity during direct calls."""
    try:
        yield
    except (Exception, SystemExit) as exc:
        raise ValueError(label + ': ' + str(exc)) from exc


def read_native(native_otf, work, snapshot):
    """Reject stale/missing/changed native output; parse each payload
    once.
    """
    native_otf, work = Path(native_otf), Path(work)
    result = json.loads(
        (work / 'native-result.json').read_text(encoding='utf-8')
    )
    if (
        not isinstance(result, dict)
        or result.get('schema') != 'mtp2otf7-native-result/2'
    ):
        raise ValueError('invalid native result schema')
    if result.get('identity') != snapshot['build_identity']:
        raise ValueError('native result run/edition/coverage/UPM mismatch')
    if hashlib.sha256(native_otf.read_bytes()).hexdigest() != result.get(
        'native_otf_sha256'
    ):
        raise ValueError('native OTF differs from current result')
    filenames = ('math-constants.json', 'large-variant-build.json')
    if not isinstance(result.get('payloads'), dict) or set(
        result['payloads']
    ) != set(filenames):
        raise ValueError('native result payload inventory mismatch')
    payloads = {
        name: json.loads(
            verify_contract(work / name, result['payloads'][name])
        )
        for name in filenames
    }
    math = payloads['math-constants.json']
    if math.get('upm') != snapshot['build_identity']['upm']:
        raise ValueError('native MATH UPM mismatch')
    constants = font_geometry.local_math_values(math)
    inventory = payloads['large-variant-build.json']
    if (
        inventory.get('edition') != snapshot['build_identity']['edition']
        or inventory.get('policy') != 'source'
        or inventory.get('input_hashes') != snapshot['inputs']
    ):
        raise ValueError('native selector input/edition/policy mismatch')
    return constants, inventory


@dataclass(frozen=True)
class OriginalSources:
    """Parsed PFB/raw-TFM groups only; owned by one postprocessing call.
    """

    mbf: dict
    ams: dict | None = None
    alternates: dict | None = None
    ams_alternates: dict | None = None


def load_originals(catalog, snapshot, edition, ledger):
    """Reuse validated catalog faces, including raw TFM where required.
    """

    def group(roles):
        return catalog.originals(roles)

    mbf = group(('bold', 'bold_s', 'bold_ss'))
    if edition == 'lite':
        return OriginalSources(mbf)
    ams = group(('ams', 'ams_s', 'ams_ss'))
    tags = tuple(
        dict.fromkeys(
            style['alternate']['tag']
            for row in ledger
            for style in row['source_styles']
        )
    )
    return OriginalSources(mbf, ams, group(tags), ams)


def edit_full(font, originals, snapshot, ledger):
    """Full-only mutation sequence; all original faces were loaded by
    the
    owner.
    """
    with stage('AMS checkmark/maltese'):
        source_glyphs.add_ams_glyphs(font, originals.ams)
    with stage('optical alternates/Fraktur'):
        source_glyphs.add_optical_alternates(
            font, originals.alternates, snapshot, ledger
        )
    with stage('AMS yen/registered'):
        source_glyphs.add_ams_alternates(font, originals.ams_alternates)


def edit_initial(font, *, edition, constants):
    """Edit the native font up to the required CFF/bbox normalization
    boundary.
    """
    with stage('font_geometry'):
        font_geometry.edit(font, edition=edition, local_values=constants)


def edit_remaining(font, *, edition, inventory, originals, snapshot, ledger):
    """Install selectors and original-source additions after
    normalization.
    """
    with stage('fixed selectors'):
        fixed_selectors.edit(font, inventory)
    if edition == 'full':
        edit_full(font, originals, snapshot, ledger)
    with stage('original mathematical bold'):
        source_glyphs.add_original_bold(font, originals.mbf, snapshot, edition)


def process(native_otf, final_otf, *, work, catalog, snapshot, alternate_path):
    """Load, normalize CFF in memory, edit, and save atomically."""
    with stage('native handoff'):
        constants, inventory = read_native(native_otf, work, snapshot)
        edition = snapshot['build_identity']['edition']
        ledger = (
            load_alternates(alternate_path)['rows']
            if edition == 'full'
            else None
        )
    originals = load_originals(catalog, snapshot, edition, ledger)
    final_otf = Path(final_otf)
    final_otf.parent.mkdir(parents=True, exist_ok=True)
    with BytesIO() as normalized:
        with TTFont(native_otf) as font:
            edit_initial(font, edition=edition, constants=constants)
            # Fixed selectors require serialized head/CFF bounds.
            # Keep this in-memory compile/decompile before installing
            # them.
            # Earlier disk roundtrips are unnecessary.
            with stage('CFF/bbox normalization before selectors'):
                font.save(normalized, reorderTables=False)
        normalized.seek(0)
        with TTFont(normalized, recalcTimestamp=False) as font:
            edit_remaining(
                font,
                edition=edition,
                inventory=inventory,
                originals=originals,
                snapshot=snapshot,
                ledger=ledger,
            )
            _save_final(font, final_otf)


def _save_final(font, final_otf):
    """I/O helper of process; never called by an editing function."""
    with stage('final OTF serialization'):
        fd, name = tempfile.mkstemp(
            prefix='final-otf-', suffix='.otf', dir=final_otf.parent
        )
        os.close(fd)
        temporary = Path(name)
        try:
            font.save(temporary)
            with temporary.open('rb') as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, final_otf)
        finally:
            temporary.unlink(missing_ok=True)
