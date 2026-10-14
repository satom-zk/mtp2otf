"""Private native entry: sources, geometry, and features in order."""
from contextlib import contextmanager, ExitStack
import hashlib
import json
import os
from pathlib import Path
import sys

# FontForge script runners do not uniformly add the
# script's own directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ff_sources as sources
import ff_constructions as constructions
import ff_features as features
import source_policy
import donor_coverage
from compatibility_metrics import capture
from build_config import identity
from contract_io import write_contract


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
    font, work, edition, snapshot, imported, ordinary_ic, constants,
    min_overlap
):
    """Bind payloads to the serialized native font."""
    _source_contract_path = str(work / 'ordinary-ic.json')
    _source_contract_expected = write_contract(
        _source_contract_path,
        {
            'ordinary_ic_lefts': [
                {'glyph': name, 'italic_correction': value}
                for name, value in sorted(ordinary_ic.items())
            ],
        }
    )
    min_overlap = int(
        getattr(font.math, 'MinConnectorOverlap', min_overlap) or 0
    )
    math_expected = write_contract(
        work / 'math-constants.json',
        {
            'upm': font.em, 'constants': dict(constants),
            'MinConnectorOverlap': min_overlap
        }
    )
    inventory_expected = write_contract(
        work / 'large-variant-build.json',
        {
            'policy': 'source', 'edition': edition,
            'input_hashes': snapshot['inputs'],
            'imports': [
                {'tag': tag, 'slot': slot, 'glyph': name}
                for (tag, slot), name in sorted(imported.items())
                if name in font
            ],
        }
    )
    return {
        'ordinary-ic.json': _source_contract_expected,
        'math-constants.json': math_expected,
        'large-variant-build.json': inventory_expected
    }


def save_native(font, work, basename, snapshot, payloads, prime_shift):
    path = work / (basename + '.otf')
    font.generate(str(path), flags=('opentype',))
    write_contract(
        work / 'native-result.json',
        {
            'schema': 'mtp2otf7-native-result/1',
            'identity': snapshot['build_identity'],
            'native_otf_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'prime_shift': prime_shift, 'payloads': payloads,
        }
    )


def generate(
    root, work, snapshot_path, edition, regular, bold, coverage, policy, *,
    purpose='font', metrics_path=None
):
    if (
        purpose not in ('font', 'windows')
        or policy != ('source' if purpose == 'font' else 'legacy')
    ):
        raise ValueError('invalid FontForge purpose/condition')
    if purpose == 'windows' and metrics_path is None:
        raise ValueError('compatibility metrics output absent')
    coverage = donor_coverage.public_mode(coverage)
    root, work = Path(root), Path(work)
    pl_dir = work / 'pl'
    pl_dir.mkdir(parents=True, exist_ok=True)
    with stage('input snapshot'):
        snapshot = read_snapshot(snapshot_path, edition, coverage, policy)
        rules = source_policy.policy_from_data(snapshot)
        limits = constructions.VariantLimits(policy)
        spec = donor_coverage.load_spec() if coverage == 'minimal' else None
    with ExitStack() as owners:
        with stage('source faces'):
            faces = owners.enter_context(
                sources.source_faces(
                    root / 'mtpro2', pl_dir, edition, snapshot
                )
            )
        with sources.native_font() as font:
            family, basename, _ = identity(edition)
            font.encoding = 'UnicodeFull'
            font.em = 1000
            font.familyname = family
            font.fontname = basename
            font.fullname = family
            font.weight = 'Regular'
            font.copyright = ('Copyright (C) Publish or Perish, Inc. 2005.  '
            'Outlines from the MathTime(TM) Professional II Type1 fonts. '
            "Unofficial OpenType MATH conversion for the licensee's own use; "
            'redistribution of this font file is not permitted.')
            glyphs = sources.GlyphSources(font, faces, rules)
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
                optical = features.import_optical_forms(glyphs, accents)
            with stage('Word prime geometry'):
                prime_shift = constructions.build_word_primes(
                    glyphs, optical, snapshot['geometry']
                )
            with stage('optical routes'):
                features.install_optical_routes(glyphs, optical, alphabet)
            with stage('remaining Roman donor'):
                sources.import_remaining_roman(
                    glyphs, regular, edition, coverage, spec
                )
            with stage('private codepoints'):
                features.assign_private_codepoints(glyphs)
            with stage('native metrics'):
                bounds = features.assign_metrics(glyphs)
            # Exactly the same native glyph set/scan;
            # no source-only payloads.
            if purpose == 'windows':
                with stage('compatibility result'):
                    write_contract(
                        metrics_path, capture(font, snapshot, bounds)
                    )
                return
            with stage('source spacing and GDEF'):
                ordinary_ic = features.finish_source_features(
                    glyphs, limits, accents, variants
                )
            with stage('source payloads'):
                payloads = write_payloads(
                    font, work, edition, snapshot, glyphs.imported,
                    ordinary_ic, constants, min_overlap
                )
            with stage('native range and donor checks'):
                features.check_native_ranges(glyphs)
                sources.check_minimal_supply(glyphs, spec, alphabet)
            with stage('serialization and handoff'):
                save_native(
                    font, work, basename, snapshot, payloads, prime_shift
                )


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
        os.environ['MTP2_EDITION'], Path(os.environ['MTP2_ROMAN_REGULAR']),
        Path(os.environ['MTP2_ROMAN_BOLD']),
        os.environ[donor_coverage.INTERNAL_MODE],
        os.environ['MTP2_LARGE_VARIANTS'], purpose=args.purpose,
        metrics_path=args.metrics_output
    )


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as exc:
        print('error: ' + str(exc), file=sys.stderr)
        raise SystemExit(1) from None
