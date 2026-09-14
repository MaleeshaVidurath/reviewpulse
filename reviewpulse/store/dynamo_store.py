"""DynamoDB-backed ReviewStore -- same interface as SqliteReviewStore, but
state survives across separate invocations of stateless compute (Lambda,
AgentCore Runtime), unlike a SQLite file on local/ephemeral disk.

Tables (all PAY_PER_REQUEST, created once via `aws dynamodb create-table`,
not managed by this class):
    reviewpulse-seen     pk=review_key   -- dedupe
    reviewpulse-triage   pk=review_key   -- cached verdicts
    reviewpulse-tickets  pk=cluster_key  -- ticket-sync dedup
    reviewpulse-cursor   pk=cursor_id    -- CSV read offset, for the web API
"""

from __future__ import annotations

from datetime import datetime, timezone

import boto3

from reviewpulse.sources.base import RawReview


def _review_key(source: str, source_review_id: str) -> str:
    return f"{source}#{source_review_id}"


class DynamoReviewStore:
    def __init__(self, region_name: str = "us-west-2"):
        resource = boto3.resource("dynamodb", region_name=region_name)
        self._seen = resource.Table("reviewpulse-seen")
        self._triage = resource.Table("reviewpulse-triage")
        self._tickets = resource.Table("reviewpulse-tickets")
        self._cursor = resource.Table("reviewpulse-cursor")

    def close(self) -> None:
        pass  # boto3 resources need no explicit close

    def filter_new(self, reviews: list[RawReview]) -> list[RawReview]:
        if not reviews:
            return []
        now = datetime.now(timezone.utc).isoformat()
        new_reviews = []
        for r in reviews:
            key = _review_key(r.source, r.source_review_id)
            existing = self._seen.get_item(Key={"review_key": key}).get("Item")
            if existing is None:
                new_reviews.append(r)
                self._seen.put_item(Item={"review_key": key, "first_seen_at": now})
        return new_reviews

    # --- triage cache -------------------------------------------------------

    def filter_untriaged(self, reviews: list[RawReview]) -> list[RawReview]:
        if not reviews:
            return []
        out = []
        for r in reviews:
            key = _review_key(r.source, r.source_review_id)
            existing = self._triage.get_item(Key={"review_key": key}).get("Item")
            if existing is None:
                out.append(r)
        return out

    def save_triage(self, paired: list[tuple[RawReview, object]], model_id: str) -> int:
        if not paired:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        saved = 0
        for r, v in paired:
            key = _review_key(r.source, r.source_review_id)
            if self._triage.get_item(Key={"review_key": key}).get("Item"):
                continue  # first write wins, same as sqlite_store's ON CONFLICT DO NOTHING
            self._triage.put_item(Item={
                "review_key": key,
                "source": r.source,
                "source_review_id": r.source_review_id,
                "sentiment": v.sentiment,
                "category": v.category,
                "severity": v.severity,
                "feature_area": v.feature_area,
                "summary": v.summary,
                "app_version": r.app_version or "",
                "rating": r.rating,
                "updated_at": r.updated_at.isoformat(),
                "model_id": model_id,
                "triaged_at": now,
            })
            saved += 1
        return saved

    def triage_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.triaged_rows():
            counts[row["category"]] = counts.get(row["category"], 0) + 1
        return counts

    def triaged_rows(self, limit: int | None = None) -> list[dict]:
        items = []
        scan_kwargs = {}
        while True:
            resp = self._triage.scan(**scan_kwargs)
            items.extend(resp.get("Items", []))
            if "LastEvaluatedKey" not in resp:
                break
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

        items.sort(key=lambda i: i["triaged_at"])
        if limit:
            items = items[:limit]

        return [
            {
                "source_review_id": i["source_review_id"],
                "rating": int(i["rating"]),
                "sentiment": i["sentiment"],
                "category": i["category"],
                "severity": i["severity"],
                "feature_area": i["feature_area"],
                "summary": i["summary"],
                "app_version": i["app_version"],
            }
            for i in items
        ]

    # --- ticket sync ----------------------------------------------------------

    def get_ticket(self, feature_area: str, category: str) -> tuple[str, int] | None:
        key = f"{feature_area}#{category}"
        item = self._tickets.get_item(Key={"cluster_key": key}).get("Item")
        if item is None:
            return None
        return (item["jira_issue_key"], int(item["review_count"]))

    def save_ticket(self, feature_area: str, category: str, jira_issue_key: str, review_count: int) -> None:
        key = f"{feature_area}#{category}"
        now = datetime.now(timezone.utc).isoformat()
        existing = self._tickets.get_item(Key={"cluster_key": key}).get("Item")
        created_at = existing["created_at"] if existing else now
        self._tickets.put_item(Item={
            "cluster_key": key,
            "feature_area": feature_area,
            "category": category,
            "jira_issue_key": jira_issue_key,
            "review_count": review_count,
            "created_at": created_at,
            "updated_at": now,
        })

    # --- CSV read cursor (web API only; not part of ReviewStore protocol) ---

    def get_cursor(self, cursor_id: str = "default") -> int:
        item = self._cursor.get_item(Key={"cursor_id": cursor_id}).get("Item")
        return int(item["offset"]) if item else 0

    def save_cursor(self, offset: int, cursor_id: str = "default") -> None:
        self._cursor.put_item(Item={"cursor_id": cursor_id, "offset": offset})
