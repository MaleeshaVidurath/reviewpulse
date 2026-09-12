"""Demo loop: simulates a live review feed by releasing the frozen Spotify
CSV in chunks over time instead of loading all ~84k rows at once. Not part
of the production pipeline -- exists so ingest -> dedupe -> triage can be
demoed as an ongoing agent process rather than a single static dump.

Each tick's new (post-dedupe) reviews are run through the triage stage
(reviewpulse.agents.triage) and cached in the store -- this makes real
Bedrock calls and needs AWS credentials with Bedrock access; see the
README's Setup section (`aws login`). Without credentials, triage fails
per-batch (logged, not fatal) and the tick falls back to printing the raw
reviews instead.

After triage, clusters are regrouped from everything triaged so far
(reviewpulse.agents.cluster.build_clusters) and any at/above
CLUSTER_MIN_SIZE are shown. This is free (no LLM call) and safe to run
every tick. Drafting an actual ticket title/description per cluster is a
separate Sonnet call and deliberately NOT done here automatically --
run scripts/draft_tickets.py by hand for that, same "manual round"
philosophy as this file's own triage step.

Crisis detection (reviewpulse.signals.detect_crisis) also runs every tick
-- free, pure statistics comparing the recent negative-review rate against
the historical baseline. Unlike ticket drafting, when it DOES trigger the
escalation draft (Sonnet) fires automatically rather than waiting for a
manual command: crises are rare by construction, so the cost is
negligible, and getting a human notified fast matters more here.

Production shape this stands in for: a scheduled trigger (AWS EventBridge)
invokes the pipeline periodically; a live source's `fetch(since)` returns
only what's new since the last run. Here there's no live upstream to poll,
so a persisted cursor over the CSV plays that role instead -- each tick
advances it and releases the next chunk.

    python scripts/demo_loop.py                                # 15-min interval, 50/chunk
    python scripts/demo_loop.py --interval 5 --chunk-size 20    # fast pacing for a live demo
    python scripts/demo_loop.py --once                          # single tick, no loop
    python scripts/demo_loop.py --reset                         # start over from the beginning
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from reviewpulse.agents.cluster import build_clusters
from reviewpulse.agents.triage import triage_reviews
from reviewpulse.config import TRIAGE_MODEL_ID
from reviewpulse.signals.detector import detect_crisis
from reviewpulse.signals.escalation import draft_escalation, notify_human
from reviewpulse.sources.spotify_csv import DEFAULT_CSV_PATH, fetch_reviews
from reviewpulse.store.sqlite_store import SqliteReviewStore

CURSOR_PATH = Path(__file__).resolve().parent.parent / "data" / "demo_cursor.json"


def _load_cursor(path: Path) -> int:
    if not path.exists():
        return 0
    return json.loads(path.read_text(encoding="utf-8")).get("offset", 0)


def _save_cursor(path: Path, offset: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"offset": offset}), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Simulate a live review feed from the Spotify CSV")
    parser.add_argument("--interval", type=float, default=900, help="seconds between ticks (default: 900 = 15 min)")
    parser.add_argument("--chunk-size", type=int, default=50, help="reviews released per tick")
    parser.add_argument("--once", action="store_true", help="run a single tick and exit")
    parser.add_argument("--reset", action="store_true", help="reset the cursor to the start of the CSV")
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.reset and CURSOR_PATH.exists():
        CURSOR_PATH.unlink()

    store = SqliteReviewStore(**({"db_path": args.db} if args.db else {}))

    try:
        while True:
            offset = _load_cursor(CURSOR_PATH)
            result = fetch_reviews(DEFAULT_CSV_PATH, offset=offset, limit=args.chunk_size)

            if result.status != "ok":
                print(f"WARNING: fetch failed: {result.detail}", file=sys.stderr)
                break
            if not result.reviews:
                print(f"[tick] offset={offset}: end of CSV reached, nothing left to release")
                break

            new_reviews = store.filter_new(result.reviews)
            _save_cursor(CURSOR_PATH, offset + len(result.reviews))

            print(f"[tick] offset={offset} released={len(result.reviews)} new={len(new_reviews)}")

            if new_reviews:
                paired = triage_reviews(new_reviews)
                saved = store.save_triage(paired, model_id=TRIAGE_MODEL_ID)
                print(f"    triaged={len(paired)} saved={saved}")
                for r, v in paired[:3]:
                    print(f"      {v.sentiment}/{v.category}/{v.severity} [{v.feature_area}]: {v.summary}")
                if not paired:
                    # Triage produced nothing (e.g. no Bedrock/AWS credentials) --
                    # show the raw reviews instead of a silent, empty tick.
                    for r in new_reviews[:3]:
                        print(f"      (untriaged) {r.rating}/5 {r.body[:80]!r}")

            triaged_rows = store.triaged_rows()

            clusters = build_clusters(triaged_rows)
            if clusters:
                print(f"    clusters at/above threshold: {len(clusters)}")
                for c in clusters[:3]:
                    print(f"      [{c.feature_area}/{c.category}] {c.count} reviews, "
                          f"severities={c.severity_counts}")

            signal = detect_crisis(triaged_rows)
            if signal.triggered:
                print(f"    CRISIS SIGNAL: {signal.recent_negative_rate:.0%} negative in last "
                      f"{signal.window_size} reviews (baseline {signal.baseline_negative_rate:.0%})")
                escalation = draft_escalation(signal)
                if escalation is None:
                    print("      (escalation draft failed -- see log)")
                else:
                    notify_human(escalation)

            if args.once:
                break
            time.sleep(args.interval)
    finally:
        store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
