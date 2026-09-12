"""Run triage over a sample of the real fixture corpus and report what came
back, so the classifier's behaviour is a measured thing rather than an
assumption.

This costs real money (Bedrock calls), so it defaults to a small sample and
prints an estimate before running. Results are cached in the store, so
re-running only pays for reviews it hasn't already classified.

    python scripts/eval_triage.py --limit 100
    python scripts/eval_triage.py --limit 100 --dry-run   # no API calls
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

from reviewpulse.agents.triage import triage_reviews
from reviewpulse.cli import load_fixture_corpus
from reviewpulse.config import TRIAGE_BATCH_SIZE, TRIAGE_MODEL_ID
from reviewpulse.store.sqlite_store import SqliteReviewStore

CORPUS = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "review_corpus.json"
OUT_DIR = Path(__file__).resolve().parent.parent / "data"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Evaluate the triage stage")
    parser.add_argument("--limit", type=int, default=100, help="reviews to classify")
    parser.add_argument("--seed", type=int, default=7, help="sampling seed (reproducible)")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="show the plan, make no calls")
    args = parser.parse_args()

    corpus = load_fixture_corpus(CORPUS)
    random.seed(args.seed)
    sample = random.sample(corpus, min(args.limit, len(corpus)))

    store = SqliteReviewStore(**({"db_path": args.db} if args.db else {}))
    todo = store.filter_untriaged(sample)

    batches = (len(todo) + TRIAGE_BATCH_SIZE - 1) // TRIAGE_BATCH_SIZE
    print(f"corpus={len(corpus)} sample={len(sample)} already_triaged={len(sample) - len(todo)}")
    print(f"to classify: {len(todo)} reviews in {batches} batch(es) of {TRIAGE_BATCH_SIZE}")
    print(f"model: {TRIAGE_MODEL_ID}")

    if args.dry_run:
        print("\n--dry-run: no API calls made. Sample prompt for batch 1:\n")
        from reviewpulse.agents.triage import build_batch_prompt
        print(build_batch_prompt(todo[:2])[:1200])
        store.close()
        return 0

    if todo:
        paired = triage_reviews(todo)
        saved = store.save_triage(paired, model_id=TRIAGE_MODEL_ID)
        print(f"classified and stored: {saved} (of {len(todo)} attempted)")

    rows = store.triaged_rows()
    print(f"\n=== distribution over {len(rows)} triaged reviews ===")
    for field in ("category", "sentiment", "severity"):
        counts = Counter(r[field] for r in rows)
        print(f"\n{field}:")
        for value, n in counts.most_common():
            print(f"  {value:<16} {n:>4}  {n / len(rows) * 100:5.1f}%")

    areas = Counter(r["feature_area"] for r in rows)
    print(f"\nfeature_area (top 15 of {len(areas)} distinct):")
    for value, n in areas.most_common(15):
        print(f"  {value:<22} {n:>4}")

    # Sanity signal: a 1-star review classified as praise, or a 5-star as a
    # crash, is the kind of thing worth eyeballing before trusting the stage.
    suspicious = [
        r for r in rows
        if (r["rating"] <= 2 and r["sentiment"] == "positive")
        or (r["rating"] >= 4 and r["category"] in {"crash", "bug"} and r["severity"] in {"high", "critical"})
    ]
    print(f"\nrating/label mismatches worth eyeballing: {len(suspicious)}")
    for r in suspicious[:10]:
        print(f"  {r['rating']}/5 -> {r['sentiment']}/{r['category']}/{r['severity']}: {r['summary'][:70]}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "triage_eval.json"
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nfull results written to {out}")
    print("Review these by hand to get a real accuracy number for the pitch.")

    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
