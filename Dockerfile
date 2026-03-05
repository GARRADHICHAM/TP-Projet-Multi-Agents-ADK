# ─────────────────────────────────────────────────────────────────────────────
# Dockerfile — Investment Agent ADK
# Expose le root_agent (InvestmentAdvisor) via FastAPI sur le port 8080
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# Métadonnées
LABEL maintainer="investment-agent"
LABEL description="ADK Multi-Agents Investment Platform"

WORKDIR /app

# Variables d'environnement
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Dépendances système minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Installer les dépendances Python en premier (cache Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
# On copie seulement ce qui est nécessaire (voir .dockerignore)
COPY investment_agent/ ./investment_agent/
COPY tests/investment_scenarios.test.json ./tests/
COPY server.py .

# Exposer le port Cloud Run
EXPOSE 8080

# Lancer le serveur FastAPI
# $PORT est injecté automatiquement par Cloud Run
CMD exec uvicorn server:app --host 0.0.0.0 --port $PORT --workers 1
