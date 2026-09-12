"""Central configuration. Model IDs live here rather than inline at call
sites so the two-tier routing (cheap model for volume, capable model for
judgment) stays visible in one place and is easy to re-point.

The Bedrock model IDs below were read off this account with:

    aws bedrock list-foundation-models --region us-west-2 \
        --query "modelSummaries[?contains(modelId,'anthropic')].modelId"

They are region- and account-specific -- don't copy IDs from blog posts.
Both need the `us.` cross-region inference profile prefix on this account
(a bare model ID fails with "on-demand throughput isn't supported" --
confirmed via `aws bedrock list-inference-profiles`). Verified 2026-09-12:
`anthropic.claude-sonnet-5` itself returns AccessDeniedException on this
account ("not available for this account") even though it's listed --
Bedrock model access is granted per model, separately from being listed --
so REASONING_MODEL_ID uses sonnet-4-6 instead, which this account can
actually invoke.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Loads .env into the process environment if present (see .env.example).
# Never overrides a variable already set in the real environment.
load_dotenv()

AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")

# Bulk classification: every new review goes through this model, so it's the
# one that actually drives cost. Haiku is the right tier for a constrained
# labeling task with a fixed output schema.
TRIAGE_MODEL_ID = os.environ.get(
    "REVIEWPULSE_TRIAGE_MODEL",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
)

# Judgment calls on a much smaller number of items: deciding whether two
# clusters are really the same issue, and drafting a crisis escalation a
# human will act on. Low volume, high consequence -- worth the better model.
REASONING_MODEL_ID = os.environ.get(
    "REVIEWPULSE_REASONING_MODEL",
    "us.anthropic.claude-sonnet-4-6",
)

# Reviews per triage call. Larger batches amortize the system prompt across
# more reviews (cheaper) but raise the blast radius of one malformed
# response and push toward the model's output limit. Matches
# scripts/demo_loop.py's default --chunk-size so one manual round (--once)
# is exactly one Bedrock call.
TRIAGE_BATCH_SIZE = int(os.environ.get("REVIEWPULSE_TRIAGE_BATCH_SIZE", "50"))

# Truncation guard for a single review body. Sources generally cap review
# text well below this, but a pathological entry shouldn't be able to blow
# out a batch's token count.
MAX_REVIEW_CHARS = 1200

# A (feature_area, category) group needs at least this many triaged reviews
# before it's surfaced as a cluster worth a ticket. Below this, one-off
# reports aren't worth an engineer's attention yet.
CLUSTER_MIN_SIZE = int(os.environ.get("REVIEWPULSE_CLUSTER_MIN_SIZE", "3"))

# Crisis detection: compares the negative-sentiment rate in the most recent
# CRISIS_WINDOW_SIZE triaged reviews against the baseline rate from
# everything triaged before that window. A burst is flagged when the
# recent rate is at least CRISIS_BASELINE_MULTIPLIER times the baseline
# (or the baseline is zero and the recent rate isn't) AND the recent rate
# itself clears CRISIS_MIN_NEGATIVE_RATE -- that floor exists so a handful
# of negative reviews in a still-mostly-positive window doesn't count as a
# "burst" just because the account's history happens to be very clean.
CRISIS_WINDOW_SIZE = int(os.environ.get("REVIEWPULSE_CRISIS_WINDOW_SIZE", "20"))
CRISIS_MIN_BASELINE_SIZE = int(os.environ.get("REVIEWPULSE_CRISIS_MIN_BASELINE_SIZE", "20"))
CRISIS_BASELINE_MULTIPLIER = float(os.environ.get("REVIEWPULSE_CRISIS_BASELINE_MULTIPLIER", "3.0"))
CRISIS_MIN_NEGATIVE_RATE = float(os.environ.get("REVIEWPULSE_CRISIS_MIN_NEGATIVE_RATE", "0.5"))

# Jira Cloud REST v3 credentials for ticket sync. No defaults -- these are
# per-account secrets, and reviewpulse.jira.client.JiraClient.from_env()
# raises a clear error listing exactly which of these are missing rather
# than silently pointing at the wrong instance.
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL")  # e.g. "https://yourteam.atlassian.net"
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")
JIRA_PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY")  # e.g. "RP"
