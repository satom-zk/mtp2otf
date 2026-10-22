"""Concretize planned alphabet identities and delegate backend/table
work.
"""

from copy import deepcopy

import declarations
import font_geometry
import mapping as U
import positioning
import substitution


def apply(font, catalog, snapshot, ledger, inventory):
    """Apply adopted common routes and return exact source provenance.
    """
    f = font
    edition = catalog.edition
    cmap = f.getBestCmap().copy()
    oldcmap = cmap.copy()
    spec = snapshot["plan"]["alphabet"]
    LEDGER = ledger or []
    oldss = deepcopy(substitution.ssty_mapping(f))
    ss = deepcopy(oldss)
    native_sources = {
        (r["tag"], r["slot"]): r["glyph"] for r in inventory["imports"]
    }
    resolver = font_geometry.AlphabetGlyphs(f, catalog)
    glyph, bind = resolver.glyph, resolver.bind
    sourceglyph = resolver.sources

    def optical(role, slot):
        names = [glyph(role + s, slot) for s in U.ALPHABET_SUFFIX]
        ss[names[0]] = names[1:]
        return names

    def oldnames(n):
        return [n, *oldss.get(n, [n, n])]

    for slot, (cp, _) in U.MIT.items():
        if cp in oldcmap:
            bind("mit", slot, oldnames(oldcmap[cp]))
    for slot, (cp, _) in spec["bold"]:
        bind(
            "bold",
            slot,
            [f"original.mbf.u{cp:05X}." + style for style in ["T", "S", "SS"]],
        )
    if edition == "full":
        for role, kind in [
            ("bb", "bb"),
            ("script", "script"),
            ("bscript", "bscript"),
            ("bfrak", "bfrak"),
            ("frak", "frak"),
        ]:
            for slot, (cp, nm) in U.alpha_map(kind).items():
                if cp in oldcmap:
                    bind(role, slot, oldnames(oldcmap[cp]))
                elif role == "frak" and slot in [73, 82]:
                    bind(role, slot, oldnames(chr(slot) + ".frak"))
        for role in ["bbd", "bbi", "hrb", "hrbd", "hbi"]:
            for slot, (cp, _) in U.alpha_map("bb").items():
                if (
                    role in ["bbi", "hbi"]
                    and slot not in U.BLACKBOARD_ITALIC.values()
                ):
                    continue
                bind(
                    role,
                    slot,
                    [
                        native_sources[role + s, slot]
                        for s in U.ALPHABET_SUFFIX
                    ],
                )
        for slot, (cp, _) in spec["script"]:
            bind(
                "curly",
                slot,
                [native_sources["curly" + s, slot] for s in U.ALPHABET_SUFFIX],
            )
        for slot in list(range(65, 91)) + list(range(97, 123)):
            cp = 119912 + slot - 65 if slot < 91 else 119938 + slot - 97
            bind("bmit", slot, oldnames(oldcmap[cp]))
        for slot, n in [(123, "u1D48A.dotless"), (124, "u1D48B.dotless")]:
            bind("bmit", slot, oldnames(n))
        for row in LEDGER:
            for style in row["source_styles"]:
                alt = style["alternate"]
                n = (
                    "diagnostic."
                    + row["semantic_id"].replace(".", "_")
                    + "."
                    + style["style"]
                )
                catalog.require(alt["tag"], alt["slot"], "alternate identity")
                sourceglyph[alt["tag"], alt["slot"]] = n

    bind(
        "mit", 180, [native_sources["mit" + s, 180] for s in U.ALPHABET_SUFFIX]
    )
    maps = {
        k: {}
        for k in [
            "cv01",
            "cv33",
            "cv34",
            "ss01",
            "cv31",
            "ss02",
            "dtls",
            "cv32",
        ]
    }
    newbold = {}
    for slot, (cp, _) in spec["bold"]:
        names = optical("bold", slot)
        oldn = cmap.get(cp)
        newbold[oldn] = names[0]
        cmap[cp] = names[0]
    for cp, n in list(cmap.items()):
        if 120488 <= cp <= 120545 and n in newbold:
            cmap[cp] = newbold[n]
    if spec["digamma"]:
        role, slot, cp = spec["digamma"]
        cmap[cp] = optical(role, slot)[0]
    if edition == "full":
        for role in ["bb", "bbd", "hrb", "hrbd"]:
            for slot, (cp, nm) in spec["blackboard"]:
                names = optical(role, slot)
                if role == "bb":
                    cmap[cp] = names[0]
        for role in ["bbi", "hbi"]:
            for cp, slot in spec["blackboard_special"]:
                names = optical(role, slot)
                if role == "bbi":
                    cmap[cp] = names[0]
        for slot, (cp, nm) in spec["blackboard"]:
            for level, s in enumerate(U.ALPHABET_SUFFIX):
                for a, b in [("bb", "bbd"), ("hrb", "hrbd")]:
                    maps["cv33"][glyph(a + s, slot)] = glyph(b + s, slot)
                for a, b in [("bb", "hrb"), ("bbd", "hrbd")]:
                    maps["cv34"][glyph(a + s, slot)] = glyph(b + s, slot)
        for cp, slot in spec["blackboard_special"]:
            for level, s in enumerate(U.ALPHABET_SUFFIX):
                maps["cv34"][glyph("bbi" + s, slot)] = glyph("hbi" + s, slot)
    for role, dotted_i, dot_i, dotted_j, dot_j in spec["dotless"]:
        for dotted, dot in [(dotted_i, dot_i), (dotted_j, dot_j)]:
            dotted_names = optical(role, dotted)
            dot_names = optical(role, dot)
            for level in range(3):
                maps["dtls"][dotted_names[level]] = dot_names[level]
    if edition == "full":
        for slot in [123, 124]:
            for level, s in enumerate(U.ALPHABET_SUFFIX):
                for a, b in [("bb", "bbd"), ("hrb", "hrbd")]:
                    maps["cv33"][glyph(a + s, slot)] = glyph(b + s, slot)
                for a, b in [("bb", "hrb"), ("bbd", "hrbd"), ("bbi", "hbi")]:
                    maps["cv34"][glyph(a + s, slot)] = glyph(b + s, slot)
    for role, cp, ordinary_slot, swash_slot in spec["swash"]:
        if role in declarations.active_tags(edition):
            a = optical(role, ordinary_slot)
            b = optical(role, swash_slot)
            for level in range(3):
                maps["cv01"][a[level]] = b[level]
    if edition == "full":
        for slot, cp in spec["bold_italic"]:
            names = optical("bmit", slot)
            cmap[cp] = names[0]
    for cp, role, slot in spec["bold_greek"]:
        if edition == "full":
            if (role, slot) not in sourceglyph and cp in oldcmap:
                n = oldcmap[cp]
                if n in oldss:
                    bind(role, slot, [n, *oldss[n]])
            names = optical(role, slot)
            cmap[cp] = names[0]
    if edition == "full":
        alt_by = {}
        for row in LEDGER:
            for i, style in enumerate(row["source_styles"]):
                alt = style["alternate"]
                role = alt["tag"]
                slot = alt["slot"]
                name = glyph(role, slot)
                alt_by[
                    row["group"],
                    row["weight"],
                    int(row["base_unicode"][2:], 16),
                    i,
                ] = name
        for row in LEDGER:
            cp = int(row["base_unicode"][2:], 16)
            base = oldcmap[cp]
            ordinary = [base, *oldss.get(base, [base, base])]
            alts = [
                alt_by[row["group"], row["weight"], cp, i] for i in range(3)
            ]
            ss[alts[0]] = alts[1:]
            tag = (
                "ss02"
                if row["group"] == "Curly"
                else "cv32"
                if row["group"] == "Frak"
                else "cv31"
            )
            for i in range(3):
                maps[tag][ordinary[i]] = alts[i]
        for cp, letter in spec["fraktur_reserved"]:
            names = optical("frak", ord(letter))
            base = oldcmap[cp]
            ordinary = [base, *oldss[base]]
            for i in range(3):
                maps["cv32"][ordinary[i]] = names[i]
        for slot, (cp, _) in spec["script"]:
            normal = [oldcmap[cp], *oldss[oldcmap[cp]]]
            curl = optical("curly", slot)
            for i in range(3):
                scriptalt = alt_by.get(("Script", "regular", cp, i), normal[i])
                curlyalt = alt_by.get(("Curly", "regular", cp, i), curl[i])
                maps["ss01"][normal[i]] = curl[i]
                if scriptalt != normal[i]:
                    maps["ss01"][scriptalt] = curlyalt
                if curlyalt != curl[i]:
                    maps["cv31"][curl[i]] = curlyalt
                maps["ss02"][normal[i]] = curlyalt
                maps["ss02"][scriptalt] = curlyalt
                maps["ss02"][curl[i]] = curlyalt
        for slot in [123, 124]:
            for s in U.ALPHABET_SUFFIX:
                maps["ss01"][glyph("script" + s, slot)] = glyph(
                    "curly" + s, slot
                )
    added_pairs = positioning.install_alphabet_kerns(
        f, catalog, sourceglyph, spec
    )
    substitution.install_alphabet_routes(f, maps, ss)
    excluded = set()
    if edition == "full":
        for role in ("bbi", "hbi"):
            for slot in U.alpha_map("bb"):
                n = native_sources[role, slot]
                if n not in sourceglyph.values():
                    excluded.add(n)
    for cp, name in list(cmap.items()):
        if 0xE000 <= cp <= 0xF8FF and name in excluded:
            del cmap[cp]
    font_geometry.bind_cmap(f, cmap)
    return dict(
        source_glyphs=resolver.provenance(),
        added_source_kerns=added_pairs,
        removed_italic_members=sorted(excluded),
        cmap_changes=[
            dict(Unicode=cp, old=oldcmap.get(cp), new=name)
            for cp, name in cmap.items()
            if oldcmap.get(cp) != name
        ],
    )
