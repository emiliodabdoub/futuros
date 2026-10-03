"""Indicadores deterministas en ticks (spec §4). Ningún valor se inventa: falta de datos → None."""

from __future__ import annotations

from collections.abc import Sequence

from trading_scanner.features.bars import Bar


def true_range(bar: Bar, prev_close: int | None) -> int:
    if prev_close is None:
        return bar.high - bar.low
    return max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close))


def atr_simple(bars: Sequence[Bar], period: int = 14) -> float | None:
    """F03: media simple de los últimos `period` TR; requiere period+1 barras completas (15 cierres)."""
    if len(bars) < period + 1:
        return None
    trs = [true_range(bars[i], bars[i - 1].close) for i in range(len(bars) - period, len(bars))]
    return sum(trs) / period


def efficiency_ratio(closes: Sequence[int]) -> float | None:
    """F13: movimiento neto / suma de movimientos absolutos. None si < 2 cierres o suma 0."""
    if len(closes) < 2:
        return None
    net = abs(closes[-1] - closes[0])
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    if path == 0:
        return None
    return net / path


def median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def weighted_median(values: Sequence[tuple[float, float]]) -> float | None:
    """Mediana ponderada (valor, peso>0): primer valor cuyo peso acumulado alcanza la mitad del total."""
    pairs = sorted((v, w) for v, w in values if w > 0)
    total = sum(w for _, w in pairs)
    if total <= 0:
        return None
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= total / 2:
            return v
    return pairs[-1][0]
