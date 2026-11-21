"""Operations on Type 2 charstrings (width operand removed)."""

MASKS = ("hintmask", "cntrmask")
MOVES = ("rmoveto", "hmoveto", "vmoveto")


def transformed(program, scale=1, dx=0, dy=0):
    """Scale about the origin, then move by (dx, dy); hints follow."""
    if scale == 1 and dx == 0 and dy == 0:
        return program
    result, stack = [], []
    moved = False
    edges = {"h": 0, "v": 0}         # last stem edge, before and after
    new_edges = {"h": 0, "v": 0}
    tokens = iter(program)
    for token in tokens:
        if not isinstance(token, str):
            stack.append(token)
            continue
        direction = _stem_direction(token, stack, result)
        if direction:
            shift = dy if direction == "h" else dx
            stack = _stems(stack, scale, shift, edges, new_edges,
                           direction)
        else:
            stack = [value * scale for value in stack]
            if token == "flex":
                # The last operand is a threshold, not a length.
                stack[12] = stack[12] / scale
        if token in MOVES and not moved:
            stack = _moved(token, stack, dx, dy)
            token = stack.pop()
            moved = True
        result += stack + [token]
        if token in MASKS:
            result.append(next(tokens))
        stack = []
    return tuple(result)


# Stem widths that mark a single edge (ghost hints): the top edge at
# the stem's position, or the bottom edge at its position less 21.
GHOST_TOP, GHOST_BOTTOM = -20, -21


def _stems(operands, scale, shift, edges, new_edges, direction):
    """Stem operands (position relative to the last edge, width) moved
    like the outline; a ghost hint keeps its width and moves its edge."""
    result = []
    for i in range(0, len(operands), 2):
        start = edges[direction] + operands[i]
        width = operands[i + 1]
        edges[direction] = start + width
        if width == GHOST_TOP:
            new_start = start * scale + shift
        elif width == GHOST_BOTTOM:
            new_start = (start + width) * scale + shift - width
        else:
            new_start = start * scale + shift
            width = width * scale
        result += [new_start - new_edges[direction], width]
        new_edges[direction] = new_start + width
    return result


def _stem_direction(token, stack, result):
    if token in ("hstem", "hstemhm"):
        return "h"
    if token in ("vstem", "vstemhm"):
        return "v"
    # Vertical stems may be given as the operands of the first mask.
    if token in MASKS and stack:
        return "v"
    return None


def _moved(operator, operands, dx, dy):
    """Return operands and operator of a first move shifted by (dx, dy)."""
    if operator == "hmoveto":
        x, y = operands[0], 0
    elif operator == "vmoveto":
        x, y = 0, operands[0]
    else:
        x, y = operands
    x, y = x + dx, y + dy
    if y == 0:
        return [x, "hmoveto"]
    if x == 0:
        return [y, "vmoveto"]
    return [x, y, "rmoveto"]
