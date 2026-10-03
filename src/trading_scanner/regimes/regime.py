"""Régimen determinista baseline y shock de volatilidad (spec §4.1).

TREND_UP si F13 >= 0.35 y F14 >= 1; TREND_DOWN si F13 >= 0.35 y F14 <= -1; RANGE si F13 <= 0.20;
resto TRANSITION. Sin warm-up → UNKNOWN. Un cambio se confirma con DOS cierres 5m consecutivos; los
estados anteriores no se reescriben. Shock: TR de la última barra 1m > 3 × ATR previo a esa barra →
bloquea entradas 5 min, extendidos si vuelve a ocurrir. La clasificación Jev se guarda aparte y no
puede alterar este régimen ni su hora de confirmación.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from trading_scanner.features.bars import Bar
from trading_scanner.features.indicators import atr_simple, efficiency_ratio, true_range

NS = 1_000_000_000


class Regime(str, Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    TRANSITION = "TRANSITION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RegimeParams:
    er_window: int = 12
    er_trend_min: float = 0.35
    er_range_max: float = 0.20
    slope_lag: int = 6
    slope_trend_min: float = 1.0
    atr5_period: int = 14
    confirm_closes: int = 2
    shock_mult: float = 3.0
    shock_block_ns: int = 5 * 60 * NS
    atr1_period: int = 14


@dataclass
class RegimeTracker:
    params: RegimeParams = field(default_factory=RegimeParams)
    regime: Regime = Regime.UNKNOWN
    confirmed_at_ns: int | None = None
    history: list[tuple[int, Regime]] = field(default_factory=list)
    shock_until_ns: int | None = None
    shocks: int = 0
    _pending: Regime | None = None
    _pending_count: int = 0
    last_er: float | None = None
    last_slope: float | None = None

    # ---- régimen por cierres 5m ----------------------------------------------------------------
    def on_bar_5m_close(self, bars_5m: list[Bar], closed_at_ns: int) -> Regime:
        p = self.params
        raw = self._classify(bars_5m)
        if raw is Regime.UNKNOWN:
            self._pending, self._pending_count = None, 0
            if self.regime is not Regime.UNKNOWN:
                self._set(Regime.UNKNOWN, closed_at_ns)
            return self.regime
        if raw is self.regime:
            self._pending, self._pending_count = None, 0
            return self.regime
        if raw is self._pending:
            self._pending_count += 1
        else:
            self._pending, self._pending_count = raw, 1
        if self._pending_count >= p.confirm_closes or self.regime is Regime.UNKNOWN:
            self._set(raw, closed_at_ns)
            self._pending, self._pending_count = None, 0
        return self.regime

    def _set(self, r: Regime, at: int) -> None:
        self.regime, self.confirmed_at_ns = r, at
        self.history.append((at, r))

    def _classify(self, bars: list[Bar]) -> Regime:
        p = self.params
        need = max(p.er_window, p.slope_lag + 1, p.atr5_period + 1)
        if len(bars) < need:
            return Regime.UNKNOWN
        closes = [b.close for b in bars]
        er = efficiency_ratio(closes[-p.er_window:])
        atr5 = atr_simple(bars, p.atr5_period)
        if er is None or atr5 is None or atr5 == 0:
            return Regime.UNKNOWN
        slope = (closes[-1] - closes[-1 - p.slope_lag]) / atr5
        self.last_er, self.last_slope = er, slope
        if er >= p.er_trend_min and slope >= p.slope_trend_min:
            return Regime.TREND_UP
        if er >= p.er_trend_min and slope <= -p.slope_trend_min:
            return Regime.TREND_DOWN
        if er <= p.er_range_max:
            return Regime.RANGE
        return Regime.TRANSITION

    # ---- shock por barra 1m ----------------------------------------------------------------------
    def on_bar_1m_close(self, bars_1m: list[Bar], closed_at_ns: int) -> bool:
        p = self.params
        if len(bars_1m) < p.atr1_period + 2:
            return False
        atr_prev = atr_simple(bars_1m[:-1], p.atr1_period)  # ATR ANTES de la última barra
        if atr_prev is None or atr_prev <= 0:
            return False
        tr = true_range(bars_1m[-1], bars_1m[-2].close)
        if tr > p.shock_mult * atr_prev:
            self.shock_until_ns = closed_at_ns + p.shock_block_ns  # se extiende si vuelve a ocurrir
            self.shocks += 1
            return True
        return False

    def blocked_reasons(self, now_ns: int) -> tuple[str, ...]:
        out: list[str] = []
        if self.regime is Regime.UNKNOWN:
            out.append("REGIME_UNKNOWN")
        if self.shock_until_ns is not None and now_ns < self.shock_until_ns:
            out.append("VOL_SHOCK")
        return tuple(out)
