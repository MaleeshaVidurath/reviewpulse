"""Triage stage: classify each new review into a fixed schema.

Uses Strands' `structured_output` rather than parsing free text -- the
downstream clustering and ticket stages key off `category` and
`feature_area`, so a stray prose response would break the pipeline rather
than just look untidy.

Two deliberate choices worth knowing about:

1. **Reviews are addressed by batch ordinal, not by review id.** Source
   review ids can be long opaque strings; asking a model to echo them back
   verbatim invites silent transcription errors that would attach a
   verdict to the wrong review. The prompt numbers reviews 1..N and the
   mapping back to real ids happens locally.

2. **Triage is cached in the store.** Classification is the one stage
   every review passes through, so it dominates cost. A review is
   classified once, ever -- reruns and restarts read from SQLite.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from reviewpulse.config import (
    AWS_REGION,
    MAX_REVIEW_CHARS,
    TRIAGE_BATCH_SIZE,
    TRIAGE_MODEL_ID,
)
from reviewpulse.sources.base import RawReview

logger = logging.getLogger(__name__)

Sentiment = Literal["positive", "neutral", "negative"]
Category = Literal[
    "bug",
    "crash",
    "performance",
    "ux",
    "feature_request",
    "billing",
    "praise",
    "spam",
]
Severity = Literal["low", "medium", "high", "critical"]


class ReviewTriage(BaseModel):
    """One review's classification. `index` is the 1-based position in the
    batch prompt, used to map back to the real review id locally.
    """

    index: int = Field(description="1-based position of the review in the prompt")
    sentiment: Sentiment
    category: Category
    severity: Severity = Field(
        description=(
            "Impact if this is a real defect: 'critical' only for data loss, "
            "account lockout, payment failure, or the app being unusable"
        )
    )
    feature_area: str = Field(
        description=(
            "Short lowercase noun for the affected area, e.g. 'login', 'sync', "
            "'notifications', 'video_calls'. Use 'general' if unclear."
        )
    )
    summary: str = Field(
        description="One engineer-readable sentence describing the problem or feedback"
    )


class TriageBatch(BaseModel):
    """Wrapper so the model returns one object containing all verdicts --
    `structured_output` expects a single model, not a bare list.
    """

    results: list[ReviewTriage]


SYSTEM_PROMPT = """You triage customer app-store reviews for an engineering team.

For each numbered review, classify it. Be conservative with severity: most
negative reviews are 'low' or 'medium'. Reserve 'critical' for data loss,
account lockout, payment failure, or the app being completely unusable.

Use 'spam' for reviews with no product content (advertising, gibberish,
unrelated rants). Use 'praise' only when there is no actionable complaint.

feature_area should be a short lowercase noun that groups related reports
together -- prefer reusing an obvious common name ('login', 'sync',
'notifications') over inventing a specific one, since these are used to
group reviews into shared engineering tickets.

Return exactly one result per review, with `index` matching the review's
number in the prompt."""


def _truncate(text: str, limit: int = MAX_REVIEW_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def build_batch_prompt(reviews: list[RawReview]) -> str:
    """Render a batch of reviews as a numbered list for classification."""
    lines = []
    for i, r in enumerate(reviews, start=1):
        version = r.app_version or "unknown"
        lines.append(
            f"[{i}] rating={r.rating}/5 app_version={version}\n"
            f"title: {_truncate(r.title, 200)}\n"
            f"body: {_truncate(r.body)}"
        )
    return "\n\n".join(lines)


def _build_agent(model_id: str):
    """Import Strands lazily so the ingestion path and offline tests don't
    need the SDK (or AWS credentials) loaded just to import this module.
    """
    from strands import Agent
    from strands.models import BedrockModel

    model = BedrockModel(model_id=model_id, region_name=AWS_REGION, temperature=0)
    return Agent(model=model, system_prompt=SYSTEM_PROMPT)


def triage_batch(
    reviews: list[RawReview],
    agent=None,
    model_id: str = TRIAGE_MODEL_ID,
) -> list[tuple[RawReview, ReviewTriage]]:
    """Classify one batch of reviews. Returns (review, verdict) pairs.

    Verdicts whose `index` doesn't correspond to a review in this batch are
    dropped with a warning rather than raising -- one malformed row
    shouldn't cost the whole batch.
    """
    if not reviews:
        return []

    agent = agent or _build_agent(model_id)
    prompt = build_batch_prompt(reviews)
    batch: TriageBatch = agent.structured_output(TriageBatch, prompt)

    by_index = {i: r for i, r in enumerate(reviews, start=1)}
    paired: list[tuple[RawReview, ReviewTriage]] = []
    seen: set[int] = set()

    for verdict in batch.results:
        review = by_index.get(verdict.index)
        if review is None:
            logger.warning("triage returned out-of-range index %s (batch of %d)",
                           verdict.index, len(reviews))
            continue
        if verdict.index in seen:
            logger.warning("triage returned duplicate index %s, keeping first", verdict.index)
            continue
        seen.add(verdict.index)
        paired.append((review, verdict))

    missing = set(by_index) - seen
    if missing:
        logger.warning("triage omitted %d of %d reviews in batch: indexes %s",
                       len(missing), len(reviews), sorted(missing))

    return paired


def triage_reviews(
    reviews: list[RawReview],
    agent=None,
    model_id: str = TRIAGE_MODEL_ID,
    batch_size: int = TRIAGE_BATCH_SIZE,
) -> list[tuple[RawReview, ReviewTriage]]:
    """Classify reviews in batches. A failed batch is logged and skipped so
    a single bad response doesn't abort a whole ingestion run.
    """
    paired: list[tuple[RawReview, ReviewTriage]] = []

    for start in range(0, len(reviews), batch_size):
        chunk = reviews[start : start + batch_size]
        try:
            paired.extend(triage_batch(chunk, agent=agent, model_id=model_id))
        except Exception as exc:  # noqa: BLE001 - batch isolation is the point
            logger.error("triage batch %d-%d failed: %s", start, start + len(chunk), exc)

    return paired
