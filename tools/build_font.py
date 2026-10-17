"""Private native entry: sources, geometry, and features in order."""

from contextlib import contextmanager, ExitStack
import hashlib
import json
import os
from pathlib import Path
import sys

import glyphs as sources
import outlines
import substitution
import primes
import constructions
import math_tables as features
import declarations
import donors
from compatibility_metrics import capture
from config import identity
from contract_io import write_contract

# FontForge script runners do not uniformly add the
# script's own directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))


@contextmanager
def stage(label):
    try:
        yield
    except (Exception, SystemExit) as exc:
        raise ValueError('native ' + label + ': ' + str(exc)) from exc


def read_snapshot(path, edition, coverage, condition):
    with Path(path).open(encoding='utf-8') as stream:
        snapshot = json.load(stream)
    run = snapshot['build_identity']
    if (
        run['edition'] != edition
        or run['donor_coverage'] != coverage
        or run['upm'] != 1000
        or snapshot['large_variants'] != condition
    ):
        raise ValueError(
            (
                'native inputs differ from the requested '
                'edition/coverage/condition'
            )
        )
    return snapshot


def write_payloads(
    font, work, edition, snapshot, imported, constants, min_overlap
):
    """Bind payloads to the serialized native font."""
    min_overlap = int(
        getattr(font.math, 'MinConnectorOverlap', min_overlap) or 0
    )
    math_expected = write_contract(
        work / 'math-constants.json',
        {
            'upm': font.em,
            'constants': dict(constants),
            'MinConnectorOverlap': min_overlap,
        },
    )
    inventory_expected = write_contract(
        work / 'large-variant-build.json',
        {
            'policy': 'source',
            'edition': edition,
            'input_hashes': snapshot['inputs'],
            'imports': [
                {'tag': tag, 'slot': slot, 'glyph': name}
                for (tag, slot), name in sorted(imported.items())
                if name in font
            ],
        },
    )
    return {
        'math-constants.json': math_expected,
        'large-variant-build.json': inventory_expected,
    }


def save_native(font, work, basename, snapshot, payloads):
    path = work / (basename + '.otf')
    font.generate(str(path), flags=('opentype',))
    write_contract(
        work / 'native-result.json',
        {
            'schema': 'mtp2otf7-native-result/2',
            'identity': snapshot['build_identity'],
            'native_otf_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'payloads': payloads,
        },
    )


def generate(
    root,
    work,
    snapshot_path,
    edition,
    regular,
    bold,
    coverage,
    policy,
    *,
    purpose='font',
    metrics_path=None
):
    if purpose not in ('font', 'windows') or policy != (
        'source' if purpose == 'font' else 'legacy'
    ):
        raise ValueError('invalid FontForge purpose/condition')
    if purpose == 'windows' and metrics_path is None:
        raise ValueError('compatibility metrics output absent')
    coverage = donors.public_mode(coverage)
    root, work = Path(root), Path(work)
    pl_dir = work / 'pl'
    pl_dir.mkdir(parents=True, exist_ok=True)
    with stage('input snapshot'):
        snapshot = read_snapshot(snapshot_path, edition, coverage, policy)
        rules = declarations.policy_from_data(snapshot)
        limits = constructions.VariantLimits(policy)
        spec = donors.load_spec() if coverage == 'minimal' else None
    with ExitStack() as owners:
        with stage('source faces'):
            faces = owners.enter_context(
                outlines.source_faces(root / 'mtpro2', edition, snapshot)
            )
        with sources.native_font() as font:
            family, basename, _ = identity(edition)
            font.encoding = 'UnicodeFull'
            font.em = 1000
            font.familyname = family
            font.fontname = basename
            font.fullname = family
            font.weight = 'Regular'
            font.copyright = (
                'Copyright (C) Publish or Perish, Inc. 2005.  '
                'Outlines from the MathTime(TM) Professional II Type1 fonts. '
                "Unofficial OpenType MATH conversion "
                "for the licensee's own use; "
                'redistribution of this font file is not permitted.'
            )
            glyphs = sources.GlyphSources(font, faces, rules, snapshot["plan"])
            with stage('core source glyphs'):
                operators = sources.import_core(glyphs, limits)
            with stage('Roman donor glyphs'):
                dotless_i, dotless_j = sources.import_roman(
                    glyphs, regular, bold
                )
            with stage('source alphabets and aliases'):
                alphabet = sources.import_bold_and_aliases(
                    glyphs, dotless_i, dotless_j
                )
            with stage('large variants'):
                variants = constructions.build_variants(
                    glyphs, limits, operators, snapshot['geometry']
                )
            with stage('accents and dots'):
                accents = constructions.build_accents_and_dots(glyphs)
            with stage('arrows and braces'):
                constructions.build_arrows_and_braces(
                    glyphs, limits, variants, accents
                )
            with stage('initial MATH'):
                constants, min_overlap = features.install_initial_math(
                    glyphs, accents
                )
            with stage('variant and connector geometry'):
                constructions.install_variant_geometry(
                    glyphs, limits, variants
                )
            with stage('optical source glyphs'):
                optical = sources.import_optical_forms(glyphs, accents)
            with stage('source prime geometry'):
                prime_accents = primes.build_primes(glyphs, optical)
            with stage('optical routes'):
                substitution.install_optical_routes(glyphs, optical, alphabet)
            with stage('remaining Roman donor'):
                sources.import_remaining_roman(
                    glyphs, regular, edition, coverage, spec
                )
            with stage('private codepoints'):
                features.assign_private_codepoints(glyphs)
            with stage('native metrics'):
                bounds = features.assign_metrics(
                    glyphs, cap_height=constants['FlattenedAccentBaseHeight']
                )
            # Exactly the same native glyph set/scan;
            # no source-only payloads.
            if purpose == 'windows':
                with stage('compatibility result'):
                    write_contract(
                        metrics_path, capture(font, snapshot, bounds)
                    )
                return
            with stage('source spacing and GDEF'):
                features.finish_source_features(
                    glyphs,
                    limits,
                    accents,
                    variants,
                    prime_accents=prime_accents,
                )
            with stage('source payloads'):
                payloads = write_payloads(
                    font,
                    work,
                    edition,
                    snapshot,
                    glyphs.imported,
                    constants,
                    min_overlap,
                )
            with stage('native range and donor checks'):
                features.check_native_ranges(glyphs)
                sources.check_minimal_supply(glyphs, spec, alphabet)
            with stage('serialization and handoff'):
                save_native(font, work, basename, snapshot, payloads)


def main(argv=None):
    import argparse

    p = argparse.ArgumentParser(description='Private FontForge backend entry')
    p.add_argument('--purpose', choices=('font', 'windows'), required=True)
    p.add_argument('--metrics-output', type=Path)
    args = p.parse_args(argv)
    generate(
        Path(__file__).resolve().parents[1],
        Path(os.environ['MTP2_BUILD_DIR']),
        Path(os.environ['MTP2_SOURCE_POLICY_JSON']),
        os.environ['MTP2_EDITION'],
        Path(os.environ['MTP2_ROMAN_REGULAR']),
        Path(os.environ['MTP2_ROMAN_BOLD']),
        os.environ[donors.INTERNAL_MODE],
        os.environ['MTP2_LARGE_VARIANTS'],
        purpose=args.purpose,
        metrics_path=args.metrics_output,
    )


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as exc:
        print('error: ' + str(exc), file=sys.stderr)
        raise SystemExit(1) from None
