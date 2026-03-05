"""
Market analysis tools providing price data and technical indicators.
Uses simulated data for demonstration purposes.
"""

import random
from datetime import datetime
from typing import Any


# Seed for reproducible results in demos
random.seed(42)

# ── Mock data ──────────────────────────────────────────────────────────────────

_BASE_PRICES: dict[str, float] = {
    "AAPL": 189.50,  "GOOGL": 175.20, "MSFT": 415.80,
    "NVDA": 875.30,  "TSLA":  248.70, "AMZN": 192.40,
    "META": 523.10,  "BTC":  67500.0, "ETH":  3800.0,
    "SOL":   165.0,  "BNB":   415.0,  "SPY":   527.0,
}


def get_market_data(symbol: str) -> dict[str, Any]:
    """
    Retrieve current market data for a given asset symbol.

    Args:
        symbol: Ticker or crypto symbol, e.g. 'AAPL', 'BTC', 'ETH'.

    Returns:
        A dict with price, 24h change, volume, market cap, 52-week range,
        and average daily volume.

    Raises:
        ValueError: If symbol is an empty string.
    """
    if not symbol or not symbol.strip():
        raise ValueError("Symbol must be a non-empty string.")

    sym = symbol.strip().upper()
    base = _BASE_PRICES.get(sym, random.uniform(50, 500))

    price       = round(base * random.uniform(0.97, 1.03), 2)
    change_pct  = round(random.uniform(-6.5, 6.5), 2)
    volume      = random.randint(500_000, 60_000_000)
    avg_volume  = int(volume * random.uniform(0.8, 1.2))

    return {
        "symbol":          sym,
        "price_usd":       price,
        "change_24h_pct":  change_pct,
        "direction":       "UP" if change_pct >= 0 else "DOWN",
        "volume":          volume,
        "avg_volume_30d":  avg_volume,
        "volume_ratio":    round(volume / avg_volume, 2),
        "market_cap_usd":  round(price * random.randint(1_000_000, 15_000_000_000), 0),
        "52w_high":        round(base * 1.40, 2),
        "52w_low":         round(base * 0.60, 2),
        "distance_from_high_pct": round((1 - price / (base * 1.40)) * 100, 1),
        "timestamp":       datetime.now().isoformat(),
    }


def get_technical_indicators(symbol: str) -> dict[str, Any]:
    """
    Compute technical indicators for a given asset symbol.

    Args:
        symbol: Ticker or crypto symbol, e.g. 'AAPL', 'BTC'.

    Returns:
        A dict containing RSI, MACD, moving averages (MA20/50/200),
        Bollinger Bands, ADX, and a composite trend signal.

    Raises:
        ValueError: If symbol is an empty string.
    """
    if not symbol or not symbol.strip():
        raise ValueError("Symbol must be a non-empty string.")

    sym  = symbol.strip().upper()
    base = _BASE_PRICES.get(sym, 200.0)

    rsi  = round(random.uniform(20, 80), 1)
    macd = round(random.uniform(-8, 8), 3)
    adx  = round(random.uniform(10, 50), 1)

    ma20  = round(base * random.uniform(0.95, 1.05), 2)
    ma50  = round(base * random.uniform(0.90, 1.10), 2)
    ma200 = round(base * random.uniform(0.80, 1.20), 2)
    price = round(base * random.uniform(0.97, 1.03), 2)

    rsi_signal   = "OVERBOUGHT" if rsi > 70 else ("OVERSOLD" if rsi < 30 else "NEUTRAL")
    macd_signal  = "BULLISH" if macd > 0 else "BEARISH"
    trend_signal = "BULLISH" if (price > ma50 > ma200) else ("BEARISH" if price < ma50 else "MIXED")
    adx_strength = "STRONG" if adx > 25 else "WEAK"

    composite_signals = [
        1 if rsi_signal == "NEUTRAL" else (-1 if rsi_signal == "OVERBOUGHT" else 0),
        1 if macd_signal == "BULLISH" else -1,
        1 if trend_signal == "BULLISH" else (-1 if trend_signal == "BEARISH" else 0),
    ]
    composite_score = round(sum(composite_signals) / 3, 2)

    return {
        "symbol":          sym,
        "current_price":   price,
        "RSI_14":          rsi,
        "RSI_signal":      rsi_signal,
        "MACD":            macd,
        "MACD_signal":     macd_signal,
        "ADX_14":          adx,
        "trend_strength":  adx_strength,
        "MA_20":           ma20,
        "MA_50":           ma50,
        "MA_200":          ma200,
        "price_vs_MA50":   "ABOVE" if price > ma50 else "BELOW",
        "price_vs_MA200":  "ABOVE" if price > ma200 else "BELOW",
        "golden_cross":    ma50 > ma200,
        "bollinger_upper": round(ma20 * 1.08, 2),
        "bollinger_lower": round(ma20 * 0.92, 2),
        "bollinger_band":  "UPPER" if price > ma20 * 1.06 else ("LOWER" if price < ma20 * 0.94 else "MIDDLE"),
        "volume_trend":    random.choice(["INCREASING", "DECREASING", "STABLE"]),
        "composite_signal": composite_score,
        "overall_signal":  "BUY" if composite_score > 0.33 else ("SELL" if composite_score < -0.33 else "HOLD"),
    }