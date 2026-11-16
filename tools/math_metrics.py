"""Plan source attachments and final ordinary italic advances."""

from collections import defaultdict
from fractions import Fraction

import mapping as U
from mapping import bold_identities
from source_glyphs import AMS_SYMBOLS, ams_alternates_identities
from substitution import ssty_mapping


def apply(font, catalog, snapshot, inventory, alphabets):
    table = font["MATH"].table.MathGlyphInfo.MathTopAccentAttachment
    current = dict(
        zip(table.TopAccentCoverage.glyphs, table.TopAccentAttachment)
    )
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    sources = defaultdict(set)
    rows = inventory["imports"] + [
        dict(tag=r["role"], slot=r["slot"], glyph=r["glyph"])
        for r in alphabets["source_glyphs"]
    ]
    rows += [
        dict(
            tag=r["source_role"],
            slot=r["source_slot"],
            glyph=r["output_glyph"],
        )
        for r in bold_identities()
    ]
    if catalog.edition == "full":
        rows += [
            dict(tag=r["source_role"], slot=r["slot"], glyph=r["output_glyph"])
            for r in ams_alternates_identities()
        ]
        for _, slot, name in AMS_SYMBOLS:
            for level, suffix in enumerate(("", "_s", "_ss")):
                rows.append(
                    dict(
                        tag="ams" + suffix,
                        slot=slot,
                        glyph=name + (".ssty" + str(level) if level else ""),
                    )
                )
    for r in rows:
        if (
            r["glyph"] in current
            and r["tag"] in catalog.faces
            and (
                r["tag"] in snapshot["skewchar_by_tag"]
                or r["tag"].startswith("ams")
            )
        ):
            sources[r["glyph"]].add((r["tag"], r["slot"]))
    ss = ssty_mapping(font)
    protected = set()
    for cp in (0x2032, 0x2033, 0x2034, 0x2035, 0x2036, 0x2037, 0x2057):
        n = font.getBestCmap().get(cp)
        if n:
            protected.add(n)
            protected.update(ss.get(n, ()))
    changes, checked, preserved = [], [], []
    for name, refs in sorted(sources.items()):
        if classes.get(name) == 3 or name in protected:
            preserved.append(
                dict(
                    glyph=name,
                    value=current[name].Value,
                    reason=(
                        "geometric/fixed accent or "
                        "prime transform"
                    ),
                )
            )
            continue
        values = []
        provenance = []
        for role, slot in sorted(refs):
            data = source_values(catalog, role, slot)
            values.append(data["TopAccent"])
            provenance.append(dict(role=role, slot=slot, **data))
        if len(set(values)) != 1:
            raise ValueError("conflicting source TopAccent: " + name)
        old, new = current[name].Value, values[0]
        item = dict(glyph=name, before=old, after=new, source=provenance)
        checked.append(item)
        if old != new:
            changes.append(item)
            current[name].Value = new
    return dict(
        checked=checked,
        changes=changes,
        protected=preserved,
        formula="round(1000*(W_fix20+I_fix20+2*K_fix20)/(2*2^20))",
        changed_other_metrics=False,
    )


def source_values(catalog, role, slot):
    """Final raw W/I/K arithmetic shared by matching, creation and MATH.
    """
    catalog.require(role, slot, "raw values")
    key = (role, slot)
    if key not in catalog.value_cache:
        record = catalog.source_record(role, slot)
        raw = record["metrics"]
        w = round(raw.get("width", 0) * (1 << 20))
        i = round(raw.get("italic", 0) * (1 << 20))
        skew = record["skew"]
        k = record["kerns"].get((slot, skew), 0) if skew is not None else 0
        exact = Fraction(1000 * (w + i + 2 * k), 2 * (1 << 20))
        catalog.value_cache[key] = dict(
            width=round(raw["width"] * 1000),
            IC=round(raw.get("italic", 0) * 1000),
            TopAccent=round(exact),
            width_fix20=w,
            italic_fix20=i,
            skew_fix20=k,
            numerator=exact.numerator,
            denominator=exact.denominator,
            rounded=round(exact),
            skewchar=skew,
        )
    return catalog.value_cache[key]


def kern_advance(fix):
    return round(1000 * fix / (1 << 20))


