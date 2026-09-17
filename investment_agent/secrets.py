"""
secrets.py — Chargement de GOOGLE_API_KEY depuis Google Secret Manager
========================================================================
Remplace l'injection de la clé via une variable d'environnement statique
(Cloud Run --set-secrets, ou un fichier .env commité par erreur) par un
appel explicite à l'API Secret Manager au démarrage du process.

Pourquoi Secret Manager plutôt qu'une variable d'environnement "en dur" :
  - Rotation : changer la valeur du secret ne nécessite pas de redéployer
    le service (contrairement à --set-env-vars) ; il suffit de créer une
    nouvelle version du secret dans Secret Manager.
  - Audit : chaque accès au secret est journalisé (Cloud Audit Logs), ce
    qui n'est pas le cas d'une variable d'environnement.
  - Permissions fines : l'accès est accordé secret par secret via IAM
    (roles/secretmanager.secretAccessor), pas au niveau du projet entier.
  - Historique : les versions précédentes du secret restent consultables
    (rollback possible), ce qu'un simple `--set-env-vars` ne permet pas.

Authentification : comme pour Vertex AI, aucune clé à gérer ici — le
client Secret Manager s'authentifie via les Application Default
Credentials (ADC) : le compte de service d'exécution sur Cloud Run,
ou `gcloud auth application-default login` en local.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def load_api_key(
    secret_id: str = "GOOGLE_API_KEY",
    env_var: str = "GOOGLE_API_KEY",
) -> None:
    """Charge `env_var` dans os.environ depuis Secret Manager, si nécessaire.

    Comportement :
      1. Si `env_var` est déjà présent dans l'environnement (ex: posé par
         `load_dotenv()` en dev local via investment_agent/.env), on ne
         fait rien — ça évite un appel réseau inutile et permet de
         continuer à développer sans accès GCP.
      2. Sinon, si GOOGLE_CLOUD_PROJECT est défini (c'est le cas sur Cloud
         Run, où cette variable est déjà positionnée), on interroge Secret
         Manager pour la dernière version du secret `secret_id` et on la
         place dans os.environ[env_var].
      3. En cas d'échec (API indisponible, permission manquante, secret
         inexistant), on logue un avertissement et on laisse la main au
         reste du code — qui échouera avec une erreur claire ("No API key
         was provided") plutôt qu'un crash opaque ici.

    Args:
        secret_id: Nom du secret dans Secret Manager.
        env_var: Variable d'environnement à peupler avec sa valeur.
    """
    if os.environ.get(env_var):
        logger.debug("%s déjà présent dans l'environnement — Secret Manager ignoré.", env_var)
        return

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        logger.info(
            "GOOGLE_CLOUD_PROJECT absent — impossible d'interroger Secret "
            "Manager pour '%s'.", secret_id,
        )
        return

    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(name=name)
        os.environ[env_var] = response.payload.data.decode("UTF-8")
        logger.info("✅ %s chargé depuis Secret Manager (secret '%s').", env_var, secret_id)
    except Exception as exc:  # noqa: BLE001 — on veut dégrader proprement, pas crasher ici
        logger.warning(
            "⚠️ Impossible de charger '%s' depuis Secret Manager (%s). "
            "%s restera vide sauf s'il est fourni autrement.",
            secret_id, exc, env_var,
        )
