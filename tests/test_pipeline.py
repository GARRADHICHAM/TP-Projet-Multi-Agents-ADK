"""
Tests fonctionnels du pipeline d'investissement.
Vérifie que chaque agent produit bien une sortie non-vide et cohérente.

Usage:
    python -m tests.test_pipeline
"""

import asyncio
import json
import re
import sys
import os
from pathlib import Path

# ── Load .env BEFORE any ADK import so Ollama is used instead of Gemini ───────
def _load_env():
    env_path = Path(__file__).parent.parent / "investment_agent" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())
        print(f"✅ .env chargé : {env_path}")
    else:
        print(f"⚠️  .env introuvable : {env_path}")

_load_env()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from investment_agent.agent import root_agent

APP_NAME = "investment_platform_test"

# ── Colours for terminal output ────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

passed = 0
failed = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  {GREEN}✅ PASS{RESET} — {msg}")


def fail(msg):
    global failed
    failed += 1
    print(f"  {RED}❌ FAIL{RESET} — {msg}")


def warn(msg):
    print(f"  {YELLOW}⚠️  WARN{RESET} — {msg}")


# ══════════════════════════════════════════════════════════════════════════════
# HELPER — parse JSON robustement (nettoie backticks markdown)
# ══════════════════════════════════════════════════════════════════════════════

def _parse_json(raw: str) -> dict:
    """Nettoie et parse un JSON potentiellement entouré de backticks markdown."""
    if not raw:
        return {}
    try:
        clean = raw.strip()
        clean = re.sub(r'^```json\s*', '', clean, flags=re.MULTILINE)
        clean = re.sub(r'^```\s*',     '', clean, flags=re.MULTILINE)
        clean = re.sub(r'\s*```$',     '', clean, flags=re.MULTILINE)
        # Extraire le premier objet JSON si du texte parasite précède
        match = re.search(r'\{.*\}', clean, re.DOTALL)
        if match:
            clean = match.group(0)
        return json.loads(clean)
    except (json.JSONDecodeError, AttributeError):
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# UNIT TESTS — Tools work independently
# ══════════════════════════════════════════════════════════════════════════════

