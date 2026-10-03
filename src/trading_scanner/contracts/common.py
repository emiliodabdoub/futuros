"""Enumeraciones y constantes compartidas."""

from enum import Enum

SCHEMA_VERSION = "1.0"


class EventType(str, Enum):
    TRADE = "TRADE"
    BOOK = "BOOK"
    STATUS = "STATUS"
    RESET = "RESET"
    CORRECTION = "CORRECTION"


class Aggressor(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    UNKNOWN = "UNKNOWN"


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class SetupKind(str, Enum):
    LIQUIDITY_REVERSAL = "LR"
    TREND_CONTINUATION = "TC"
    BREAKOUT = "BO"


class CandidateState(str, Enum):
    """Máquina de estados de la spec §5.2."""

    IDLE = "IDLE"
    ARMED = "ARMED"
    SWEPT = "SWEPT"
    RECLAIMED = "RECLAIMED"
    READY = "READY"
    PENDING_CLASSIFICATION = "PENDING_CLASSIFICATION"
    SELECTED = "SELECTED"
    REJECTED = "REJECTED"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


class TerminalReason(str, Enum):
    """Etiquetas de outcome de la spec §7.3."""

    TARGET_TRIGGERED = "TARGET_TRIGGERED"
    STOP_TRIGGERED = "STOP_TRIGGERED"
    TIME_EXIT = "TIME_EXIT"
    EMERGENCY_EXIT = "EMERGENCY_EXIT"
    NO_FILL = "NO_FILL"
    INVALID_DATA = "INVALID_DATA"
    UNPRICED_EXIT = "UNPRICED_EXIT"
