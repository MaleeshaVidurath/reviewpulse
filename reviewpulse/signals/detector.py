"""Crisis detection: pure statistical burst-detection on the triaged
review stream. No LLM involved in detection itself -- only once a burst
trips does the (rare, low-volume) escalation-drafting stage in
reviewpulse.signals.escalation run Sonnet.

Detection compares the negative-sentiment rate in the most recent
`window_size` triaged reviews against the baseline rate from everything
triaged before that window. A burst is flagged when:
  - the recent window is full-sized and there's enough baseline history
    to compare against (otherwise there's nothing meaningful to compare)
  - the recent negative rate clears an absolute floor (min_negative_rate)
    -- without this, a baseline near zero would make even a couple of
    negative reviews register as an "infinite" multiple of the baseline
  - the recent rate is at least `baseline_multiplier` times the baseline
    rate (or the baseline is exactly zero and the recent rate isn't)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from reviewpulse.config import (
    CRISIS_BASELINE_MULTIPLIER,
    CRISIS_MIN_BASELINE_SIZE,
    CRISIS_MIN_NEGATIVE_RATE,
    CRISIS_WINDOW_SIZE,
)


@dataclass
class CrisisSignal:
    triggered: bool
    window_size: int
    recent_negative_rate: float
    baseline_negative_rate: float
    recent_negative_reviews: list[dict] = field(repr=False)


def _negative_rate(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if r["sentiment"] == "negative") / len(rows)


def detect_crisis(
    rows: list[dict],
    window_size: int = CRISIS_WINDOW_SIZE,
    baseline_multiplier: float = CRISIS_BASELINE_MULTIPLIER,
    min_baseline_size: int = CRISIS_MIN_BASELINE_SIZE,
    min_negative_rate: float = CRISIS_MIN_NEGATIVE_RATE,
) -> CrisisSignal:
    """`rows` must be chronologically ordered oldest-first (see
    SqliteReviewStore.triaged_rows()). Cheap and pure -- safe to call every
    tick regardless of whether anything actually triggers.
    """
    recent_rows = rows[-window_size:] if rows else []
    baseline_rows = rows[:-window_size] if len(rows) > window_size else []

    recent_rate = _negative_rate(recent_rows)
    baseline_rate = _negative_rate(baseline_rows)
    recent_negative_reviews = [r for r in recent_rows if r["sentiment"] == "negative"]

    enough_history = len(recent_rows) == window_size and len(baseline_rows) >= min_baseline_size
    rate_floor_cleared = recent_rate >= min_negative_rate
    is_burst = recent_rate > 0 if baseline_rate == 0 else recent_rate >= baseline_rate * baseline_multiplier

    triggered = enough_history and rate_floor_cleared and is_burst

    return CrisisSignal(
        triggered=triggered,
        window_size=window_size,
        recent_negative_rate=recent_rate,
        baseline_negative_rate=baseline_rate,
        recent_negative_reviews=recent_negative_reviews,
    )
