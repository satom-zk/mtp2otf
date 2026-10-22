"""Structural rules for source-complete large symbols.

No input-dependent metrics or drawings belong in this public module.
"""

VERTICAL = frozenset((40, 41, 123, 125, 10216, 10217, 47, 92, 8730))
HORIZONTAL = frozenset((770, 771, 780, 9182, 9183, 9180))


def exempt(policy, identity, direction, operator=False):
    if policy not in ("legacy", "source"):
        raise ValueError("unknown large-variant policy: " + policy)
    return policy == "source" and (
        direction == "h"
        and (operator or identity in VERTICAL)
        or (direction == "w" and identity in HORIZONTAL)
    )


def checked_chain(chars, start, next_key="nextlarger"):
    """A missing successor and a cycle are errors, never truncated
    ladders.
    """
    sequence, seen, slot = ([], set(), start)
    while slot is not None:
        if slot in seen:
            raise ValueError("NEXTLARGER cycle at slot %d" % slot)
        if slot not in chars:
            raise ValueError("NEXTLARGER missing slot %d" % slot)
        seen.add(slot)
        sequence.append(slot)
        slot = chars[slot].get(next_key)
    return sequence


def field_range(label, value, lower, upper):
    if not lower <= value <= upper:
        raise ValueError(
            "%s=%s outside [%s,%s]" % (label, value, lower, upper)
        )


def compound_reference_offsets(boxes, scale):
    """Undo individual centering so halves share their original
    baseline.
    """
    center = (min((b[1] for b in boxes)) + max((b[3] for b in boxes))) / 2
    return [((b[1] + b[3]) / 2 - center) * scale for b in boxes]
