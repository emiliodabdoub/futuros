"""ENG-05: barras [inicio, fin) con margen, datos tardíos, ATR exacto, efficiency ratio."""

from trading_scanner.contracts import Aggressor
from trading_scanner.features import Bar, BarBuilder, atr_simple, efficiency_ratio, true_range

NS = 1_000_000_000
M = 60 * NS


def test_bar_interval_is_half_open_and_finalizes_after_margin():
    b = BarBuilder(M, finalize_margin_ns=250_000_000)
    b.add_trade(ts_event_ns=0, available_at_ns=0, price=100, size=1, aggressor=Aggressor.BUY)
    b.add_trade(ts_event_ns=M - 1, available_at_ns=M - 1, price=102, size=2, aggressor=Aggressor.SELL)  # aún en [0, M)
    assert b.finalized == [] and b.current.high == 102
    b.observe(M + 249_999_999)  # dentro del margen: no finaliza
    assert b.finalized == []
    b.observe(M + 250_000_000)
    assert len(b.finalized) == 1
    bar = b.finalized[0]
    assert (bar.open, bar.high, bar.low, bar.close, bar.volume, bar.delta) == (100, 102, 100, 102, 3, -1)
    assert bar.finalized_at_ns == M + 250_000_000


def test_late_trade_after_finalization_is_recorded_not_applied():
    b = BarBuilder(M)
    b.add_trade(0, 0, 100, 1, Aggressor.BUY)
    b.observe(M + 250_000_000)
    assert len(b.finalized) == 1
    b.add_trade(ts_event_ns=30 * NS, available_at_ns=M + 300_000_000, price=999, size=5, aggressor=Aggressor.BUY)
    assert b.finalized[0].high == 100 and b.finalized[0].volume == 1
    assert b.late_revisions == 1 and b.revisions == [(0, 999, 5)]


def test_trade_in_next_bar_before_margin_closes_current_bar():
    b = BarBuilder(M)
    b.add_trade(0, 0, 100, 1, Aggressor.BUY)
    b.add_trade(M + 1, M + 1, 101, 1, Aggressor.BUY)  # ts_event ya en la siguiente barra
    assert len(b.finalized) == 1 and b.current.start_ns == M


def test_atr_simple_requires_15_bars_and_matches_formula():
    bars = [Bar(i * M, (i + 1) * M, 100, 110, 90, 100 + (i % 3)) for i in range(14)]
    assert atr_simple(bars, 14) is None
    bars.append(Bar(14 * M, 15 * M, 100, 130, 95, 120))
    trs = [true_range(bars[i], bars[i - 1].close) for i in range(1, 15)]
    assert atr_simple(bars, 14) == sum(trs) / 14
    assert true_range(Bar(0, M, 100, 105, 95, 100), prev_close=120) == 25  # |low - prev_close|


def test_efficiency_ratio_edge_cases():
    assert efficiency_ratio([100, 110, 120]) == 1.0
    assert efficiency_ratio([100, 110, 100]) == 0.0
    assert efficiency_ratio([100, 100, 100]) is None  # suma de movimientos 0 → missing, no 0
    assert efficiency_ratio([100]) is None
