"""
Portfolio management tools: risk scoring and capital allocation.
"""

from typing import Any


_ALLOCATIONS: dict[str, dict[str, dict[str, float]]] = {
    "CONSERVATIVE": {
        "SHORT_TERM": {"stocks": 20, "bonds": 50, "cash": 20, "alternatives": 10},
        "LONG_TERM":  {"stocks": 40, "bonds": 40, "cash": 10, "alternatives": 10},
        "BALANCED":   {"stocks": 30, "bonds": 45, "cash": 15, "alternatives": 10},
    },
    "MODERATE": {
        "SHORT_TERM": {"stocks": 40, "bonds": 30, "cash": 20, "alternatives": 10},
        "LONG_TERM":  {"stocks": 65, "bonds": 20, "cash":  5, "alternatives": 10},
        "BALANCED":   {"stocks": 55, "bonds": 25, "cash": 10, "alternatives": 10},
    },
    "AGGRESSIVE": {
        "SHORT_TERM": {"stocks": 60, "bonds": 15, "cash": 15, "alternatives": 10},
        "LONG_TERM":  {"stocks": 85, "bonds":  5, "cash":  0, "alternatives": 10},
        "BALANCED":   {"stocks": 70, "bonds": 10, "cash":  5, "alternatives": 15},
    },
}

_EXPECTED_RETURNS: dict[str, str] = {
    "CONSERVATIVE": "4 – 6 %",
    "MODERATE":     "7 – 10 %",
    "AGGRESSIVE":   "10 – 15 %",
}

_MAX_DRAWDOWN: dict[str, str] = {
    "CONSERVATIVE": "10 – 15 %",
    "MODERATE":     "20 – 30 %",
    "AGGRESSIVE":   "35 – 50 %",
}


def calculate_portfolio_allocation(
    risk_profile: str,
    strategy: str,
    available_capital: float,
) -> dict[str, Any]:
    """
    Calculate optimal portfolio allocation based on risk profile and strategy.

    Args:
        risk_profile: Investor's risk tolerance — 'CONSERVATIVE', 'MODERATE',
                      or 'AGGRESSIVE'.
        strategy: Investment horizon — 'SHORT_TERM', 'LONG_TERM', or 'BALANCED'.
        available_capital: Total capital to invest in USD (must be positive).

    Returns:
        A dict with asset-class breakdown (percentage + USD amount), rebalancing
        frequency, expected annual return range, and max historical drawdown estimate.

    Raises:
        ValueError: If available_capital is not positive.
    """
    if available_capital <= 0:
        raise ValueError("available_capital must be a positive number.")

    profile = risk_profile.strip().upper()
    strat   = strategy.strip().upper()

    if profile not in _ALLOCATIONS:
        profile = "MODERATE"
    if strat not in _ALLOCATIONS[profile]:
        strat = "BALANCED"

    pct_map = _ALLOCATIONS[profile][strat]

    allocation_detail = {
        asset: {
            "percentage_pct": pct,
            "amount_usd":     round(available_capital * pct / 100, 2),
        }
        for asset, pct in pct_map.items()
    }

    return {
        "risk_profile":           profile,
        "strategy":               strat,
        "total_capital_usd":      available_capital,
        "allocations":            allocation_detail,
        "rebalancing_frequency":  "MONTHLY" if strat == "SHORT_TERM" else "QUARTERLY",
        "expected_annual_return": _EXPECTED_RETURNS[profile],
        "max_drawdown_estimate":  _MAX_DRAWDOWN[profile],
        "sharpe_ratio_estimate":  {
            "CONSERVATIVE": "0.8",
            "MODERATE":     "1.1",
            "AGGRESSIVE":   "0.9",
        }[profile],
    }


def assess_risk_score(
    volatility_pct: float,
    market_sentiment: str,
    num_assets: int,
) -> dict[str, Any]:
    """
    Calculate a composite investment risk score.

    Args:
        volatility_pct: Annualised volatility as a percentage (0–100).
        market_sentiment: Current sentiment — 'BULLISH', 'BEARISH', 'NEUTRAL', 'MIXED'.
        num_assets: Number of distinct assets in the portfolio (≥ 1).

    Returns:
        A dict with risk score (0–100), risk level, component breakdown,
        and concrete risk-mitigation recommendations.

    Raises:
        ValueError: If volatility_pct is outside [0, 100] or num_assets < 1.
    """
    if not (0 <= volatility_pct <= 100):
        raise ValueError("volatility_pct must be between 0 and 100.")
    if num_assets < 1:
        raise ValueError("num_assets must be at least 1.")

    vol_score   = min(volatility_pct / 100 * 40, 40)
    sent_scores = {"BEARISH": 30, "MIXED": 20, "NEUTRAL": 12, "BULLISH": 5}
    sent_score  = sent_scores.get(market_sentiment.strip().upper(), 15)
    div_score   = max(0.0, 30 - num_assets * 1.8)

    total = round(vol_score + sent_score + div_score, 1)

    level = (
        "VERY_HIGH" if total >= 70 else
        "HIGH"      if total >= 50 else
        "MODERATE"  if total >= 30 else
        "LOW"
    )

    recommendations: dict[str, list[str]] = {
        "VERY_HIGH": [
            "Reduce position sizes to ≤ 2 % per asset.",
            "Raise cash allocation to at least 25 %.",
            "Add put options or inverse ETFs as hedges.",
            "Pause new entries until VIX < 25.",
        ],
        "HIGH": [
            "Diversify into at least 15 uncorrelated assets.",
            "Set hard stop-losses at 7–10 % below entry.",
            "Reduce crypto / small-cap exposure.",
            "Increase bond allocation by 10–15 pp.",
        ],
        "MODERATE": [
            "Maintain current strategy with monthly rebalancing.",
            "Monitor key risk indicators weekly.",
            "Consider adding a 5 % gold allocation as hedge.",
        ],
        "LOW": [
            "Consider increasing equity exposure for higher returns.",
            "Explore growth-oriented themes (AI, clean energy).",
            "Optimise tax-loss harvesting opportunities.",
        ],
    }

    return {
        "risk_score": total,
        "risk_level": level,
        "components": {
            "volatility_contribution_pct":      round(vol_score, 1),
            "sentiment_contribution_pct":       round(sent_score, 1),
            "diversification_contribution_pct": round(div_score, 1),
        },
        "input_summary": {
            "volatility_pct": volatility_pct,
            "sentiment":      market_sentiment.upper(),
            "assets_held":    num_assets,
        },
        "recommendations":                   recommendations[level],
        "suggested_max_position_size_pct":   max(1, round(10 - total / 15, 1)),
    }