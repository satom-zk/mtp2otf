"""Compute MATH constants from local sources using public conversion formulas."""
from __future__ import annotations

from fractions import Fraction


def _pct(frac: Fraction) -> int:
    return round(frac.numerator * 100 / frac.denominator)


def compute(sy, ex, *, script_sy, script_ratio: Fraction, scriptscript_ratio: Fraction,
            display_operator_min_height: int, quad=1000.0):
    """Return MATH values in output units from local fontdimens and conversion policy."""
    upm = round(quad)
    s = lambda i: round(sy[i] * upm)
    e = lambda i: round(ex[i] * upm)
    theta = e(8)
    xh = s(5)

    c = {}
    c['AxisHeight'] = s(22)
    c['FractionNumeratorShiftUp'] = s(9)
    c['FractionNumeratorDisplayStyleShiftUp'] = s(8)
    c['FractionDenominatorShiftDown'] = s(12)
    c['FractionDenominatorDisplayStyleShiftDown'] = s(11)
    c['FractionNumeratorGapMin'] = theta
    c['FractionNumDisplayStyleGapMin'] = 3 * theta
    c['FractionDenominatorGapMin'] = theta
    c['FractionDenomDisplayStyleGapMin'] = 3 * theta
    c['FractionRuleThickness'] = theta
    c['StackTopShiftUp'] = s(10)
    c['StackTopDisplayStyleShiftUp'] = s(8)
    c['StackBottomShiftDown'] = s(12)
    c['StackBottomDisplayStyleShiftDown'] = s(11)
    c['StackGapMin'] = 3 * theta
    c['StackDisplayStyleGapMin'] = 7 * theta
    c['SuperscriptShiftUp'] = s(14)
    c['SuperscriptShiftUpCramped'] = s(15)
    c['SubscriptShiftDown'] = s(17)
    c['SubscriptTopMax'] = round(Fraction(4, 5) * s(5))
    c['SuperscriptBottomMin'] = round(Fraction(1, 4) * s(5))
    c['SuperscriptBottomMaxWithSubscript'] = round(Fraction(4, 5) * s(5))
    c['SubSuperscriptGapMin'] = 4 * theta
    # TFM-sourced values assigned by the Word placement compatibility policy.
    # The upper-limit pair is not the direct TeX parameter correspondence.
    c['UpperLimitBaselineRiseMin'] = e(9)
    c['UpperLimitGapMin'] = e(11)
    c['LowerLimitGapMin'] = e(10)
    c['LowerLimitBaselineDropMin'] = e(12)
    c['StretchStackTopShiftUp'] = e(9)
    c['StretchStackGapAboveMin'] = e(11)
    c['StretchStackGapBelowMin'] = e(10)
    c['StretchStackBottomShiftDown'] = e(12)
    c['OverbarRuleThickness'] = theta
    c['OverbarVerticalGap'] = 3 * theta
    c['OverbarExtraAscender'] = theta
    c['UnderbarRuleThickness'] = theta
    c['UnderbarVerticalGap'] = 3 * theta
    c['UnderbarExtraDescender'] = theta
    c['RadicalRuleThickness'] = theta
    c['RadicalExtraAscender'] = theta
    c['RadicalVerticalGap'] = theta + theta // 4
    c['RadicalDisplayStyleVerticalGap'] = theta + xh // 4
    c['RadicalKernBeforeDegree'] = round(Fraction(5, 18) * upm)
    c['RadicalKernAfterDegree'] = -round(Fraction(10, 18) * upm)
    c['RadicalDegreeBottomRaisePercent'] = 60
    c['ScriptPercentScaleDown'] = _pct(script_ratio)
    c['ScriptScriptPercentScaleDown'] = _pct(scriptscript_ratio)

    # OpenType migration values; individual sources are documented in PROVENANCE.
    c['MinConnectorOverlap'] = 100
    c['AccentBaseHeight'] = 477
    c['FlattenedAccentBaseHeight'] = 656
    c['DelimitedSubFormulaMinHeight'] = int(display_operator_min_height)
    c['DisplayOperatorMinHeight'] = int(display_operator_min_height)
    c['MathLeading'] = 154
    c['SkewedFractionHorizontalGap'] = 350
    c['SkewedFractionVerticalGap'] = 102
    c['SpaceAfterScript'] = round(Fraction(1, 20) * upm)
    # Convert the next-style TFM drops to the first-level parent em.
    c['SubscriptBaselineDropMin'] = round(script_sy[19] * float(script_ratio) * upm)
    c['SuperscriptBaselineDropMax'] = round(script_sy[18] * float(script_ratio) * upm)
    return c


