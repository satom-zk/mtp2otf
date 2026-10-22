"""Own one system-Python OpenType editing sequence and its final
serialization.
"""

import hashlib
import json
import os
import tempfile
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import alphabets
import diagnostics
import font_geometry
import math_metrics
import math_tables
import source_glyphs
import substitution
from diagnostics import verify_contract, write_contract
from fontTools import subset
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont
from mapping import load_alternates


@contextmanager
def stage(label):
    """Preserve the failing edit's identity when called directly in this
    process.
    """
    try:
        yield
    except (Exception, SystemExit) as exc:
        raise ValueError(label + ": " + str(exc)) from exc


def read_native(native_otf, work, snapshot):
    """Reject stale/missing/changed native output; parse each payload
    once.
    """
    native_otf, work = Path(native_otf), Path(work)
    result = json.loads(
        (work / "native-result.json").read_text(encoding="utf-8")
    )
    if (
        not isinstance(result, dict)
        or result.get("schema") != "mtp2otf7-native-result/2"
    ):
        raise ValueError("invalid native result schema")
    if result.get("identity") != snapshot["build_identity"]:
        raise ValueError("native result run/edition/coverage/UPM mismatch")
    if hashlib.sha256(native_otf.read_bytes()).hexdigest() != result.get(
        "native_otf_sha256"
    ):
        raise ValueError("native OTF differs from current result")
    filenames = ("math-constants.json", "large-variant-build.json")
    if not isinstance(result.get("payloads"), dict) or set(
        result["payloads"]
    ) != set(filenames):
        raise ValueError("native result payload inventory mismatch")
    payloads = {
        name: json.loads(
            verify_contract(work / name, result["payloads"][name])
        )
        for name in filenames
    }
    math = payloads["math-constants.json"]
    if math.get("upm") != snapshot["build_identity"]["upm"]:
        raise ValueError("native MATH UPM mismatch")
    constants = font_geometry.local_math_values(math)
    inventory = payloads["large-variant-build.json"]
    if (
        inventory.get("edition") != snapshot["build_identity"]["edition"]
        or inventory.get("policy") != "source"
        or inventory.get("input_hashes") != snapshot["inputs"]
    ):
        raise ValueError("native selector input/edition/policy mismatch")
    return constants, inventory


@dataclass(frozen=True)
class OriginalSources:
    """Parsed PFB/raw-TFM groups only; owned by one postprocessing call.
    """

    mbf: dict
    ams: dict | None = None
    alternates: dict | None = None
    ams_alternates: dict | None = None


def load_originals(catalog, snapshot, edition, ledger):
    """Reuse already validated catalog faces, including raw TFM where
    required.
    """

    def group(roles):
        return catalog.originals(roles)

    mbf = group(("bold", "bold_s", "bold_ss"))
    if edition == "lite":
        return OriginalSources(mbf)
    ams = group(("ams", "ams_s", "ams_ss"))
    tags = tuple(
        dict.fromkeys(
            style["alternate"]["tag"]
            for row in ledger
            for style in row["source_styles"]
        )
    )
    return OriginalSources(mbf, ams, group(tags), ams)


def edit_full(font, originals, snapshot, ledger):
    """Full-only mutation sequence; all original faces were loaded by
    the
    owner.
    """
    with stage("AMS checkmark/maltese"):
        source_glyphs.add_ams_glyphs(font, originals.ams)
    with stage("optical alternates/Fraktur"):
        source_glyphs.add_optical_alternates(
            font, originals.alternates, snapshot, ledger
        )
    with stage("AMS yen/registered"):
        source_glyphs.add_ams_alternates(font, originals.ams_alternates)


def edit_initial(font, *, edition, constants):
    """Edit the native font up to the required CFF/bbox normalization
    boundary.
    """
    with stage("font_geometry"):
        font_geometry.edit(font, edition=edition, local_values=constants)


