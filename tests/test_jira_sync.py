"""Ticket-sync tests. A stub Jira client stands in for the real HTTP calls
-- no network, no credentials, no cost -- same pattern as StubAgent in
test_triage.py/test_cluster.py.
"""

from datetime import datetime, timezone

import pytest

from reviewpulse.agents.cluster import Cluster, TicketDraft
from reviewpulse.jira.sync import sync_cluster
from reviewpulse.store.sqlite_store import SqliteReviewStore


@pytest.fixture()
def store(tmp_path):
    s = SqliteReviewStore(tmp_path / "test.db")
    yield s
    s.close()


def make_cluster(count: int = 4, feature_area: str = "login", category: str = "bug") -> Cluster:
    return Cluster(
        feature_area=feature_area,
        category=category,
        count=count,
        severity_counts={"high": count},
        source_review_ids=[f"id-{i}" for i in range(count)],
        sample_summaries=["Cannot log in."],
    )


def make_ticket() -> TicketDraft:
    return TicketDraft(title="Login failures spike", description="Users can't log in.")


class StubJiraClient:
    def __init__(self, next_key: str = "RP-1"):
        self.next_key = next_key
        self.created: list[tuple[str, str]] = []
        self.comments: list[tuple[str, str]] = []

    def create_issue(self, summary: str, description: str) -> str:
        self.created.append((summary, description))
        return self.next_key

    def add_comment(self, issue_key: str, body: str) -> None:
        self.comments.append((issue_key, body))


class FailingJiraClient:
    def create_issue(self, summary: str, description: str) -> str:
        raise RuntimeError("jira is down")

    def add_comment(self, issue_key: str, body: str) -> None:
        raise RuntimeError("jira is down")


def test_first_sync_creates_an_issue(store):
    client = StubJiraClient(next_key="RP-1")

    result = sync_cluster(make_cluster(count=4), make_ticket(), store, client)

    assert result.action == "created"
    assert result.issue_key == "RP-1"
    assert client.created == [("Login failures spike", "Users can't log in.")]
    assert store.get_ticket("login", "bug") == ("RP-1", 4)


def test_resyncing_same_cluster_never_creates_a_second_issue(store):
    client = StubJiraClient(next_key="RP-1")
    sync_cluster(make_cluster(count=4), make_ticket(), store, client)

    result = sync_cluster(make_cluster(count=4), make_ticket(), store, client)

    assert result.action == "unchanged"
    assert len(client.created) == 1


def test_growing_cluster_adds_a_comment_not_a_new_issue(store):
    client = StubJiraClient(next_key="RP-1")
    sync_cluster(make_cluster(count=4), make_ticket(), store, client)

    result = sync_cluster(make_cluster(count=7), make_ticket(), store, client)

    assert result.action == "commented"
    assert result.issue_key == "RP-1"
    assert len(client.created) == 1
    assert client.comments == [("RP-1", "3 more review(s) reported this issue since the last sync (total 7).")]
    assert store.get_ticket("login", "bug") == ("RP-1", 7)


def test_shrinking_or_equal_count_does_not_comment(store):
    client = StubJiraClient(next_key="RP-1")
    sync_cluster(make_cluster(count=7), make_ticket(), store, client)

    result = sync_cluster(make_cluster(count=5), make_ticket(), store, client)

    assert result.action == "unchanged"
    assert client.comments == []


def test_different_clusters_get_different_issues(store):
    client = StubJiraClient(next_key="RP-1")
    sync_cluster(make_cluster(feature_area="login", category="bug"), make_ticket(), store, client)

    client.next_key = "RP-2"
    result = sync_cluster(make_cluster(feature_area="sync", category="bug"), make_ticket(), store, client)

    assert result.action == "created"
    assert result.issue_key == "RP-2"
    assert len(client.created) == 2


def test_create_failure_is_caught_not_raised(store):
    result = sync_cluster(make_cluster(), make_ticket(), store, FailingJiraClient())

    assert result.action == "failed"
    assert "jira is down" in result.detail
    assert store.get_ticket("login", "bug") is None


def test_comment_failure_is_caught_and_ticket_state_unchanged(store):
    client = StubJiraClient(next_key="RP-1")
    sync_cluster(make_cluster(count=4), make_ticket(), store, client)

    result = sync_cluster(make_cluster(count=7), make_ticket(), store, FailingJiraClient())

    assert result.action == "failed"
    # Last successful sync's count is preserved, not silently advanced.
    assert store.get_ticket("login", "bug") == ("RP-1", 4)