# Provenance contains no evaluated proprietary-source values.  The local build
# combines this metadata with the values it actually reads/computes.
PROVENANCE = {
    'ScriptPercentScaleDown': ('MT-STY', 'defaultscriptratio', 'MTPro2 package script ratio.'),
    'ScriptScriptPercentScaleDown': ('MT-STY', 'defaultscriptscriptratio', 'MTPro2 package scriptscript ratio.'),
    'DelimitedSubFormulaMinHeight': ('MT-MIG+MT', 'local text/display operator size midpoint', 'OpenType migration threshold evaluated from the active extension TFM.'),
    'DisplayOperatorMinHeight': ('MT-TFM', 'local text/display operator size midpoint', 'Derived from the active extension TFM metrics.'),
    'MathLeading': ('OT-MIG', 'Word line-layout policy', 'OpenType-only migration policy.'),
    'AxisHeight': ('MT-TFM', 'symbol fontdimen axis_height', 'Direct TeX axis mapping.'),
    'AccentBaseHeight': ('OT-MIG', 'accent-raising threshold policy', 'OpenType-only migration policy.'),
    'FlattenedAccentBaseHeight': ('OT-MIG', 'flattened-accent policy', 'OpenType-only migration policy.'),
    'SubscriptShiftDown': ('MT-TFM+OT-MIG', 'symbol fontdimen sub2', 'Source branch selected as the common subscript shift; subscript-only TeX placement can differ.'),
    'SubscriptTopMax': ('OT-SUG+MT', 'fraction of local x-height', 'OpenType suggested formula.'),
    'SubscriptBaselineDropMin': ('MT-TFM+OT-MIG', 'script symbol sub_drop * package script ratio', 'First-level parent-em conversion verified in Word; nested styles and engine scaling can differ.'),
    'SuperscriptShiftUp': ('MT-TFM+OT-MIG', 'symbol fontdimen sup2', 'Source branch selected as the common ordinary superscript shift; display-style TeX placement can differ.'),
    'SuperscriptShiftUpCramped': ('MT-TFM', 'symbol fontdimen cramped superscript shift', 'Direct TeX mapping.'),
    'SuperscriptBottomMin': ('OT-SUG+MT', 'fraction of local x-height', 'OpenType suggested formula.'),
    'SuperscriptBaselineDropMax': ('MT-TFM+OT-MIG', 'script symbol sup_drop * package script ratio', 'First-level parent-em conversion verified in Word; nested styles and engine scaling can differ.'),
    'SubSuperscriptGapMin': ('OT-SUG+MT', 'multiple of local rule thickness', 'OpenType suggested formula.'),
    'SuperscriptBottomMaxWithSubscript': ('OT-SUG+MT', 'fraction of local x-height', 'OpenType suggested formula.'),
    'SpaceAfterScript': ('TeX', 'plain-TeX scriptspace policy', 'TeX default not overridden by MTPro2.'),
    'UpperLimitGapMin': ('OT-MIG+MT', 'extension big_op_spacing3 applied as upper-limit gap', 'TFM-sourced value assigned by the Word placement compatibility policy; not direct TeX correspondence.'),
    'UpperLimitBaselineRiseMin': ('OT-MIG+MT', 'extension big_op_spacing1 applied as upper-limit rise', 'TFM-sourced value assigned by the Word placement compatibility policy; not direct TeX correspondence.'),
    'LowerLimitGapMin': ('MT-TFM', 'extension fontdimen lower-limit gap', 'Direct TeX mapping.'),
    'LowerLimitBaselineDropMin': ('MT-TFM', 'extension fontdimen lower-limit drop', 'Direct TeX mapping.'),
    'StackTopShiftUp': ('MT-TFM', 'symbol fontdimen stack top shift', 'Direct TeX mapping.'),
    'StackTopDisplayStyleShiftUp': ('MT-TFM', 'symbol fontdimen display stack top shift', 'Direct TeX mapping.'),
    'StackBottomShiftDown': ('MT-TFM', 'symbol fontdimen stack bottom shift', 'Direct TeX mapping.'),
    'StackBottomDisplayStyleShiftDown': ('MT-TFM', 'symbol fontdimen display stack bottom shift', 'Direct TeX mapping.'),
    'StackGapMin': ('OT-SUG+MT', 'multiple of local rule thickness', 'OpenType suggested formula.'),
    'StackDisplayStyleGapMin': ('OT-SUG+MT', 'multiple of local rule thickness', 'OpenType suggested formula.'),
    'StretchStackTopShiftUp': ('OT-MIG+MT', 'extension big_op_spacing1 applied as stretch-stack top shift', 'TFM-sourced value assigned by the stretch-stack migration policy.'),
    'StretchStackBottomShiftDown': ('OT-MIG+MT', 'extension lower-limit drop reused for stretch stacks', 'TFM-sourced value assigned to a separate OpenType role; lower-side controls were not independently optimized.'),
    'StretchStackGapAboveMin': ('OT-MIG+MT', 'extension big_op_spacing3 applied as stretch-stack upper gap', 'TFM-sourced value assigned by the stretch-stack migration policy.'),
    'StretchStackGapBelowMin': ('OT-MIG+MT', 'extension lower-limit gap reused for stretch stacks', 'TFM-sourced value assigned to a separate OpenType role; lower-side controls were not independently optimized.'),
    'FractionNumeratorShiftUp': ('MT-TFM', 'symbol fontdimen numerator shift', 'Direct TeX mapping.'),
    'FractionNumeratorDisplayStyleShiftUp': ('MT-TFM', 'symbol fontdimen display numerator shift', 'Direct TeX mapping.'),
    'FractionDenominatorShiftDown': ('MT-TFM', 'symbol fontdimen denominator shift', 'Direct TeX mapping.'),
    'FractionDenominatorDisplayStyleShiftDown': ('MT-TFM', 'symbol fontdimen display denominator shift', 'Direct TeX mapping.'),
    'FractionNumeratorGapMin': ('OT-SUG+MT', 'local rule thickness', 'OpenType suggested formula.'),
    'FractionNumDisplayStyleGapMin': ('OT-SUG+MT', 'multiple of local rule thickness', 'OpenType suggested formula.'),
    'FractionRuleThickness': ('MT-TFM', 'extension fontdimen rule thickness', 'Direct TeX mapping.'),
    'FractionDenominatorGapMin': ('OT-SUG+MT', 'local rule thickness', 'OpenType suggested formula.'),
    'FractionDenomDisplayStyleGapMin': ('OT-SUG+MT', 'multiple of local rule thickness', 'OpenType suggested formula.'),
    'SkewedFractionHorizontalGap': ('OT-MIG', 'skewed-fraction policy', 'OpenType-only migration policy.'),
    'SkewedFractionVerticalGap': ('OT-MIG', 'skewed-fraction policy', 'OpenType-only migration policy.'),
    'OverbarVerticalGap': ('OT-SUG+MT', 'multiple of local rule thickness', 'OpenType suggested formula.'),
    'OverbarRuleThickness': ('MT-TFM', 'extension fontdimen rule thickness', 'Direct TeX mapping.'),
    'OverbarExtraAscender': ('OT-SUG+MT', 'local rule thickness', 'OpenType suggested formula.'),
    'UnderbarVerticalGap': ('OT-SUG+MT', 'multiple of local rule thickness', 'OpenType suggested formula.'),
    'UnderbarRuleThickness': ('MT-TFM', 'extension fontdimen rule thickness', 'Direct TeX mapping.'),
    'UnderbarExtraDescender': ('OT-SUG+MT', 'local rule thickness', 'OpenType suggested formula.'),
    'RadicalVerticalGap': ('OT-SUG+MT', 'local rule-thickness formula', 'OpenType suggested formula.'),
    'RadicalDisplayStyleVerticalGap': ('OT-SUG+MT', 'local rule-thickness/x-height formula', 'OpenType suggested formula.'),
    'RadicalRuleThickness': ('MT-TFM', 'extension fontdimen rule thickness', 'Direct TeX mapping.'),
    'RadicalExtraAscender': ('OT-SUG+MT', 'local rule thickness', 'OpenType suggested formula.'),
    'RadicalKernBeforeDegree': ('OT-SUG', 'OpenType em-ratio recommendation', 'OpenType suggested value.'),
    'RadicalKernAfterDegree': ('OT-SUG', 'OpenType em-ratio recommendation', 'OpenType suggested value.'),
    'RadicalDegreeBottomRaisePercent': ('OT-SUG', 'OpenType percentage recommendation', 'OpenType suggested value.'),
    'MinConnectorOverlap': ('OT-MIG+MT-PFB', 'initial overlap policy limited by measured connector runs', 'Both ends of repeatable parts are joining ends; validate against local outline geometry.'),
}


def audit_payload(constants):
    rows = {}
    missing = []
    for name, value in constants.items():
        meta = PROVENANCE.get(name)
        if not meta:
            missing.append(name)
            continue
        source, formula, rationale = meta
        rows[name] = {
            'value': int(value),
            'source_class': source,
            'formula': formula,
            'rationale': rationale,
        }
    extra = sorted(set(PROVENANCE) - set(constants))
    if missing or extra:
        raise ValueError('MATH provenance mismatch: missing=%r extra=%r' % (missing, extra))
    return rows