def edit_remaining(font, *, edition, inventory, originals, snapshot, ledger):
    """Install selectors and original-source additions after
    normalization.
    """
    with stage("brace choice roots"):
        math_tables.install_brace_choices(font, inventory)
    if edition == "full":
        edit_full(font, originals, snapshot, ledger)
    with stage("original mathematical bold"):
        source_glyphs.add_original_bold(font, originals.mbf, snapshot, edition)


def process(native_otf, final_otf, *, work, catalog, snapshot, alternate_path):
    """Load, normalize CFF in memory, edit, and save atomically."""
    with stage("native handoff"):
        constants, inventory = read_native(native_otf, work, snapshot)
        edition = snapshot["build_identity"]["edition"]
        ledger = (
            load_alternates(alternate_path)["rows"]
            if edition == "full"
            else None
        )
    originals = load_originals(catalog, snapshot, edition, ledger)
    final_otf = Path(final_otf)
    final_otf.parent.mkdir(parents=True, exist_ok=True)
    with BytesIO() as normalized:
        with TTFont(native_otf) as font:
            edit_initial(font, edition=edition, constants=constants)
            # Fixed selectors require serialized head/CFF bounds.
            # Keep this in-memory compile/decompile before installing
            # them.
            # Earlier disk roundtrips are unnecessary.
            with stage("CFF/bbox normalization boundary"):
                font.save(normalized, reorderTables=False)
        normalized.seek(0)
        with TTFont(normalized, recalcTimestamp=False) as font:
            edit_remaining(
                font,
                edition=edition,
                inventory=inventory,
                originals=originals,
                snapshot=snapshot,
                ledger=ledger,
            )
            # Common source corrections and minimal entrance/growth
            # policy
            # remain separate records in the same in-memory font owner.
            reports = {}
            with stage("source alphabet identities and final routes"):
                alphabet = alphabets.apply(
                    font, catalog, snapshot, ledger, inventory
                )
            with stage("raw TFM attachment values"):
                reports["attachments"] = math_metrics.apply(
                    font, catalog, snapshot, inventory, alphabet
                )
            with stage("measured growth records"):
                reports["growth"] = math_tables.finalize_measured_growth(font)
            with stage("left vector assembly geometry"):
                reports["left-vector"] = font_geometry.build_left_vector(font)
            with stage("ordinary and Plain brace recipes"):
                reports["braces"] = font_geometry.build_overbrace(
                    font, inventory
                )
            with stage("group delimiter recipes"):
                reports["groups"] = font_geometry.build_groups(font, inventory)
            with stage("source relation identities and routes"):
                reports["relations"] = source_glyphs.build_relations(
                    font, catalog, snapshot, alphabet
                )
            with stage("standard Unicode entrances and combining attachment"):
                reports["unicode"] = source_glyphs.bind_unicode(font, catalog)
            with stage("logical-and choice routes"):
                reports["logical-and"] = substitution.install_logical_and(font)
            with stage("negative relation choices"):
                reports["negative-choices"] = (
                    substitution.install_negative_choices(
                        font, catalog.edition
                    )
                )
            with stage("source overbar and vector recipes"):
                reports["accents"] = font_geometry.build_standard_accents(
                    font, catalog
                )
            with stage("vertical choice roots and optical growth"):
                reports["vertical-choices"] = (
                    math_tables.install_vertical_choices(font)
                )
            with stage("final public substitutions"):
                reports["substitutions"] = substitution.finish(font, edition)
            with stage("reference closure and physical serialization set"):
                reports["closure"] = prune(font)
            with stage("final average width and Windows ANSI policy"):
                font_geometry.update_average_width(font)
                font_geometry.preserve_windows_ansi_compatibility(font)
            reports["AB"] = diagnostics.alphabet_report(alphabet)
            reports["source_usage"] = catalog.source_usage()
            write_contract(Path(work) / "construction-results.json", reports)
            _save_final(font, final_otf)


def _save_final(font, final_otf):
    """I/O helper of process; never called by an editing function."""
    with stage("final OTF serialization"):
        fd, name = tempfile.mkstemp(
            prefix="final-otf-", suffix=".otf", dir=final_otf.parent
        )
        os.close(fd)
        temporary = Path(name)
        try:
            font.save(temporary)
            with temporary.open("rb") as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, final_otf)
        finally:
            temporary.unlink(missing_ok=True)


