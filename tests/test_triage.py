"""Triage tests. These exercise the batching/mapping logic with a stub
agent -- no Bedrock calls, no AWS credentials, no cost. The parts that can
actually corrupt data (a verdict landing on the wrong review) are what's
covered here; whether the model's judgement is *good* is measured
separately by scripts/eval_triage.py against the real corpus.
"""

from datetime import datetime, timezone

import pytest

from reviewpulse.agents.triage import (
    ReviewTriage,
    TriageBatch,
    build_batch_prompt,
    triage_batch,
    triage_reviews,
)
from reviewpulse.sources.base import RawReview


def make_review(review_id: str, title: str = "t", body: str = "b", rating: int = 1) -> RawReview:
    return RawReview(
        source="spotify_csv",
        source_review_id=review_id,
        author="someone",
        title=title,
        body=body,
        rating=rating,
        app_version="1.2.3",
        updated_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
    )


def verdict(index: int, **kw) -> ReviewTriage:
    defaults = dict(
        index=index,
        sentiment="negative",
        category="bug",
        severity="medium",
        feature_area="login",
        summary="Cannot log in.",
    )
    defaults.update(kw)
    return ReviewTriage(**defaults)


class StubAgent:
    """Returns a canned TriageBatch, recording the prompt it was given."""

    def __init__(self, batch: TriageBatch | Exception):
        self._batch = batch
        self.prompts: list[str] = []

    def structured_output(self, model, prompt):
        self.prompts.append(prompt)
        if isinstance(self._batch, Exception):
            raise self._batch
        return self._batch


def test_prompt_numbers_reviews_from_one():
    reviews = [make_review("a", title="First"), make_review("b", title="Second")]
    prompt = build_batch_prompt(reviews)

    assert "[1]" in prompt and "First" in prompt
    assert "[2]" in prompt and "Second" in prompt
    assert "rating=1/5" in prompt


def test_prompt_never_exposes_real_review_ids():
    """The model addresses reviews by ordinal so it *can't* mis-transcribe a
    real review id onto the wrong verdict. If ids ever start appearing in
    the prompt, that safety property is gone.
    """
    reviews = [make_review("437314fe-1b1d-4352-abea-12fec30fce58"), make_review("4933ad2c-c70a-4a84-957d-d405439b2e0f")]

    prompt = build_batch_prompt(reviews)

    assert "437314fe-1b1d-4352-abea-12fec30fce58" not in prompt
    assert "4933ad2c-c70a-4a84-957d-d405439b2e0f" not in prompt


def test_long_review_body_is_truncated():
    reviews = [make_review("a", body="x" * 5000)]

    prompt = build_batch_prompt(reviews)

    assert len(prompt) < 2000
    assert prompt.rstrip().endswith("...")


def test_verdicts_map_back_to_correct_reviews_by_index():
    reviews = [make_review("id-1"), make_review("id-2"), make_review("id-3")]
    agent = StubAgent(TriageBatch(results=[
        verdict(3, feature_area="sync"),
        verdict(1, feature_area="login"),
        verdict(2, feature_area="billing"),
    ]))

    paired = triage_batch(reviews, agent=agent)

    got = {r.source_review_id: v.feature_area for r, v in paired}
    assert got == {"id-1": "login", "id-2": "billing", "id-3": "sync"}


def test_out_of_range_index_is_dropped_not_misassigned():
    reviews = [make_review("id-1"), make_review("id-2")]
    agent = StubAgent(TriageBatch(results=[verdict(1), verdict(99)]))

    paired = triage_batch(reviews, agent=agent)

    assert [r.source_review_id for r, _ in paired] == ["id-1"]


def test_duplicate_index_keeps_first_verdict():
    reviews = [make_review("id-1"), make_review("id-2")]
    agent = StubAgent(TriageBatch(results=[
        verdict(1, feature_area="first"),
        verdict(1, feature_area="second"),
    ]))

    paired = triage_batch(reviews, agent=agent)

    assert len(paired) == 1
    assert paired[0][1].feature_area == "first"


def test_missing_verdict_still_returns_the_others():
    reviews = [make_review("id-1"), make_review("id-2"), make_review("id-3")]
    agent = StubAgent(TriageBatch(results=[verdict(1), verdict(3)]))

    paired = triage_batch(reviews, agent=agent)

    assert {r.source_review_id for r, _ in paired} == {"id-1", "id-3"}


def test_reviews_are_split_into_batches():
    reviews = [make_review(f"id-{i}") for i in range(5)]
    agent = StubAgent(TriageBatch(results=[verdict(1), verdict(2)]))

    triage_reviews(reviews, agent=agent, batch_size=2)

    # 5 reviews at batch_size=2 -> 3 calls (2, 2, 1)
    assert len(agent.prompts) == 3
    assert "[3]" not in agent.prompts[0]


def test_failing_batch_is_isolated_not_fatal():
    reviews = [make_review(f"id-{i}") for i in range(4)]
    agent = StubAgent(RuntimeError("bedrock exploded"))

    # Must not raise -- a bad batch is logged and skipped.
    paired = triage_reviews(reviews, agent=agent, batch_size=2)

    assert paired == []


def test_empty_input_makes_no_calls():
    agent = StubAgent(TriageBatch(results=[]))
    assert triage_batch([], agent=agent) == []
    assert agent.prompts == []


def test_severity_and_category_are_schema_constrained():
    with pytest.raises(Exception):
        ReviewTriage(
            index=1, sentiment="negative", category="not_a_category",
            severity="medium", feature_area="login", summary="x",
        )
    with pytest.raises(Exception):
        ReviewTriage(
            index=1, sentiment="negative", category="bug",
            severity="apocalyptic", feature_area="login", summary="x",
        )
