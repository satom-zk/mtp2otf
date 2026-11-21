"""Connector lengths measured from outlines (design document, section 6).

A connector may overlap the next part as far as the cross-section of
the outline stays within TOLERANCE of its section at the joining end.
"""

SLICES = 64
TOLERANCE = 8
CURVE_STEPS = 8


def straight_run(outline, vertical, at_end):
    """Length from one end of the outline along which it keeps the
    cross-section of that end.

    vertical: measure along y.  at_end: start from the top or right
    end instead of the bottom or left one.
    """
    polygons = _flattened(outline)
    along = 1 if vertical else 0
    values = [p[along] for polygon in polygons for p in polygon]
    low, high = min(values), max(values)
    sections = [
        _section(polygons, along, low + (high - low) * (k + 0.5) / SLICES)
        for k in range(SLICES)]
    if at_end:
        sections.reverse()
    reference = sections[0]
    if reference is None:
        return 0
    count = 0
    for section in sections:
        if section is None or any(
                abs(a - b) > TOLERANCE for a, b in zip(section, reference)):
            break
        count += 1
    return int(count * (high - low) / SLICES)


def _flattened(outline):
    polygons = []
    for contour in outline:
        points, current = [], None
        for segment in contour:
            if segment[0] in ("move", "line"):
                current = segment[1]
                points.append(current)
                continue
            (x0, y0), (x1, y1), (x2, y2), (x3, y3) = (current,) + segment[1:]
            for k in range(1, CURVE_STEPS + 1):
                t = k / CURVE_STEPS
                a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, \
                    3 * (1 - t) * t * t, t ** 3
                points.append((
                    a * x0 + b * x1 + c * x2 + d * x3,
                    a * y0 + b * y1 + c * y2 + d * y3))
            current = segment[3]
        if points:
            polygons.append(points)
    return polygons


def _section(polygons, along, value):
    """(min, max) of the outline across the line at `value`, or None."""
    across = 1 - along
    hits = []
    for points in polygons:
        for p, q in zip(points, points[1:] + points[:1]):
            a, b = p[along], q[along]
            if a <= value < b or b <= value < a:
                t = (value - a) / (b - a)
                hits.append(p[across] + (q[across] - p[across]) * t)
    return (min(hits), max(hits)) if len(hits) >= 2 else None
