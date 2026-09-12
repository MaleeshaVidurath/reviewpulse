"""Manual round: draft engineering tickets for clusters that have crossed
CLUSTER_MIN_SIZE, and optionally sync them to Jira. Grouping itself
(reviewpulse.agents.cluster.build_clusters) is free and runs every time;
drafting a title/description per cluster is a Sonnet call, and syncing
writes to a real Jira project -- so, same philosophy as
scripts/demo_loop.py's triage step, this is a deliberate, manually-run
command, not something on a schedule.

    python scripts/draft_tickets.py                  # draft only, print, no Jira writes
    python scripts/draft_tickets.py --sync            # also create/update Jira issues
    python scripts/draft_tickets.py --min-size 5      # raise the threshold for this run
    python scripts/draft_tickets.py --limit 3         # only process the top 3 clusters (by size)

Requires JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY set as
environment variables when --sync is passed (see reviewpulse/config.py).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from reviewpulse.agents.cluster import build_clusters, draft_ticket
from reviewpulse.config import CLUSTER_MIN_SIZE
from reviewpulse.jira.sync import sync_cluster
from reviewpulse.store.sqlite_store import SqliteReviewStore


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Draft tickets for clusters above threshold")
    parser.add_argument("--min-size", type=int, default=CLUSTER_MIN_SIZE)
    parser.add_argument("--limit", type=int, default=None, help="only process the top N clusters")
    parser.add_argument("--sync", action="store_true", help="also create/update Jira issues")
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args(argv)

    client = None
    if args.sync:
        from reviewpulse.jira.client import JiraClient
        client = JiraClient.from_env()

    store = SqliteReviewStore(**({"db_path": args.db} if args.db else {}))

    try:
        clusters = build_clusters(store.triaged_rows(), min_size=args.min_size)
        if not clusters:
            print(f"No clusters have reached min_size={args.min_size} yet.")
            return 0

        print(f"{len(clusters)} cluster(s) at or above min_size={args.min_size}:\n")
        for cluster in clusters[: args.limit]:
            print(f"[{cluster.feature_area}/{cluster.category}] "
                  f"{cluster.count} reviews, severities={cluster.severity_counts}")

            ticket = draft_ticket(cluster)
            if ticket is None:
                print("    (ticket draft failed -- see log)")
                print()
                continue

            print(f"    title: {ticket.title}")
            print(f"    description: {ticket.description}")

            if args.sync:
                result = sync_cluster(cluster, ticket, store, client)
                if result.action == "created":
                    print(f"    -> created {result.issue_key}")
                elif result.action == "commented":
                    print(f"    -> commented on {result.issue_key}")
                elif result.action == "unchanged":
                    print(f"    -> unchanged, {result.issue_key} already up to date")
                else:
                    print(f"    -> sync failed: {result.detail}")
            print()
    finally:
        store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
