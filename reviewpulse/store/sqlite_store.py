"""Local SQLite-backed ReviewStore. Zero extra dependencies (stdlib sqlite3),
good enough for the whole local-development phase (Days 2-6). Swapped for
`store.dynamo.DynamoReviewStore` (same interface) only at the Day 7 AWS
deploy step -- nothing else in the pipeline needs to change.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from reviewpulse.sources.base import RawReview

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "reviewpulse.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_reviews (
    source TEXT NOT NULL,
    source_review_id TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    PRIMARY KEY (source, source_review_id)
);

CREATE TABLE IF NOT EXISTS watermarks (
    source TEXT NOT NULL,
    app_id TEXT NOT NULL,
    country TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    PRIMARY KEY (source, app_id, country)
);
"""


class SqliteReviewStore:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def filter_new(self, reviews: list[RawReview]) -> list[RawReview]:
        if not reviews:
            return []
        cur = self._conn.cursor()
        new_reviews = []
        now = datetime.now(timezone.utc).isoformat()
        for r in reviews:
            cur.execute(
                "SELECT 1 FROM seen_reviews WHERE source = ? AND source_review_id = ?",
                (r.source, r.source_review_id),
            )
            if cur.fetchone() is None:
                new_reviews.append(r)
                cur.execute(
                    "INSERT INTO seen_reviews (source, source_review_id, first_seen_at) VALUES (?, ?, ?)",
                    (r.source, r.source_review_id, now),
                )
        self._conn.commit()
        return new_reviews

    def get_watermark(self, source: str, app_id: str, country: str) -> datetime | None:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT last_updated_at FROM watermarks WHERE source = ? AND app_id = ? AND country = ?",
            (source, app_id, country),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return datetime.fromisoformat(row[0])

    def set_watermark(self, source: str, app_id: str, country: str, value: datetime) -> None:
        self._conn.execute(
            """
            INSERT INTO watermarks (source, app_id, country, last_updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source, app_id, country)
            DO UPDATE SET last_updated_at = excluded.last_updated_at
            """,
            (source, app_id, country, value.isoformat()),
        )
        self._conn.commit()
