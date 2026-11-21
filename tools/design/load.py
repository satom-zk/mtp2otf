"""Read the design tables and check their form."""

import csv
import re
from dataclasses import replace
from pathlib import Path

from design.types import (
    Constructed,
    Design,
    FeatureName,
    Ref,
    Role,
    Series,
    SlotGlyph,
    StretchItem,
    Substitution,
)
from errors import Error

DATA = Path(__file__).resolve().parents[1] / "data"

COLUMNS = {
    "roles.tsv": ("role", "declaration", "lite"),
    "slots.tsv": ("role", "slot", "codepoints"),
    "donor.tsv": ("codepoints",),
    "spaces.tsv": ("codepoint", "advance"),
    "metrics.tsv": ("role", "slot", "metrics"),
    "constructed.tsv": (
        "name", "codepoints", "method", "arguments"),
    "features.tsv": ("feature", "input", "output"),
    "stretch.tsv": ("root", "axis", "kind", "glyph"),
    "feature_names.tsv": ("feature", "name", "description", "options"),
    "series.tsv": ("root", "bottom", "connector_cap", "measure"),
}

DECLARATION = re.compile(r"\\\w+@?|\w+/\w+/\w+/\w+")
CODEPOINT = re.compile(r"[0-9A-F]{4,5}")
FEATURE = re.compile(r"ccmp|dtls|cv\d\d|ss\d\d")
NAMED_FEATURE = re.compile(r"cv\d\d|ss\d\d")
CODEPOINT_REF = re.compile(r"U\+([0-9A-F]{4,5})")
SLOT_REF = re.compile(r"([a-z]+):(\d+)")
NAME_REF = re.compile(r"[a-z]+(\.[a-z0-9]+)*")
AXES = ("v", "h")
METHODS = (
    "prime", "dotless", "row", "spaced", "vdots", "ddots", "moustache",
    "rule", "mirror", "column", "interpolate", "vector", "overparen",
)
KINDS = ("variant", "part", "extender", "chain")


class DesignError(Error):
    pass


