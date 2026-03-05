"""
News sentiment and macroeconomic indicator tools.
Uses simulated data to demonstrate news impact analysis.
"""

import random
from datetime import datetime
from typing import Any


_HEADLINE_TEMPLATES: dict[str, list[str]] = {
    "positive": [
        "{topic} beats quarterly earnings estimates by 12%, raising annual guidance.",
        "Institutional investors accumulate {topic} amid bullish outlook.",
        "{topic} announces strategic partnership expected to boost revenue 20%.",
        "Analysts upgrade {topic} to 'Strong Buy' with a raised price target.",
        "{topic} captures new market share in high-growth segment.",
    ],
    "negative": [
        "{topic} misses revenue expectations; CEO cites macro headwinds.",
        "Regulatory probe into {topic} widens across three jurisdictions.",
        "Short-sellers publish report questioning {topic} accounting practices.",
        "{topic} loses key contract, shares under pressure.",
        "Supply chain disruptions hit {topic} production outlook.",
    ],
    "neutral": [
        "{topic} maintains full-year outlook despite mixed Q3 results.",
        "Board approves share buyback program for {topic}.",
        "{topic} appoints new CFO as part of strategic realignment.",
        "Analysts split on {topic} after in-line earnings release.",
    ],
}


def get_news_sentiment(topic: str) -> dict[str, Any]:
    """
    Analyze recent news sentiment for a given stock, crypto, or market topic.

    Args:
        topic: Company name, ticker symbol, or market theme (e.g. 'AAPL', 'crypto').

    Returns:
        A dict with overall sentiment, sentiment score (-1 to 1), confidence,
        key headlines, article count, market impact level, and upcoming risk events.

    Raises:
        ValueError: If topic is an empty string.
    """
    if not topic or not topic.strip():
        raise ValueError("Topic must be a non-empty string.")

    t = topic.strip()

    category = random.choices(
        ["positive", "negative", "neutral"],
        weights=[0.40, 0.30, 0.30],
    )[0]

    score = {
        "positive": round(random.uniform(0.35, 0.90), 3),
        "negative": round(random.uniform(-0.90, -0.35), 3),
        "neutral":  round(random.uniform(-0.25, 0.25), 3),
    }[category]

    headlines = [
        h.format(topic=t)
        for h in random.sample(
            _HEADLINE_TEMPLATES[category],
            k=min(3, len(_HEADLINE_TEMPLATES[category])),
        )
    ]

    abs_score = abs(score)
    impact    = "HIGH" if abs_score > 0.65 else ("MEDIUM" if abs_score > 0.35 else "LOW")

    upcoming_events = random.sample([
        "Earnings report in 3 weeks",
        "Fed interest rate decision next week",
        "Sector rotation risk due to macro data",
        "Options expiration (large open interest)",
        "CPI data release this Friday",
        "Congressional hearing on sector regulation",
    ], k=2)

    return {
        "topic":             t,
        "overall_sentiment": category.upper(),
        "sentiment_score":   score,
        "confidence":        round(random.uniform(0.65, 0.97), 2),
        "article_count":     random.randint(8, 80),
        "headlines":         headlines,
        "market_impact":     impact,
        "social_buzz":       random.choice(["TRENDING", "ABOVE_AVERAGE", "NORMAL", "LOW"]),
        "upcoming_events":   upcoming_events,
        "timestamp":         datetime.now().isoformat(),
    }


def get_economic_indicators() -> dict[str, Any]:
    """
    Retrieve current macroeconomic indicators affecting investment decisions.

    Returns:
        A dict with inflation, interest rates, GDP growth, unemployment,
        equity valuations, volatility index, and overall market regime.
    """
    vix    = round(random.uniform(11, 38), 1)
    regime = (
        "VOLATILE"  if vix > 30 else
        "BEAR"      if vix > 22 else
        "SIDEWAYS"  if vix > 15 else
        "BULL"
    )

    gdp_growth = round(random.uniform(-0.5, 3.8), 2)
    inflation  = round(random.uniform(2.1, 6.5), 2)
    fed_rate   = round(random.uniform(4.25, 5.50), 2)
    pe_ratio   = round(random.uniform(17, 30), 1)

    market_health = "HEALTHY" if (gdp_growth > 2 and inflation < 4 and vix < 20) else (
        "STRESSED" if (inflation > 5 or vix > 28) else "MIXED"
    )

    return {
        "inflation_rate_pct":       inflation,
        "core_inflation_pct":       round(inflation * 0.85, 2),
        "fed_funds_rate_pct":       fed_rate,
        "real_rate_pct":            round(fed_rate - inflation, 2),
        "gdp_growth_pct":           gdp_growth,
        "unemployment_rate_pct":    round(random.uniform(3.4, 5.8), 1),
        "sp500_pe_ratio":           pe_ratio,
        "sp500_pe_vs_avg":          "EXPENSIVE" if pe_ratio > 25 else ("CHEAP" if pe_ratio < 18 else "FAIR"),
        "vix":                      vix,
        "vix_regime":               regime,
        "dollar_index_dxy":         round(random.uniform(98, 108), 1),
        "10y_treasury_yield_pct":   round(random.uniform(3.8, 5.2), 2),
        "yield_curve_spread_pct":   round(random.uniform(-0.6, 1.2), 2),
        "yield_curve":              "INVERTED" if random.random() < 0.3 else "NORMAL",
        "market_regime":            regime,
        "market_health":            market_health,
        "timestamp":                datetime.now().isoformat(),
    }