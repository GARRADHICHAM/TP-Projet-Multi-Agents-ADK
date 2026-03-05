"""
main.py — Runner programmatique pour Investment Advisor
========================================================
Contrainte C7 satisfaite :
  ✅ Instancie InMemorySessionService
  ✅ Instancie Runner avec root_agent
  ✅ Exécute une session complète de façon asynchrone
  ✅ Affiche les événements et le rapport final

Usage :
    python main.py
    python main.py --query "Analyse NVDA et BTC pour un portefeuille de 50000$"

Compatible adk web :
    adk web  (le package expose root_agent dans __init__.py)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

# Import du root_agent depuis le package
from investment_agent.agent import root_agent

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────
APP_NAME    = "investment_advisor"
USER_ID     = "demo_user_001"
DEFAULT_QUERY = (
    "Analyse AAPL et BTC pour moi. "
    "Je veux investir 100 000 $ avec un profil modéré."
)


# ══════════════════════════════════════════════════════════════════════════════
# RUNNER PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

async def run_investment_analysis(user_query: str) -> dict:
    """
    Lance une analyse d'investissement complète via le pipeline multi-agents.

    Args:
        user_query: La question ou demande de l'utilisateur.

    Returns:
        Un dict contenant les rapports produits et l'audit trail.
    """
    print("\n" + "═" * 70)
    print("  💼  INVESTMENT ADVISOR — Plateforme Multi-Agents ADK")
    print("═" * 70)
    print(f"  📝  Query : {user_query}")
    print("═" * 70 + "\n")

    # ── 1. Instanciation des services (Contrainte C7) ─────────────────────────
    session_service = InMemorySessionService()

    # ── 2. Création de la session ─────────────────────────────────────────────
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        state={
            # Injection du message utilisateur dans le state initial
            # pour que before_agent_callback puisse extraire les symboles
            "user_message": user_query,
        },
    )
    logger.info("Session créée : %s", session.id)

    # ── 3. Instanciation du Runner (Contrainte C7) ────────────────────────────
    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )
    logger.info("Runner instancié avec l'agent : %s", root_agent.name)

    # ── 4. Préparation du message utilisateur ─────────────────────────────────
    user_message = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=user_query)],
    )

    # ── 5. Exécution asynchrone et collecte des événements ───────────────────
    final_response_text = ""
    events_count        = 0

    print("🚀  Démarrage du pipeline...\n")

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=user_message,
    ):
        events_count += 1

        # Affichage des événements intermédiaires
        agent_name = getattr(event, "author", "unknown")
        if hasattr(event, "content") and event.content:
            for part in event.content.parts:
                if getattr(part, "text", None):
                    preview = part.text[:100].replace("\n", " ")
                    print(f"  📡  [{agent_name}] {preview}…")

        # Capture de la réponse finale
        if event.is_final_response():
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if getattr(part, "text", None):
                        final_response_text += part.text

    # ── 6. Récupération du state final ────────────────────────────────────────
    final_session = await session_service.get_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=session.id,
    )
    final_state = final_session.state if final_session else {}

    # ── 7. Affichage du rapport final ─────────────────────────────────────────
    print("\n" + "═" * 70)
    print("  📊  RAPPORT FINAL")
    print("═" * 70)
    print(final_response_text or "(Aucune réponse finale capturée)")

    # Affichage des rapports intermédiaires si disponibles
    reports = {
        "market_analysis":    "📈 Market Analysis",
        "news_impact":        "📰 News & Macro",
        "risk_assessment":    "⚠️  Risk Assessment",
        "investment_strategy": "🎯 Investment Strategy",
        "portfolio_decision": "✅ Portfolio Decision",
    }

    print("\n" + "─" * 70)
    print("  📋  RAPPORTS PAR AGENT (depuis session state)")
    print("─" * 70)
    for key, label in reports.items():
        value = final_state.get(key, "")
        if value:
            preview = value[:200].replace("\n", " ")
            print(f"\n  {label}:\n  {preview}…")
        else:
            print(f"\n  {label}: (non disponible)")

    # Audit trail
    audit = final_state.get("audit_trail", [])
    if audit:
        print("\n" + "─" * 70)
        print(f"  🗒️   AUDIT TRAIL ({len(audit)} entrées)")
        print("─" * 70)
        for entry in audit:
            print(f"  • {entry}")

    print("\n" + "═" * 70)
    print(f"  ✅  Pipeline terminé — {events_count} événements traités")
    print("═" * 70 + "\n")

    return {
        "query":              user_query,
        "final_response":     final_response_text,
        "market_analysis":    final_state.get("market_analysis", ""),
        "news_impact":        final_state.get("news_impact", ""),
        "risk_assessment":    final_state.get("risk_assessment", ""),
        "investment_strategy": final_state.get("investment_strategy", ""),
        "portfolio_decision": final_state.get("portfolio_decision", ""),
        "audit_trail":        audit,
        "events_count":       events_count,
    }


# ══════════════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Investment Advisor — Pipeline Multi-Agents ADK"
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        default=DEFAULT_QUERY,
        help="Question ou demande d'investissement",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Fichier JSON pour sauvegarder les résultats (optionnel)",
    )
    args = parser.parse_args()

    # Lancement du pipeline asynchrone
    result = asyncio.run(run_investment_analysis(args.query))

    # Sauvegarde optionnelle des résultats
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"💾  Résultats sauvegardés dans : {args.output}")


if __name__ == "__main__":
    main()