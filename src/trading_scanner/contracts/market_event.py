"""Evento de mercado normalizado (spec §3.2)."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trading_scanner.contracts.common import SCHEMA_VERSION, Aggressor, EventType


class BookLevel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    price_ticks: int
    size_contracts: int = Field(ge=0)
    order_count: int | None = Field(default=None, ge=0)


class MarketEvent(BaseModel):
    """Los validadores comprueban tipos y unidades. Anomalías de mercado (libro cruzado,
    tamaños raros) las marca el quality gate (ENG-04), no se corrigen aquí (ADR-001 §5)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = SCHEMA_VERSION
    source: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    channel_id: int | None = None
    sequence: int | None = Field(default=None, ge=0)
    record_index: int = Field(ge=0)
    ts_event_ns: int = Field(ge=0)
    ts_vendor_recv_ns: int | None = Field(default=None, ge=0)
    ts_local_recv_ns: int | None = Field(default=None, ge=0)
    available_at_ns: int = Field(ge=0)
    event_type: EventType
    price_ticks: int | None = None
    size_contracts: int | None = Field(default=None, ge=0)
    aggressor: Aggressor = Aggressor.UNKNOWN
    bid_levels: tuple[BookLevel, ...] = ()
    ask_levels: tuple[BookLevel, ...] = ()
    quality_flags: tuple[str, ...] = ()
    raw_partition_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def _invariants(self) -> "MarketEvent":
        if self.available_at_ns < self.ts_event_ns:
            raise ValueError("available_at_ns no puede ser anterior a ts_event_ns (ADR-001 §4)")
        if self.event_type is EventType.TRADE:
            if self.price_ticks is None or self.size_contracts is None:
                raise ValueError("TRADE requiere price_ticks y size_contracts")
            if self.size_contracts <= 0:
                raise ValueError("TRADE requiere size_contracts > 0")
        return self

    @property
    def best_bid_ticks(self) -> int | None:
        return self.bid_levels[0].price_ticks if self.bid_levels else None

    @property
    def best_ask_ticks(self) -> int | None:
        return self.ask_levels[0].price_ticks if self.ask_levels else None

    @property
    def spread_ticks(self) -> int | None:
        if self.best_bid_ticks is None or self.best_ask_ticks is None:
            return None
        return self.best_ask_ticks - self.best_bid_ticks
