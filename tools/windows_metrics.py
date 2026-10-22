"""FontForge bounds boundary and its small, run-owned process result.

Only standard-library dependencies: safe in FontForge's embedded Python.
This is a numeric result, not a serialized legacy font or a font cache.
"""

import hashlib
import json
import math
from pathlib import Path

from config import identity

SCHEMA = "mtp2otf7-compatibility-metrics/1"
BOUNDARY = "fontforge-legacy-windows-assignment"


def assign_windows(font):
    """Compute Windows bounds over the native glyph set."""
    ymin = ymax = 0
    for glyph in font.glyphs():
        box = glyph.boundingBox()
        if box[1] == box[3] == 0 and box[0] == box[2] == 0:
            continue
        ymin = min(ymin, box[1])
        ymax = max(ymax, box[3])
    font.os2_winascent = max(806, int(math.ceil(ymax)))
    font.os2_winascent_add = 0
    font.os2_windescent = max(194, int(math.ceil(-ymin)))
    font.os2_windescent_add = 0
    return [ymin, ymax]


def capture(font, snapshot, bounds):
    result = {
        "schema": SCHEMA,
        "boundary": BOUNDARY,
        "condition": "legacy",
        "identity": snapshot["build_identity"],
        "input_hashes": snapshot["inputs"],
        "Windows": [font.os2_winascent, font.os2_windescent],
        "typo": [
            font.os2_typoascent,
            font.os2_typodescent,
            font.os2_typolinegap,
        ],
        "hhea": [font.hhea_ascent, font.hhea_descent, font.hhea_linegap],
        "upm": font.em,
        "bounds_y": bounds,
    }
    validate(result, snapshot)
    return result


def integer_values(obj, key, count, lower, upper):
    values = obj.get(key)
    if (
        not isinstance(values, list)
        or len(values) != count
        or any(
            type(value) is not int or not lower <= value <= upper
            for value in values
        )
    ):
        raise ValueError("compatibility metrics integer range: " + key)
    return values


def validate_identity(obj):
    identity = obj.get("identity")
    if (
        not isinstance(identity, dict)
        or identity.get("edition") not in ("full", "lite")
        or identity.get("donor_coverage") not in ("minimal", "extended")
        or type(identity.get("upm")) is not int
        or identity["upm"] != 1000
        or not isinstance(identity.get("run_id"), str)
        or len(identity["run_id"]) != 32
        or any(c not in "0123456789abcdef" for c in identity["run_id"])
    ):
        raise ValueError("compatibility metrics identity invalid")
    inputs = obj.get("input_hashes")
    if (
        not isinstance(inputs, dict)
        or not inputs.get("mtpro2")
        or not inputs.get("donors")
    ):
        raise ValueError("compatibility metrics input identity missing")


def validate(result, snapshot=None):
    if not isinstance(result, dict):
        raise ValueError("compatibility metrics result must be an object")
    if (
        result.get("schema") != SCHEMA
        or result.get("boundary") != BOUNDARY
        or result.get("condition") != "legacy"
    ):
        raise ValueError("invalid compatibility metrics boundary")
    validate_identity(result)
    windows = integer_values(result, "Windows", 2, 0, 65535)
    for key in ("typo", "hhea"):
        if integer_values(result, key, 3, -32768, 32767) != [806, -194, 200]:
            raise ValueError(
                "compatibility metrics vertical metrics mismatch: " + key
            )
    if (
        type(result.get("upm")) is not int
        or result["upm"] != result["identity"]["upm"]
    ):
        raise ValueError("compatibility metrics UPM mismatch")
    bounds = result.get("bounds_y")
    if (
        not isinstance(bounds, list)
        or len(bounds) != 2
        or any(
            type(value) not in (int, float) or not math.isfinite(value)
            for value in bounds
        )
        or not bounds[0] <= 0 <= bounds[1]
    ):
        raise ValueError("compatibility metrics bounds invalid")
    if windows != [
        max(806, math.ceil(bounds[1])),
        max(194, math.ceil(-bounds[0])),
    ]:
        raise ValueError("compatibility metrics bounds/Windows mismatch")
    if snapshot is not None:
        if result["identity"] != snapshot["build_identity"]:
            raise ValueError(
                "compatibility metrics run/edition/coverage/UPM mismatch"
            )
        if result["input_hashes"] != snapshot["inputs"]:
            raise ValueError("compatibility metrics source input mismatch")
    return result


