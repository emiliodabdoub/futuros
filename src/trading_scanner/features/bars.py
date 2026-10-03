"""Barras de trades con intervalos [inicio, fin) y finalización con margen (spec §3.3, F02).

- La barra a la que pertenece un trade se decide por `ts_event` (tiempo de bolsa).
- Una barra se FINALIZA cuando se observa cualquier evento con `available_at >= fin + margen`
  (250 ms en el piloto) o cuando `flush(now)` lo indica. Después de finalizada no se reescribe.
- Un trade que llega tarde para una barra ya finalizada se cuenta en `late_revisions` y se conserva
  en `revisions` con flag; no modifica la barra publicada.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from trading_scanner.contracts import Aggressor

NS = 1_000_000_000


@dataclass
class Bar:
    start_ns: int
    end_ns: int
    open: int
    high: int
    low: int
    close: int
    volume: int = 0
    buy_volume: int = 0
    sell_volume: int = 0
    unknown_volume: int = 0
    trades: int = 0
    finalized_at_ns: int | None = None

    def add(self, price: int, size: int, aggressor: Aggressor) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += size
        self.trades += 1
        if aggressor is Aggressor.BUY:
            self.buy_volume += size
        elif aggressor is Aggressor.SELL:
            self.sell_volume += size
        else:
            self.unknown_volume += size

    @property
    def delta(self) -> int:
        return self.buy_volume - self.sell_volume


@dataclass
class BarBuilder:
    interval_ns: int
    finalize_margin_ns: int = 250_000_000
    on_finalize: Callable[[Bar], None] | None = None
    finalized: list[Bar] = field(default_factory=list)
    current: Bar | None = None
    late_revisions: int = 0
    revisions: list[tuple[int, int, int]] = field(default_factory=list)  # (bar_start, price, size)
    _last_finalized_end: int | None = None

    def _bar_start(self, ts_event_ns: int) -> int:
        return (ts_event_ns // self.interval_ns) * self.interval_ns

    def observe(self, available_at_ns: int) -> None:
        """Cualquier evento (trade o no) puede cerrar la barra en curso si ya pasó fin + margen."""
        while self.current is not None and available_at_ns >= self.current.end_ns + self.finalize_margin_ns:
            self._finalize(available_at_ns)

    def add_trade(self, ts_event_ns: int, available_at_ns: int, price: int, size: int, aggressor: Aggressor) -> None:
        self.observe(available_at_ns)
        start = self._bar_start(ts_event_ns)
        if self._last_finalized_end is not None and start < self._last_finalized_end:
            self.late_revisions += 1
            self.revisions.append((start, price, size))
            return
        if self.current is None or start != self.current.start_ns:
            if self.current is not None and start > self.current.start_ns:
                # trade de una barra posterior antes de que venza el margen: cierra la actual (nunca retrocede)
                self._finalize(available_at_ns)
            self.current = Bar(start_ns=start, end_ns=start + self.interval_ns, open=price, high=price, low=price, close=price)
        self.current.add(price, size, aggressor)

    def flush(self, now_ns: int) -> None:
        self.observe(now_ns)

    def _finalize(self, now_ns: int) -> None:
        assert self.current is not None
        bar = self.current
        bar.finalized_at_ns = now_ns
        self.finalized.append(bar)
        self._last_finalized_end = bar.end_ns
        self.current = None
        if self.on_finalize:
            self.on_finalize(bar)
