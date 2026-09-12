"""Ticket-sync stage: turn a cluster's drafted ticket into a real Jira
issue, or update the existing one if this cluster has already been synced.

Dedup key is (feature_area, category) -- the same key clustering already
groups by -- tracked in the store's `tickets` table, not by searching Jira.
This means a cluster maps to exactly one Jira issue for the life of the
local store: re-syncing never creates a duplicate issue, it comments with
the delta instead, and does nothing at all if nothing changed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from reviewpulse.agents.cluster import Cluster, TicketDraft

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    feature_area: str
    category: str
    action: str  # "created" | "commented" | "unchanged" | "failed"
    issue_key: str | None = None
    detail: str | None = None


def sync_cluster(cluster: Cluster, ticket: TicketDraft, store, client) -> SyncResult:
    """Create or update the Jira issue for one cluster. Never raises -- a
    failed Jira call is logged and reported as action="failed" so it
    doesn't abort a run over several clusters.
    """
    existing = store.get_ticket(cluster.feature_area, cluster.category)

    try:
        if existing is None:
            issue_key = client.create_issue(ticket.title, ticket.description)
            store.save_ticket(cluster.feature_area, cluster.category, issue_key, cluster.count)
            return SyncResult(cluster.feature_area, cluster.category, "created", issue_key)

        issue_key, last_synced_count = existing
        if cluster.count <= last_synced_count:
            return SyncResult(cluster.feature_area, cluster.category, "unchanged", issue_key)

        new_count = cluster.count - last_synced_count
        client.add_comment(
            issue_key,
            f"{new_count} more review(s) reported this issue since the last sync "
            f"(total {cluster.count}).",
        )
        store.save_ticket(cluster.feature_area, cluster.category, issue_key, cluster.count)
        return SyncResult(cluster.feature_area, cluster.category, "commented", issue_key)
    except Exception as exc:  # noqa: BLE001 - one cluster's Jira failure shouldn't abort the run
        logger.error("ticket sync failed for %s/%s: %s", cluster.feature_area, cluster.category, exc)
        return SyncResult(cluster.feature_area, cluster.category, "failed", detail=str(exc))
