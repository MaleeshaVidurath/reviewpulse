"""Storage interface for deduping reviews.

Same pattern as `sources.base.ReviewSource`: a small Protocol so the local
SQLite implementation (used through local development) and a future
DynamoDB implementation are interchangeable everywhere else in the
pipeline.
"""

from __future__ import annotations

from typing import Protocol

from reviewpulse.sources.base import RawReview


class ReviewStore(Protocol):
    def filter_new(self, reviews: list[RawReview]) -> list[RawReview]:
        """Return only the reviews not already recorded, and record all of
        them (new + already-seen) as seen. Dedupe key is
        (source, source_review_id).
        """
        ...
