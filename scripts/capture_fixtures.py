"""One-off script: pull a real review corpus from the Apple feed and freeze
it to tests/fixtures/ so the rest of the project (triage evaluation, the
demo video's --replay mode, tests) never depends on a live, throttle-prone
API. Re-run manually whenever you want to refresh the corpus -- not part
of the regular pipeline.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from reviewpulse.sources.apple_rss import AppleFeedTarget, fetch_many

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

# A handful of real, high-review-volume apps across a couple of categories,
# so the fixture corpus has a realistic mix of bug reports, praise, and
# feature requests rather than one app's idiosyncrasies.
TARGETS = [
    AppleFeedTarget(app_id="310633997", country="us"),   # WhatsApp
    AppleFeedTarget(app_id="310633997", country="gb"),
    AppleFeedTarget(app_id="284882215", country="us"),   # Facebook
    AppleFeedTarget(app_id="333903271", country="us"),   # Twitter/X
]


def _default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"not serializable: {o!r}")


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    reviews, throttled = fetch_many(TARGETS, max_pages=10)

    if throttled:
        print(f"WARNING: throttled on {len(throttled)} target(s): {throttled}")

    out_path = FIXTURES_DIR / "review_corpus.json"
    payload = [asdict(r) for r in reviews]
    # `raw` is the full Apple entry dict, kept for debugging but not needed
    # by anything downstream -- strip it to keep the fixture file readable.
    for row in payload:
        row.pop("raw", None)

    out_path.write_text(json.dumps(payload, default=_default, indent=2), encoding="utf-8")
    print(f"Wrote {len(reviews)} reviews to {out_path}")

    by_app = {}
    for r in reviews:
        by_app.setdefault((r.app_id, r.country), 0)
        by_app[(r.app_id, r.country)] += 1
    for key, count in by_app.items():
        print(f"  {key}: {count}")


if __name__ == "__main__":
    main()