POLICY = "source-ttf-fontforge-compatibility-windows/1"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if obj.get("policy") != POLICY or obj.get("profile") != "source":
        raise ValueError("invalid Windows policy")
    validate_identity(obj)
    measurement = obj.get("measurement")
    if not isinstance(measurement, dict):
        raise ValueError("Windows policy lacks current measurement")
    validate(
        measurement,
        {"build_identity": obj["identity"], "inputs": obj["input_hashes"]},
    )
    for key in ("Windows", "typo", "hhea", "upm"):
        if obj.get(key) != measurement[key]:
            raise ValueError("Windows policy/measurement mismatch: " + key)
    integer_values(obj, "source_head_bbox", 4, -32768, 32767)
    if (
        not isinstance(obj.get("source_otf_sha256"), str)
        or len(obj["source_otf_sha256"]) != 64
    ):
        raise ValueError("Windows policy lacks source artifact identity")
    return obj


def provenance_errors(obj, edition, manifest, source_path=None):
    out = []
    if edition is None:
        out.append("Windows policy caller edition absent")
    elif obj["identity"]["edition"] != edition:
        out.append("Windows policy edition mismatch")
    if manifest is None:
        out.append(
            "Windows policy input manifest absent: provenance unverified"
        )
    else:
        snapshot = json.loads(Path(manifest).read_text(encoding="utf-8"))
        if snapshot.get("large_variants") != "source":
            out.append("Windows policy source condition mismatch")
        if obj["identity"] != snapshot.get("build_identity"):
            out.append("Windows policy run/edition/coverage/UPM mismatch")
        if obj["input_hashes"] != snapshot.get("inputs"):
            out.append("Windows policy source input mismatch")
    if source_path is None:
        out.append(
            "Windows policy source OTF path absent: provenance unverified"
        )
    elif sha(source_path) != obj["source_otf_sha256"]:
        out.append("Windows policy source OTF hash mismatch")
    return out


def errors(
    font,
    obj,
    profile,
    *,
    font_path=None,
    edition=None,
    manifest=None,
    source_path=None,
):
    if profile != "source" or "glyf" not in font:
        return ["Windows compatibility policy is restricted to source TTF"]
    out = provenance_errors(obj, edition, manifest, source_path)
    os2, hhea = font["OS/2"], font["hhea"]
    if font_path is None:
        out.append(
            "Windows policy target TTF path absent: artifact unverified"
        )
    elif (
        not obj.get("target_ttf_sha256")
        or sha(font_path) != obj["target_ttf_sha256"]
    ):
        out.append("Windows policy target TTF hash mismatch")
    actual = {
        "Windows": [os2.usWinAscent, os2.usWinDescent],
        "typo": [os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap],
        "hhea": [hhea.ascent, hhea.descent, hhea.lineGap],
        "upm": font["head"].unitsPerEm,
    }
    for key, value in actual.items():
        if value != obj[key]:
            out.append("Windows policy " + key + " mismatch")
    if [
        getattr(font["head"], n) for n in ("xMin", "yMin", "xMax", "yMax")
    ] != obj.get("source_ttf_head_bbox"):
        out.append("Windows policy source bbox changed")
    head = font["head"]
    fits = head.yMax <= os2.usWinAscent and -head.yMin <= os2.usWinDescent
    if fits != obj.get("source_head_fits_windows", False):
        out.append("Windows source TTF containment differs from source record")
    return out


def derive(source_otf, measurement, snapshot, source_sha):
    """Use explicitly bound numeric input, never a legacy final
    file/path.
    """
    from fontTools.ttLib import TTFont

    validate(measurement, snapshot)
    edition = snapshot["build_identity"]["edition"]
    with TTFont(source_otf) as font:
        if font["name"].getDebugName(6) != identity(edition)[1]:
            raise ValueError("Windows actual font edition mismatch")
        os2, hhea = font["OS/2"], font["hhea"]
        if font["head"].unitsPerEm != measurement["upm"]:
            raise ValueError("Windows source/measurement UPM mismatch")
        if [
            os2.sTypoAscender,
            os2.sTypoDescender,
            os2.sTypoLineGap,
        ] != measurement["typo"] or [
            hhea.ascent,
            hhea.descent,
            hhea.lineGap,
        ] != measurement["hhea"]:
            raise ValueError(
                "Windows source/measurement vertical metrics mismatch"
            )
        return {
            "policy": POLICY,
            "profile": "source",
            "identity": measurement["identity"],
            "input_hashes": measurement["input_hashes"],
            "measurement": measurement,
            "source_otf_sha256": source_sha,
            "source_head_bbox": [
                getattr(font["head"], n)
                for n in ("xMin", "yMin", "xMax", "yMax")
            ],
            # C10 numbers stay unchanged. Minimal closure may
            # legitimately
            # remove the old vertical overshoots; record that
            # observation
            # instead of requiring every later subset to remain clipped.
            "source_head_fits_windows": (
                font["head"].yMax <= measurement["Windows"][0]
                and -font["head"].yMin <= measurement["Windows"][1]
            ),
            **{
                key: measurement[key]
                for key in ("Windows", "typo", "hhea", "upm")
            },
        }
