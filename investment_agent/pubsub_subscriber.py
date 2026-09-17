"""
pubsub_subscriber.py — Consommateur découplé des rapports MarketAnalysisAgent
=============================================================================
Processus indépendant qui écoute le topic `market-analysis-completed` et
traite chaque rapport dès qu'il est publié — sans jamais avoir été appelé
directement par MarketAnalysisAgent ni par le pipeline principal.

Représente ce que serait un vrai consommateur en aval : ici on se contente
de logger le résultat (démo), mais ça pourrait être un service d'audit, une
alerte Slack sur signal fort, un pipeline d'ingestion analytique... Le
point à retenir : ajouter/retirer ce consommateur ne touche à aucune ligne
du pipeline principal (main.py, server.py, agent.py).

Usage :
    python -m investment_agent.pubsub_subscriber

Tourne indéfiniment (écoute en streaming) jusqu'à Ctrl+C. À lancer dans un
terminal séparé pendant qu'on exécute le pipeline principal (main.py ou
server.py) dans un autre, pour observer le découplage : le pipeline répond
à l'utilisateur sans attendre ce processus, qui reçoit l'événement en
parallèle, dès qu'il est publié.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

_SUBSCRIPTION_ID = os.environ.get(
    "PUBSUB_MARKET_ANALYSIS_SUBSCRIPTION", "market-analysis-completed-sub"
)


def _handle_message(message) -> None:
    """Traite un message reçu du topic. Ici : on le journalise simplement."""
    try:
        data = json.loads(message.data.decode("utf-8"))
        preview = data.get("market_analysis", "")[:150].replace("\n", " ")
        logger.info(
            "📬 Rapport marché reçu — session=%s | requête=\"%s\"\n    Aperçu : %s…",
            data.get("session_id"),
            data.get("user_query"),
            preview,
        )
    except Exception:
        logger.exception("Message Pub/Sub illisible, acquitté quand même pour éviter une boucle.")
    finally:
        # On acquitte toujours : dans cette démo, un message qu'on ne sait
        # pas traiter ne doit pas rester indéfiniment en attente de retry.
        message.ack()


def main() -> None:
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        print("GOOGLE_CLOUD_PROJECT doit être défini.", file=sys.stderr)
        sys.exit(1)

    from google.cloud import pubsub_v1

    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(project_id, _SUBSCRIPTION_ID)

    logger.info("🔊 En écoute sur %s (Ctrl+C pour arrêter)...", subscription_path)
    streaming_pull_future = subscriber.subscribe(subscription_path, callback=_handle_message)

    try:
        streaming_pull_future.result()
    except KeyboardInterrupt:
        streaming_pull_future.cancel()
        streaming_pull_future.result()
        logger.info("Arrêté.")


if __name__ == "__main__":
    main()
