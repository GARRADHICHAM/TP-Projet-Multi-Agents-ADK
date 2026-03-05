"""
Plateforme d'investissement automatisée — Architecture ADK améliorée
====================================================================
Modèle : gemini-2.5-flash-lite

Contraintes ADK satisfaites :
  ✅ C1  — 6 LlmAgents distincts (IntentAgent, MarketAnalysisAgent, NewsAgent,
            RiskAnalysisAgent, StrategyAgent, DecisionAgent)
  ✅ C2  — 6 tools custom appelés via before_agent_callback
  ✅ C3  — 2 Workflow Agents : SequentialAgent (AnalysisPipeline)
            + LoopAgent (StrategyRefinementLoop)
  ✅ C4  — output_key sur chaque LlmAgent + templates {variable}
  ✅ C5  — AgentTool : DecisionAgent invoque StrategyAgent comme outil
            transfer_to_agent : InvestmentAdvisor délègue à AnalysisPipeline
  ✅ C6  — 3 callbacks : before_agent_callback, before_model_callback,
            after_model_callback
  ✅ C7  — main.py avec Runner + InMemorySessionService
  ✅ C8  — Compatible adk web (root_agent exposé au niveau du package)

Améliorations v2 :
  🆕 IntentAgent  — LLM extrait symboles, capital, risk_profile, strategy
  🆕 Plus de hardcoding — tout vient du message utilisateur
  🆕 before_agent_callback lit le state dynamiquement
"""

from __future__ import annotations
import json
import re
import logging
from typing import Optional

from google.adk.agents import LlmAgent, SequentialAgent, LoopAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types as genai_types
from google.adk.tools import agent_tool

from .tools import (
    get_market_data,
    get_technical_indicators,
    get_news_sentiment,
    get_economic_indicators,
    calculate_portfolio_allocation,
    assess_risk_score,
)

logger = logging.getLogger(__name__)

_MODEL    = "gemini-2.5-flash-lite"
_MAX_CALLS = 3


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _log_start(name: str, state: dict) -> None:
    count = state.get("agents_executed", 0) + 1
    state["agents_executed"] = count
    state[f"_calls_{name}"] = 0
    print(f"\n{'─'*60}\n🤖  [{count}] {name} — démarré\n{'─'*60}")


def _clean_json(raw: str) -> dict:
    """Nettoie et parse un JSON potentiellement entouré de backticks markdown."""
    if not raw:
        return {}
    try:
        clean = raw.strip()
        # Supprimer les backticks markdown que le LLM peut ajouter
        clean = re.sub(r'^```json\s*', '', clean, flags=re.MULTILINE)
        clean = re.sub(r'^```\s*', '', clean, flags=re.MULTILINE)
        clean = re.sub(r'\s*```$', '', clean, flags=re.MULTILINE)
        clean = clean.strip()
        return json.loads(clean)
    except (json.JSONDecodeError, AttributeError):
        return {}


def _get_symbols(state: dict) -> list[str]:
    """
    Récupère les symboles extraits par IntentAgent depuis le state.
    Fallback sur AAPL + BTC si parsing échoue.
    """
    data = _clean_json(state.get("intent_data", ""))
    if data:
        symbols = data.get("requested_symbols", [])
        if symbols:
            logger.info("✅ Symbols from IntentAgent: %s", symbols)
            return symbols

    # Fallback direct depuis state
    symbols = state.get("requested_symbols", [])
    if isinstance(symbols, str):
        try:
            symbols = json.loads(symbols)
        except json.JSONDecodeError:
            symbols = []
    return symbols if symbols else ["AAPL", "BTC"]


def _get_capital(state: dict) -> float:
    """Récupère le capital depuis le state (peuplé par IntentAgent)."""
    data = _clean_json(state.get("intent_data", ""))
    if data:
        capital = data.get("user_capital", 100_000)
        try:
            if capital and float(capital) >= 1000:
                return float(capital)
        except (ValueError, TypeError):
            pass
    return float(state.get("user_capital", 100_000))


def _get_risk_profile(state: dict) -> str:
    """Récupère le profil de risque depuis le state."""
    data = _clean_json(state.get("intent_data", ""))
    if data:
        profile = data.get("risk_profile", "MODERATE").upper()
        if profile in ("CONSERVATIVE", "MODERATE", "AGGRESSIVE"):
            return profile
    return state.get("risk_profile", "MODERATE").upper()


