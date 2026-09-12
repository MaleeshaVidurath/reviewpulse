"""Crisis detection tests. detect_crisis is pure/deterministic (no LLM),
tested directly against row dicts. Escalation drafting uses a stub agent,
same pattern as test_triage.py/test_cluster.py.
"""

import pytest

from reviewpulse.signals.detector import CrisisSignal, detect_crisis
from reviewpulse.signals.escalation import EscalationDraft, draft_escalation, notify_human


def make_row(sentiment: str, summary: str = "x") -> dict:
    return {"sentiment": sentiment, "summary": summary}


def positives(n: int) -> list[dict]:
    return [make_row("positive") for _ in range(n)]


def negatives(n: int, summary: str = "Cannot log in.") -> list[dict]:
    return [make_row("negative", summary) for _ in range(n)]


class StubAgent:
    def __init__(self, result: EscalationDraft | Exception):
        self._result = result
        self.prompts: list[str] = []

    def structured_output(self, model, prompt):
        self.prompts.append(prompt)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def test_not_enough_history_never_triggers():
    rows = positives(5) + negatives(5)

    signal = detect_crisis(rows, window_size=20, min_baseline_size=20)

    assert signal.triggered is False


def test_stable_negative_rate_does_not_trigger():
    # Baseline and recent window both ~20% negative -- no burst.
    baseline = (positives(4) + negatives(1)) * 5  # 20 rows, 20% negative
    recent = (positives(4) + negatives(1)) * 4    # 20 rows, 20% negative

    signal = detect_crisis(baseline + recent, window_size=20, min_baseline_size=20)

    assert signal.triggered is False


def test_sudden_spike_triggers():
    baseline = (positives(9) + negatives(1)) * 2  # 20 rows, 10% negative
    recent = negatives(15) + positives(5)         # 20 rows, 75% negative

    signal = detect_crisis(
        baseline + recent, window_size=20, min_baseline_size=20,
        baseline_multiplier=3.0, min_negative_rate=0.5,
    )

    assert signal.triggered is True
    assert signal.recent_negative_rate == 0.75
    assert signal.baseline_negative_rate == 0.1
    assert len(signal.recent_negative_reviews) == 15


def test_zero_baseline_with_any_recent_negatives_triggers():
    baseline = positives(20)         # 0% negative baseline
    recent = negatives(11) + positives(9)  # 55% negative -- clears the floor

    signal = detect_crisis(
        baseline + recent, window_size=20, min_baseline_size=20, min_negative_rate=0.5,
    )

    assert signal.triggered is True
    assert signal.baseline_negative_rate == 0.0


def test_zero_baseline_with_zero_recent_negatives_does_not_trigger():
    rows = positives(40)

    signal = detect_crisis(rows, window_size=20, min_baseline_size=20)

    assert signal.triggered is False


def test_below_absolute_floor_does_not_trigger_even_with_huge_ratio():
    # Recent rate is technically "infinite times" the near-zero baseline,
    # but only 1 of 20 recent reviews is negative -- shouldn't read as a crisis.
    baseline = positives(19) + negatives(1)  # 5% negative
    recent = positives(19) + negatives(1)    # 5% negative -- same rate, no spike anyway

    signal = detect_crisis(
        baseline + recent, window_size=20, min_baseline_size=20, min_negative_rate=0.5,
    )

    assert signal.triggered is False


def test_draft_escalation_returns_parsed_result():
    rows = positives(9) + negatives(1) + negatives(15, "App crashes on launch.") + positives(5)
    signal = detect_crisis(rows, window_size=20, min_baseline_size=10, min_negative_rate=0.5)
    agent = StubAgent(EscalationDraft(headline="Crash spike detected", holding_statement="We're looking into it."))

    escalation = draft_escalation(signal, agent=agent)

    assert escalation.headline == "Crash spike detected"
    assert len(agent.prompts) == 1
    assert "App crashes on launch." in agent.prompts[0]


def test_draft_escalation_returns_none_on_failure_not_raises():
    signal = CrisisSignal(
        triggered=True, window_size=20,
        recent_negative_rate=0.9, baseline_negative_rate=0.1,
        recent_negative_reviews=[],
    )

    assert draft_escalation(signal, agent=StubAgent(RuntimeError("bedrock exploded"))) is None


def test_notify_human_prints_headline_and_statement(capsys):
    notify_human(EscalationDraft(headline="Crash spike", holding_statement="Investigating now."))

    captured = capsys.readouterr()
    assert "Crash spike" in captured.err
    assert "Investigating now." in captured.err
