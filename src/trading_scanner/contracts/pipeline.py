"""Contratos internos del pipeline (spec §10). Todos inmutables (ADR-001 §8)."""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from trading_scanner.contracts.common import (
    CandidateState,
    Direction,
    SetupKind,
    TerminalReason,
)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FeatureSnapshot(_Frozen):
    id: str
    as_of_ns: int = Field(ge=0)
    max_input_available_at_ns: int = Field(ge=0)
    feature_version: str
    contract_spec_version: str
    values: dict[str, float | int | str | None]
    units: dict[str, str]
    missing_reasons: dict[str, str] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if self.max_input_available_at_ns > self.as_of_ns:
            raise ValueError("un snapshot no puede usar inputs disponibles después de as_of")
        for k, v in self.values.items():
            if v is None and k not in self.missing_reasons:
                raise ValueError(f"feature {k} es null sin missing_reason (ADR-001 §3)")


class StateTransition(_Frozen):
    state: CandidateState
    at_ns: int = Field(ge=0)
    reason: str | None = None


class Candidate(_Frozen):
    id: str
    source_event_id: str
    snapshot_id: str
    contract_id: str
    setup_version: str
    setup_kind: SetupKind
    direction: Direction
    level_id: str | None = None
    stop_ticks: int
    target_rule: str
    entry_policy: str
    created_at_ns: int = Field(ge=0)
    expires_at_ns: int = Field(ge=0)
    state_history: tuple[StateTransition, ...] = ()

    def model_post_init(self, __context: Any) -> None:
        if self.expires_at_ns <= self.created_at_ns:
            raise ValueError("expires_at debe ser posterior a created_at")
        prev = -1
        for t in self.state_history:
            if t.at_ns < prev:
                raise ValueError("state_history no es monótona en el tiempo")
            prev = t.at_ns

    @property
    def state(self) -> CandidateState:
        return self.state_history[-1].state if self.state_history else CandidateState.IDLE


class ClassificationResult(_Frozen):
    id: str
    candidate_id: str
    state_hash: str
    questions_hash: str
    requested_model: str
    resolved_model: str | None = None
    requested_at_ns: int = Field(ge=0)
    received_at_ns: int | None = Field(default=None, ge=0)
    distributions: dict[str, dict[str, float]] = Field(default_factory=dict)
    confidence_fields: dict[str, float] = Field(default_factory=dict)
    validation_status: str
    usage: dict[str, int] = Field(default_factory=dict)
    failure_reason: str | None = None


class Prediction(_Frozen):
    id: str
    candidate_id: str
    model_bundle_id: str
    calibration_id: str
    p_fill: float = Field(ge=0, le=1)
    p_outcomes_given_fill: dict[str, float]
    p_net_positive_given_fill: float = Field(ge=0, le=1)
    EV_USD: Decimal
    EV_R: float
    lower95_EV_R: float
    tail_R: float = Field(ge=0)
    RAEV_R: float
    support_status: str


class Decision(_Frozen):
    epoch_ns: int = Field(ge=0)
    candidate_ids: tuple[str, ...]
    excluded_reasons: dict[str, str] = Field(default_factory=dict)
    ordered_scores: tuple[tuple[str, float], ...] = ()
    selected_id_or_null: str | None = None
    action: str
    risk_snapshot_id: str
    policy_hash: str


class Outcome(_Frozen):
    candidate_id: str
    execution_policy_hash: str
    simulated_or_observed: str
    fill_at_ns: int | None = Field(default=None, ge=0)
    fill_price_ticks: int | None = None
    trigger_at_ns: int | None = Field(default=None, ge=0)
    exit_at_ns: int | None = Field(default=None, ge=0)
    exit_price_ticks: int | None = None
    terminal_reason: TerminalReason
    net_positive: bool | None = None
    costs_USD: Decimal = Decimal("0")
    PnL_USD: Decimal | None = None
    PnL_R: float | None = None
    label_start_ns: int = Field(ge=0)
    label_end_ns: int = Field(ge=0)
    data_quality: dict[str, Any] = Field(default_factory=dict)
    ambiguity_flags: tuple[str, ...] = ()

    def model_post_init(self, __context: Any) -> None:
        if self.label_end_ns < self.label_start_ns:
            raise ValueError("label_end anterior a label_start")
        if self.terminal_reason is TerminalReason.NO_FILL and self.fill_at_ns is not None:
            raise ValueError("NO_FILL no puede llevar fill_at")
        if self.PnL_USD is not None and self.net_positive is None:
            raise ValueError("net_positive debe declararse cuando hay PnL_USD")
