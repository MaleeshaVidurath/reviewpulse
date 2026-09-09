"""Storage interface for deduping reviews and tracking per-source watermarks.

Same pattern as `sources.base.ReviewSource`: a small Protocol so the local
SQLite implementation (used through Day 6) and the DynamoDB implementation
(added for the Day 7 AWS deploy) are interchangeable everywhere else in the
pipeline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from reviewpulse.sources.base import RawReview


class ReviewStore(Protocol):
    def filter_new(self, reviews: list[RawReview]) -> list[RawReview]:
        """Return only the reviews not already recorded, and record all of
        them (new + already-seen) as seen. Dedupe key is
        (source, source_review_id).
        """
        ...

    def get_watermark(self, source: str, app_id: str, country: str) -> datetime | None:
        """Last `updated_at` seen for this (source, app_id, country), or
        None if never fetched before.
        """
        ...

    def set_watermark(self, source: str, app_id: str, country: str, value: datetime) -> None:
        ...
