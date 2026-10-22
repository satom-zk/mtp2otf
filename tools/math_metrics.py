"""Final source arithmetic and native-to-final attachment assignment.

Preserve geometric accent origins and the separately adopted prime
transform. No advance, italic correction, kern, or MATH constant is
changed here.
"""

from collections import defaultdict
from fractions import Fraction

from mapping import bold_identities
from source_glyphs import (
    AMS_SYMBOLS,
    ams_alternates_identities,
)
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
                        "C03 geometric/fixed accent or C09 adopted "
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
