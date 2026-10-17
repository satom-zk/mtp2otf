"""Compute MATH constants from source dimensions, TeX rules, and
explicit OpenType migration choices.
"""

from __future__ import annotations

from fractions import Fraction


def _pct(frac: Fraction) -> int:
    return round(frac.numerator * 100 / frac.denominator)


def compute(
    sy,
    ex,
    *,
    script_sy,
    script_ratio: Fraction,
    scriptscript_ratio: Fraction,
    operator_sizes,
    cap_height,
    quad=1000.0,
):
    """Return MATH values in output units from local fontdimens and
    conversion policy.
    """
    upm = round(quad)

    def s(i):
        return round(sy[i] * upm)

    def e(i):
        return round(ex[i] * upm)

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
    c['SuperscriptShiftUp'] = s(13)
    c['SuperscriptShiftUpCramped'] = s(15)
    c['SubscriptShiftDown'] = s(17)
    c['SubscriptTopMax'] = round(Fraction(4, 5) * s(5))
    c['SuperscriptBottomMin'] = round(Fraction(1, 4) * s(5))
    c['SuperscriptBottomMaxWithSubscript'] = round(Fraction(4, 5) * s(5))
    c['SubSuperscriptGapMin'] = 4 * theta
    # Map the original upper-limit minimum gap and baseline rise by
    # their OpenType meanings. Do not include big_op_spacing5 here.
    c['UpperLimitBaselineRiseMin'] = e(11)
    c['UpperLimitGapMin'] = e(9)
    c['LowerLimitGapMin'] = e(10)
    c['LowerLimitBaselineDropMin'] = e(12)
    c['StretchStackTopShiftUp'] = e(11)
    c['StretchStackGapAboveMin'] = e(9)
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

    # Round each mapped text/display TFM extent before taking extrema.
    # The shared threshold is a migration choice, not a TFM fontdimen.
    text_sizes, display_sizes = zip(*operator_sizes)
    display_operator_min_height = (
        max(round(size * upm) for size in text_sizes)
        + min(round(size * upm) for size in display_sizes)
    ) // 2

    # Source dimensions and explicit OpenType migration values.
    c['MinConnectorOverlap'] = 100
    c['AccentBaseHeight'] = xh
    c['FlattenedAccentBaseHeight'] = round(cap_height * upm)
    c['DelimitedSubFormulaMinHeight'] = int(display_operator_min_height)
    c['DisplayOperatorMinHeight'] = int(display_operator_min_height)
    # Fixed reference median: LM 154, STIX Two 150, Cambria 300/2048 em.
    # These reference fonts are not build inputs. Skewed-fraction values
    # likewise remain explicit migration values, not TFM-derived values.
    c['MathLeading'] = 150
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
