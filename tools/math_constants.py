"""Compute MATH constants from local sources using public conversion
formulas.
"""
from __future__ import annotations

from fractions import Fraction


def _pct(frac: Fraction) -> int:
    return round(frac.numerator * 100 / frac.denominator)


def compute(
    sy, ex, *, script_sy, script_ratio: Fraction, scriptscript_ratio: Fraction,
    display_operator_min_height: int, quad=1000.0
):
    """Return MATH values in output units from local fontdimens and
    conversion policy.
    """
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
    # TFM-sourced values assigned by the Word placement compatibility
    # policy. The upper-limit pair is not the direct TeX
    # parameter correspondence.
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

    # OpenType migration values; derive these from the
    # local font dimensions.
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
    c['SubscriptBaselineDropMin'] = round(
        script_sy[19] * float(script_ratio) * upm
    )
    c['SuperscriptBaselineDropMax'] = round(
        script_sy[18] * float(script_ratio) * upm
    )
    return c
