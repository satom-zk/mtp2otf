"""Required source references and construction dependencies, then
preflight. Mapping owns semantic slots. TFM supplies chain/assembly
relationships only; Encoding and CharStrings establish presence, never
substitute another slot.
"""

from dataclasses import dataclass, field

import mapping as U


@dataclass
class GenerationPlan:
    native: dict
    originals: dict
    routes: list
    coverage: str
    growth: dict
    alphabet: dict
    required_uses: list
    numeric: dict
    alternate_rows: list = field(default_factory=list, repr=False)

    def to_data(self):
        return dict(
            native={t: sorted(s) for t, s in self.native.items()},
            originals={t: sorted(s) for t, s in self.originals.items()},
            routes=self.routes,
            donor_coverage=self.coverage,
            growth=self.growth,
            alphabet=self.alphabet,
            required_uses=self.required_uses,
            numeric_references=self.numeric,
            input_categories={
                "native": (
                    "outline, assembly, hint estimator and Windows "
                    "measurement inputs"
                ),
                "originals": "raw Type1/raw TFM product additions",
                "numeric_references": "family skewchar and fontdimens",
            },
        )


def create(catalog, coverage):
    native, post, routes = {}, {}, []
    ledger = []

    def add(tag, slots, target=native):
        if tag in catalog.faces:
            target.setdefault(tag, set()).update(slots)

    def optical(tag, table):
        for suffix in ["", "_s", "_ss"]:
            add(tag + suffix, table)

    for tag, table in [("mit", U.MIT), ("syt", U.SYT), ("ams", U.AMSA)]:
        optical(tag, table)
    for tag, kind in [
        ("bb", "bb"),
        ("script", "script"),
        ("frak", "frak"),
        ("curly", "curly"),
        ("bscript", "bscript"),
        ("bfrak", "bfrak"),
        ("bbd", "bb"),
        ("bbi", "bb"),
        ("hrb", "bb"),
        ("hrbd", "bb"),
        ("hbi", "bb"),
    ]:
        optical(tag, U.alpha_map(kind))
    optical("bmit", U.bold_source_slots())
    optical(
        "bsyt", [slot for slot, (cp, name) in U.SYT.items() if cp == 0x2207]
    )
    for slot, (cp, name, display) in U.EXA_OPS.items():
        add("exa", [slot, display])
        if name in U.XL_TABLE:
            for tag, s in zip(["xl", "xl", "xl", "xxxl"], U.XL_TABLE[name]):
                add(tag, s if isinstance(s, tuple) else [s])
    starts = []
    for cp, (base, start) in list(U.V_DELIMS.items()) + list(
        U.V_DELIMS_ALT.items()
    ):
        add(base[0], [base[1]])
        add("exa", [start])
        starts.append(("exa", start))
        if cp in U.V_DELIMS:
            for tag in ["exe", "exf", "exg"]:
                chars = catalog.faces[tag].tfm.chars
                targets = {
                    v["next"]
                    for v in chars.values()
                    if v.get("next") is not None
                }
                if start in chars and start not in targets:
                    starts.append((tag, start))
                    add(tag, [start])
    for cp, chain in U.H_CHAINS.items():
        for tag, slot in chain:
            add(tag, [slot])
        if cp in [0x302, 0x303, 0x30C]:
            exa = [s for t, s in chain if t == "exa"]
            if exa:
                for tag in ["exe", "exf", "exg"]:
                    chars = catalog.faces[tag].tfm.chars
                    targets = {
                        v["next"]
                        for v in chars.values()
                        if v.get("next") is not None
                    }
                    if exa[0] in chars and exa[0] not in targets:
                        starts.append((tag, exa[0]))
                        add(tag, [exa[0]])
    add("exa", U.SOURCE_BRACE_PIECES + U.SOURCE_MORPHED_SLOTS + (195,))
    add("exf", U.SOURCE_OVERPAREN_CONTINUATION)
    for tag, start in U.SOURCE_WIDEARC_CHAINS:
        add(tag, [start])
        starts.append((tag, start))
    for cp, series in U.SOURCE_BRACE_SERIES:
        for tag, first, last in series:
            add(tag, range(first, last + 1))
    for choice in U.vertical_choices().values():
        for tag, slot in choice["refs"]:
            add(tag, [slot])
    add("exa", U.VERTICAL_METRIC_REFERENCES.values())
    # Native chains include their original VARCHAR components; keep
    # cycle/error
    # checks.
    for tag, start in starts:
        chars = catalog.faces[tag].tfm.chars
        slot = start
        seen = set()
        while slot is not None and slot in chars and slot not in seen:
            seen.add(slot)
            add(tag, [slot])
            v = chars[slot]
            if v.get("varchar"):
                add(tag, v["varchar"].values())
            slot = v.get("next")
        if slot is not None and slot not in chars:
            # Keep the missing target in the required set for joint
            # preflight.
            add(tag, [slot])
        elif slot is not None:
            raise ValueError(
                f"plan {catalog.faces[tag].stem}.tfm role={tag} "
                f"slot={slot}: broken NEXTLARGER chain"
            )
    # Independent original-source additions intentionally use binary
    # metrics.
    for row in U.bold_identities():
        add(row["source_role"], [row["source_slot"]], post)
    if catalog.edition == "full":
        for role in ["ams", "ams_s", "ams_ss"]:
            add(role, [88, 122, 85, 114], post)
        ledger = U.load_alternates(U.ALTERNATE_PATH)["rows"]
        for row in ledger:
            routes.append(row["semantic_id"])
            for style in row["source_styles"]:
                alt = style["alternate"]
                add(alt["tag"], [alt["slot"]], post)
                if alt["font"] != U.SOURCE_FONTS[alt["tag"]]:
                    raise ValueError("plan alternate source family mismatch")
                if (
                    alt["accent_calibration"]["skewchar"]
                    != catalog.declarations.skewchar_by_tag[alt["tag"]]
                ):
                    raise ValueError("plan alternate skew policy mismatch")
    alphabet = U.alphabet_spec(catalog.edition)
    required = U.final_source_requests(catalog.edition, alphabet, ledger)
    for row in required:
        if row["role"] not in catalog.faces:
            raise ValueError(
                "planned product source role missing: " + row["role"]
            )
        add(row["role"], [row["slot"]], post)
    return GenerationPlan(
        native,
        post,
        routes,
        coverage,
        normal_growth(catalog),
        alphabet,
        required,
        dict(
            **U.SOURCE_NUMERIC_REQUIREMENTS,
            skew_operands={
                role: value
                for role, value in catalog.declarations.skewchar_by_tag.items()
                if role in catalog.faces
            },
        ),
        ledger,
    )


