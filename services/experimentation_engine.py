"""Experimentation engine: two-proportion z-test in pure stdlib math.

Used to evaluate A/B growth experiments (for example two title or hook
variants). No external calls, no invented data — the caller supplies the
observed conversions and sample sizes.
"""
from __future__ import annotations

import math
from typing import Any


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def two_proportion_ztest(
    a_conversions: int, a_n: int, b_conversions: int, b_n: int
) -> dict[str, Any]:
    """Two-sided two-proportion z-test of variant B against baseline A.

    Decision rule (p < 0.05): B significantly better -> "adopt_b";
    B significantly worse -> "keep_a"; otherwise "inconclusive".
    The 95% confidence interval uses the unpooled standard error.
    """
    if a_n <= 0 or b_n <= 0:
        raise ValueError("Both variants need a sample size greater than zero.")
    if not (0 <= a_conversions <= a_n) or not (0 <= b_conversions <= b_n):
        raise ValueError("Conversions must be between 0 and the sample size.")

    p_a = a_conversions / a_n
    p_b = b_conversions / b_n
    diff = p_b - p_a

    pooled = (a_conversions + b_conversions) / (a_n + b_n)
    se_pooled = math.sqrt(pooled * (1 - pooled) * (1 / a_n + 1 / b_n))
    z = diff / se_pooled if se_pooled > 0 else 0.0
    p_value = 2.0 * (1.0 - _normal_cdf(abs(z)))
    p_value = min(max(p_value, 0.0), 1.0)

    se_unpooled = math.sqrt(p_a * (1 - p_a) / a_n + p_b * (1 - p_b) / b_n)
    margin = 1.96 * se_unpooled
    ci_low, ci_high = diff - margin, diff + margin

    significant = p_value < 0.05
    if significant and diff > 0:
        decision = "adopt_b"
    elif significant and diff < 0:
        decision = "keep_a"
    else:
        decision = "inconclusive"

    return {
        "a": {"conversions": a_conversions, "n": a_n, "rate": round(p_a, 6)},
        "b": {"conversions": b_conversions, "n": b_n, "rate": round(p_b, 6)},
        "difference": round(diff, 6),
        "z_score": round(z, 4),
        "p_value": round(p_value, 6),
        "significant_at_0_05": significant,
        "confidence_interval_95": [round(ci_low, 6), round(ci_high, 6)],
        "decision": decision,
        "method": "two-proportion z-test (pooled SE for z, unpooled SE for 95% CI)",
    }
