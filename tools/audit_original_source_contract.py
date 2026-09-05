#!/usr/bin/env python3
"""Audit local MTPro2 declarations against structural source identities."""
from __future__ import annotations

import argparse
from pathlib import Path
import re

import source_policy


def _read(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f'missing original MTPro2 source declaration: {path}')
    return path.read_text(encoding='latin-1')


def _need(text: str, pattern: str, label: str) -> None:
    if not re.search(pattern, text, re.DOTALL):
        raise SystemExit(f'original-source contract missing: {label}')


def _active_tags(edition: str):
    return source_policy.LITE_TAGS if edition == 'lite' else source_policy.SOURCE_FONTS.keys()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--mtpro2-dir', required=True)
    ap.add_argument('--edition', choices=('full', 'lite'), default='full')
    ns = ap.parse_args()
    root = Path(ns.mtpro2_dir)
    tags = tuple(_active_tags(ns.edition))

    # Fail early on a mixed/incomplete source tree.  Lite is an explicit source
    # profile; missing Full-only files are irrelevant to a Lite build.
    missing = []
    for tag in tags:
        base = source_policy.SOURCE_FONTS[tag]
        for suffix in ('.pfb', '.tfm'):
            p = root / (base + suffix)
            if not p.is_file():
                missing.append(p.name)
    if missing:
        raise SystemExit('incomplete MTPro2 %s source set: %s' %
                         (ns.edition, ', '.join(sorted(missing))))

    # Parsing itself is an audit: each required declaration must be unique and
    # syntactically usable.  Numeric values are intentionally not echoed here.
    try:
        policy = source_policy.extract_policy(root, tags)
    except Exception as exc:
        raise SystemExit(f'original-source policy parse failed: {exc}') from exc

    if not policy.skewchar_by_tag:
        raise SystemExit('original-source contract missing active skewchar policy')

    required_accents = {
        'grave', 'acute', 'check', 'breve', 'bar', 'hat', 'dot', 'tilde',
        'ddot', 'mathring', 'vec', 'wbar', 'wwbar', 'what', 'wtilde',
        'wcheck', 'dotup', 'ddotup', 'dddot', 'ddddot', 'dddotup', 'ddddotup',
    }
    missing_accents = sorted(required_accents - set(policy.accents))
    if missing_accents:
        raise SystemExit('original-source contract missing MathAccent declarations: ' +
                         ', '.join(missing_accents))
    for name in required_accents:
        rec = policy.accents[name]
        if rec.math_class != 'mathord' or rec.symbol_family != 'symbols':
            raise SystemExit(
                f'original-source accent semantics changed for \\{name}: '
                f'class={rec.math_class!r} family={rec.symbol_family!r}')

    # Full-only option alphabets must still be wired to the source basenames
    # declared by the public structural registry.  This checks *identity* and
    # optical-size ordering, not any proprietary metric value.
    if ns.edition == 'full':
        fd_checks = source_policy.OPTICAL_FD_GROUPS
        for filename, checks in fd_checks.items():
            text = _read(root / filename)
            for label, group_tags in checks:
                # Preserve the package's scriptscript -> script -> text order.
                # Basenames come from the same structural source registry used
                # by the builder; no filename tuple is duplicated here.
                basenames = tuple(source_policy.SOURCE_FONTS[tag] for tag in group_tags)
                pattern = r'.*?'.join(re.escape(x) for x in basenames)
                _need(text, pattern, f'{filename}: {label}')

    print('ORIGINAL SOURCE CONTRACT PASS: local package/source declarations are structurally consistent')


if __name__ == '__main__':
    main()
