"""Libro consistente a partir de MarketEvent (ENG-04). El libro solo se publica al cierre de evento
(`F_LAST`, ADR-003); los registros intermedios de un mismo paquete no son un estado observable."""

from __future__ import annotations

from dataclasses import dataclass

from trading_scanner.contracts import BookLevel, EventType, MarketEvent


@dataclass(frozen=True)
class BookSnapshot:
    contract_id: str
    as_of_ns: int  # available_at del evento que lo cerró
    ts_event_ns: int
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    sequence: int | None

    @property
    def best_bid(self) -> int | None:
        return self.bids[0].price_ticks if self.bids else None

    @property
    def best_ask(self) -> int | None:
        return self.asks[0].price_ticks if self.asks else None

    @property
    def spread_ticks(self) -> int | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    @property
    def crossed(self) -> bool:
        s = self.spread_ticks
        return s is not None and s <= 0

    @property
    def complete(self) -> bool:
        return bool(self.bids) and bool(self.asks)

    def depth_imbalance(self, levels: int = 5) -> float | None:
        """F11: (bid_qty - ask_qty) / (bid_qty + ask_qty) sobre los primeros `levels`. None si denominador 0."""
        b = sum(l.size_contracts for l in self.bids[:levels])
        a = sum(l.size_contracts for l in self.asks[:levels])
        if b + a == 0:
            return None
        return (b - a) / (b + a)


class BookTracker:
    """Mantiene el último libro cerrado por contrato. No corrige anomalías: las expone (crossed, incomplete)."""

    def __init__(self, contract_id: str) -> None:
        self.contract_id = contract_id
        self._pending: MarketEvent | None = None
        self.snapshot: BookSnapshot | None = None
        self.last_available_ns: int | None = None
        self.resets = 0
        self.closed_events = 0

    def apply(self, ev: MarketEvent) -> BookSnapshot | None:
        """Devuelve un snapshot nuevo solo cuando el evento cierra (F_LAST) un paquete de libro/trade."""
        if ev.contract_id != self.contract_id:
            raise ValueError(f"evento de {ev.contract_id} en tracker de {self.contract_id}")
        self.last_available_ns = ev.available_at_ns
        if ev.event_type is EventType.STATUS:
            return None
        if ev.event_type is EventType.RESET:
            self.resets += 1
            self.snapshot = None
            self._pending = None
        if ev.event_type in (EventType.BOOK, EventType.TRADE, EventType.RESET, EventType.CORRECTION):
            self._pending = ev
        if "F_LAST" in ev.quality_flags and self._pending is not None:
            self.snapshot = BookSnapshot(
                contract_id=self.contract_id, as_of_ns=ev.available_at_ns, ts_event_ns=ev.ts_event_ns,
                bids=ev.bid_levels, asks=ev.ask_levels, sequence=ev.sequence,
            )
            self._pending = None
            self.closed_events += 1
            return self.snapshot
        return None
