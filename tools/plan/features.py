"""Substitutions (design document, section 8)."""

from __future__ import annotations

from collections import defaultdict

from plan import names
from plan.types import Feature

OPTICAL_SIZES = "ssty"


def reachable(design, lite, available):
    """Which references a build can resolve.

    available: function telling whether a constructed glyph can be
    made.  Returns a function: Ref -> key or None.  A key is
    ("codepoint", code point), ("slot", role, slot) or ("name", name).
    """
    codepoints = {}
    for row in design.slots:
        if not (lite and not design.roles[row.role].lite):
            for codepoint in row.codepoints:
                codepoints[codepoint] = names.primary(row.codepoints)
    for row in design.donor:
        for codepoint in row:
            codepoints[codepoint] = names.primary(row)
    for codepoint in design.spaces:
        codepoints[codepoint] = codepoint
    for item in design.constructed.values():
        if item.codepoints and available(item.name):
            for codepoint in item.codepoints:
                codepoints[codepoint] = names.primary(item.codepoints)

    def key(ref):
        if ref.kind == "codepoint":
            if ref.value in codepoints:
                return ("codepoint", codepoints[ref.value])
            return None
        if ref.kind == "slot":
            role = design.roles[ref.value[0]]
            if lite and not role.lite:
                return None
            return ("slot",) + ref.value
        return ("name", ref.value) if available(ref.value) else None

    return key


def substitutions(design, key):
    """The rows of the feature table a build can resolve.

    Returns a list of (feature, option, input keys, output key);
    option counts the rows of one input from 1.
    """
    rows, seen = [], defaultdict(int)
    for row in design.features:
        inputs = tuple(key(ref) for ref in row.input)
        output = key(row.output)
        if None in inputs or output is None:
            continue
        seen[row.feature, inputs] += 1
        rows.append((row.feature, seen[row.feature, inputs], inputs, output))
    return rows


def name_edges(design, key, rows):
    """How glyphs are reached, for naming them."""
    edges = defaultdict(list)
    options = defaultdict(int)
    for feature, option, inputs, output in rows:
        options[feature, inputs] = max(options[feature, inputs], option)
    for feature, option, inputs, output in rows:
        suffix = "." + feature
        if options[feature, inputs] > 1:
            suffix += ".%d" % option
        edges[inputs[0]].append((output, "form", suffix))
    series = defaultdict(list)
    for item in design.stretch:
        if item.kind == "variant":
            series[item.root, item.axis].append(item.glyph)
    for (root, axis), variants in series.items():
        start = key(root)
        # Steps are numbered from the root, whether or not the root
        # is itself the first step.
        first = 0 if variants[0] == root else 1
        for number, variant in enumerate(variants, first):
            target = key(variant)
            if start and target and target != start:
                edges[start].append((target, "step", ".%s%d" % (axis, number)))
    return edges


def plan_features(design, rows, glyph_names, optical):
    """Build the features.

    glyph_names: key -> text glyph name.  optical: text glyph name ->
    (script name, scriptscript name).
    """
    mappings = defaultdict(lambda: defaultdict(list))
    entries = defaultdict(list)
    for feature, option, inputs, output in rows:
        text = tuple(glyph_names[k] for k in inputs)
        target = glyph_names[output]
        mappings[feature][text].append(target)
        kind, value = inputs[0][:2]
        if kind == "codepoint" and value not in entries[feature]:
            entries[feature].append(value)
        # A row holds for the smaller sizes when every glyph in it
        # has them.
        if all(name in optical for name in text + (target,)):
            for size in (0, 1):
                small = tuple(optical[name][size] for name in text)
                mappings[feature][small].append(optical[target][size])
    features = []
    for tag, mapping in mappings.items():
        label = design.feature_names.get(tag)
        features.append(Feature(
            tag, *_shaped(mapping),
            name=label.name if label else "",
            description=label.description if label else "",
            options=label.options if label else (),
            characters=tuple(sorted(entries[tag])) if label else ()))
    features.append(Feature(OPTICAL_SIZES, "alternate", dict(optical)))
    return tuple(features)


def _shaped(mapping):
    """Return (kind, mapping) in the form of model.Feature."""
    if any(len(inputs) > 1 for inputs in mapping):
        return "ligature", {
            inputs: outputs[0] for inputs, outputs in mapping.items()}
    if any(len(outputs) > 1 for outputs in mapping.values()):
        return "alternate", {
            inputs[0]: tuple(outputs)
            for inputs, outputs in mapping.items()}
    return "single", {
        inputs[0]: outputs[0] for inputs, outputs in mapping.items()}
