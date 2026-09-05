#!/usr/bin/env python3
"""Check public files for local inputs, runtime artifacts, and metric patterns."""
from __future__ import annotations

from pathlib import Path
import io
import re
import sys
import tokenize

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]).resolve()
REQUIRED = {
    'LICENSE', 'readme.txt', '.gitignore',
    'build.sh',
    'mtpro2/PUT_LOCAL_MTPRO2_HERE.txt',
    'times/PUT_LOCAL_NIMBUS_HERE.txt',
}
FORBIDDEN_SUFFIXES = {
    '.pfb', '.pfm', '.tfm', '.otf', '.ttf', '.woff', '.woff2',
    '.pdf', '.aux', '.log', '.pyc', '.fd', '.sty',
}
PUBLIC_SPECIMENS = {'doc/word.pdf', 'doc/lualatex.pdf'}
FORBIDDEN_BASENAMES = {
    'mtpro2.sty', 'REPORT.txt',
    'LOCAL-SOURCE-VALUES.json', 'LOCAL-MATH-VALUES.json', 'LOCAL-BUILD-MEMO.txt',
    'source-policy.json', 'math-constants.json', 'mtpro2-source-contract.json',
}
FORBIDDEN_DIRS = {'.git', '__pycache__', 'out', 'build'}
PROSE_FILES = ('readme.txt',)
# These patterns intentionally target table/report-like evaluated measurements,
# not version numbers, Unicode identities, TeX slots, or CSS values.
EVALUATED_PROSE_PATTERNS = (
    re.compile(r'(?i)fontdimen[^\n<]{0,80}=\s*[-+]?\d'),
    re.compile(
        r'(?i)(?:source metrics?|ordinary\s+TFM\s+kern\s+pairs|ordinary\s+nonzero-IC)[^\n<]{0,80}\d'),
    re.compile(
        r'(?i)(?:x-height|rule thickness|GPOS adjustment|ymin|ink center)[^\n<]{0,80}=\s*[-+]?\d'),
)

# Public source comments/docstrings may describe formulas and structural identities.
# Evaluated source measurements are local evidence only.  Conversion-policy
# constants in executable code are project policy, not values copied from MTPro2.
EVALUATED_COMMENT_PATTERNS = (
    re.compile(r'(?i)fontdimen[^\n]{0,100}=\s*[-+]?\d'),
    re.compile(r'(?i)(?:ink|advance|width|height|ymin|overhang|kern|skewchar|connector|metric)'
               r'[^\n]{0,100}[-+]?\d+(?:\.\d+)?\s*(?:u|em|pt|units?)\b'),
    re.compile(r'(?i)(?:measured|observed|accepted|source-derived)[^\n]{0,100}'
               r'[-+]?\d+(?:\.\d+)?\s*(?:u|em|pt|units?)\b'),
)


def _python_comments(path: Path):
    try:
        data = path.read_bytes()
        for token in tokenize.tokenize(io.BytesIO(data).readline):
            if token.type == tokenize.COMMENT:
                yield token.start[0], token.string
    except (SyntaxError, UnicodeDecodeError, tokenize.TokenError) as exc:
        bad.append(f'{path.relative_to(ROOT)}: cannot tokenize public Python source: {exc}')


bad: list[str] = []
for rel in sorted(REQUIRED):
    if not (ROOT / rel).is_file():
        bad.append(f'missing required public file: {rel}')

for p in ROOT.rglob('*'):
    rel = p.relative_to(ROOT).as_posix()
    if any(part in FORBIDDEN_DIRS for part in p.relative_to(ROOT).parts):
        if p.is_file():
            bad.append(f'private/generated directory content: {rel}')
        continue
    if not p.is_file():
        continue
    if p.suffix.lower() in FORBIDDEN_SUFFIXES and rel not in PUBLIC_SPECIMENS:
        bad.append(f'forbidden binary/runtime artifact: {rel}')
    if p.name in FORBIDDEN_BASENAMES or p.name.startswith('LOCAL-'):
        bad.append(f'forbidden local/static evidence file: {rel}')
    if p.suffix.lower() in {'.fd', '.dtx'} and rel.startswith('mtpro2/'):
        bad.append(f'proprietary MTPro2 source file: {rel}')

for directory in ('mtpro2', 'times'):
    q = ROOT / directory
    if q.is_dir():
        placeholder = {
            'mtpro2': 'PUT_LOCAL_MTPRO2_HERE.txt',
            'times': 'PUT_LOCAL_NIMBUS_HERE.txt',
        }[directory]
        extras = sorted(x.name for x in q.iterdir() if x.name != placeholder)
        if extras:
            bad.append(f'{directory}/ contains local inputs: {", ".join(extras)}')

for rel in PROSE_FILES:
    p = ROOT / rel
    if not p.is_file():
        continue
    text = p.read_text(encoding='utf-8', errors='replace')
    for pattern in EVALUATED_PROSE_PATTERNS:
        m = pattern.search(text)
        if m:
            excerpt = ' '.join(m.group(0).split())[:120]
            bad.append(f'{rel}: possible evaluated MTPro2 value in public prose: {excerpt!r}')

for p in sorted((ROOT / 'tools').glob('*.py')) if (ROOT / 'tools').is_dir() else ():
    for lineno, comment in _python_comments(p):
        for pattern in EVALUATED_COMMENT_PATTERNS:
            m = pattern.search(comment)
            if m:
                excerpt = ' '.join(comment.split())[:140]
                bad.append(
                    f'{p.relative_to(ROOT)}:{lineno}: possible evaluated MTPro2 value in public comment: {excerpt!r}')
                break

if bad:
    print('PUBLIC SOURCE AUDIT FAIL', file=sys.stderr)
    for item in bad:
        print('  ' + item, file=sys.stderr)
    raise SystemExit(1)
print('PUBLIC SOURCE AUDIT PASS: no prohibited paths or matching metric patterns; named specimen PDFs are permitted')
