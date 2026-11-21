"""Stretch series and assemblies (design document, section 6)."""

from __future__ import annotations

import math
from collections import defaultdict
from fractions import Fraction

from outline import bounds
from plan import names
from plan.connectors import TOLERANCE, straight_run
from plan.types import Construction, Glyph, Part

# Integral signs count as extended shapes in text size too.
EXTENDED_TEXT = range(0x222B, 0x2234)


def advance_measurement(glyph, axis, series=None):
    box = bounds(glyph.outline)
    extent = box[3] - box[1] if axis == "v" else box[2] - box[0]
    if series and series.ceil_measure:
        return math.ceil(extent)
    return math.floor(extent) + 1


class StretchPlanner:
    """Builds the constructions and the glyphs they alone use."""

    def __init__(self, design, maker, builder, key, glyph_names, glyphs,
                 optical, constants):
        self.design = design
        self.maker = maker
        self.builder = builder      # constructed glyphs
        self.key = key              # Ref -> key, see features.reachable
        self.names = glyph_names    # key -> glyph name
        self.glyphs = glyphs        # glyph name -> Glyph
        self.optical = optical      # text glyph name -> (script, sscript)
        self.ratios = (
            Fraction(constants["ScriptPercentScaleDown"], 100),
            Fraction(constants["ScriptScriptPercentScaleDown"], 100))
        self.new = []               # glyphs made here, in order made
        self._parts = {}            # how a part was made -> glyph name
        self._scaled = {}           # (origin, factor) -> glyph name

    def plan(self):
        constructions = []
        for (root, axis), (variants, parts) in self._series().items():
            text = self._text(root, axis, variants, parts)
            if text is None:
                continue
            constructions.append(text)
            if text.root not in self.optical:
                continue
            if axis == "v":
                constructions += self._smaller_delimiters(text)
            else:
                constructions += self._smaller_horizontal(
                    root, variants, parts, text)
        constructions = self._unshared(constructions)
        return tuple(constructions), self._extended(constructions)

    def _unshared(self, constructions):
        """TeX engines give each glyph one larger size (LuaTeX reads the
        series that way), so a step that two series continue
        differently is copied for the later series."""
        following = {}      # glyph -> what comes after it
        copies = {}         # (glyph, what follows) -> copy
        result = []
        for c in constructions:
            steps = list(c.variants)
            after = ("assembly", c.parts) if c.parts else None
            for index in range(len(steps) - 1, -1, -1):
                name, measure = steps[index]
                if name == c.root:
                    break
                known = following.setdefault(name, after)
                if known != after:
                    if (name, after) not in copies:
                        copy = names.with_suffix(c.root, ".%s%d" % (
                            c.axis, index))
                        self._add(_renamed(self.glyphs[name], copy))
                        copies[name, after] = copy
                        following[copy] = after
                    name = copies[name, after]
                    steps[index] = (name, measure)
                after = name
            if not steps or steps[0][0] != c.root:
                following.setdefault(c.root, after)
            result.append(Construction(c.root, c.axis, tuple(steps), c.parts))
        return result

    def _series(self):
        series = defaultdict(lambda: ([], []))
        for item in self.design.stretch:
            variants, parts = series[item.root, item.axis]
            if item.kind == "variant":
                variants.append(item.glyph)
            else:
                parts.append((item.glyph, item.kind == "extender"))
        return series

    def _name(self, ref):
        key = self.key(ref)
        return self.names.get(key) if key else None

    def _text(self, root, axis, variants, parts):
        root_name = self._name(root)
        if root_name is None:
            return None
        found = [self._name(ref) for ref in variants]
        series = self.design.series.get(root)
        steps = tuple(
            (name, advance_measurement(self.glyphs[name], axis, series))
            for name in found if name)
        assembly = ()
        if parts:
            assembly = self._assembly(
                root_name, axis, [self.key(ref) for ref, _ in parts],
                [extender for _, extender in parts],
                series, 0) or ()
        return Construction(root_name, axis, steps, assembly)

    def _assembly(self, root_name, axis, keys, extenders, series, size):
        """size: 0 for text, 1 for script, 2 for scriptscript.  None if
        a part has no glyph of that size."""
        sources = [self._source(key, size) for key in keys]
        if None in sources:
            return None
        offset = 0
        if series and series.bottom is not None:
            offset = series.bottom - min(
                bounds(glyph.outline)[1] for glyph in sources)
        limit = None
        if series and series.connector_cap:
            limit = min(
                _thickness(glyph, axis) - TOLERANCE
                for glyph, extender in zip(sources, extenders) if extender)
        count = len(sources)
        parts = []
        for index, (glyph, extender) in enumerate(zip(sources, extenders)):
            first, last = index == 0, index == count - 1
            if extender:
                kind = "ext"
            elif axis == "v":
                kind = "bot" if first else "top" if last else "mid"
            else:
                kind = "left" if first else "right" if last else "mid"
            joins_start = extender or not first
            joins_end = extender or not last
            part = self._part(
                root_name, kind, glyph, axis, joins_start, joins_end, offset)
            full = (
                round(_height(part)) if axis == "v" else part.advance)
            if extender:
                start = end = full
            else:
                start = self._connector(part, axis, False, limit, joins_start)
                end = self._connector(part, axis, True, limit, joins_end)
            parts.append(Part(part.name, extender, start, end, full))
        return tuple(parts)

    def _source(self, key, size):
        """The glyph a part is cut from, as its source draws it."""
        if key is None:
            return None
        if key[0] == "name":
            return self.builder.raw(key[1], size)
        role = self.design.roles[key[1]]
        source = (role.text, role.script, role.scriptscript)[size]
        return self.maker.from_slot(source, key[2], "") if source else None

    def _connector(self, glyph, axis, at_end, limit, joins):
        if not joins:
            return 0
        length = straight_run(glyph.outline, axis == "v", at_end)
        return min(length, limit) if limit is not None else length

    def _part(self, root_name, kind, glyph, axis, joins_start, joins_end,
              offset):
        """A part glyph: a vertical part has its ink bottom at 0; a
        horizontal part has no side bearing where it joins."""
        box = bounds(glyph.outline)
        if axis == "v":
            dx, dy, advance = 0, -box[1], None
        else:
            dx = -box[0] if joins_start else 0
            dy = offset
            advance = round(box[2] + dx) if joins_end else None
        how = (glyph.origin, axis, dx, dy, advance)
        if how in self._parts:
            return self.glyphs[self._parts[how]]
        name = names.with_suffix(root_name, "." + kind)
        if name in self.glyphs:
            raise ValueError("two parts named %s" % name)
        part = self.maker.derive(glyph, name, dx=dx, dy=dy, advance=advance)
        self._add(part)
        self._parts[how] = name
        return part

    def _add(self, glyph):
        self.glyphs[glyph.name] = glyph
        self.new.append(glyph)

    def _scale(self, glyph, factor, name):
        """The glyph scaled; roots that share an outline share it."""
        cache = (self._origin(glyph), factor)
        if cache not in self._scaled:
            self._add(self.maker.derive(glyph, name, float(factor)))
            self._scaled[cache] = name
        return self.glyphs[self._scaled[cache]]

    def _origin(self, glyph):
        return glyph.origin or glyph.name

    def _smaller_delimiters(self, text):
        """Series for the script and scriptscript forms of a vertical
        root: the next optical size up, scaled, then the larger text
        steps (TeX tries the next size before the extension font)."""
        script, scriptscript = self.optical[text.root]
        root = self.glyphs[text.root]
        larger = [step for step in text.variants if step[0] != text.root]
        r1, r2 = self.ratios
        chains = (
            (script, ((root, 1 / r1, ".v1"),)),
            (scriptscript, (
                (self.glyphs[script], r1 / r2, ".v1"),
                (root, 1 / r2, ".v2"))),
        )
        result = []
        for small, scaled in chains:
            size = names.size_suffix(small)
            steps = [(small, advance_measurement(self.glyphs[small], "v"))]
            for glyph, factor, step in scaled:
                name = names.with_suffix(text.root, step) + size
                made = self._scale(glyph, factor, name)
                steps.append((made.name, advance_measurement(made, "v")))
            steps += [s for s in larger if s[1] > steps[-1][1]]
            result.append(
                Construction(small, "v", tuple(steps), text.parts))
        return result

    def _smaller_horizontal(self, root, variants, parts, text):
        """The same construction from the smaller optical sizes, where
        every glyph of it has them."""
        found = [name for name in map(self._name, variants) if name]
        if not all(name in self.optical for name in found):
            return []
        keys = [self.key(ref) for ref, _ in parts]
        extenders = [extender for _, extender in parts]
        series = self.design.series.get(root)
        result = []
        for size in (1, 2):
            assembly = ()
            if parts:
                assembly = self._assembly(
                    self.optical[text.root][size - 1], "h", keys,
                    extenders, series, size)
                if assembly is None:
                    return []
            small = [self.optical[name][size - 1] for name in found]
            steps = tuple(
                (name, advance_measurement(self.glyphs[name], "h", series))
                for name in small)
            result.append(Construction(
                self.optical[text.root][size - 1], "h", steps, assembly))
        return result

    def _extended(self, constructions):
        """The sizes of vertical series other than the roots, the parts
        of vertical assemblies, and the integral signs of text size."""
        shapes = set()
        for construction in constructions:
            if construction.axis != "v":
                continue
            for name, _ in construction.variants:
                if name != construction.root and \
                        not self.glyphs[name].codepoints:
                    shapes.add(name)
            shapes.update(part.glyph for part in construction.parts)
        for glyph in self.glyphs.values():
            if any(c in EXTENDED_TEXT for c in glyph.codepoints):
                shapes.add(glyph.name)
        return frozenset(shapes)


def _renamed(glyph, name):
    fields = dict(glyph.__dict__)
    fields.update(name=name, codepoints=())
    return Glyph(**fields)


def _height(glyph):
    box = bounds(glyph.outline)
    return box[3] - box[1]


def _thickness(glyph, axis):
    """Extent of the ink across the direction of stretching."""
    box = bounds(glyph.outline)
    return box[2] - box[0] if axis == "v" else box[3] - box[1]
