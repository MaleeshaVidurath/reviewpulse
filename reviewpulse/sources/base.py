from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


@dataclass(frozen=True)
class RawReview:
    source: str 
    source_review_id: str
    author: str
    title: str
    body: str
    rating: int  # 1-5
    app_version: str | None
    updated_at: datetime
    url: str | None = None
    raw: dict = field(default_factory=dict, repr=False, compare=False)


class FetchStatus:
    OK = "ok"
    THROTTLED = "throttled"
    ERROR = "error"


@dataclass
class FetchResult:
    status: str 
    reviews: list[RawReview]
    detail: str | None = None


class ReviewSource(Protocol):

    name: str

    def fetch(self, since: datetime | None) -> FetchResult:     
        ...


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
