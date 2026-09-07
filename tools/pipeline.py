"""Build and validate one edition before publishing its fonts to out/."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from build_config import EDITIONS, identity


def main():
    parser = argparse.ArgumentParser(prog='./build.sh', allow_abbrev=False)
    parser.add_argument('--edition', choices=EDITIONS, default='full')
    parser.add_argument('--roman-regular')
    parser.add_argument('--roman-bold')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = root / 'mtpro2'
    donors = root / 'donors'

    for command in ('fontforge', 'tftopl'):
        if not shutil.which(command):
            parser.exit(2, f'error: required command not found: {command}\n')
    for module in ('fontTools.ttLib', 'fontTools.t1Lib', 'fontTools.pens.cu2quPen'):
        try:
            importlib.import_module(module)
        except ImportError as exc:
            parser.exit(2, f'error: required Python module unavailable: {module}: {exc}\n')

    import source_policy
    from audit_original_source_contract import audit as audit_original

    tags = source_policy.active_tags(args.edition)
    required = source_policy.required_source_files(tags)
    missing = [name for name in required
               if not (source / name).is_file()]
    regular = args.roman_regular
    bold = args.roman_bold
    if regular == '' or bold == '':
        parser.exit(2, 'error: Roman donor paths must not be empty\n')
    regular = Path(regular or donors / 'NimbusRoman-Regular.otf').resolve()
    bold = Path(bold or donors / 'NimbusRoman-Bold.otf').resolve()
    missing_donors = [str(p) for p in (regular, bold) if not p.is_file()]
    if missing or missing_donors:
        if len(missing) == len(required):
            parser.exit(2, 'error: build inputs are not ready.\n\n'
                        'Place the MTPro2 files in mtpro2/\n'
                        'and the Roman donor fonts in donors/.\n\n'
                        'See README for details.\n')
        lines = ['error: build inputs are not ready.', '']
        if missing:
            lines += ['Missing files in mtpro2/:', *('  ' + n for n in missing)]
        if missing_donors:
            lines += ['Missing Roman donors:', *('  ' + n for n in missing_donors)]
        parser.exit(2, '\n'.join(lines) + '\n')

    family, basename, _ = identity(args.edition)
    work = root / 'build' / args.edition
    work.mkdir(parents=True, exist_ok=True)
    log_path = work / 'build.log'
    policy_path = work / 'source-policy.json'
    contract = work / 'mtpro2-source-contract.json'
    values = work / 'math-constants.json'
    otf = work / (basename + '.otf')
    ttf = work / (basename + '.ttf')
    env = dict(os.environ, MTP2_EDITION=args.edition,
               MTP2_BUILD_DIR=str(work), MTP2_SOURCE_POLICY_JSON=str(policy_path),
               MTP2_SYSTEM_PYTHON=sys.executable, MTP2_ROMAN_REGULAR=str(regular),
               MTP2_ROMAN_BOLD=str(bold), PYTHONDONTWRITEBYTECODE='1')
    tools = root / 'tools'

    print(f'building {family}', flush=True)
    with log_path.open('w+', encoding='utf-8') as log:
        def run(label, command):
            log.write(f'\n{label}\n')
            log.flush()
            start = log.tell()
            result = subprocess.run([str(x) for x in command], env=env,
                                    stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                log.seek(start)
                diagnostic = log.read()
                print(f'error: {label}', file=sys.stderr)
                print(diagnostic, end='' if diagnostic.endswith('\n') else '\n',
                      file=sys.stderr)
                print(f'see {log_path.relative_to(root)}', file=sys.stderr)
                raise SystemExit(1)
            log.seek(0, 2)

        def tool(name, *arguments):
            run(name, [sys.executable, tools / name, *arguments])

        run('FontForge Python 3.10 support', ['fontforge', '-lang=py', '-c',
                                             'import sys, fontforge, psMat; '
                                             'sys.version_info >= (3, 10) or '
                                             'sys.exit("FontForge embedded Python 3.10 or later is required")'])
        tool('audit_roman_donor_contract.py', '--regular', regular,
             '--bold', bold, '--check-inputs-only')
        policy = source_policy.extract_policy(source, tags)
        audit_original(source, args.edition, policy)
        payload = policy.to_jsonable()
        payload['source_font_by_tag'] = {t: source_policy.SOURCE_FONTS[t] for t in sorted(tags)}
        payload['policy_source_files'] = list(source_policy.required_policy_files(tags))
        payload['geometry'] = source_policy.extract_geometry(source, policy)
        payload['inputs'] = {
            'mtpro2': {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
                       for name in source_policy.required_source_files(tags)},
            'donors': {role: {'name': path.name,
                              'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                       for role, path in (('regular', regular), ('bold', bold))},
        }
        policy_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n',
                               encoding='utf-8')

        # A failed producer must not leave an earlier candidate eligible for reuse.
        for candidate in (otf, ttf, contract, values):
            candidate.unlink(missing_ok=True)
        run('FontForge build', ['fontforge', '-lang=py', '-script', tools / 'build.py'])
        for artifact in (otf, contract, values):
            if not artifact.is_file():
                raise ValueError(f'producer did not write {artifact.relative_to(root)}')
        tool('validate.py', otf)
        tool('audit_edition_naming.py', otf, '--edition', args.edition)
        tool('audit_source_contract.py', otf, '--contract', contract,
             '--tfm-dir', source, '--edition', args.edition)
        if args.edition == 'full':
            tool('audit_bb_option_ssty.py', otf, '--contract', contract)
        else:
            tool('audit_lite_semantic_contract.py', otf)
        tool('audit_roman_donor_contract.py', otf, '--regular', regular,
             '--bold', bold, '--sty', source / 'mtpro2.sty')
        tool('otf2ttf.py', otf, ttf)
        tool('validate.py', ttf)
        tool('audit_edition_naming.py', ttf, '--edition', args.edition)
        tool('verify_otf_ttf.py', otf, ttf)
        tool('audit_source_contract.py', ttf, '--reference-font', otf,
             '--contract', contract, '--tfm-dir', source, '--edition', args.edition)
        tool('audit_math_values.py', otf, '--values', values)

    output = root / 'out'
    output.mkdir(exist_ok=True)
    for font in (otf, ttf):
        destination = output / font.name
        # Replace each validated file intact; no multi-file transaction is claimed.
        fd, name = tempfile.mkstemp(prefix=font.name + '.', suffix='.tmp', dir=output)
        os.close(fd)
        temporary = Path(name)
        try:
            shutil.copy2(font, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        diagnostic = exc.stderr or str(exc)
        if isinstance(diagnostic, bytes):
            diagnostic = diagnostic.decode('utf-8', errors='replace')
        print(f'error: {diagnostic}', file=sys.stderr)
        raise SystemExit(1) from None
    except (OSError, ValueError, KeyError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        raise SystemExit(1) from None
