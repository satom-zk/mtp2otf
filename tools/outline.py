"""Operations on outlines (see sources.types.Outline)."""

from fontTools.pens.boundsPen import BoundsPen


def draw(outline, pen):
    for contour in outline:
        for segment in contour:
            if segment[0] == "move":
                pen.moveTo(segment[1])
            elif segment[0] == "line":
                pen.lineTo(segment[1])
            else:
                pen.curveTo(*segment[1:])
        pen.closePath()


def bounds(outline):
    """Return (x_min, y_min, x_max, y_max) of the ink, or None."""
    pen = BoundsPen(None)
    draw(outline, pen)
    return pen.bounds


def scaled(outline, factor):
    return tuple(
        tuple(
            (segment[0],) + tuple(
                (x * factor, y * factor) for x, y in segment[1:])
            for segment in contour)
        for contour in outline)


def moved(outline, dx, dy):
    if dx == 0 and dy == 0:
        return outline
    return tuple(
        tuple(
            (segment[0],) + tuple((x + dx, y + dy) for x, y in segment[1:])
            for segment in contour)
        for contour in outline)


def rectangle(x_min, y_min, x_max, y_max, clockwise=False):
    corners = [(x_min, y_min), (x_max, y_min), (x_max, y_max), (x_min, y_max)]
    if clockwise:
        corners = [corners[0]] + corners[:0:-1]
    return (("move", corners[0]),) + tuple(("line", p) for p in corners[1:])
