# 🏗️ Investment Advisor — Projet Multi-Agents ADK

Un système d'analyse d'investissement multi-agents construit avec Google ADK et des LLMs locaux via Ollama. Ce document retrace l'intégralité du développement, notamment chaque obstacle majeur et les décisions architecturales qui ont permis de les résoudre.

---

## Architecture finale (v5 — Stable)

```
SequentialAgent (AnalysisPipeline)
  ├─ MarketAnalysisAgent   ← tools=[], données pré-chargées via before_agent_callback
  ├─ NewsAgent             ← tools=[], données pré-chargées via before_agent_callback
  ├─ RiskAnalysisAgent     ← tools=[], données pré-chargées via before_agent_callback
  └─ DecisionAgent         ← tools=[], données pré-chargées via before_agent_callback
```

**Principe clé :** Les 6 tools (`get_market_data`, `get_technical_indicators`, `get_news_sentiment`, `get_economic_indicators`, `assess_risk_score`) sont appelés directement en Python via `before_agent_callback` — le LLM reçoit les données déjà collectées et se contente de rédiger le rapport.

---

## Architecture initiale (v1)

Le design original était ambitieux et couvrait toutes les contraintes du TP dès le départ :

```
InvestmentAdvisor (LlmAgent — root)
  └─ transfer_to_agent ──► AnalysisPipeline (SequentialAgent)
                             ├─ DataGatheringAgent (ParallelAgent)
                             │    ├─ MarketAnalysisAgent  ← tools: get_market_data, get_technical_indicators
                             │    └─ NewsAgent             ← tools: get_news_sentiment, get_economic_indicators
                             ├─ RiskAnalysisAgent          ← tool: assess_risk_score
                             └─ DecisionAgent              ← AgentTool → StrategyAgent
```

Toutes les contraintes étaient couvertes : 5 `LlmAgent`s, 6 tools, `SequentialAgent` + `ParallelAgent`, `transfer_to_agent` + `AgentTool`, 3 callbacks, état partagé.

---

## Problèmes rencontrés & solutions

### 🔴 Problème 1 — `google-adk[extensions]` introuvable

**Erreur :** `ollama/gemma2:2b` nécessite `litellm`, qui n'était pas installé.  
**Cause :** `zsh` interprète les `[]` comme des globs shell.  
**Solution :**

```bash
pip install "google-adk[extensions]"  # guillemets obligatoires sous zsh
```

---

### 🔴 Problème 2 — Noms d'agents hallucinés comme tools

**Erreur :** `Tool 'AnalysisPipeline' not found`  
**Cause :** `gemma2:2b` (2B paramètres) voyait le nom `AnalysisPipeline` dans le contexte ADK et tentait de l'appeler comme une fonction.  
**Solution :** Instructions ultra-simplifiées avec un `"Do not call any other function"` explicite.  
**Résultat :** Toujours instable avec `gemma2:2b`.

---

### 🔴 Problème 3 — Boucle infinie d'appels de tools

**Erreur :** `MarketAnalysisAgent` appelait `get_market_data` en boucle pendant plus de 10 minutes, saturant la RAM.  
**Cause :** Les petits modèles locaux ne savent pas quand arrêter d'appeler des tools.  
**Solution :** Ajout d'un `before_model_callback` comme disjoncteur — coupe l'agent après N appels LLM :

```python
def before_model_callback(ctx, llm_request):
    calls = state.get(f"_calls_{name}", 0) + 1
    if calls > _MAX_CALLS:
        return LlmResponse(...)  # arrêt forcé
```

---

### 🔴 Problème 4 — `gemma2:2b` trop limité → passage à `llama3.2`

**Cause :** 2B paramètres insuffisants pour le function calling multi-agents.  
**Solution :** `ollama pull llama3.2` + mise à jour de `_MODEL`.  
**Résultat :** Les mêmes problèmes persistaient.

---

### 🔴 Problème 5 — `llama3.2` hallucine aussi (`Tool 'NewsAgent' not found`)

**Cause :** ADK expose les noms des sous-agents dans le contexte système — `llama3.2` les confondait avec des tools appelables.  
**Solution :** Suppression du `ParallelAgent`, remplacement par un `SequentialAgent` pur, `root_agent = analysis_pipeline` directement.  
**Résultat :** Toujours instable.

---

### 🔴 Problème 6 — `{variable}` dans les instructions déclenche des hallucinations

**Erreur :** `Tool 'market_analysis' not found`  
**Cause :** `{market_analysis}` dans les instructions était interprété par `llama3.2` comme un nom de fonction à appeler.  
**Solution :** **Supprimer tous les `{variable}` des instructions des agents.**

---

### 🔴 Problème 7 — Quota de l'API Gemini épuisé

**Erreur :** `429 RESOURCE_EXHAUSTED, limit: 0`  
**Cause :** Nouvelle clé API pas encore activée / quota journalier atteint.  
**Solution :** Retour à Ollama avec l'architecture simplifiée.

---

### 🔴 Problème 8 — RAM saturée avec `llama3.1` (8B)

**Contexte :** `llama3.1` gère bien le function calling, mais nécessite 8 Go de RAM.  
**Cause :** MacBook Air 8 Go → gel du système.  
**Solution :** Abandon de tous les modèles locaux 7B+.

---

### ✅ Solution finale — Architecture pré-fetch

**Cause profonde :** `llama3.2` voit les noms des tools dans son contexte et hallucine des appels. La seule solution fiable : **ne lui montrer aucun tool**.

```
Avant (instable) :
  LLM → décide quels tools appeler → hallucine des noms → crash

Après (stable) :
  Python (before_agent_callback) → appelle les tools → stocke dans state
  LLM → reçoit les données déjà collectées → rédige uniquement le rapport
```

Chaque agent a `tools=[]`. Les 6 tools sont invoqués directement en Python avant que le LLM soit appelé :

```python
def before_agent_callback(ctx):
    if name == "MarketAnalysisAgent":
        for sym in symbols:
            state["prefetched_market"] = get_market_data(sym)  # Python pur
    # Le LLM reçoit les données et rédige le rapport — zéro appel de tool
```

---

## Évolution de l'architecture

| Version | Modèle      | Architecture                       | Résultat                |
| ------- | ----------- | ---------------------------------- | ----------------------- |
| v1      | `gemma2:2b` | Parallel + Sequential + AgentTool  | ❌ Hallucinations       |
| v2      | `llama3.2`  | Sequential + AgentTool             | ❌ Boucles infinies     |
| v3      | `llama3.2`  | Sequential sans ParallelAgent      | ❌ Confond agents/tools |
| v4      | `llama3.1`  | Sequential simplifié               | ❌ RAM insuffisante     |
| v5      | `llama3.2`  | Pré-fetch en callbacks, `tools=[]` | ✅ Fonctionne           |

---

## Leçon principale

> **Les petits modèles locaux (< 7B) ne sont pas conçus pour le function calling dans des systèmes multi-agents.**
>
> La solution architecturale : déplacer la logique d'appel des tools du LLM vers le code Python via les callbacks ADK. Laisser le LLM faire ce pour quoi il est performant — générer du texte à partir de données structurées — et gérer toute l'orchestration des tools en Python.
