"""Read all the inputs of one build."""

from __future__ import annotations

from pathlib import Path

from errors import Error
from sources.donor import read_donor
from sources.tfm import read_tfm
from sources.type1 import read_type1
from sources.types import Sources


class SourceError(Error):
    pass


def read_sources(directory, donor_path, names, package) -> Sources:
    """Read the named PFB/TFM pairs and the donor; the package has been
    read already."""
    directory = Path(directory)
    if not Path(donor_path).is_file():
        raise SourceError("%s: no such file" % donor_path)
    fonts, metrics = {}, {}
    for name in names:
        pfb = directory / (name + ".pfb")
        tfm = directory / (name + ".tfm")
        for path in (pfb, tfm):
            if not path.is_file():
                raise SourceError("%s: no such file" % path)
        fonts[name] = read_type1(pfb)
        metrics[name] = read_tfm(tfm)
    return Sources(fonts, metrics, package, read_donor(donor_path))
