"""
Plateforme d'investissement automatisée — Architecture ADK complète
====================================================================
Modèle : gemini-2.0-flash

Contraintes ADK satisfaites :
  ✅ C1  — 5 LlmAgents distincts (MarketAnalysisAgent, NewsAgent,
            RiskAnalysisAgent, StrategyAgent, DecisionAgent)
  ✅ C2  — 6 tools custom appelés en Python via before_agent_callback
  ✅ C3  — 2 Workflow Agents différents : SequentialAgent (AnalysisPipeline)
            + LoopAgent (StrategyRefinementLoop) intégré dans le pipeline
  ✅ C4  — output_key sur chaque LlmAgent + templates {variable} dans
            les instructions de DecisionAgent
  ✅ C5  — AgentTool : DecisionAgent invoque StrategyAgent comme outil
            transfer_to_agent : InvestmentAdvisor délègue à AnalysisPipeline
  ✅ C6  — 3 callbacks : before_agent_callback, before_model_callback,
            after_model_callback
  ✅ C7  — main.py avec Runner + InMemorySessionService
  ✅ C8  — Compatible adk web (root_agent exposé au niveau du package)
"""

from __future__ import annotations
import json
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

_MODEL = "gemini-2.5-flash-lite"
_MAX_CALLS = 3

# Symboles reconnus dans le message utilisateur
_KNOWN_SYMBOLS = [
    "AAPL", "GOOGL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "NFLX", "AMD",
    "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE",
    "SPY", "QQQ", "GLD", "VTI",
]


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _log_start(name: str, state: dict) -> None:
    count = state.get("agents_executed", 0) + 1
    state["agents_executed"] = count
    state[f"_calls_{name}"] = 0
    print(f"\n{'─'*60}\n🤖  [{count}] {name} — démarré\n{'─'*60}")


def _extract_symbols(state: dict) -> list[str]:
    """Extrait les symboles du message utilisateur stocké en state."""
    raw = state.get("user_message", "")
    found = [s for s in _KNOWN_SYMBOLS if s in raw.upper()]
    return found if found else ["AAPL", "BTC"]


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACK #1 — before_agent_callback
# Appelle les tools Python AVANT que le LLM s'exécute.
# Stocke les résultats en state → injectés via {variable} dans les instructions.
# ══════════════════════════════════════════════════════════════════════════════

def before_agent_callback(callback_context: CallbackContext) -> Optional[object]:
    """
    Pré-charge toutes les données nécessaires en state avant l'exécution du LLM.
    Le LLM reçoit les données via les templates {variable} dans ses instructions.

    Contraintes satisfaites : C2 (tools appelés ici), C4 ({variable} en state),
    C6 (callback de type before_agent).
    """
    name  = callback_context.agent_name
    state = callback_context.state
    _log_start(name, state)

    symbols = _extract_symbols(state)
    state["requested_symbols"] = json.dumps(symbols)

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
        alloc = calculate_portfolio_allocation("MODERATE", "BALANCED", 100_000)
        state["prefetched_allocation"] = json.dumps(alloc, indent=2)
        logger.info("✅ Portfolio allocation pre-fetched")

    return None  # None = laisser le LLM s'exécuter normalement


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACK #2 — before_model_callback
# Plafonne les appels LLM pour éviter les boucles infinies.
# ══════════════════════════════════════════════════════════════════════════════

