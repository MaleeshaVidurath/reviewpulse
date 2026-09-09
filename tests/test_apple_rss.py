"""Unit tests for the Apple RSS adapter, using saved fixture payloads so
they run offline and deterministically -- no dependency on Apple's live
feed or its throttling behavior.
"""

import json
from pathlib import Path

import pytest

from reviewpulse.sources.apple_rss import AppleFeedTarget, fetch_reviews
from reviewpulse.sources.base import FetchStatus

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """Returns a fixed sequence of canned responses, one per .get() call,
    regardless of URL -- enough to drive fetch_reviews's page loop.
    """

    def __init__(self, payloads: list[dict]):
        self._payloads = list(payloads)
        self.calls = 0

    def get(self, url, headers=None, timeout=None):
        self.calls += 1
        if not self._payloads:
            raise AssertionError("FakeSession ran out of canned responses")
        return FakeResponse(self._payloads.pop(0))


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_throttled_feed_is_reported_as_throttled_not_empty():
    """The exact payload captured from a throttled cloud-IP request:
    HTTP 200, zero entries, blank pagination links. Must be reported as
    THROTTLED, never as a clean "no new reviews" OK result.
    """
    session = FakeSession([load_fixture("apple_feed_throttled.json")])
    result = fetch_reviews(AppleFeedTarget(app_id="310633997", country="us"), session=session)

    assert result.status == FetchStatus.THROTTLED
    assert result.reviews == []


def test_end_of_real_pages_is_ok_not_throttled():
    """Past the last real page: zero entries, but first/last links are
    populated (pointing back at the real page range). This is a genuine
    "no more reviews" case and must NOT be flagged as throttled.
    """
    session = FakeSession([load_fixture("apple_feed_end_of_pages.json")])
    result = fetch_reviews(AppleFeedTarget(app_id="310633997", country="us"), session=session)

    assert result.status == FetchStatus.OK
    assert result.reviews == []


def test_sample_page_parses_expected_fields():
    session = FakeSession([
        load_fixture("apple_feed_sample_page.json"),
        load_fixture("apple_feed_end_of_pages.json"),
    ])
    result = fetch_reviews(AppleFeedTarget(app_id="310633997", country="us"), session=session)

    assert result.status == FetchStatus.OK
    assert len(result.reviews) == 2

    negative, positive = result.reviews
    assert negative.source == "apple_app_store"
    assert negative.source_review_id == "14512713110"
    assert negative.rating == 1
    assert negative.app_version == "26.34.74"
    assert negative.author == "Katy_Ph"
    assert "can't protect your data" in negative.body

    assert positive.rating == 5
    assert positive.source_review_id == "14513012601"


def test_throttle_mid_pagination_returns_partial_results():
    """If page 1 succeeds and page 2 is throttled, reviews already
    collected from page 1 must still be returned (status OK), not lost.
    """
    session = FakeSession([
        load_fixture("apple_feed_sample_page.json"),
        load_fixture("apple_feed_throttled.json"),
    ])
    result = fetch_reviews(AppleFeedTarget(app_id="310633997", country="us"), session=session, max_pages=5)

    assert result.status == FetchStatus.OK
    assert len(result.reviews) == 2
    assert result.detail and "throttled" in result.detail