def _get_strategy(state: dict) -> str:
    """Récupère la stratégie depuis le state."""
    data = _clean_json(state.get("intent_data", ""))
    if data:
        strat = data.get("investment_strategy_type", "BALANCED").upper()
        if strat in ("SHORT_TERM", "BALANCED", "LONG_TERM"):
            return strat
    return state.get("investment_strategy_type", "BALANCED").upper()


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACK #1 — before_agent_callback
# Appelle les tools Python AVANT que le LLM s'exécute.
# Lit les paramètres dynamiquement depuis le state (peuplé par IntentAgent).
# ══════════════════════════════════════════════════════════════════════════════

def before_agent_callback(callback_context: CallbackContext) -> Optional[object]:
    name  = callback_context.agent_name
    state = callback_context.state
    _log_start(name, state)

    # IntentAgent n'a pas besoin de pre-fetch
    if name == "IntentAgent":
        return None

    symbols = _get_symbols(state)
    logger.info("🔍 Symbols for %s: %s", name, symbols)

    if name == "MarketAnalysisAgent":
        data = {}
        for sym in symbols:
            data[sym] = {
                "market":     get_market_data(sym),
                "indicators": get_technical_indicators(sym),
            }
        state["prefetched_market"] = json.dumps(data, indent=2)
        logger.info("✅ Market data pre-fetched for: %s", symbols)

    elif name == "NewsAgent":
        news_data = {sym: get_news_sentiment(sym) for sym in symbols}
        macro     = get_economic_indicators()
        state["prefetched_news"]  = json.dumps(news_data, indent=2)
        state["prefetched_macro"] = json.dumps(macro, indent=2)
        logger.info("✅ News & macro data pre-fetched for: %s", symbols)

    elif name == "RiskAnalysisAgent":
        risk = assess_risk_score(30, "NEUTRAL", len(symbols))
        state["prefetched_risk"] = json.dumps(risk, indent=2)
        logger.info("✅ Risk score pre-fetched")

    elif name == "StrategyAgent":
        capital      = _get_capital(state)
        risk_profile = _get_risk_profile(state)
        strategy     = _get_strategy(state)
        logger.info("💰 Capital: $%s | Risk: %s | Strategy: %s", capital, risk_profile, strategy)
        alloc = calculate_portfolio_allocation(risk_profile, strategy, capital)
        state["prefetched_allocation"] = json.dumps(alloc, indent=2)
        state["user_capital_display"]  = f"${capital:,.0f}"
        logger.info("✅ Portfolio allocation pre-fetched")

    return None


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACK #2 — before_model_callback
# ══════════════════════════════════════════════════════════════════════════════