def italic_advance_plan(font, catalog, inventory, alphabet, reports):
    """Resolve ordinary uses before moving nonzero IC into advances."""
    order = font.getGlyphOrder()
    names = set(order)
    info = font["MATH"].table.MathGlyphInfo
    if info.MathKernInfo is not None:
        raise ValueError("italic advance requires absent MathKernInfo")
    table = info.MathItalicsCorrectionInfo
    corrections = dict(zip(table.Coverage.glyphs, table.ItalicsCorrection))
    if any(r.DeviceTable is not None for r in corrections.values()):
        raise ValueError("unsupported italic correction DeviceTable")
    cps, internal = U.italic_advance_roots(catalog.edition)
    cmap = font.getBestCmap()
    candidates = {cmap[cp] for cp in cps if cp in cmap} | internal
    if not internal <= names:
        raise ValueError("missing reserved italic advance entrance")
    edges = defaultdict(set)
    gsub = font["GSUB"].table
    for record in gsub.FeatureList.FeatureRecord:
        if record.FeatureTag not in U.ITALIC_ADVANCE_FEATURES:
            continue
        for index in record.Feature.LookupListIndex:
            for sub in gsub.LookupList.Lookup[index].SubTable:
                if hasattr(sub, "ExtSubTable"):
                    sub = sub.ExtSubTable
                if hasattr(sub, "mapping"):
                    pairs = [(a, [b]) for a, b in sub.mapping.items()]
                elif hasattr(sub, "alternates"):
                    pairs = sub.alternates.items()
                else:
                    raise ValueError("unsupported italic advance route")
                for source, targets in pairs:
                    edges[source].update(targets)
    pending = list(candidates)
    while pending:
        additions = edges[pending.pop()] - candidates
        candidates.update(additions)
        pending.extend(additions)
    if not candidates <= names:
        raise ValueError("italic advance route references absent glyph")

    variants = font["MATH"].table.MathVariants
    protected = set(info.ExtendedShapeCoverage.glyphs)
    vertical = {}
    for direction in ("Vert", "Horiz"):
        coverage = getattr(variants, direction + "GlyphCoverage")
        constructions = getattr(variants, direction + "GlyphConstruction")
        roots = coverage.glyphs if coverage else ()
        for root, construction in zip(roots, constructions):
            if direction == "Vert":
                vertical[root] = construction
            protected.add(root)
            protected.update(v.VariantGlyph for v in
                             construction.MathGlyphVariantRecord)
            assembly = construction.GlyphAssembly
            if assembly:
                protected.update(p.glyph for p in assembly.PartRecords)
                if assembly.ItalicsCorrection.DeviceTable is not None:
                    raise ValueError("unsupported assembly IC DeviceTable")
    operators = set()
    for cp, name, _ in U.EXA_OPS.values():
        if name in U.LARGE_OPERATOR_SERIES:
            root = cmap[cp] if cp is not None else name
            operators.update(v.VariantGlyph for v in
                             vertical[root].MathGlyphVariantRecord)
    protected.update(operators)
    protected.update(n for n, cls in
                     font["GDEF"].table.GlyphClassDef.classDefs.items()
                     if cls == 3)
    styles = ssty_mapping(font)
    for cp in (0x2032, 0x2033, 0x2034, 0x2035, 0x2036, 0x2037, 0x2057):
        if cp in cmap:
            protected.add(cmap[cp])
            protected.update(styles.get(cmap[cp], ()))
    collision = candidates & protected
    if collision:
        raise ValueError("italic advance protected uses: " +
                         ", ".join(sorted(collision)))
    nonzero = {n for n, r in corrections.items() if r.Value}
    unknown = nonzero - candidates - operators
    if unknown:
        raise ValueError("unclassified italic correction: " +
                         ", ".join(sorted(unknown)))

    sources = defaultdict(set)
    for row in inventory["imports"]:
        sources[row["glyph"]].add((row["tag"], row["slot"]))
    for row in alphabet["source_glyphs"] + reports["relations"]["sources"]:
        sources[row["glyph"]].add((row["role"], row["slot"]))
    for row in reports["attachments"]["checked"]:
        sources[row["glyph"]].update(
            (s["role"], s["slot"]) for s in row["source"]
        )
    accents = set(info.MathTopAccentAttachment.TopAccentCoverage.glyphs)
    rows = []
    for gid, name in enumerate(order):
        if name not in candidates & nonzero:
            continue
        width, lsb = font["hmtx"][name]
        value = corrections[name].Value
        if value < 0 or not 0 <= width + value <= 65535:
            raise ValueError("unsupported italic advance value: " + name)
        if name not in accents or not sources[name]:
            raise ValueError("missing italic advance origin: " + name)
        provenance = []
        for role, slot in sorted(sources[name]):
            data = source_values(catalog, role, slot)
            if (data["width"], data["IC"]) != (width, value):
                raise ValueError("conflicting italic advance source: " + name)
            provenance.append(dict(role=role, slot=slot))
        rows.append(dict(
            gid=gid, glyph=name, use="ordinary", source=provenance,
            width=width, italic=value, lsb=lsb,
            advance=width + value, bottom_right=-value,
        ))
    return dict(
        formula="advance=W+I; IC=0; BottomRight=-I",
        candidates=len(candidates), changes=rows,
        preserved_nonzero=sorted(nonzero & operators, key=font.getGlyphID),
    )
