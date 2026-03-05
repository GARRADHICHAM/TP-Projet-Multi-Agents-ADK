#!/bin/bash
# ============================================================
# setup_gcp.sh — Configuration GCP pour Investment Agent ADK
# Usage: bash setup_gcp.sh <PROJECT_ID> <GITHUB_REPO>
# Exemple: bash setup_gcp.sh mon-projet-123 monuser/TP_MULTI_AGENTS
# ============================================================

set -e

PROJECT_ID=${1:-""}
GITHUB_REPO=${2:-""}
REGION="europe-west1"
SERVICE_NAME="investment-agent"
REPO_NAME="investment-agent-repo"
SA_NAME="github-actions-deploy"

# ── Validation ────────────────────────────────────────────────────────────────
if [ -z "$PROJECT_ID" ] || [ -z "$GITHUB_REPO" ]; then
  echo "❌ Usage: bash setup_gcp.sh <PROJECT_ID> <GITHUB_REPO>"
  echo "   Exemple: bash setup_gcp.sh mon-projet-123 monuser/TP_MULTI_AGENTS"
  exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   Investment Agent — Setup Google Cloud              ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Project  : $PROJECT_ID"
echo "║  Region   : $REGION"
echo "║  GitHub   : $GITHUB_REPO"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── 1. Projet ─────────────────────────────────────────────────────────────────
gcloud config set project "$PROJECT_ID"
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
echo "✅ Projet: $PROJECT_ID (numéro: $PROJECT_NUMBER)"

# ── 2. APIs nécessaires ───────────────────────────────────────────────────────
echo ""
echo "📦 Activation des APIs Google Cloud..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  --quiet
echo "✅ APIs activées"

# ── 3. Artifact Registry ──────────────────────────────────────────────────────
echo ""
echo "🐳 Création du repo Docker dans Artifact Registry..."
gcloud artifacts repositories create "$REPO_NAME" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Images Docker pour $SERVICE_NAME" \
  2>/dev/null && echo "✅ Repo créé" || echo "⚠️  Repo déjà existant, on continue"

# ── 4. Service Account pour GitHub Actions ────────────────────────────────────
echo ""
echo "🔑 Création du Service Account GitHub Actions..."
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create "$SA_NAME" \
  --display-name="GitHub Actions — Investment Agent Deploy" \
  2>/dev/null && echo "✅ SA créé" || echo "⚠️  SA déjà existant, on continue"

echo "🔐 Attribution des permissions au SA..."
for ROLE in \
  "roles/run.admin" \
  "roles/artifactregistry.writer" \
  "roles/storage.admin" \
  "roles/iam.serviceAccountUser" \
  "roles/secretmanager.secretAccessor"; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$ROLE" \
    --quiet
  echo "   ✓ $ROLE"
done

# ── 5. Workload Identity Federation (pas de clé JSON) ────────────────────────
echo ""
echo "🔗 Configuration Workload Identity Federation..."
POOL_NAME="github-pool"
PROVIDER_NAME="github-provider"

gcloud iam workload-identity-pools create "$POOL_NAME" \
  --location="global" \
  --description="Pool pour GitHub Actions" \
  --display-name="GitHub Pool" \
  2>/dev/null && echo "✅ Pool créé" || echo "⚠️  Pool déjà existant"

POOL_ID=$(gcloud iam workload-identity-pools describe "$POOL_NAME" \
  --location="global" \
  --format="value(name)")

gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_NAME" \
  --location="global" \
  --workload-identity-pool="$POOL_NAME" \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  2>/dev/null && echo "✅ Provider créé" || echo "⚠️  Provider déjà existant"

# Autoriser le repo GitHub
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/${POOL_ID}/attribute.repository/${GITHUB_REPO}" \
  --quiet
echo "✅ Repo GitHub autorisé: $GITHUB_REPO"

PROVIDER_FULL=$(gcloud iam workload-identity-pools providers describe "$PROVIDER_NAME" \
  --location="global" \
  --workload-identity-pool="$POOL_NAME" \
  --format="value(name)")

# ── 6. Secret Manager — GOOGLE_API_KEY ───────────────────────────────────────
echo ""
echo "🔒 Configuration du secret GOOGLE_API_KEY..."
echo "   (C'est ta clé API Gemini, disponible sur https://aistudio.google.com/apikey)"
echo ""
read -rsp "   Entrer ta GOOGLE_API_KEY: " GOOGLE_API_KEY
echo ""

if gcloud secrets describe GOOGLE_API_KEY --quiet 2>/dev/null; then
  echo -n "$GOOGLE_API_KEY" | gcloud secrets versions add GOOGLE_API_KEY --data-file=-
  echo "✅ Secret mis à jour"
else
  echo -n "$GOOGLE_API_KEY" | gcloud secrets create GOOGLE_API_KEY \
    --data-file=- \
    --replication-policy="automatic"
  echo "✅ Secret créé"
fi

# Donner accès au SA Cloud Run (compute SA)
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
gcloud secrets add-iam-policy-binding GOOGLE_API_KEY \
  --member="serviceAccount:${COMPUTE_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --quiet
echo "✅ Accès secret accordé au SA Cloud Run"

# ── 7. Premier déploiement test (optionnel) ───────────────────────────────────
echo ""
read -rp "🚀 Lancer un premier déploiement manuel maintenant ? (o/n): " DEPLOY_NOW
if [ "$DEPLOY_NOW" = "o" ]; then
  echo "   Déploiement depuis le code source..."
  gcloud run deploy "$SERVICE_NAME" \
    --source . \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --port 8080 \
    --memory 1Gi \
    --set-secrets "GOOGLE_API_KEY=GOOGLE_API_KEY:latest" \
    --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID},PYTHONUNBUFFERED=1"

  SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
    --region "$REGION" \
    --format 'value(status.url)')
  echo ""
  echo "✅ Service déployé: $SERVICE_URL"
  echo "   Test: curl $SERVICE_URL/health"
fi

# ── 8. Résumé des secrets GitHub à configurer ─────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  📋 COPIER CES VALEURS DANS GitHub → Settings → Secrets         ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║"
echo "║  GCP_PROJECT_ID:"
echo "║    $PROJECT_ID"
echo "║"
echo "║  WIF_PROVIDER:"
echo "║    $PROVIDER_FULL"
echo "║"
echo "║  WIF_SERVICE_ACCOUNT:"
echo "║    $SA_EMAIL"
echo "║"
echo "║  GOOGLE_API_KEY:"
echo "║    (déjà dans Secret Manager ✅)"
echo "║"
echo "║  FRONTEND_URL:"
echo "║    https://your-app.vercel.app  ← après déploiement Next.js"
echo "║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "✅ Setup terminé ! Prochaine étape : configurer les secrets GitHub,"
echo "   puis faire un git push main pour déclencher le CI/CD."