class _Table:
    """Rows of one file; errors carry the file name and line number."""

    def __init__(self, directory, name):
        self.name = name
        self.line = 1
        with open(directory / name, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
        if not rows or tuple(rows[0]) != COLUMNS[name]:
            self.fail("header must be " + " ".join(COLUMNS[name]))
        self.rows = rows[1:]

    def __iter__(self):
        for self.line, row in enumerate(self.rows, 2):
            if len(row) != len(COLUMNS[self.name]):
                self.fail("wrong number of columns")
            yield row

    def fail(self, message):
        raise DesignError("%s:%d: %s" % (self.name, self.line, message))

    def number(self, text):
        if not text.isdecimal():
            self.fail("not a number: %r" % text)
        return int(text)

    def flag(self, text):
        if text not in ("yes", "no"):
            self.fail("must be yes or no: %r" % text)
        return text == "yes"

    def choice(self, text, allowed):
        if text not in allowed:
            self.fail("must be one of %s: %r" % (", ".join(allowed), text))
        return text

    def codepoint(self, text):
        if not CODEPOINT.fullmatch(text):
            self.fail("not a code point: %r" % text)
        return int(text, 16)

    def codepoints(self, text):
        return tuple(self.codepoint(word) for word in text.split())

    def ref(self, text):
        match = CODEPOINT_REF.fullmatch(text)
        if match:
            return Ref("codepoint", int(match.group(1), 16))
        match = SLOT_REF.fullmatch(text)
        if match:
            return Ref("slot", (match.group(1), int(match.group(2))))
        if NAME_REF.fullmatch(text):
            return Ref("name", text)
        self.fail("not a glyph reference: %r" % text)


def load_design(directory=DATA):
    directory = Path(directory)
    roles = _roles(_Table(directory, "roles.tsv"))
    assigned = set()
    slots = _slots(_Table(directory, "slots.tsv"), roles, assigned)
    donor = _donor(_Table(directory, "donor.tsv"), assigned)
    spaces = _spaces(_Table(directory, "spaces.tsv"), assigned)
    constructed = _constructed(
        _Table(directory, "constructed.tsv"), assigned)
    known = _Known(roles, assigned, constructed)
    stretch = _stretch(_Table(directory, "stretch.tsv"), known)
    return Design(
        roles=roles,
        slots=slots,
        metric_slots=_metric_slots(_Table(directory, "metrics.tsv"), roles),
        donor=donor,
        spaces=spaces,
        constructed=constructed,
        features=_features(_Table(directory, "features.tsv"), known),
        stretch=stretch,
        series=_series(_Table(directory, "series.tsv"), stretch, known),
        feature_names=_feature_names(
            _Table(directory, "feature_names.tsv")),
    )


class _Known:
    """What a glyph reference may point to."""

    def __init__(self, roles, codepoints, names):
        self.roles = roles
        self.codepoints = codepoints
        self.names = names

    def ref(self, table, text):
        ref = table.ref(text)
        if ref.kind == "codepoint" and ref.value not in self.codepoints:
            table.fail("code point not assigned: %s" % text)
        if ref.kind == "slot":
            role, slot = ref.value
            if role not in self.roles or slot > 255:
                table.fail("unknown slot: %s" % text)
        if ref.kind == "name":
            if ref.value not in self.names:
                table.fail("unknown constructed glyph: %s" % text)
            # One way to write each reference.
            if self.names[ref.value].codepoints:
                table.fail("refer to it by code point: %s" % text)
        return ref


def _assign(table, codepoints, assigned):
    for codepoint in codepoints:
        if codepoint in assigned:
            table.fail("code point assigned twice: %04X" % codepoint)
        assigned.add(codepoint)


def _roles(table):
    roles = {}
    for name, declaration, lite in table:
        if name in roles:
            table.fail("role defined twice: %s" % name)
        if not DECLARATION.fullmatch(declaration):
            table.fail("not a font shape or command: %r" % declaration)
        roles[name] = Role(name, declaration, table.flag(lite))
    return roles


def _slots(table, roles, assigned):
    slots = []
    for role, slot, codepoints in table:
        if role not in roles:
            table.fail("unknown role: %s" % role)
        glyph = SlotGlyph(
            role, table.number(slot), table.codepoints(codepoints))
        if glyph.slot > 255:
            table.fail("slot out of range: %s" % slot)
        if not glyph.codepoints:
            table.fail("no code point")
        _assign(table, glyph.codepoints, assigned)
        slots.append(glyph)
    return tuple(slots)


def _metric_slots(table, roles):
    metric_slots = {}
    for role, slot, metrics in table:
        if role not in roles:
            table.fail("unknown role: %s" % role)
        key = (role, table.number(slot))
        if key in metric_slots:
            table.fail("slot listed twice")
        metric_slots[key] = table.number(metrics)
    return metric_slots


def _donor(table, assigned):
    donor = []
    for (text,) in table:
        codepoints = table.codepoints(text)
        if not codepoints:
            table.fail("no code point")
        _assign(table, codepoints, assigned)
        donor.append(codepoints)
    return tuple(donor)


def _spaces(table, assigned):
    spaces = {}
    for codepoint, advance in table:
        codepoint = table.codepoint(codepoint)
        _assign(table, (codepoint,), assigned)
        match = CODEPOINT_REF.fullmatch(advance)
        if match:
            # As wide as that glyph (U+2007 the digits, U+2008 the period).
            width = int(match.group(1), 16)
            if width not in assigned:
                table.fail("code point not assigned: %s" % advance)
            spaces[codepoint] = Ref("codepoint", width)
        else:
            spaces[codepoint] = table.number(advance)
    return spaces


def _constructed(table, assigned):
    constructed = {}
    for name, text, method, arguments in table:
        if name in constructed:
            table.fail("glyph defined twice: %s" % name)
        if not NAME_REF.fullmatch(name):
            table.fail("not a name: %r" % name)
        codepoints = table.codepoints(text)
        _assign(table, codepoints, assigned)
        constructed[name] = Constructed(
            name, codepoints, table.choice(method, METHODS),
            tuple(arguments.split()))
    return constructed


def _features(table, known):
    features = []
    for feature, inputs, output in table:
        if not FEATURE.fullmatch(feature):
            table.fail("not a feature: %r" % feature)
        inputs = tuple(known.ref(table, word) for word in inputs.split())
        if not inputs:
            table.fail("no input")
        features.append(
            Substitution(feature, inputs, known.ref(table, output)))
    return tuple(features)


def _stretch(table, known):
    stretch = []
    axes = {}
    for root, axis, kind, glyph in table:
        root = known.ref(table, root)
        if axes.setdefault(root, table.choice(axis, AXES)) != axis:
            table.fail("a root stretches along one axis")
        item = StretchItem(
            root, axis, table.choice(kind, KINDS), known.ref(table, glyph))
        if kind == "chain" and item.glyph.kind != "slot":
            table.fail("a chain starts at a source slot: %s" % glyph)
        stretch.append(item)
    return tuple(stretch)


def expand_chains(design, metrics):
    """The design with each chain row replaced by the steps of the TFM
    "next larger" list from its slot; a list that ends in an extensible
    character gives the assembly too, after the other rows of the root.

    metrics: role name -> Tfm of the text size, for the roles the build
    reads; chains of other roles (Full only, in a Lite build) go."""
    stretch, parts = [], {}
    for item in design.stretch:
        if item.kind != "chain":
            stretch.append(item)
            continue
        role, slot = item.glyph.value
        if role not in metrics:
            continue
        chars = metrics[role].chars
        seen = set()
        while True:
            seen.add(slot)
            char = chars.get(slot)
            if char is not None and char.extensible:
                parts[item.root] = [
                    StretchItem(item.root, item.axis, kind,
                                Ref("slot", (role, code)))
                    for kind, code in _recipe(*char.extensible)]
                break
            # A missing slot stays, for the preflight to report.
            stretch.append(StretchItem(
                item.root, item.axis, "variant", Ref("slot", (role, slot))))
            slot = char.next_larger if char else None
            if slot is None or slot in seen:
                break
    for root, items in parts.items():
        if any(i.root == root and i.kind != "variant" for i in stretch):
            raise DesignError("%s: a chain and parts both give the assembly"
                              % root)
        last = max(k for k, i in enumerate(stretch) if i.root == root)
        stretch[last + 1:last + 1] = items
    return replace(design, stretch=tuple(stretch))


def _recipe(top, middle, bottom, repeat):
    """Parts of a TFM extensible recipe, from the bottom."""
    result = []
    if bottom is not None:
        result.append(("part", bottom))
    result.append(("extender", repeat))
    if middle is not None:
        result += [("part", middle), ("extender", repeat)]
    if top is not None:
        result.append(("part", top))
    return result


def _series(table, stretch, known):
    roots = {item.root for item in stretch}
    series = {}
    for root, bottom, cap, measure in table:
        root = known.ref(table, root)
        if root not in roots:
            table.fail("not the root of a series: %s" % root)
        if root in series:
            table.fail("series listed twice: %s" % root)
        if measure not in ("", "ceil"):
            table.fail("unknown measure: %r" % measure)
        series[root] = Series(
            table.number(bottom) if bottom else None,
            table.flag(cap) if cap else False,
            measure == "ceil")
    return series


def _feature_names(table):
    names = {}
    for feature, name, description, options in table:
        if not NAMED_FEATURE.fullmatch(feature):
            table.fail("not a named feature: %r" % feature)
        if feature in names:
            table.fail("feature named twice: %s" % feature)
        if not name:
            table.fail("no name")
        options = tuple(options.split(";")) if options else ()
        names[feature] = FeatureName(feature, name, description, options)
    return names
