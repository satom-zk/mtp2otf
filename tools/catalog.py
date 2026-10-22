"""Resolve role/size/slot/Encoding/TFM provenance before any glyph
generation.
"""

import hashlib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import declarations
import donors
import mapping
import metrics
import outlines


def sha(path, hashes=None):
    path = Path(path).resolve()
    if hashes is None:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if path not in hashes:
        hashes[path] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes[path]


@dataclass
class SourceFace:
    role: str
    stem: str
    pfb_path: Path
    tfm_path: Path
    font: object
    tfm: object
    slots: dict
    raw: object = None
    kern_fix20: object = None

    def raw_metrics(self):
        if self.raw is None:
            try:
                self.raw = metrics.read_raw(self.tfm_path)
            except Exception as exc:
                raise ValueError(
                    f"raw TFM {self.tfm_path} role={self.role}: {exc}"
                ) from exc
        return self.raw

    def kerns(self):
        if self.kern_fix20 is None:
            self.kern_fix20 = metrics.read_kerns_fix20(self.tfm_path)
        return self.kern_fix20


@dataclass
class Catalog:
    source: Path
    edition: str
    declarations: object
    faces: dict
    donors: dict
    inputs: dict
    planned: set | None = field(default=None, repr=False)
    used: dict = field(default_factory=dict, repr=False)
    value_cache: dict = field(default_factory=dict, repr=False)

    def bind_plan(self, generation):
        self.planned = {
            (role, slot)
            for table in (generation.native, generation.originals)
            for role, slots in table.items()
            for slot in slots
        }
        for role, face in self.faces.items():
            if not isinstance(face.font, PlannedType1):
                face.font = PlannedType1(self, role, face.font)

    def require(self, role, slot, use):
        if self.planned is None or (role, slot) not in self.planned:
            raise ValueError(
                f"unplanned source acquisition role={role} "
                f"slot={slot} use={use}"
            )
        self.used.setdefault((role, slot), set()).add(use)

    def source_record(self, role, slot):
        self.require(role, slot, "raw values")
        face = self.faces[role]
        name = face.font["Encoding"][slot]
        raw = face.raw_metrics().chars[slot]
        return dict(
            role=role,
            slot=slot,
            name=name,
            font=face.font,
            metrics=raw,
            kerns=face.kerns(),
            skew=self.declarations.skewchar_by_tag.get(role),
            pfb=face.pfb_path.name,
            tfm=face.tfm_path.name,
        )

    def source_usage(self):
        return [
            dict(role=r, slot=s, uses=sorted(uses))
            for (r, s), uses in sorted(self.used.items())
        ]

    def originals(self, roles):
        """One Type1/raw-TFM pair per role, shared by post-native
        additions.
        """
        return {
            self.faces[r].stem: (
                self.faces[r].font,
                self.faces[r].raw_metrics(),
            )
            for r in roles
        }

    def snapshot(self, coverage, generation):
        payload = self.declarations.to_jsonable()
        payload["source_font_by_tag"] = {
            r: f.stem for r, f in self.faces.items()
        }
        payload["policy_source_files"] = list(
            declarations.required_policy_files(self.faces)
        )
        tag, slot = mapping.H_CHAINS[0x23DC][-1]
        face = self.faces[tag]
        payload["geometry"] = {
            "overparen_template": outlines.slot_path(
                face.font, face.pfb_path, slot
            )
        }
        payload["catalog"] = {
            r: dict(
                stem=f.stem,
                metrics=metrics.to_data(f.tfm),
                encoding_names={str(s): n for s, n in f.slots.items()},
                metric_interpretation=(
                    "raw-WIK overlay"
                    if r in mapping.ADDED_ALPHABET_TAGS
                    else "historical tftopl PL"
                ),
            )
            for r, f in self.faces.items()
        }
        payload["plan"] = generation.to_data()
        payload["inputs"] = self.inputs
        payload["build_identity"] = dict(
            run_id=uuid.uuid4().hex,
            edition=self.edition,
            donor_coverage=coverage,
            upm=1000,
        )
        return payload


def read_inputs(
    source,
    pl_dir,
    edition,
    regular,
    bold,
    *,
    run=None,
    hashes=None,
    stage=None,
):
    """Read dictionaries and metrics, never copy source glyphs to an
    output
    font.
    """
    source, pl_dir = Path(source), Path(pl_dir)
    tags = declarations.active_tags(edition)
    declarations.validate_source_files(source, tags)
    rules = declarations.extract_policy(source, tags)
    pl_dir.mkdir(parents=True, exist_ok=True)
    faces = {}
    for role in tags:
        stem = mapping.SOURCE_FONTS[role]
        pfb, tfm = source / (stem + ".pfb"), source / (stem + ".tfm")
        if stage is not None:
            stage(f"read source role={role} {pfb.name} / {tfm.name}")
        reading = pfb
        try:
            font = outlines.read_type1(pfb)
            reading = tfm
            values = metrics.read_pl(tfm, pl_dir / (stem + ".pl"), run=run)
            if role in mapping.ADDED_ALPHABET_TAGS:
                metrics.apply_raw_alphabet_metrics(
                    values, metrics.raw_alphabet_metrics(tfm)
                )
            faces[role] = SourceFace(
                role, stem, pfb, tfm, font, values, outlines.slot_names(font)
            )
        except Exception as exc:
            raise ValueError(f"catalog {reading} role={role}: {exc}") from exc
    if stage is not None:
        stage("read donor supply")
    supply = {
        role: donors.read_supply(path)
        for role, path in [("regular", Path(regular)), ("bold", Path(bold))]
    }
    inputs = dict(
        mtpro2={
            n: sha(source / n, hashes)
            for n in declarations.required_source_files(tags)
        },
        donors={
            r: dict(name=f["path"].name, sha256=sha(f["path"], hashes))
            for r, f in supply.items()
        },
    )
    return Catalog(source, edition, rules, faces, supply, inputs)


class PlannedType1:
    """Read-only Type1 adapter; outline retrieval cannot extend the
    plan.
    """

    def __init__(self, catalog, role, font):
        self.catalog, self.role, self.font = catalog, role, font

    def __getitem__(self, key):
        if key == "CharStrings":
            return PlannedGlyphSet(self.catalog, self.role, self.font[key])
        return self.font[key]

    def getGlyphSet(self):
        return PlannedGlyphSet(
            self.catalog, self.role, self.font.getGlyphSet()
        )


class PlannedGlyphSet(Mapping):
    def __init__(self, catalog, role, glyphs):
        self.catalog, self.role, self.glyphs = catalog, role, glyphs

    def __iter__(self):
        return iter(self.glyphs)

    def __len__(self):
        return len(self.glyphs)

    def __contains__(self, name):
        return name in self.glyphs

    def __getitem__(self, name):
        slots = [
            s
            for s, n in self.catalog.faces[self.role].slots.items()
            if n == name
        ]
        allowed = [
            s for s in slots if (self.role, s) in (self.catalog.planned or ())
        ]
        if not allowed:
            raise ValueError(
                f"unplanned source outline role={self.role} "
                f"slots={slots} name={name}"
            )
        self.catalog.require(self.role, min(allowed), "outline")
        return self.glyphs[name]
