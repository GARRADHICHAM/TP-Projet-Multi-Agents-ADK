"""
bigquery_logger.py — Persistance des résultats du pipeline dans BigQuery
==========================================================================
Écrit une ligne par rapport d'agent (Intent, Market, News, Risk, Strategy,
Decision) à la fin de chaque exécution du pipeline. Objectifs :

  - Historiser les analyses produites — aujourd'hui uniquement visibles
    dans les logs ou la réponse HTTP, perdues juste après.
  - Permettre des requêtes analytiques a posteriori en SQL sur les
    décisions prises : distribution des recommandations (INVEST/HOLD/
    AVOID), volumétrie par agent, dérive du sentiment dans le temps...
  - Démontrer un pattern d'écriture "best effort" : une panne BigQuery ne
    doit jamais faire échouer une requête utilisateur — le pipeline a déjà
    produit sa réponse, l'écriture analytique est secondaire.

Ressources GCP (déjà créées, cf. commandes plus bas) :
  Dataset : investment_pipeline (région europe-west1)
  Table   : agent_results
    timestamp     TIMESTAMP  — horodatage de l'écriture
    agent_source  STRING     — nom de l'agent ADK ayant produit le résultat
    result        STRING     — texte du rapport produit par l'agent
    metadata      STRING     — JSON encodé : session_id, requête utilisateur

Méthode d'écriture : streaming insert (tabledata.insertAll, exposé par le
SDK via `insert_rows_json`) plutôt qu'un load job. Pertinent ici car on
écrit quelques lignes à la fois, immédiatement disponibles en lecture ;
un load job serait plus adapté à un import massif par batch. Autre
différence pratique : le streaming insert ne nécessite que le rôle
bigquery.dataEditor sur le dataset, pas bigquery.jobUser (requis pour les
jobs de requête/chargement).
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_DATASET_ID = os.environ.get("BIGQUERY_DATASET", "investment_pipeline")
_TABLE_ID   = os.environ.get("BIGQUERY_TABLE", "agent_results")

# output_key du state ADK -> nom d'agent stocké dans agent_source
_AGENT_OUTPUT_KEYS = {
    "intent_data":         "IntentAgent",
    "market_analysis":     "MarketAnalysisAgent",
    "news_impact":         "NewsAgent",
    "risk_assessment":     "RiskAnalysisAgent",
    "investment_strategy": "StrategyAgent",
    "portfolio_decision":  "DecisionAgent",
}


def log_pipeline_run(
    session_id: str,
    user_query: str,
    final_state: dict[str, Any],
) -> None:
    """Écrit un résultat par agent ayant produit une sortie non vide.

    N'échoue jamais bruyamment : une exception ici est capturée et journalisée
    en warning, jamais propagée — l'utilisateur a déjà reçu sa réponse, on ne
    veut pas qu'une panne BigQuery fasse échouer la requête après coup.
    """
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        logger.info("GOOGLE_CLOUD_PROJECT absent — écriture BigQuery ignorée.")
        return

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    metadata = json.dumps(
        {"session_id": session_id, "user_query": user_query},
        ensure_ascii=False,
    )

    rows = [
        {
            "timestamp":    now,
            "agent_source": agent_name,
            "result":       str(final_state[output_key]),
            "metadata":     metadata,
        }
        for output_key, agent_name in _AGENT_OUTPUT_KEYS.items()
        if final_state.get(output_key)
    ]
    if not rows:
        logger.info("Aucun résultat d'agent à écrire dans BigQuery.")
        return

    try:
        from google.cloud import bigquery

        client = bigquery.Client(project=project_id)
        table_ref = f"{project_id}.{_DATASET_ID}.{_TABLE_ID}"
        errors = client.insert_rows_json(table_ref, rows)
        if errors:
            logger.warning("⚠️ Erreurs lors de l'écriture BigQuery : %s", errors)
        else:
            logger.info(
                "✅ %d résultat(s) écrit(s) dans BigQuery (%s).", len(rows), table_ref
            )
    except Exception as exc:  # noqa: BLE001 — best effort, ne jamais propager
        logger.warning(
            "⚠️ Écriture BigQuery impossible (%s) — résultats non persistés.", exc
        )