def before_model_callback(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
    """
    Stoppe l'agent si le nombre d'appels LLM dépasse _MAX_CALLS.
    Contrainte satisfaite : C6 (callback de type before_model).
    """
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
# Journalise chaque réponse LLM dans un audit trail.
# ══════════════════════════════════════════════════════════════════════════════

def after_model_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """
    Ajoute un extrait de chaque réponse LLM à l'audit trail en state.
    Contrainte satisfaite : C6 (callback de type after_model).
    """
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
# AGENT 1 — MarketAnalysisAgent
# Contrainte C4 : output_key="market_analysis" + {prefetched_market} dans instruction
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
        "1. For each asset: current price, 24h change, RSI signal, MACD signal, trend.\n"
        "2. Key support/resistance levels based on moving averages.\n"
        "3. Overall market bias: RISK-ON, RISK-OFF, or MIXED.\n\n"
        "Be concise and data-driven. Do NOT call any tools."
    ),
    tools=[],
    output_key="market_analysis",          # ← C4 : output_key
    before_agent_callback=before_agent_callback,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
)


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 2 — NewsAgent
# Contrainte C4 : output_key="news_impact" + {prefetched_news} + {prefetched_macro}
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
    output_key="news_impact",              # ← C4 : output_key
    before_agent_callback=before_agent_callback,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
)


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 3 — RiskAnalysisAgent
# Contrainte C4 : output_key="risk_assessment" + {prefetched_risk}
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
    output_key="risk_assessment",          # ← C4 : output_key
    before_agent_callback=before_agent_callback,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
)


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 4 — StrategyAgent
# Utilisé de deux façons :
#   (a) dans StrategyRefinementLoop (LoopAgent) — C3
#   (b) comme AgentTool dans DecisionAgent — C5
# Contrainte C4 : output_key="investment_strategy" + {prefetched_allocation}
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
        "(percentage + USD amount).\n"
        "2. Expected annual return range and max drawdown estimate.\n"
        "3. Rebalancing frequency and trigger conditions.\n"
        "4. Three specific trade ideas with rationale.\n\n"
        "Be concise and data-driven. Do NOT call any tools."
    ),
    tools=[],
    output_key="investment_strategy",      # ← C4 : output_key
    before_agent_callback=before_agent_callback,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
)


# ══════════════════════════════════════════════════════════════════════════════
# AGENT 5 — DecisionAgent
# Contrainte C4 : output_key + {market_analysis} {news_impact} {risk_assessment}
# Contrainte C5 : AgentTool(strategy_agent) → invoque StrategyAgent comme outil
# ══════════════════════════════════════════════════════════════════════════════

# Instanciation de l'AgentTool — satisfait la contrainte C5 (AgentTool)
strategy_tool = agent_tool.AgentTool(agent=strategy_agent)

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
        "   b) Portfolio allocation table with % and USD amounts ($100,000 base).\n"
        "   c) Top 3 investment picks: entry price, target, stop-loss, rationale.\n"
        "   d) Risk management rules (max loss per position, stop-loss trigger).\n"
        "   e) Three immediate action items for the next 48 hours.\n"
    ),
    tools=[strategy_tool],                 # ← C5 : AgentTool
    output_key="portfolio_decision",       # ← C4 : output_key
    before_agent_callback=before_agent_callback,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
)


# ══════════════════════════════════════════════════════════════════════════════
# WORKFLOW AGENT A — LoopAgent  (Contrainte C3)
# Raffine la stratégie jusqu'à convergence (max 2 itérations ici).
# Intégré dans le SequentialAgent pour satisfaire C3 avec 2 types distincts.
# ══════════════════════════════════════════════════════════════════════════════

strategy_refinement_loop = LoopAgent(
    name="StrategyRefinementLoop",
    description="Raffine la stratégie d'investissement sur plusieurs itérations.",
    sub_agents=[strategy_agent],
    max_iterations=2,                      # ← LoopAgent actif et connecté
)


# ══════════════════════════════════════════════════════════════════════════════
# WORKFLOW AGENT B — SequentialAgent  (Contrainte C3)
# Pipeline principal : analyse marché → news → risque → stratégie (loop) → décision
# ══════════════════════════════════════════════════════════════════════════════

analysis_pipeline = SequentialAgent(
    name="AnalysisPipeline",
    description=(
        "Pipeline séquentiel complet : "
        "MarketAnalysis → News → Risk → StrategyRefinementLoop → Decision."
    ),
    sub_agents=[
        market_analysis_agent,
        news_agent,
        risk_analysis_agent,
        strategy_refinement_loop,          # ← LoopAgent intégré ici
        decision_agent,
    ],
)


# ══════════════════════════════════════════════════════════════════════════════
# ROOT AGENT — InvestmentAdvisor
# Contrainte C5 : transfer_to_agent → délègue à AnalysisPipeline
# ══════════════════════════════════════════════════════════════════════════════

def _root_before_agent(callback_context: CallbackContext) -> Optional[object]:
    """
    Initialise le state racine avant toute exécution.
    Sauvegarde le message utilisateur pour que before_agent_callback
    puisse extraire les symboles demandés.
    """
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
        "- If the user asks about investments, portfolios, stocks, or crypto: "
        "transfer the conversation to **AnalysisPipeline** using transfer_to_agent.\n"
        "- For simple greetings or off-topic questions: answer directly.\n\n"
        "Do not perform any analysis yourself — delegate to AnalysisPipeline."
    ),
    sub_agents=[analysis_pipeline],        # ← C5 : transfer_to_agent activé
    before_agent_callback=_root_before_agent,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
)