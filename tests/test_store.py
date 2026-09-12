"""Store tests: dedupe and the triage cache.

The triage cache is the cost-control mechanism -- if `filter_untriaged`
ever returns an already-classified review, the project pays twice for the
same answer -- so it gets the same scrutiny as the review dedupe.
"""

from datetime import datetime, timezone

import pytest

from reviewpulse.sources.base import RawReview
from reviewpulse.store.sqlite_store import SqliteReviewStore


@pytest.fixture()
def store(tmp_path):
    s = SqliteReviewStore(tmp_path / "test.db")
    yield s
    s.close()


def make_review(review_id: str, rating: int = 1) -> RawReview:
    return RawReview(
        source="spotify_csv",
        source_review_id=review_id,
        author="a",
        title="t",
        body="b",
        rating=rating,
        app_version="1.0",
        updated_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
    )


class FakeVerdict:
    def __init__(self, area="login"):
        self.sentiment = "negative"
        self.category = "bug"
        self.severity = "high"
        self.feature_area = area
        self.summary = "Cannot log in."


def test_filter_new_is_idempotent(store):
    reviews = [make_review("a"), make_review("b")]

    assert len(store.filter_new(reviews)) == 2
    assert store.filter_new(reviews) == []


def test_filter_new_only_returns_unseen(store):
    store.filter_new([make_review("a")])

    new = store.filter_new([make_review("a"), make_review("b")])

    assert [r.source_review_id for r in new] == ["b"]


def test_triage_is_never_paid_for_twice(store):
    reviews = [make_review("a"), make_review("b")]
    assert len(store.filter_untriaged(reviews)) == 2

    store.save_triage([(reviews[0], FakeVerdict())], model_id="test-model")

    remaining = store.filter_untriaged(reviews)
    assert [r.source_review_id for r in remaining] == ["b"]


def test_saving_triage_twice_does_not_duplicate(store):
    review = make_review("a")
    store.save_triage([(review, FakeVerdict("login"))], model_id="m")
    store.save_triage([(review, FakeVerdict("sync"))], model_id="m")

    rows = store.triaged_rows()
    assert len(rows) == 1
    # First write wins -- re-triaging shouldn't silently rewrite history.
    assert rows[0]["feature_area"] == "login"


def test_triage_counts_groups_by_category(store):
    store.save_triage(
        [(make_review(f"id-{i}"), FakeVerdict()) for i in range(3)],
        model_id="m",
    )

    assert store.triage_counts() == {"bug": 3}


def test_triaged_rows_carry_review_metadata(store):
    store.save_triage([(make_review("a", rating=2), FakeVerdict())], model_id="m")

    row = store.triaged_rows()[0]

    assert row["source_review_id"] == "a"
    assert row["rating"] == 2


def test_get_ticket_returns_none_when_never_synced(store):
    assert store.get_ticket("login", "bug") is None


def test_save_and_get_ticket_round_trip(store):
    store.save_ticket("login", "bug", "RP-1", 4)

    assert store.get_ticket("login", "bug") == ("RP-1", 4)


def test_save_ticket_updates_in_place(store):
    store.save_ticket("login", "bug", "RP-1", 4)
    store.save_ticket("login", "bug", "RP-1", 7)

    assert store.get_ticket("login", "bug") == ("RP-1", 7)


def test_tickets_are_keyed_independently_per_cluster(store):
    store.save_ticket("login", "bug", "RP-1", 4)
    store.save_ticket("sync", "bug", "RP-2", 3)

    assert store.get_ticket("login", "bug") == ("RP-1", 4)
    assert store.get_ticket("sync", "bug") == ("RP-2", 3)