def normal_growth(catalog):
    """Resolve final allowed source identities before an outline is
    copied.
    """
    vertical = {}
    for cp in sorted(U.NORMAL_VERTICAL):
        base, start = U.V_DELIMS[cp]
        allowed = {base}
        chars = catalog.faces["exa"].raw_metrics().chars
        seen = set()
        while start is not None:
            if start in seen or start not in chars:
                raise ValueError(
                    f"normal growth exa:{start}: broken NEXTLARGER"
                )
            seen.add(start)
            record = chars[start]
            if not record.get("varchar"):
                allowed.add(("exa", start))
            start = record.get("nextlarger")
        vertical[str(cp)] = sorted(allowed)
    # Explicit morphed topology supersedes the broken raw NEXTLARGER
    # links.
    for cp, side in ((123, 0), (125, 1)):
        vertical[str(cp)] = [U.V_DELIMS[cp][0]] + [
            ("exa", slot + side) for slot in (182, 184, 186, 188)
        ]
    operators = {
        name: [("exa", text), ("exa", display)]
        for text, (cp, name, display) in U.EXA_OPS.items()
    }
    horizontal = {
        str(cp): [(role, s) for role, slots in series for s in slots]
        for cp, series in U.NORMAL_HORIZONTAL.items()
    }
    return dict(
        vertical=vertical,
        horizontal=horizontal,
        operators=operators,
        choices=U.vertical_choices(),
        metric_references=U.VERTICAL_METRIC_REFERENCES,
    )
