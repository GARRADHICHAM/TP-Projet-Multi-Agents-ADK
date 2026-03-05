"""
server.py — FastAPI wrapper pour Investment Agent ADK
Expose root_agent (InvestmentAdvisor) via une API REST consommable par Next.js
"""

from __future__ import annotations

import inspect
import json
import logging
import os
import uuid
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from investment_agent.agent import root_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Investment Agent API",
    description="Plateforme d'investissement automatisée — ADK Multi-Agents",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", FRONTEND_URL, "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

APP_NAME = "investment_agent"
session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=session_service,
)


class AnalyzeRequest(BaseModel):
    query: str
    user_id: Optional[str] = "web_user"
    session_id: Optional[str] = None


class AgentOutput(BaseModel):
    market_analysis:     Optional[str] = None
    news_impact:         Optional[str] = None
    risk_assessment:     Optional[str] = None
    investment_strategy: Optional[str] = None
    portfolio_decision:  Optional[str] = None
    audit_trail:         Optional[list[str]] = None


class AnalyzeResponse(BaseModel):
    session_id:     str
    final_response: str
    outputs:        AgentOutput
    status:         str = "success"


async def _call(fn, *args, **kwargs):
    """Appelle une fonction sync ou async de façon transparente."""
    result = fn(*args, **kwargs)
    if inspect.isawaitable(result):
        result = await result
    return result


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "investment-agent", "model": "gemini-2.5-flash-lite"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    session_id = request.session_id or str(uuid.uuid4())

    try:
        # Créer la session (sync ou async selon la version ADK)
        await _call(
            session_service.create_session,
            app_name=APP_NAME,
            user_id=request.user_id,
            session_id=session_id,
            state={"user_message": request.query},
        )

        message = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=request.query)],
        )

        final_text = ""
        state = {}

        async for event in runner.run_async(
            user_id=request.user_id,
            session_id=session_id,
            new_message=message,
        ):
            if hasattr(event, "state") and event.state:
                state.update(event.state)
            if event.is_final_response():
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if getattr(part, "text", None):
                            final_text = part.text
                            break

        # Récupérer le state final si vide
        if not state:
            try:
                final_session = await _call(
                    session_service.get_session,
                    app_name=APP_NAME,
                    user_id=request.user_id,
                    session_id=session_id,
                )
                state = dict(final_session.state) if final_session and final_session.state else {}
            except Exception:
                state = {}

        outputs = AgentOutput(
            market_analysis=state.get("market_analysis"),
            news_impact=state.get("news_impact"),
            risk_assessment=state.get("risk_assessment"),
            investment_strategy=state.get("investment_strategy"),
            portfolio_decision=state.get("portfolio_decision"),
            audit_trail=state.get("audit_trail"),
        )

        return AnalyzeResponse(
            session_id=session_id,
            final_response=final_text or state.get("portfolio_decision", ""),
            outputs=outputs,
            status="success",
        )

    except Exception as exc:
        logger.exception("Pipeline error for session %s", session_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/scenarios")
async def list_scenarios() -> dict[str, Any]:
    try:
        with open("tests/investment_scenarios.test.json", "r", encoding="utf-8") as f:
            scenarios = json.load(f)
        return {"scenarios": scenarios}
    except FileNotFoundError:
        return {"scenarios": []}


@app.get("/symbols")
async def list_symbols() -> dict[str, list[str]]:
    from investment_agent.agent import _KNOWN_SYMBOLS
    return {"symbols": _KNOWN_SYMBOLS}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")