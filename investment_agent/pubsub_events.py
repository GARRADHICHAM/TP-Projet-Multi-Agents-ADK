"""
pubsub_events.py — Découplage de la communication entre agents via Pub/Sub
=============================================================================
Publie un événement Pub/Sub quand MarketAnalysisAgent termine son rapport,
au lieu que ce résultat ne soit consommé que par un appel direct de fonction
dans le pipeline.

Pourquoi découpler ici, et pas ailleurs dans le pipeline :
  - MarketAnalysisAgent n'a aucune idée de qui consomme son résultat, ni de
    combien de consommateurs il y a : zéro aujourd'hui (démo), demain un
    service d'audit/conformité, une alerte sur signal fort, un pipeline
    d'entraînement ML... Ajouter un consommateur ne nécessite aucun
    changement ici ni dans le reste du pipeline — c'est tout l'intérêt du
    découplage par messages face à un couplage direct par appel de fonction.
  - Le consommateur (investment_agent/pubsub_subscriber.py) tourne comme un
    processus totalement séparé, avec son propre cycle de vie/scaling,
    indépendant du service API principal.
  - C'est un choix délibérément différent du reste du pipeline :
    AnalysisPipeline (SequentialAgent) reste un enchaînement direct et
    bloquant, parce que le rapport final doit être renvoyé au même
    utilisateur, dans la même requête HTTP — rien à découpler là. Pub/Sub
    est adapté à ce qui PEUT être asynchrone et fire-and-forget (ici : la
    notification qu'un rapport marché est prêt), pas à ce qui doit
    produire une réponse synchrone.

Comme Secret Manager et BigQuery : publication best effort, ne doit jamais
faire échouer le pipeline principal si Pub/Sub est indisponible.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_TOPIC_ID = os.environ.get("PUBSUB_MARKET_ANALYSIS_TOPIC", "market-analysis-completed")


def publish_market_analysis(session_id: str, user_query: str, market_analysis: str) -> None:
    """Publie le rapport de MarketAnalysisAgent sur Pub/Sub (best effort)."""
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        logger.info("GOOGLE_CLOUD_PROJECT absent — publication Pub/Sub ignorée.")
        return

    try:
        from google.cloud import pubsub_v1

        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(project_id, _TOPIC_ID)

        payload = json.dumps(
            {
                "session_id": session_id,
                "user_query": user_query,
                "market_analysis": market_analysis,
            },
            ensure_ascii=False,
        ).encode("utf-8")

        # Attributs de message : filtrables côté abonnement sans désérialiser
        # le payload (ex: un abonnement pourrait ne s'intéresser qu'à
        # agent_source=MarketAnalysisAgent parmi plusieurs types d'événements
        # publiés sur le même topic).
        future = publisher.publish(topic_path, payload, agent_source="MarketAnalysisAgent")
        message_id = future.result(timeout=5)
        logger.info(
            "✅ Événement publié sur Pub/Sub (%s), message_id=%s", topic_path, message_id
        )
    except Exception as exc:  # noqa: BLE001 — best effort, ne jamais propager
        logger.warning("⚠️ Publication Pub/Sub impossible (%s) — événement non émis.", exc)
