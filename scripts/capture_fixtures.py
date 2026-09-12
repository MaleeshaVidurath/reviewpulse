"""One-off script: freeze a reproducible sample of the Spotify CSV export to
tests/fixtures/review_corpus.json, so the rest of the project (triage
evaluation, the demo video's --replay mode, tests) works against a small,
stable corpus rather than the full 80k+ row CSV. Re-run manually whenever
you want to refresh the sample -- not part of the regular pipeline.

Reads the CSV directly (not through spotify_csv.fetch_reviews(), which only
takes bounded chunks now) since this script's whole job is a one-off full
scan of the file -- exactly the "load it all" case the production adapter
deliberately no longer supports.
"""

from __future__ import annotations

import csv
import json
import random
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from reviewpulse.sources.spotify_csv import DEFAULT_CSV_PATH, parse_row

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
SAMPLE_SIZE = 2000
SEED = 7


def _default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"not serializable: {o!r}")


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    with DEFAULT_CSV_PATH.open(newline="", encoding="utf-8") as f:
        reviews = [r for row in csv.DictReader(f) if (r := parse_row(row)) is not None]

    random.seed(SEED)
    sample = random.sample(reviews, min(SAMPLE_SIZE, len(reviews)))

    out_path = FIXTURES_DIR / "review_corpus.json"
    payload = [asdict(r) for r in sample]
    # `raw` is the full CSV row dict, kept for debugging but not needed by
    # anything downstream -- strip it to keep the fixture file readable.
    for row in payload:
        row.pop("raw", None)

    out_path.write_text(json.dumps(payload, default=_default, indent=2), encoding="utf-8")
    print(f"Wrote {len(sample)} reviews (of {len(reviews)} total) to {out_path}")


if __name__ == "__main__":
    main()
