#!/usr/bin/env python3
"""Check public files for local inputs, runtime artifacts, and metric patterns."""
from __future__ import annotations

from pathlib import Path
import ast
import io
import re
import sys
import tokenize

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]).resolve()
REQUIRED = {
    'LICENSE', 'README', '.gitignore', 'build.sh',
    'doc/mtp2otf.tex',
}
FORBIDDEN_SUFFIXES = {
    '.pfb', '.pfm', '.tfm', '.otf', '.ttf', '.woff', '.woff2',
    '.pdf', '.aux', '.log', '.pyc', '.fd', '.sty',
}
PUBLIC_PDFS = {'doc/word.pdf', 'doc/lualatex.pdf', 'doc/mtp2otf.pdf'}
FORBIDDEN_BASENAMES = {
    'source-policy.json', 'math-constants.json', 'mtpro2-source-contract.json',
}
FORBIDDEN_DIRS = {'.git', '__pycache__', 'out', 'build', 'mtpro2', 'donors'}
PROSE_FILES = ('README', 'doc/mtp2otf.tex')
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


def _python_docstrings(path: Path):
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'))
    except (SyntaxError, UnicodeDecodeError) as exc:
        bad.append(f'{path.relative_to(ROOT)}: cannot parse public Python source: {exc}')
        return
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            yield first.lineno, first.value.value


bad: list[str] = []
for rel in sorted(REQUIRED):
    if not (ROOT / rel).is_file():
        bad.append(f'missing required public file: {rel}')

for p in ROOT.rglob('*'):
    relpath = p.relative_to(ROOT)
    rel = relpath.as_posix()
    if p.is_dir() and p.name in FORBIDDEN_DIRS:
        bad.append(f'forbidden private/generated directory: {rel}')
        continue
    if any(part in FORBIDDEN_DIRS for part in relpath.parts):
        continue
    if not p.is_file():
        continue
    if p.suffix.lower() in FORBIDDEN_SUFFIXES and rel not in PUBLIC_PDFS:
        bad.append(f'forbidden binary/runtime artifact: {rel}')
    if p.name in FORBIDDEN_BASENAMES:
        bad.append(f'forbidden local/static evidence file: {rel}')

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
    for kind, entries in (('comment', _python_comments(p)),
                          ('docstring', _python_docstrings(p))):
        for lineno, text in entries:
            for pattern in EVALUATED_COMMENT_PATTERNS:
                m = pattern.search(text)
                if m:
                    excerpt = ' '.join(text.split())[:140]
                    bad.append(
                        f'{p.relative_to(ROOT)}:{lineno}: possible evaluated MTPro2 value '
                        f'in public {kind}: {excerpt!r}')
                    break

if bad:
    print('PUBLIC SOURCE AUDIT FAIL', file=sys.stderr)
    for item in bad:
        print('  ' + item, file=sys.stderr)
    raise SystemExit(1)
