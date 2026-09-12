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

CREATE TABLE IF NOT EXISTS triage (
    source TEXT NOT NULL,
    source_review_id TEXT NOT NULL,
    sentiment TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    feature_area TEXT NOT NULL,
    summary TEXT NOT NULL,
    app_version TEXT,
    rating INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    model_id TEXT NOT NULL,
    triaged_at TEXT NOT NULL,
    PRIMARY KEY (source, source_review_id)
);

CREATE INDEX IF NOT EXISTS idx_triage_grouping
    ON triage (feature_area, category);

CREATE TABLE IF NOT EXISTS tickets (
    feature_area TEXT NOT NULL,
    category TEXT NOT NULL,
    jira_issue_key TEXT NOT NULL,
    review_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (feature_area, category)
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

    # --- triage cache -----------------------------------------------------
    # Classification is the one stage every review passes through, so it's
    # what actually costs money. Nothing is ever classified twice.

    def filter_untriaged(self, reviews: list[RawReview]) -> list[RawReview]:
        if not reviews:
            return []
        cur = self._conn.cursor()
        out = []
        for r in reviews:
            cur.execute(
                "SELECT 1 FROM triage WHERE source = ? AND source_review_id = ?",
                (r.source, r.source_review_id),
            )
            if cur.fetchone() is None:
                out.append(r)
        return out

    def save_triage(self, paired: list[tuple[RawReview, object]], model_id: str) -> int:
        """Persist (review, verdict) pairs. `verdict` is a ReviewTriage but is
        typed loosely here so the store doesn't import the agent layer.
        """
        if not paired:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (
                r.source,
                r.source_review_id,
                v.sentiment,
                v.category,
                v.severity,
                v.feature_area,
                v.summary,
                r.app_version,
                r.rating,
                r.updated_at.isoformat(),
                model_id,
                now,
            )
            for r, v in paired
        ]
        self._conn.executemany(
            """
            INSERT INTO triage (
                source, source_review_id, sentiment, category, severity,
                feature_area, summary, app_version, rating,
                updated_at, model_id, triaged_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, source_review_id) DO NOTHING
            """,
            rows,
        )
        self._conn.commit()
        return len(rows)

    def triage_counts(self) -> dict[str, int]:
        """Distribution across categories -- used by the eval script and,
        later, as the input to clustering.
        """
        cur = self._conn.cursor()
        cur.execute("SELECT category, COUNT(*) FROM triage GROUP BY category ORDER BY 2 DESC")
        return dict(cur.fetchall())

    def triaged_rows(self, limit: int | None = None) -> list[dict]:
        """Rows ordered oldest-triaged-first -- crisis detection depends on
        this order to define its "most recent window" of reviews.
        """
        cur = self._conn.cursor()
        sql = """
            SELECT source_review_id, rating, sentiment, category,
                   severity, feature_area, summary, app_version
            FROM triage
            ORDER BY triaged_at ASC
        """
        if limit:
            sql += f" LIMIT {int(limit)}"
        cur.execute(sql)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    # --- ticket sync --------------------------------------------------------
    # Dedup key is (feature_area, category) -- the same key clustering
    # already groups by. This is what makes a cluster map to exactly one
    # Jira issue for the life of the local store, instead of a new issue
    # every time the same cluster gets synced again.

    def get_ticket(self, feature_area: str, category: str) -> tuple[str, int] | None:
        """Return (jira_issue_key, review_count_at_last_sync), or None if
        this cluster has never been synced.
        """
        cur = self._conn.cursor()
        cur.execute(
            "SELECT jira_issue_key, review_count FROM tickets WHERE feature_area = ? AND category = ?",
            (feature_area, category),
        )
        row = cur.fetchone()
        return (row[0], row[1]) if row else None

    def save_ticket(self, feature_area: str, category: str, jira_issue_key: str, review_count: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO tickets (feature_area, category, jira_issue_key, review_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(feature_area, category)
            DO UPDATE SET jira_issue_key = excluded.jira_issue_key,
                          review_count = excluded.review_count,
                          updated_at = excluded.updated_at
            """,
            (feature_area, category, jira_issue_key, review_count, now, now),
        )
        self._conn.commit()
