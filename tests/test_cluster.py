"""Cluster tests: grouping is pure/deterministic (no LLM), so it's tested
directly against row dicts shaped like SqliteReviewStore.triaged_rows().
Ticket drafting uses a stub agent, same pattern as test_triage.py.
"""

import pytest

from reviewpulse.agents.cluster import Cluster, TicketDraft, build_clusters, draft_ticket


def make_row(review_id, feature_area="login", category="bug", severity="medium", summary="Cannot log in."):
    return {
        "source_review_id": review_id,
        "rating": 1,
        "sentiment": "negative",
        "category": category,
        "severity": severity,
        "feature_area": feature_area,
        "summary": summary,
        "app_version": "1.0",
    }


class StubAgent:
    def __init__(self, result: TicketDraft | Exception):
        self._result = result
        self.prompts: list[str] = []

    def structured_output(self, model, prompt):
        self.prompts.append(prompt)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def test_groups_by_feature_area_and_category():
    rows = [
        make_row("a", feature_area="login", category="bug"),
        make_row("b", feature_area="login", category="bug"),
        make_row("c", feature_area="sync", category="bug"),
    ]

    clusters = build_clusters(rows, min_size=1)

    keys = {(c.feature_area, c.category) for c in clusters}
    assert keys == {("login", "bug"), ("sync", "bug")}


def test_different_categories_in_same_feature_area_are_separate_clusters():
    rows = [
        make_row("a", feature_area="login", category="bug"),
        make_row("b", feature_area="login", category="feature_request"),
    ]

    clusters = build_clusters(rows, min_size=1)

    assert len(clusters) == 2


def test_min_size_filters_small_groups():
    rows = [make_row("a"), make_row("b")]

    assert build_clusters(rows, min_size=3) == []
    assert len(build_clusters(rows, min_size=2)) == 1


def test_clusters_sorted_largest_first():
    rows = (
        [make_row(f"a{i}", feature_area="login") for i in range(2)]
        + [make_row(f"b{i}", feature_area="sync") for i in range(5)]
    )

    clusters = build_clusters(rows, min_size=1)

    assert [c.feature_area for c in clusters] == ["sync", "login"]
    assert clusters[0].count == 5


def test_severity_counts_tally_correctly():
    rows = [
        make_row("a", severity="high"),
        make_row("b", severity="high"),
        make_row("c", severity="low"),
    ]

    clusters = build_clusters(rows, min_size=1)

    assert clusters[0].severity_counts == {"high": 2, "low": 1}


def test_source_review_ids_are_preserved():
    rows = [make_row("a"), make_row("b"), make_row("c")]

    clusters = build_clusters(rows, min_size=1)

    assert set(clusters[0].source_review_ids) == {"a", "b", "c"}


def test_sample_summaries_capped_at_sample_size():
    rows = [make_row(f"id-{i}", summary=f"issue {i}") for i in range(10)]

    clusters = build_clusters(rows, min_size=1)

    assert len(clusters[0].sample_summaries) == 5


def test_draft_ticket_returns_parsed_result():
    cluster = build_clusters([make_row("a"), make_row("b"), make_row("c")], min_size=1)[0]
    agent = StubAgent(TicketDraft(title="Login failures spike", description="Users can't log in."))

    ticket = draft_ticket(cluster, agent=agent)

    assert ticket.title == "Login failures spike"
    assert len(agent.prompts) == 1
    assert "login" in agent.prompts[0]


def test_draft_ticket_returns_none_on_failure_not_raises():
    cluster = build_clusters([make_row("a"), make_row("b"), make_row("c")], min_size=1)[0]
    agent = StubAgent(RuntimeError("bedrock exploded"))

    assert draft_ticket(cluster, agent=agent) is None
