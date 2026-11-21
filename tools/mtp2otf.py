"""Build the fonts into out/, and the log and the plan's values as
tables into build/<edition>/.

Run by build.sh as: python3 tools/mtp2otf.py full|lite DONOR
"""

import collections
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from plan import product

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "mtpro2"
OUTPUT = ROOT / "out"
LOGS = ROOT / "build"
SUFFIXES = (".pfb", ".tfm")


def main(argv):
    """Called by build.sh, which reads the command line and checks the
    environment: argv is [full|lite, absolute path of the donor]."""
    edition, donor = argv
    from errors import Error
    try:
        build(edition == "lite", Path(donor))
    except (Error, OSError) as error:
        print("build.sh: %s" % error, file=sys.stderr)
        return 1
    return 0


def build(lite, donor):
    import preflight
    from design.load import expand_chains, load_design
    from emit.font import write_otf, write_ttf
    from emit.tables import tables
    from plan.build import make_plan
    from plan.glyphs import source_names
    from sources.load import read_sources
    from sources.package import read_package

    design = load_design()
    package_paths = [INPUT / name for name in preflight.package_files(lite)]
    preflight.check_files(package_paths + [donor])
    package = read_package(package_paths[0], package_paths[1:])
    design = preflight.resolve_roles(design, package, lite)
    names = source_names(design, lite)
    preflight.check_files(
        INPUT / (name + suffix) for name in names for suffix in SUFFIXES)
    sources = read_sources(INPUT, donor, names, package)
    design = expand_chains(design, {
        name: sources.metrics[role.text]
        for name, role in design.roles.items() if role.text in names})
    preflight.check_contents(design, sources, lite)
    plan = make_plan(design, sources, lite)
    OUTPUT.mkdir(exist_ok=True)
    outputs = []
    for write, suffix in ((write_otf, ".otf"), (write_ttf, ".ttf")):
        path = OUTPUT / (plan.postscript_name + suffix)
        _write(write, plan, path)
        outputs.append(path)
    records = tables(plan)
    records["build.log"] = _log(plan, names, package_paths, donor, outputs)
    _write_records(LOGS / ("lite" if lite else "full"), records)


def _log(plan, names, package_paths, donor, outputs):
    """What went into the fonts and what came out, for diagnosis."""
    from emit.tables import group
    groups = collections.Counter(group(glyph) for glyph in plan.glyphs)
    files = sorted(
        INPUT / (name + suffix) for name in names for suffix in SUFFIXES)
    files += package_paths
    lines = [
        "mtp2otf %s" % product.VERSION,
        "date %s" % time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "python %s" % sys.version.split()[0],
        "fonttools %s" % _fonttools_version(),
        "tx %s" % _tx_version(),
        "",
        "inputs (sha256)",
    ]
    lines += ["  %s  %s" % (_digest(path), path.name) for path in files]
    lines += [
        "  %s  %s (donor)" % (_digest(Path(donor)), Path(donor).name),
        "",
        "font %s %s" % (plan.family, plan.version),
        "  glyphs %d" % len(plan.glyphs),
        "  code points %d" % sum(len(g.codepoints) for g in plan.glyphs),
        "  features %s" % " ".join(f.tag for f in plan.features),
        "  stretch constructions %d" % len(plan.constructions),
        "  kerning pairs %d" % len(plan.kerns),
        "  hint dictionaries %d" % (len(plan.hints) + 1),
        "  groups %s" % " ".join(
            "%s %d" % item for item in sorted(groups.items())),
        "",
        "outputs (sha256)",
    ]
    lines += ["  %s  %s" % (_digest(path), path.name) for path in outputs]
    return "\n".join(lines) + "\n"


def _fonttools_version():
    import fontTools
    return fontTools.version


def _tx_version():
    run = subprocess.run(["tx", "-v"], capture_output=True, text=True)
    return (run.stdout + run.stderr).strip().split()[-1]


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_records(directory, files):
    """Replace the directory as a whole, so that its tables and its log
    always come from the same build."""
    directory.parent.mkdir(parents=True, exist_ok=True)
    new = Path(tempfile.mkdtemp(dir=directory.parent, prefix=".new-"))
    old = directory.parent / (".old-" + new.name[len(".new-"):])
    try:
        for name, text in files.items():
            (new / name).write_text(text, encoding="utf-8")
        os.chmod(new, 0o777 & ~_umask())
        if directory.exists():
            os.replace(directory, old)
        os.replace(new, directory)
    finally:
        for path in (new, old):
            if path.exists():
                shutil.rmtree(path)


def _umask():
    mask = os.umask(0)
    os.umask(mask)
    return mask


def _write(write, plan, path):
    """Write beside the target, then replace it: no half-written font."""
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    os.close(handle)
    try:
        write(plan, temporary)
        os.chmod(temporary, 0o666 & ~_umask())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