def test_tools():
    print(f"\n{BOLD}{BLUE}═══ TEST 1 : Tools unitaires ═══{RESET}")

    from investment_agent.tools import (
        get_market_data, get_technical_indicators,
        get_news_sentiment, get_economic_indicators,
        calculate_portfolio_allocation, assess_risk_score,
    )

    # get_market_data
    try:
        r = get_market_data("AAPL")
        assert "price_usd" in r and r["price_usd"] > 0
        assert "symbol" in r and r["symbol"] == "AAPL"
        ok(f"get_market_data('AAPL') → price=${r['price_usd']}, change={r['change_24h_pct']}%")
    except Exception as e:
        fail(f"get_market_data: {e}")

    # get_technical_indicators
    try:
        r = get_technical_indicators("BTC")
        assert 0 <= r["RSI_14"] <= 100
        assert r["overall_signal"] in ["BUY", "SELL", "HOLD"]
        ok(f"get_technical_indicators('BTC') → RSI={r['RSI_14']}, signal={r['overall_signal']}")
    except Exception as e:
        fail(f"get_technical_indicators: {e}")

    # get_news_sentiment
    try:
        r = get_news_sentiment("NVDA")
        assert r["overall_sentiment"] in ["POSITIVE", "NEGATIVE", "NEUTRAL"]
        assert -1 <= r["sentiment_score"] <= 1
        ok(f"get_news_sentiment('NVDA') → {r['overall_sentiment']} (score={r['sentiment_score']})")
    except Exception as e:
        fail(f"get_news_sentiment: {e}")

    # get_economic_indicators
    try:
        r = get_economic_indicators()
        assert "vix" in r and r["vix"] > 0
        assert "market_regime" in r
        ok(f"get_economic_indicators() → VIX={r['vix']}, regime={r['market_regime']}")
    except Exception as e:
        fail(f"get_economic_indicators: {e}")

    # calculate_portfolio_allocation
    for profile in ["CONSERVATIVE", "MODERATE", "AGGRESSIVE"]:
        try:
            r = calculate_portfolio_allocation(profile, "BALANCED", 100_000)
            total = sum(v["percentage_pct"] for v in r["allocations"].values())
            assert abs(total - 100) < 0.1, f"Allocations don't sum to 100%: {total}"
            assert r["total_capital_usd"] == 100_000
            ok(f"calculate_portfolio_allocation('{profile}') → total={total}%, return={r['expected_annual_return']}")
        except Exception as e:
            fail(f"calculate_portfolio_allocation({profile}): {e}")

    # assess_risk_score
    for sentiment in ["BULLISH", "BEARISH", "NEUTRAL", "MIXED"]:
        try:
            r = assess_risk_score(30, sentiment, 3)
            assert 0 <= r["risk_score"] <= 100
            assert r["risk_level"] in ["LOW", "MODERATE", "HIGH", "VERY_HIGH"]
            ok(f"assess_risk_score(sentiment='{sentiment}') → score={r['risk_score']}, level={r['risk_level']}")
        except Exception as e:
            fail(f"assess_risk_score({sentiment}): {e}")

    # Edge cases
    try:
        get_market_data("")
        fail("get_market_data('') should raise ValueError")
    except ValueError:
        ok("get_market_data('') raises ValueError as expected")

    try:
        assess_risk_score(-5, "NEUTRAL", 2)
        fail("assess_risk_score(-5, ...) should raise ValueError")
    except ValueError:
        ok("assess_risk_score(volatility=-5) raises ValueError as expected")


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRATION TEST — Full pipeline via ADK runner
# ══════════════════════════════════════════════════════════════════════════════

async def test_pipeline(query: str, expected_symbols: list[str]):
    print(f"\n{BOLD}{BLUE}═══ TEST 2 : Pipeline complet ═══{RESET}")
    print(f"  Query: \"{query}\"")

    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id="test_user",
    )

    session.state["user_message"] = query.upper()

    message = types.Content(role="user", parts=[types.Part(text=query)])
    response_text = ""
    events_seen = []

    try:
        async for event in runner.run_async(
            user_id="test_user",
            session_id=session.id,
            new_message=message,
        ):
            events_seen.append(event)
            if event.is_final_response() and event.content and event.content.parts:
                for part in event.content.parts:
                    if getattr(part, "text", None):
                        response_text += part.text
    except Exception as e:
        fail(f"Pipeline crashed: {e}")
        return None

    final_session = await session_service.get_session(
        app_name=APP_NAME,
        user_id="test_user",
        session_id=session.id,
    )
    state = final_session.state if final_session else {}

    return response_text, state, events_seen