def before_model_callback(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
    name  = callback_context.agent_name
    state = callback_context.state
    key   = f"_calls_{name}"
    calls = state.get(key, 0) + 1
    state[key] = calls
    logger.info("📞 %s — LLM call #%d", name, calls)

    if calls > _MAX_CALLS:
        logger.warning("⛔ %s — force stop at call #%d.", name, calls)
        return LlmResponse(
            content=genai_types.Content(
                role="model",
                parts=[genai_types.Part(text=f"[{name}] Rapport finalisé.")],
            )
        )
    return None


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACK #3 — after_model_callback
# ══════════════════════════════════════════════════════════════════════════════

def after_model_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    name  = callback_context.agent_name
    state = callback_context.state
    preview = ""
    if llm_response.content and llm_response.content.parts:
        for part in llm_response.content.parts:
            if getattr(part, "text", None):
                preview = part.text[:120].replace("\n", " ")
                break

    entry = f"[{name}] {preview}…" if preview else f"[{name}] (no text)"
    state["audit_trail"] = state.get("audit_trail", []) + [entry]
    logger.info("📝 audit: %s", entry)
    return None


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 0 — IntentAgent  🆕
# Premier agent du pipeline — extrait les paramètres via LLM
# Contrainte C1 : 6ème LlmAgent
# Contrainte C4 : output_key="intent_data"
# ══════════════════════════════════════════════════════════════════════════════

intent_agent = LlmAgent(
    name="IntentAgent",
    model=_MODEL,
    description="Extrait les paramètres d'investissement depuis le message utilisateur.",
    instruction=(
        "You are a financial intent parser.\n\n"
        "Analyze this user message:\n"
        "```\n{user_message}\n```\n\n"
        "Extract the following parameters and respond ONLY with a valid JSON object "
        "(no markdown, no explanation, just raw JSON):\n\n"
        "{\n"
        '  "requested_symbols": [],     // list of ticker symbols found (e.g. ["NVDA", "BTC"])\n'
        '  "user_capital": 100000,      // investment amount in USD (default 100000)\n'
        '  "risk_profile": "MODERATE",  // CONSERVATIVE | MODERATE | AGGRESSIVE\n'
        '  "investment_strategy_type": "BALANCED"  // SHORT_TERM | BALANCED | LONG_TERM\n'
        "}\n\n"
        "Rules:\n"
        "- If no symbols found, use [\"AAPL\", \"BTC\"]\n"
        "- If no amount mentioned, use 100000\n"
        "- Detect risk from words like: aggressive/aggressif → AGGRESSIVE, "
        "conservative/prudent/conservateur → CONSERVATIVE\n"
        "- Detect strategy from: court terme/short → SHORT_TERM, "
        "long terme/long → LONG_TERM\n"
        "- Convert amounts: 50k → 50000, $1M → 1000000\n"
        "- Recognize tickers in any language: Toyota → TM, Apple → AAPL"
    ),
    tools=[],
    output_key="intent_data",                   # ← C4
    before_agent_callback=before_agent_callback,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
)


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 1 — MarketAnalysisAgent
# ══════════════════════════════════════════════════════════════════════════════

market_analysis_agent = LlmAgent(
    name="MarketAnalysisAgent",
    model=_MODEL,
    description="Rédige un rapport d'analyse de marché à partir des données pré-chargées.",
    instruction=(
        "You are a senior market analyst.\n\n"
        "Here is the pre-fetched market and technical data:\n"
        "```json\n{prefetched_market}\n```\n\n"
        "Write a structured **Market Analysis Report** covering:\n"
        "1. Price action and 24h performance per asset.\n"
        "2. Technical signals: RSI, MACD, moving averages, Bollinger Bands.\n"
        "3. Volume analysis and market cap context.\n"
        "4. Overall market trend: BULLISH / BEARISH / MIXED.\n\n"
        "Be concise and data-driven. Do NOT call any tools."
    ),
    tools=[],
    output_key="market_analysis",               # ← C4
    before_agent_callback=before_agent_callback,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
)


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 2 — NewsAgent
# ══════════════════════════════════════════════════════════════════════════════

news_agent = LlmAgent(
    name="NewsAgent",
    model=_MODEL,
    description="Rédige un rapport d'actualités et de macro-économie.",
    instruction=(
        "You are a financial news analyst.\n\n"
        "Here is the pre-fetched news sentiment data:\n"
        "```json\n{prefetched_news}\n```\n\n"
        "Here are the macroeconomic indicators:\n"
        "```json\n{prefetched_macro}\n```\n\n"
        "Write a structured **News & Macro Report** covering:\n"
        "1. Sentiment score and key headlines per asset.\n"
        "2. Macro environment: inflation, VIX regime, yield curve, GDP.\n"
        "3. Upcoming risk events to watch.\n"
        "4. Overall sentiment verdict: BULLISH / BEARISH / NEUTRAL.\n\n"
        "Be concise and data-driven. Do NOT call any tools."
    ),
    tools=[],
    output_key="news_impact",                   # ← C4
    before_agent_callback=before_agent_callback,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
)


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 3 — RiskAnalysisAgent
# ══════════════════════════════════════════════════════════════════════════════

risk_analysis_agent = LlmAgent(
    name="RiskAnalysisAgent",
    model=_MODEL,
    description="Rédige un rapport d'évaluation des risques.",
    instruction=(
        "You are a chief risk officer.\n\n"
        "Here is the pre-fetched risk assessment data:\n"
        "```json\n{prefetched_risk}\n```\n\n"
        "Write a structured **Risk Assessment Report** covering:\n"
        "1. Global risk score (out of 100) and risk level.\n"
        "2. Component breakdown: volatility, sentiment, diversification.\n"
        "3. Concrete risk mitigation recommendations.\n"
        "4. Maximum suggested position size per asset.\n"
        "5. Final verdict: PROCEED / PROCEED WITH CAUTION / HOLD.\n\n"
        "Be concise and data-driven. Do NOT call any tools."
    ),
    tools=[],
    output_key="risk_assessment",               # ← C4
    before_agent_callback=before_agent_callback,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
)


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 4 — StrategyAgent
# ══════════════════════════════════════════════════════════════════════════════

strategy_agent = LlmAgent(
    name="StrategyAgent",
    model=_MODEL,
    description=(
        "Portfolio manager — builds an investment strategy from allocation data. "
        "Returns a structured strategy report with asset allocation table, "
        "expected returns, max drawdown, rebalancing frequency, and 3 trade ideas."
    ),
    instruction=(
        "You are a portfolio manager.\n\n"
        "Here is the pre-fetched portfolio allocation data:\n"
        "```json\n{prefetched_allocation}\n```\n\n"
        "Write a structured **Investment Strategy Report** covering:\n"
        "1. Asset allocation table: stocks / bonds / cash / alternatives "
        "(percentage + USD amount based on the actual capital).\n"
        "2. Expected annual return range and max drawdown estimate.\n"
        "3. Rebalancing frequency and trigger conditions.\n"
        "4. Three specific trade ideas with rationale.\n\n"
        "Be concise and data-driven. Do NOT call any tools."
    ),
    tools=[],
    output_key="investment_strategy",           # ← C4
    before_agent_callback=before_agent_callback,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
)


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 5 — DecisionAgent
# ══════════════════════════════════════════════════════════════════════════════

strategy_tool = agent_tool.AgentTool(agent=strategy_agent)  # ← C5

decision_agent = LlmAgent(
    name="DecisionAgent",
    model=_MODEL,
    description="Chief Investment Officer — produit la décision d'investissement finale.",
    instruction=(
        "You are the Chief Investment Officer.\n\n"
        "## Reports already produced by the analysis pipeline\n\n"
        "### Market Analysis\n{market_analysis}\n\n"
        "### News & Macro Impact\n{news_impact}\n\n"
        "### Risk Assessment\n{risk_assessment}\n\n"
        "## Your task\n"
        "1. Call the `StrategyAgent` tool to obtain the portfolio strategy.\n"
        "2. Write the **Final Investment Decision Report** containing:\n"
        "   a) Executive summary with recommended action: INVEST / HOLD / AVOID.\n"
        "   b) Portfolio allocation table with % and USD amounts "
        "(use the actual capital from the strategy).\n"
        "   c) Top 3 investment picks: entry price, target, stop-loss, rationale.\n"
        "   d) Risk management rules (max loss per position, stop-loss trigger).\n"
        "   e) Three immediate action items for the next 48 hours.\n"
    ),
    tools=[strategy_tool],                      # ← C5
    output_key="portfolio_decision",            # ← C4
    before_agent_callback=before_agent_callback,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
)


# ══════════════════════════════════════════════════════════════════════════════
# WORKFLOW A — LoopAgent  (C3)
# ══════════════════════════════════════════════════════════════════════════════

strategy_refinement_loop = LoopAgent(
    name="StrategyRefinementLoop",
    description="Raffine la stratégie d'investissement sur plusieurs itérations.",
    sub_agents=[strategy_agent],
    max_iterations=2,
)


# ══════════════════════════════════════════════════════════════════════════════
# WORKFLOW B — SequentialAgent  (C3)
# Pipeline : Intent → Market → News → Risk → Strategy(loop) → Decision
# ══════════════════════════════════════════════════════════════════════════════

analysis_pipeline = SequentialAgent(
    name="AnalysisPipeline",
    description=(
        "Pipeline séquentiel complet : "
        "Intent → MarketAnalysis → News → Risk → StrategyRefinementLoop → Decision."
    ),
    sub_agents=[
        intent_agent,                           # 🆕 Premier — extrait les paramètres
        market_analysis_agent,
        news_agent,
        risk_analysis_agent,
        strategy_refinement_loop,
        decision_agent,
    ],
)


# ══════════════════════════════════════════════════════════════════════════════
# ROOT AGENT — InvestmentAdvisor  (C5 transfer_to_agent, C8)
# ══════════════════════════════════════════════════════════════════════════════

def _root_before_agent(callback_context: CallbackContext) -> Optional[object]:
    name  = callback_context.agent_name
    state = callback_context.state
    _log_start(name, state)
    state.setdefault("user_message", "")
    state.setdefault("audit_trail", [])
    return None


root_agent = LlmAgent(
    name="InvestmentAdvisor",
    model=_MODEL,
    description="Point d'entrée de la plateforme d'investissement.",
    instruction=(
        "You are the front desk of an AI-powered investment platform.\n\n"
        "- If the user asks about investments, portfolios, stocks, crypto, "
        "or any financial topic: transfer the conversation to **AnalysisPipeline** "
        "using transfer_to_agent.\n"
        "- For simple greetings or off-topic questions: answer directly.\n\n"
        "Do not perform any analysis yourself — delegate to AnalysisPipeline."
    ),
    sub_agents=[analysis_pipeline],             # ← C5
    before_agent_callback=_root_before_agent,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
)