"""HTTP API for the ReviewPulse pipeline, backed by DynamoDB so state
survives across separate Lambda invocations. Deployed behind a Lambda
Function URL (see reviewpulse/lambda_handler.py) for the demo dashboard.

Write endpoints (POST /api/tick, POST /api/sync) require an API key
(X-API-Key header, checked against REVIEWPULSE_API_KEY) since they trigger
real Bedrock/Jira calls -- read endpoints are open.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from reviewpulse.agents.cluster import build_clusters, draft_ticket
from reviewpulse.agents.triage import triage_reviews
from reviewpulse.config import TRIAGE_MODEL_ID
from reviewpulse.dashboard import DASHBOARD_HTML
from reviewpulse.jira.client import JiraClient
from reviewpulse.jira.sync import sync_cluster
from reviewpulse.signals.detector import detect_crisis
from reviewpulse.signals.escalation import draft_escalation
from reviewpulse.sources.spotify_csv import DEFAULT_CSV_PATH, fetch_reviews
from reviewpulse.store.dynamo_store import DynamoReviewStore

app = FastAPI(title="ReviewPulse API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return DASHBOARD_HTML


def _check_api_key(x_api_key: str | None) -> None:
    expected = os.environ.get("REVIEWPULSE_API_KEY")
    if not expected:
        raise HTTPException(500, "Server misconfigured: REVIEWPULSE_API_KEY not set")
    if x_api_key != expected:
        raise HTTPException(401, "Invalid or missing X-API-Key header")


class TickRequest(BaseModel):
    chunk_size: int = 20


class SyncRequest(BaseModel):
    feature_area: str
    category: str


def _clusters_payload(store: DynamoReviewStore) -> list[dict]:
    rows = store.triaged_rows()
    clusters = build_clusters(rows)
    return [
        {
            "feature_area": c.feature_area,
            "category": c.category,
            "count": c.count,
            "severity_counts": c.severity_counts,
            "sample_summaries": c.sample_summaries,
            "ticket": store.get_ticket(c.feature_area, c.category),
        }
        for c in clusters
    ]


@app.get("/api/status")
def status():
    store = DynamoReviewStore()
    rows = store.triaged_rows()
    signal = detect_crisis(rows)
    return {
        "total_triaged": len(rows),
        "offset": store.get_cursor(),
        "clusters": _clusters_payload(store),
        "crisis": {
            "triggered": signal.triggered,
            "recent_negative_rate": signal.recent_negative_rate,
            "baseline_negative_rate": signal.baseline_negative_rate,
        },
        "jira_base_url": os.environ.get("JIRA_BASE_URL"),
    }


@app.get("/api/reviews/recent")
def recent_reviews(limit: int = 20):
    store = DynamoReviewStore()
    rows = store.triaged_rows()
    return {"reviews": list(reversed(rows[-limit:]))}


@app.post("/api/tick")
def tick(req: TickRequest, x_api_key: str | None = Header(default=None)):
    _check_api_key(x_api_key)

    store = DynamoReviewStore()
    offset = store.get_cursor()
    result = fetch_reviews(DEFAULT_CSV_PATH, offset=offset, limit=req.chunk_size)

    if result.status != "ok":
        return {"status": result.status, "detail": result.detail}
    if not result.reviews:
        return {"status": "end_of_feed", "offset": offset}

    new_reviews = store.filter_new(result.reviews)
    store.save_cursor(offset + len(result.reviews))

    response: dict = {
        "status": "ok",
        "offset": offset,
        "released": len(result.reviews),
        "new": len(new_reviews),
    }

    if new_reviews:
        paired = triage_reviews(new_reviews)
        saved = store.save_triage(paired, model_id=TRIAGE_MODEL_ID)
        response["triaged"] = len(paired)
        response["saved"] = saved

    rows = store.triaged_rows()
    response["clusters"] = _clusters_payload(store)

    signal = detect_crisis(rows)
    response["crisis_triggered"] = signal.triggered
    if signal.triggered:
        escalation = draft_escalation(signal)
        if escalation is not None:
            response["escalation"] = {
                "headline": escalation.headline,
                "holding_statement": escalation.holding_statement,
            }

    return response


@app.post("/api/sync")
def sync(req: SyncRequest, x_api_key: str | None = Header(default=None)):
    _check_api_key(x_api_key)

    store = DynamoReviewStore()
    rows = store.triaged_rows()
    clusters = {(c.feature_area, c.category): c for c in build_clusters(rows)}
    cluster = clusters.get((req.feature_area, req.category))
    if cluster is None:
        raise HTTPException(404, "No such cluster (below threshold, or doesn't exist)")

    if cluster.category == "praise":
        raise HTTPException(422, "This cluster is pure praise -- there's no problem to file a ticket about")

    ticket_draft = draft_ticket(cluster)
    if ticket_draft is None:
        raise HTTPException(502, "Ticket drafting failed (Bedrock error) -- check CloudWatch logs")

    client = JiraClient.from_env()
    result = sync_cluster(cluster, ticket_draft, store, client)

    return {
        "action": result.action,
        "issue_key": result.issue_key,
        "detail": result.detail,
        "ticket": {"title": ticket_draft.title, "description": ticket_draft.description},
    }
