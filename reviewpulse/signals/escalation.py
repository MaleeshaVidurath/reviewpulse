"""Escalation drafting: when detect_crisis() trips, draft a human-readable
alert and holding statement via the reasoning model.

Unlike cluster ticket drafting (deliberately manual, since it could fire
often), this runs automatically the moment a crisis is detected -- crises
are rare by construction (see detector.py's thresholds), so the Bedrock
cost here is negligible, and getting a human notified fast matters more
than keeping this manual.

notify_human() is a stub: the real pipeline would push this to SNS/email/
Slack (see docs/architecture.md), but that's not built -- this just prints
loudly so a crisis is impossible to miss in the terminal.
"""

from __future__ import annotations

import logging
import sys

from pydantic import BaseModel

from reviewpulse.config import AWS_REGION, REASONING_MODEL_ID
from reviewpulse.signals.detector import CrisisSignal

logger = logging.getLogger(__name__)

SAMPLE_SIZE = 10


class EscalationDraft(BaseModel):
    headline: str
    holding_statement: str


SYSTEM_PROMPT = """You draft an internal alert and a public-facing holding
statement when a sudden burst of negative app reviews is detected.

Given the recent vs. baseline negative-review rates and a sample of the
negative review summaries driving the burst, produce:
- headline: one sentence for an internal Slack/email alert to the team,
  naming the likely problem area if the samples make it clear
- holding_statement: 2-3 sentences, calm and factual, acknowledging the
  issue is being investigated. Suitable to post publicly if needed. Do not
  promise a specific fix, cause, or timeline the samples don't support.

Do not invent details not supported by the review summaries."""


def _build_agent(model_id: str):
    """Import Strands lazily so detection and offline tests don't need the
    SDK (or AWS credentials) loaded just to import this module.
    """
    from strands import Agent
    from strands.models import BedrockModel

    model = BedrockModel(model_id=model_id, region_name=AWS_REGION, temperature=0)
    return Agent(model=model, system_prompt=SYSTEM_PROMPT)


def _build_prompt(signal: CrisisSignal) -> str:
    samples = "\n".join(f"- {r['summary']}" for r in signal.recent_negative_reviews[:SAMPLE_SIZE])
    return (
        f"recent_negative_rate: {signal.recent_negative_rate:.0%} (last {signal.window_size} reviews)\n"
        f"baseline_negative_rate: {signal.baseline_negative_rate:.0%}\n"
        f"sample negative review summaries:\n{samples}"
    )


def draft_escalation(signal: CrisisSignal, agent=None, model_id: str = REASONING_MODEL_ID) -> EscalationDraft | None:
    """Draft an escalation for a triggered crisis signal. Returns None
    (doesn't raise) if the call fails -- a failed draft shouldn't crash
    whatever loop detected the crisis.
    """
    prompt = _build_prompt(signal)
    try:
        agent = agent or _build_agent(model_id)
        return agent.structured_output(EscalationDraft, prompt)
    except Exception as exc:  # noqa: BLE001 - a failed draft must not crash the caller
        logger.error("crisis escalation draft failed: %s", exc)
        return None


def notify_human(escalation: EscalationDraft) -> None:
    """Stub for the real notification channel (SNS/email/Slack -- not
    built). Prints loudly so a crisis can't be missed in the terminal.
    """
    print("\n" + "=" * 60, file=sys.stderr)
    print("CRISIS ESCALATION -- human review needed", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"Alert:    {escalation.headline}", file=sys.stderr)
    print(f"Holding statement:\n{escalation.holding_statement}", file=sys.stderr)
    print("=" * 60 + "\n", file=sys.stderr)
