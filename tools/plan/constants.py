"""MATH constants (design document, section 5)."""

from plan.metrics import units

SYMBOLS = "sy"
EXTENSION = "exa"
ITALIC = "mi"
MIN_CONNECTOR_OVERLAP = 20


def plan_constants(design, sources):
    symbols = sources.metrics[design.roles[SYMBOLS].text]
    script = sources.metrics[design.roles[SYMBOLS].script]
    extension = sources.metrics[design.roles[EXTENSION].text]
    italic = sources.metrics[design.roles[ITALIC].text]
    package = sources.package

    def s(number):
        return units(symbols.param(number))

    def e(number):
        return units(extension.param(number))

    def percent(ratio):
        return round(ratio * 100)

    rule = e(8)
    x_height = s(5)
    operator = _display_operator_min_height(design, extension)
    return {
        "ScriptPercentScaleDown": percent(package.script_ratio),
        "ScriptScriptPercentScaleDown": percent(
            package.scriptscript_ratio),
        "DelimitedSubFormulaMinHeight": operator,
        "DisplayOperatorMinHeight": operator,
        "MathLeading": 150,
        "AxisHeight": s(22),
        "AccentBaseHeight": x_height,
        "FlattenedAccentBaseHeight": units(italic.chars[ord("A")].height),
        "SubscriptShiftDown": s(17),
        "SubscriptTopMax": round(x_height * 4 / 5),
        "SubscriptBaselineDropMin": units(
            script.param(19) * package.script_ratio),
        "SuperscriptShiftUp": s(14),
        "SuperscriptShiftUpCramped": s(15),
        "SuperscriptBottomMin": round(x_height / 4),
        "SuperscriptBaselineDropMax": units(
            script.param(18) * package.script_ratio),
        "SubSuperscriptGapMin": 4 * rule,
        "SuperscriptBottomMaxWithSubscript": round(x_height * 4 / 5),
        "SpaceAfterScript": 50,
        "UpperLimitGapMin": e(9),
        "UpperLimitBaselineRiseMin": e(11),
        "LowerLimitGapMin": e(10),
        "LowerLimitBaselineDropMin": e(12),
        "StackTopShiftUp": s(10),
        "StackTopDisplayStyleShiftUp": s(8),
        "StackBottomShiftDown": s(12),
        "StackBottomDisplayStyleShiftDown": s(11),
        "StackGapMin": 3 * rule,
        "StackDisplayStyleGapMin": 7 * rule,
        "StretchStackTopShiftUp": e(11),
        "StretchStackBottomShiftDown": e(12),
        "StretchStackGapAboveMin": e(9),
        "StretchStackGapBelowMin": e(10),
        "FractionNumeratorShiftUp": s(9),
        "FractionNumeratorDisplayStyleShiftUp": s(8),
        "FractionDenominatorShiftDown": s(12),
        "FractionDenominatorDisplayStyleShiftDown": s(11),
        "FractionNumeratorGapMin": rule,
        "FractionNumDisplayStyleGapMin": 3 * rule,
        "FractionRuleThickness": rule,
        "FractionDenominatorGapMin": rule,
        "FractionDenomDisplayStyleGapMin": 3 * rule,
        "SkewedFractionHorizontalGap": 350,
        "SkewedFractionVerticalGap": 102,
        "OverbarVerticalGap": 3 * rule,
        "OverbarRuleThickness": rule,
        "OverbarExtraAscender": rule,
        "UnderbarVerticalGap": 3 * rule,
        "UnderbarRuleThickness": rule,
        "UnderbarExtraDescender": rule,
        "RadicalVerticalGap": rule + rule // 4,
        "RadicalDisplayStyleVerticalGap": rule + x_height // 4,
        "RadicalRuleThickness": rule,
        "RadicalExtraAscender": rule,
        "RadicalKernBeforeDegree": round(1000 * 5 / 18),
        "RadicalKernAfterDegree": -round(1000 * 10 / 18),
        "RadicalDegreeBottomRaisePercent": 60,
    }


def _display_operator_min_height(design, extension):
    """Halfway between the tallest text and the shortest display size.

    The big operators are the vertical series whose root and second
    step both come from the extension font.
    """
    slots = {
        codepoint: glyph.slot
        for glyph in design.slots if glyph.role == EXTENSION
        for codepoint in glyph.codepoints}
    steps = {}
    for item in design.stretch:
        if item.axis == "v" and item.kind == "variant":
            steps.setdefault(item.root, []).append(item.glyph)
    text, display = [], []
    for root, variants in steps.items():
        if root.kind != "codepoint" or root.value not in slots:
            continue
        if len(variants) < 2 or variants[1].kind != "slot":
            continue
        role, slot = variants[1].value
        if role != EXTENSION:
            continue
        text.append(_extent(extension, slots[root.value]))
        display.append(_extent(extension, slot))
    return (max(text) + min(display)) // 2


def _extent(tfm, slot):
    char = tfm.chars[slot]
    return units(char.height + char.depth)
