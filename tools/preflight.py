"""Check, before building, that every input the build uses is there.

Every file, slot, fontdimen and donor character is required; all
shortages are collected and reported together.
"""

import re
from dataclasses import replace
from pathlib import Path

from errors import Error
from sources.donor import dotless_j

# The package files that declare the sources of each edition.
PACKAGE = ("mtpro2.sty",)
FULL_PACKAGE = PACKAGE + ("umt2ms.fd", "umt2mf.fd", "umt2bb.fd",
                          "umt2hrb.fd")

# Fontdimens read from the TFM files: (role, size) -> numbers.
FONTDIMENS = {
    ("sy", "text"): (5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 17, 22),
    ("sy", "script"): (5, 18, 19),
    ("sy", "scriptscript"): (5,),
    ("exa", "text"): (8, 9, 10, 11, 12),
}

DONOR_WEIGHTS = range(300, 600)
SLOT_ARGUMENT = re.compile(r"([a-z]+):(\d+)")


class PreflightError(Error):
    pass


def _fail(problems):
    if problems:
        raise PreflightError("%d missing or unusable input%s:\n  %s" % (
            len(problems), "" if len(problems) == 1 else "s",
            "\n  ".join(problems)))


def package_files(lite):
    return PACKAGE if lite else FULL_PACKAGE


def check_files(paths):
    """Every file the build reads must exist."""
    _fail(["%s: no such file" % path
           for path in map(Path, paths) if not path.is_file()])


def resolve_roles(design, package, lite):
    """The design with the source files and scale of each role, as the
    package declares them."""
    roles, problems = {}, []
    for name, role in design.roles.items():
        files = package.files(role.declaration)
        if files is None:
            if not lite or role.lite:
                problems.append("%s: not declared in the package"
                                % role.declaration)
            roles[name] = role
            continue
        text, script, scriptscript, scale = files
        roles[name] = replace(role, text=text, script=script,
                              scriptscript=scriptscript, scale=scale)
    _fail(problems)
    return replace(design, roles=roles)


def _slot_refs(design, lite):
    """(role, slot) of every source slot the design refers to."""
    refs = {(row.role, row.slot) for row in design.slots}
    refs |= set(design.metric_slots)
    refs |= {(role, slot) for (role, _), slot in design.metric_slots.items()}
    for item in design.features:
        refs |= {ref.value for ref in item.input + (item.output,)
                 if ref.kind == "slot"}
    for item in design.stretch:
        refs |= {ref.value for ref in (item.root, item.glyph)
                 if ref.kind == "slot"}
    for item in design.constructed.values():
        for argument in item.arguments:
            refs |= {(role, int(slot)) for role, slot
                     in SLOT_ARGUMENT.findall(argument)
                     if role in design.roles}
    return {(role, slot) for role, slot in refs
            if not lite or design.roles[role].lite}


def _donor_codepoints(design):
    return {row[0] for row in design.donor}


def check_contents(design, sources, lite):
    """Every slot in both the PFB and the TFM, every fontdimen the
    build reads, and every donor character."""
    problems = []
    for role_name, slot in sorted(_slot_refs(design, lite)):
        role = design.roles[role_name]
        for source in (role.text, role.script, role.scriptscript):
            if not source:
                continue
            if sources.fonts[source].slot(slot) is None:
                problems.append("%s.pfb: no glyph in slot %d" % (
                    source, slot))
            if slot not in sources.metrics[source].chars:
                problems.append("%s.tfm: no character %d" % (source, slot))
    for (role_name, size), numbers in sorted(FONTDIMENS.items()):
        source = getattr(design.roles[role_name], size)
        params = sources.metrics[source].params
        problems += ["%s.tfm: no fontdimen %d" % (source, number)
                     for number in numbers if number > len(params)]
    package = sources.package
    if not any(accent.family == "symbols" for accent in package.accents):
        problems.append("mtpro2.sty: no \\DeclareMathAccent for symbols")
    if package.vdots_step is None:
        problems.append("mtpro2.sty: no \\baselineskip in \\vdots")
    if (not package.ddots_raises
            or len(package.ddots_gaps) != len(package.ddots_raises) - 1):
        problems.append("mtpro2.sty: \\ddots not understood")
    donor = sources.donor
    for codepoint in sorted(_donor_codepoints(design)):
        if codepoint not in donor.cmap:
            problems.append("donor: no U+%04X" % codepoint)
        elif not donor.glyphs[donor.cmap[codepoint]].outline:
            problems.append("donor: U+%04X has no outline" % codepoint)
    if donor.weight not in DONOR_WEIGHTS:
        problems.append("donor: weight %d is not 300 to 599" % donor.weight)
    if not donor.upright:
        problems.append("donor: not upright")
    if donor.fixed_pitch:
        problems.append("donor: fixed pitch")
    if any(item.method == "dotless" for item in design.constructed.values()):
        try:
            dotless_j(donor)
        except Error as error:
            problems.append(str(error))
    _fail(problems)
