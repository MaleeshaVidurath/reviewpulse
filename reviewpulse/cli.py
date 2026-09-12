"""Local runner for the ReviewPulse pipeline.

--replay   : load a frozen fixture corpus -- deterministic, offline, used
             for tests and the demo video.

For a live-feeling run against the Spotify CSV (chunked, on a schedule,
with a persisted cursor) use scripts/demo_loop.py instead -- fetch_reviews()
no longer supports loading the whole file in one call, so there's no
"--once, load everything" mode here anymore.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from reviewpulse.sources.base import RawReview
from reviewpulse.store.sqlite_store import SqliteReviewStore


def _review_from_fixture_row(row: dict) -> RawReview:
    row = dict(row)
    row["updated_at"] = datetime.fromisoformat(row["updated_at"])
    row.setdefault("raw", {})
    return RawReview(**row)


def load_fixture_corpus(path: Path) -> list[RawReview]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [_review_from_fixture_row(r) for r in rows]


def run_replay(path: Path, store: SqliteReviewStore) -> list[RawReview]:
    reviews = load_fixture_corpus(path)
    return store.filter_new(reviews)


def main(argv: list[str] | None = None) -> int:
    # Review text is real-world UTF-8 (curly quotes, emoji, etc.) and Windows
    # consoles default to a legacy codepage that can't render it -- degrade
    # gracefully instead of crashing the whole run over a print statement.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="ReviewPulse local runner")
    parser.add_argument("--replay", type=Path, required=True, help="replay a fixture corpus JSON file")
    parser.add_argument("--db", type=Path, default=None, help="path to local SQLite store")
    args = parser.parse_args(argv)

    store_kwargs = {"db_path": args.db} if args.db else {}
    store = SqliteReviewStore(**store_kwargs)

    new_reviews = run_replay(args.replay, store)
    mode = f"replay:{args.replay}"

    print(f"[{mode}] {len(new_reviews)} new review(s) after dedupe")
    for r in new_reviews[:5]:
        print(f"  {r.rating}/5 {r.title!r} - {r.body[:80]!r}")
    if len(new_reviews) > 5:
        print(f"  ... and {len(new_reviews) - 5} more")

    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
