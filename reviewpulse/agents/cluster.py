"""Cluster stage: group triaged reviews describing the same underlying
issue into candidate tickets.

Two-step process:

1. **Grouping is free and deterministic.** Reviews are grouped by the
   (feature_area, category) pair triage already assigned -- the triage
   system prompt explicitly asks for a feature_area that "groups related
   reports together", so no further LLM judgment is needed to form the
   groups themselves. This runs against whatever's already in the store,
   costs nothing, and can run every tick.

2. **Drafting a ticket title/description is a judgment call**, made only
   for clusters that cross CLUSTER_MIN_SIZE (low volume -- most
   feature_area/category pairs never reach the threshold). That's why it
   uses REASONING_MODEL_ID (Sonnet) rather than the bulk triage model, and
   why it's a separate function callers invoke deliberately rather than
   something build_clusters() does automatically.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from pydantic import BaseModel

from reviewpulse.config import AWS_REGION, CLUSTER_MIN_SIZE, REASONING_MODEL_ID

logger = logging.getLogger(__name__)

SAMPLE_SIZE = 5


@dataclass
class Cluster:
    feature_area: str
    category: str
    count: int
    severity_counts: dict[str, int]
    source_review_ids: list[str]
    sample_summaries: list[str] = field(repr=False)


def build_clusters(rows: list[dict], min_size: int = CLUSTER_MIN_SIZE) -> list[Cluster]:
    """Group triaged rows (as returned by SqliteReviewStore.triaged_rows())
    by (feature_area, category). Returns only groups with at least
    `min_size` reviews, largest first.
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        key = (row["feature_area"], row["category"])
        groups.setdefault(key, []).append(row)

    clusters = [
        Cluster(
            feature_area=feature_area,
            category=category,
            count=len(group_rows),
            severity_counts=dict(Counter(r["severity"] for r in group_rows)),
            source_review_ids=[r["source_review_id"] for r in group_rows],
            sample_summaries=[r["summary"] for r in group_rows[:SAMPLE_SIZE]],
        )
        for (feature_area, category), group_rows in groups.items()
        if len(group_rows) >= min_size
    ]

    clusters.sort(key=lambda c: c.count, reverse=True)
    return clusters


class TicketDraft(BaseModel):
    title: str
    description: str


SYSTEM_PROMPT = """You write concise engineering ticket drafts from a
cluster of customer reviews describing the same underlying issue.

Given the feature area, category, severity breakdown, and a sample of
review summaries, produce:
- title: a short, specific engineering ticket title (not a restatement of
  the feature area alone)
- description: 2-4 sentences describing the problem pattern an engineer
  would act on, referencing the severity/volume signal briefly

Do not invent details not supported by the review summaries."""


def _build_agent(model_id: str):
    """Import Strands lazily so grouping and offline tests don't need the
    SDK (or AWS credentials) loaded just to import this module.
    """
    from strands import Agent
    from strands.models import BedrockModel

    model = BedrockModel(model_id=model_id, region_name=AWS_REGION, temperature=0)
    return Agent(model=model, system_prompt=SYSTEM_PROMPT)


def _build_prompt(cluster: Cluster) -> str:
    severities = ", ".join(f"{k}={v}" for k, v in sorted(cluster.severity_counts.items()))
    samples = "\n".join(f"- {s}" for s in cluster.sample_summaries)
    return (
        f"feature_area: {cluster.feature_area}\n"
        f"category: {cluster.category}\n"
        f"review_count: {cluster.count}\n"
        f"severity_breakdown: {severities}\n"
        f"sample review summaries:\n{samples}"
    )


def draft_ticket(cluster: Cluster, agent=None, model_id: str = REASONING_MODEL_ID) -> TicketDraft | None:
    """Draft a ticket title/description for one cluster. Returns None
    (doesn't raise) if the call fails -- one bad draft shouldn't abort a
    run over several clusters.
    """
    prompt = _build_prompt(cluster)
    try:
        agent = agent or _build_agent(model_id)
        return agent.structured_output(TicketDraft, prompt)
    except Exception as exc:  # noqa: BLE001 - isolate one cluster's failure
        logger.error("cluster ticket draft failed for %s/%s: %s",
                     cluster.feature_area, cluster.category, exc)
        return None
