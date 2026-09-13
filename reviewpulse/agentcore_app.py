"""AgentCore Runtime entrypoint: one pipeline tick (ingest -> dedupe ->
triage -> cluster -> crisis check), exposed as a Bedrock AgentCore Runtime
app so it runs on managed AWS infrastructure instead of a local machine.

This mirrors scripts/demo_loop.py's single-tick body, adapted for a
stateless-per-invocation runtime: the SQLite store and CSV-offset cursor
live under /tmp, which AgentCore Runtime does not guarantee persists
between invocations -- fine for demonstrating a real deployed invocation,
but a production deployment would need a persistent store (e.g. DynamoDB,
per store/base.py's ReviewStore protocol) instead.

Local run: `python -m reviewpulse.agentcore_app` starts the server on
:8080 the same way AgentCore Runtime would invoke it.
"""

from __future__ import annotations

import json
from pathlib import Path

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from reviewpulse.agents.cluster import build_clusters
from reviewpulse.agents.triage import triage_reviews
from reviewpulse.config import TRIAGE_MODEL_ID
from reviewpulse.signals.detector import detect_crisis
from reviewpulse.signals.escalation import draft_escalation
from reviewpulse.sources.spotify_csv import DEFAULT_CSV_PATH, fetch_reviews
from reviewpulse.store.sqlite_store import SqliteReviewStore

app = BedrockAgentCoreApp()

CURSOR_PATH = Path("/tmp/reviewpulse_cursor.json")
DB_PATH = Path("/tmp/reviewpulse.db")


def _load_cursor() -> int:
    if not CURSOR_PATH.exists():
        return 0
    return json.loads(CURSOR_PATH.read_text(encoding="utf-8")).get("offset", 0)


def _save_cursor(offset: int) -> None:
    CURSOR_PATH.write_text(json.dumps({"offset": offset}), encoding="utf-8")


@app.entrypoint
def handler(payload: dict) -> dict:
    chunk_size = int(payload.get("chunk_size", 20)) if isinstance(payload, dict) else 20

    store = SqliteReviewStore(db_path=DB_PATH)
    try:
        offset = _load_cursor()
        result = fetch_reviews(DEFAULT_CSV_PATH, offset=offset, limit=chunk_size)

        if result.status != "ok":
            return {"status": result.status, "detail": result.detail}
        if not result.reviews:
            return {"status": "end_of_feed", "offset": offset}

        new_reviews = store.filter_new(result.reviews)
        _save_cursor(offset + len(result.reviews))

        summary: dict = {
            "status": "ok",
            "offset": offset,
            "released": len(result.reviews),
            "new": len(new_reviews),
        }

        if new_reviews:
            paired = triage_reviews(new_reviews)
            saved = store.save_triage(paired, model_id=TRIAGE_MODEL_ID)
            summary["triaged"] = len(paired)
            summary["saved"] = saved

        triaged_rows = store.triaged_rows()

        clusters = build_clusters(triaged_rows)
        summary["clusters"] = [
            {"feature_area": c.feature_area, "category": c.category, "count": c.count}
            for c in clusters
        ]

        signal = detect_crisis(triaged_rows)
        summary["crisis_triggered"] = signal.triggered
        if signal.triggered:
            escalation = draft_escalation(signal)
            if escalation is not None:
                summary["escalation"] = {
                    "headline": escalation.headline,
                    "holding_statement": escalation.holding_statement,
                }

        return summary
    finally:
        store.close()


if __name__ == "__main__":
    app.run()
