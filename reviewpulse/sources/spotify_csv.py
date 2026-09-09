from __future__ import annotations

import csv
import itertools
from datetime import datetime, timezone
from pathlib import Path

from reviewpulse.sources.base import FetchResult, FetchStatus, RawReview

DEFAULT_CSV_PATH = Path(__file__).parent / "spotify_reviews.csv"


def parse_row(row: dict) -> RawReview | None:
    review_id = row.get("reviewId")
    if not review_id:
        return None
    try:
        rating = int(row["score"])
    except (KeyError, TypeError, ValueError):
        return None

    at = row.get("at")
    try:
        updated_at = datetime.fromisoformat(at) if at else datetime.now(timezone.utc)
    except ValueError:
        updated_at = datetime.now(timezone.utc)
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    return RawReview(
        source="spotify_csv",
        source_review_id=review_id,
        author=row.get("userName", ""),
        title="",
        body=(row.get("content") or "").strip(),
        rating=rating,
        app_version=row.get("appVersion") or row.get("reviewCreatedVersion") or None,
        updated_at=updated_at,
        raw=row,
    )


def fetch_reviews(csv_path: Path = DEFAULT_CSV_PATH, *, offset: int = 0, limit: int) -> FetchResult:
    try:
        with csv_path.open(newline="", encoding="utf-8") as f:
            rows = csv.DictReader(f)
            sliced = itertools.islice(rows, offset, offset + limit)
            reviews = [r for row in sliced if (r := parse_row(row)) is not None]
    except OSError as exc:
        return FetchResult(status=FetchStatus.ERROR, reviews=[], detail=str(exc))

    return FetchResult(status=FetchStatus.OK, reviews=reviews)
