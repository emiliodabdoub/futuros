"""ENG-01: contratos internos del pipeline (spec §10)."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from trading_scanner.contracts import (
    Candidate,
    CandidateState,
    Direction,
    FeatureSnapshot,
    Outcome,
    SetupKind,
    StateTransition,
    TerminalReason,
)


def test_snapshot_rejects_future_inputs():
    with pytest.raises(ValidationError, match="as_of"):
        FeatureSnapshot(id="s1", as_of_ns=100, max_input_available_at_ns=101,
                        feature_version="f1", contract_spec_version="c1", values={}, units={})


def test_snapshot_null_feature_needs_reason():
    with pytest.raises(ValidationError, match="missing_reason"):
        FeatureSnapshot(id="s1", as_of_ns=100, max_input_available_at_ns=100,
                        feature_version="f1", contract_spec_version="c1",
                        values={"F05": None}, units={"F05": "ratio"})
    ok = FeatureSnapshot(id="s1", as_of_ns=100, max_input_available_at_ns=100,
                         feature_version="f1", contract_spec_version="c1",
                         values={"F05": None}, units={"F05": "ratio"},
                         missing_reasons={"F05": "denominator_zero"})
    assert ok.values["F05"] is None


def _cand(**over):
    base = dict(id="c1", source_event_id="e1", snapshot_id="s1", contract_id="ESZ4",
                setup_version="LR-v1", setup_kind=SetupKind.LIQUIDITY_REVERSAL,
                direction=Direction.LONG, stop_ticks=19995, target_rule="2R",
                entry_policy="EXEC-v1", created_at_ns=1_000, expires_at_ns=3_000)
    base.update(over)
    return Candidate(**base)


def test_candidate_state_history_monotonic_and_last_state():
    c = _cand(state_history=(
        StateTransition(state=CandidateState.ARMED, at_ns=10),
        StateTransition(state=CandidateState.SWEPT, at_ns=20),
        StateTransition(state=CandidateState.READY, at_ns=30),
    ))
    assert c.state is CandidateState.READY
    assert _cand().state is CandidateState.IDLE
    with pytest.raises(ValidationError, match="monótona"):
        _cand(state_history=(StateTransition(state=CandidateState.ARMED, at_ns=20),
                             StateTransition(state=CandidateState.SWEPT, at_ns=10)))


def test_candidate_ttl_must_be_positive():
    with pytest.raises(ValidationError):
        _cand(expires_at_ns=1_000)


def test_candidate_is_immutable():
    c = _cand()
    with pytest.raises(ValidationError):
        c.stop_ticks = 1  # type: ignore[misc]


def _out(**over):
    base = dict(candidate_id="c1", execution_policy_hash="h", simulated_or_observed="simulated",
                terminal_reason=TerminalReason.NO_FILL, label_start_ns=1, label_end_ns=2)
    base.update(over)
    return Outcome(**base)


def test_outcome_no_fill_has_no_fill_time():
    assert _out().fill_at_ns is None
    with pytest.raises(ValidationError, match="NO_FILL"):
        _out(fill_at_ns=5)


def test_outcome_pnl_requires_net_positive_flag():
    with pytest.raises(ValidationError, match="net_positive"):
        _out(terminal_reason=TerminalReason.TARGET_TRIGGERED, fill_at_ns=1, PnL_USD=Decimal("100"))
    o = _out(terminal_reason=TerminalReason.TARGET_TRIGGERED, fill_at_ns=1,
             PnL_USD=Decimal("-3.00"), net_positive=False)
    # la barrera que dispara no garantiza el signo del P&L (spec §7.3)
    assert o.terminal_reason is TerminalReason.TARGET_TRIGGERED and o.net_positive is False
