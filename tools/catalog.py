"""Resolve role/size/slot/Encoding/TFM provenance before glyph
generation.
"""

from dataclasses import dataclass
from pathlib import Path
import hashlib
import uuid

import declarations
import mapping
import metrics
import outlines
import donors


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

    def raw_metrics(self):
        if self.raw is None:
            try:
                self.raw = metrics.read_raw(self.tfm_path)
            except Exception as exc:
                raise ValueError(
                    f'raw TFM {self.tfm_path} role={self.role}: {exc}'
                ) from exc
        return self.raw


@dataclass
class Catalog:
    source: Path
    edition: str
    declarations: object
    faces: dict
    donors: dict
    inputs: dict

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
        payload['source_font_by_tag'] = {
            r: f.stem for r, f in self.faces.items()
        }
        payload['policy_source_files'] = list(
            declarations.required_policy_files(self.faces)
        )
        tag, slot = mapping.H_CHAINS[0x23DC][-1]
        face = self.faces[tag]
        payload['geometry'] = {
            'overparen_template': outlines.slot_path(
                face.font, face.pfb_path, slot
            )
        }
        payload['catalog'] = {
            r: dict(
                stem=f.stem,
                metrics=metrics.to_data(f.tfm),
                encoding_names={str(s): n for s, n in f.slots.items()},
                metric_interpretation=(
                    'raw-WIK overlay'
                    if r in mapping.ADDED_ALPHABET_TAGS
                    else 'historical tftopl PL'
                ),
            )
            for r, f in self.faces.items()
        }
        payload['plan'] = generation.to_data()
        payload['inputs'] = self.inputs
        payload['build_identity'] = dict(
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
    """Read dictionaries and metrics without copying source glyphs."""
    source, pl_dir = Path(source), Path(pl_dir)
    tags = declarations.active_tags(edition)
    declarations.validate_source_files(source, tags)
    rules = declarations.extract_policy(source, tags)
    pl_dir.mkdir(parents=True, exist_ok=True)
    faces = {}
    for role in tags:
        stem = mapping.SOURCE_FONTS[role]
        pfb, tfm = source / (stem + '.pfb'), source / (stem + '.tfm')
        if stage is not None:
            stage(f'read source role={role} {pfb.name} / {tfm.name}')
        reading = pfb
        try:
            font = outlines.read_type1(pfb)
            reading = tfm
            values = metrics.read_pl(tfm, pl_dir / (stem + '.pl'), run=run)
            if role in mapping.ADDED_ALPHABET_TAGS:
                metrics.apply_raw_alphabet_metrics(
                    values, metrics.raw_alphabet_metrics(tfm)
                )
            faces[role] = SourceFace(
                role, stem, pfb, tfm, font, values, outlines.slot_names(font)
            )
        except Exception as exc:
            raise ValueError(f'catalog {reading} role={role}: {exc}') from exc
    if stage is not None:
        stage('read donor supply')
    supply = {
        role: donors.read_supply(path)
        for role, path in [('regular', Path(regular)), ('bold', Path(bold))]
    }
    inputs = dict(
        mtpro2={
            n: sha(source / n, hashes)
            for n in declarations.required_source_files(tags)
        },
        donors={
            r: dict(name=f['path'].name, sha256=sha(f['path'], hashes))
            for r, f in supply.items()
        },
    )
    return Catalog(source, edition, rules, faces, supply, inputs)
