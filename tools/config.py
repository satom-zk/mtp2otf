"""Installation identities shared by the build and metadata checks."""

import argparse
import os
from pathlib import Path
import shutil
import importlib

import donors
from mapping import load_alternates, ALTERNATE_PATH

EDITIONS = {
    'full': ('MTPro2 Math', 'MTPro2Math'),
    'lite': ('MTPro2 Math Lite', 'MTPro2MathLite'),
}
# head.fontRevision is a 16.16 fixed-point field.
FONT_REVISION = round(1.3 * 65536) / 65536
FONT_VERSION = 'Version 1.3'


def identity(edition):
    if edition not in EDITIONS:
        raise ValueError(f'unknown edition: {edition}')
    family, basename = EDITIONS[edition]
    return family, basename, 'MTP2;' + basename


def parse_options(argv=None):
    parser = argparse.ArgumentParser(
        prog='./build.sh',
        allow_abbrev=False,
        description='Build MTPro2 OpenType math fonts.',
    )
    parser.add_argument(
        '--edition',
        choices=EDITIONS,
        default='full',
        help='font edition (default: full)',
    )
    parser.add_argument(
        '--roman-regular',
        metavar='PATH',
        help='regular Roman donor (default: donors/NimbusRoman-Regular.otf)',
    )
    parser.add_argument(
        '--roman-bold',
        metavar='PATH',
        help='bold Roman donor (default: donors/NimbusRoman-Bold.otf)',
    )
    parser.add_argument(
        '--donor-coverage',
        choices=donors.PUBLIC_MODES,
        default='minimal',
        help=(
            'minimal functional set or extended eligible '
            'donor characters (default: minimal)'
        ),
    )
    args = parser.parse_args(argv)
    return parser, args


def resolve_inputs(args, root, log, stage, run, hashes):
    import catalog
    import declarations

    required = declarations.required_source_files(
        declarations.active_tags(args.edition)
    )
    regular = Path(
        args.roman_regular or root / 'donors/NimbusRoman-Regular.otf'
    ).resolve()
    bold = Path(
        args.roman_bold or root / 'donors/NimbusRoman-Bold.otf'
    ).resolve()
    paths = [root / 'mtpro2' / name for name in required]
    paths += [regular, bold, donors.SPEC_PATH]
    if args.edition == 'full':
        paths.append(ALTERNATE_PATH)
    missing = []
    for path in paths:
        if not path.is_file():
            log.write(f'input name={path.name!r} path={str(path)!r} missing\n')
            missing.append(path)
        else:
            log.write(
                f'input name={path.name!r} path={str(path)!r} '
                f'size={path.stat().st_size} '
                f'sha256={catalog.sha(path, hashes)}\n'
            )
        log.flush()
    # Record both executable paths even when one dependency is absent.
    commands = {name: shutil.which(name) for name in ('fontforge', 'tftopl')}
    for name, path in commands.items():
        log.write(f'dependency {name} path={path or "unavailable"}\n')
    log.flush()
    absent = [name for name, path in commands.items() if path is None]
    if commands['tftopl']:
        probe = run('tftopl version', ['tftopl', '--version'], check=False)
        if probe.returncode:
            log.write('tftopl version unretrievable\n')
    forge = None
    if commands['fontforge']:
        forge = run(
            'FontForge / embedded Python version and support',
            [
                'fontforge',
                '-lang=py',
                '-c',
                (
                    'import sys, fontforge, psMat\n'
                    'try:\n'
                    '    version = fontforge.version()\n'
                    'except Exception as exc:\n'
                    '    version = "unretrievable (" + str(exc) + ")"\n'
                    'print("FontForge version:", version)\n'
                    'print("FontForge Python path:", sys.executable)\n'
                    'print("FontForge Python version:", sys.version)\n'
                    'sys.version_info >= (3, 10) or '
                    'sys.exit("FontForge embedded Python 3.10 '
                    'or later is required")'
                ),
            ],
            check=False,
        )
        if forge.returncode:
            log.write('FontForge / Python version or support check failed\n')
    stage('validate input files and dependencies')
    if missing:
        raise ValueError(
            f'{len(missing)} required input file(s) missing; '
            f'first: {missing[0]}'
        )
    if args.roman_regular == '' or args.roman_bold == '':
        raise ValueError('Roman donor paths must not be empty')
    donors.resolve_mode(args.donor_coverage, os.environ)
    if args.edition == 'full':
        load_alternates(ALTERNATE_PATH)
    for module in (
        'fontTools.ttLib',
        'fontTools.t1Lib',
        'fontTools.pens.cu2quPen',
    ):
        importlib.import_module(module)
    if absent:
        raise ValueError('required command not found: ' + ', '.join(absent))
    if forge is not None and forge.returncode:
        raise ValueError(
            'FontForge / embedded Python support: '
            f'exit code {forge.returncode}'
        )
    stage('validate Roman donors')
    donors.validate_inputs(regular, bold)
    return regular, bold