def normalize_cff(font):
    """Bind copied/appended charstrings to one Private/Subrs owner."""
    # Rebind Private/Subrs after source append steps to one serialized
    # CFF
    # object graph before passing it to fontTools' physical subsetter.
    from fontTools.ttLib import newTable

    data = font.getTableData("CFF ")
    cff = newTable("CFF ")
    cff.decompile(data, font)
    font["CFF "] = cff


def prune(font):
    """Close adopted entrances through actual GSUB/MATH/CFF references.
    """
    normalize_cff(font)
    all_names = set(font.getGlyphOrder())
    live = set(font.getBestCmap().values()) | {".notdef"}
    reason = defaultdict(set)
    for n in live:
        reason[n].add("cmap/current public entrance or .notdef")
    gsub = font["GSUB"].table
    # Retired feature lookups have already been removed, including
    # context
    # references. Current generators use single/alternate/ligature GSUB.
    edges = []
    for lookup in gsub.LookupList.Lookup:
        for st in lookup.SubTable:
            if hasattr(st, "ExtSubTable"):
                st = st.ExtSubTable
            if hasattr(st, "mapping"):
                edges += [
                    (
                        tuple([a]),
                        [b] if isinstance(b, str) else list(b),
                        "GSUB",
                    )
                    for a, b in st.mapping.items()
                ]
            elif hasattr(st, "alternates"):
                edges += [
                    (tuple([a]), list(b), "GSUB")
                    for a, b in st.alternates.items()
                ]
            elif hasattr(st, "ligatures"):
                edges += [
                    (
                        tuple([a] + ligature.Component),
                        [ligature.LigGlyph],
                        "GSUB ligature",
                    )
                    for a, ls in st.ligatures.items()
                    for ligature in ls
                ]
            else:
                raise ValueError(
                    "unsupported closure GSUB subtable " + type(st).__name__
                )
    M = font["MATH"].table.MathVariants
    for d in ["Vert", "Horiz"]:
        for root, c in zip(
            getattr(M, d + "GlyphCoverage").glyphs,
            getattr(M, d + "GlyphConstruction"),
        ):
            out = [v.VariantGlyph for v in c.MathGlyphVariantRecord]
            out += [
                p.glyph
                for p in (
                    c.GlyphAssembly.PartRecords if c.GlyphAssembly else ()
                )
            ]
            edges.append(((root,), out, "MATH variants/assembly"))
    gs = font.getGlyphSet()

    for n in all_names:
        p = RecordingPen()
        gs[n].draw(p)
        edges += [
            ((n,), [a[0]], "CFF component")
            for op, a in p.value
            if op == "addComponent"
        ]
    changed = True
    while changed:
        changed = False
        for ins, outs, kind in edges:
            if all(n in live for n in ins):
                for n in outs:
                    reason[n].add(kind + ":" + ",".join(ins))
                    if n not in live:
                        live.add(n)
                        changed = True
    if not live <= all_names:
        raise ValueError("closure reaches missing glyph")
    options = subset.Options()
    if "FFTM" not in options.drop_tables:
        options.drop_tables.append("FFTM")
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.layout_features = ["*"]
    options.glyph_names = True
    options.notdef_outline = True
    options.recalc_timestamp = False
    # All desired graph references are now explicit. fontTools validates
    # and
    # cleans actual table coverage/counts during the physical subset.
    sub = subset.Subsetter(options=options)
    sub.populate(glyphs=live)
    sub.subset(font)
    actual = set(font.getGlyphOrder())
    if actual != live:
        raise ValueError("subsetter closure differs from explicit live set")
    return dict(
        before=len(all_names),
        after=len(actual),
        removed=sorted(all_names - actual),
        retained=[
            dict(glyph=n, reason=sorted(reason[n])) for n in sorted(actual)
        ],
        unresolved_policy=(
            "Existing PUA except rejected italic-BB "
            "entrances remain public roots; no new global "
            "PUA deletion judgment"
        ),
    )
