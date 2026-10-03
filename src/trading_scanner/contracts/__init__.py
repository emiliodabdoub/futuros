"""Contratos internos (ENG-01). Ver docs/adr/ADR-001."""

from trading_scanner.contracts.common import (
    SCHEMA_VERSION,
    Aggressor,
    CandidateState,
    Direction,
    EventType,
    SetupKind,
    TerminalReason,
)
from trading_scanner.contracts.instrument import ContractSpec
from trading_scanner.contracts.market_event import BookLevel, MarketEvent
from trading_scanner.contracts.pipeline import (
    Candidate,
    ClassificationResult,
    Decision,
    FeatureSnapshot,
    Outcome,
    Prediction,
    StateTransition,
)
from trading_scanner.contracts.units import (
    PriceNotOnGridError,
    price_to_ticks,
    ticks_to_price,
    ticks_to_usd,
)

__all__ = [
    "SCHEMA_VERSION",
    "Aggressor",
    "CandidateState",
    "Direction",
    "EventType",
    "SetupKind",
    "TerminalReason",
    "ContractSpec",
    "BookLevel",
    "MarketEvent",
    "Candidate",
    "ClassificationResult",
    "Decision",
    "FeatureSnapshot",
    "Outcome",
    "Prediction",
    "StateTransition",
    "PriceNotOnGridError",
    "price_to_ticks",
    "ticks_to_price",
    "ticks_to_usd",
]