def check_pipeline_results(response_text, state, events_seen, expected_symbols):
    """Validate pipeline outputs."""

    # ── Agents executés ────────────────────────────────────────────────────────
    agents_run = state.get("agents_executed", 0)
    if agents_run >= 4:
        ok(f"{agents_run} agents executed")
    else:
        fail(f"Only {agents_run} agents ran (expected ≥ 4)")

    # ── State keys peuplés ─────────────────────────────────────────────────────
    for key in ["market_analysis", "news_impact", "risk_assessment", "portfolio_decision"]:
        val = state.get(key, "")
        if val and len(str(val)) > 50:
            ok(f"state['{key}'] populated ({len(str(val))} chars)")
        else:
            fail(f"state['{key}'] missing or too short: '{str(val)[:50]}'")

    # ── Données pré-chargées (JSON valide) ─────────────────────────────────────
    for key in ["prefetched_market", "prefetched_news", "prefetched_risk", "prefetched_allocation"]:
        val = state.get(key, "")
        if val:
            try:
                json.loads(val)
                ok(f"state['{key}'] is valid JSON")
            except Exception:
                warn(f"state['{key}'] is not valid JSON")
        else:
            fail(f"state['{key}'] missing — tool was not called in callback")

    # ── FIX : Symboles détectés via intent_data ────────────────────────────────
    detected = []

    # Source 1 : lire intent_data directement dans le state (source principale)
    intent_raw = state.get("intent_data", "")
    if intent_raw:
        data = _parse_json(intent_raw)
        detected = data.get("requested_symbols", [])

    # Source 2 : fallback — chercher dans l'audit trail si intent_data absent
    if not detected:
        for entry in state.get("audit_trail", []):
            entry_str = str(entry)
            if "requested_symbols" in entry_str:
                data = _parse_json(entry_str)
                if not data:
                    # Tenter d'extraire le JSON embarqué dans la string d'audit
                    match = re.search(r'\{.*"requested_symbols".*\}', entry_str, re.DOTALL)
                    if match:
                        data = _parse_json(match.group(0))
                detected = data.get("requested_symbols", [])
                if detected:
                    break

    # Vérification
    if detected:
        ok(f"Symbols detected from IntentAgent: {detected}")
        for sym in expected_symbols:
            if sym in detected:
                ok(f"  → '{sym}' correctly identified")
            else:
                warn(f"  → '{sym}' not detected (found: {detected})")
    else:
        fail("No symbols detected in state['intent_data'] or audit trail")

    # ── Capital détecté ────────────────────────────────────────────────────────
    intent_raw = state.get("intent_data", "")
    if intent_raw:
        data = _parse_json(intent_raw)
        capital = data.get("user_capital")
        if capital:
            ok(f"Capital detected: ${capital:,.0f}")
        else:
            warn("Capital not found in intent_data")

    # ── Risk profile détecté ───────────────────────────────────────────────────
    if intent_raw:
        data = _parse_json(intent_raw)
        profile = data.get("risk_profile")
        if profile in ("CONSERVATIVE", "MODERATE", "AGGRESSIVE"):
            ok(f"Risk profile detected: {profile}")
        else:
            warn(f"Risk profile unexpected: {profile}")

    # ── Audit trail ────────────────────────────────────────────────────────────
    trail = state.get("audit_trail", [])
    if len(trail) >= 3:
        ok(f"Audit trail has {len(trail)} entries")
        for entry in trail:
            print(f"     {BLUE}•{RESET} {str(entry)[:120]}")
    else:
        warn(f"Audit trail short: {trail}")

    # ── Réponse finale ─────────────────────────────────────────────────────────
    if response_text and len(response_text) > 100:
        ok(f"Final response received ({len(response_text)} chars)")
        print(f"\n  {BOLD}Preview:{RESET}")
        print("  " + response_text[:300].replace("\n", "\n  ") + "...")
    else:
        fail(f"Final response empty or too short: '{response_text[:100]}'")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def run_all():
    print(f"\n{BOLD}{'═'*60}")
    print("  TESTS — Plateforme d'investissement ADK")
    print(f"{'═'*60}{RESET}")

    # Test 1 — Tools unitaires
    test_tools()

    # Test 2 — Pipeline complet
    query = "Analyse AAPL, NVDA et BTC pour un portefeuille de $100,000."
    result = await test_pipeline(query, ["AAPL", "NVDA", "BTC"])
    if result:
        response_text, state, events = result
        check_pipeline_results(response_text, state, events, ["AAPL", "NVDA", "BTC"])

    # Résumé
    print(f"\n{BOLD}{'═'*60}")
    total = passed + failed
    if failed == 0:
        print(f"{GREEN}  ✅ ALL {total} TESTS PASSED{RESET}")
    else:
        print(f"  {GREEN}{passed} passed{RESET} / {RED}{failed} failed{RESET} / {total} total")
    print(f"{'═'*60}{RESET}\n")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all())
    sys.exit(0 if success else 1)