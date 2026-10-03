"""ENG-11: TC-v1 y BO-v1 deshabilitados por defecto; positivo y negativos de cada uno."""

from trading_scanner.contracts import Direction
from trading_scanner.features.bars import Bar
from trading_scanner.setups.breakout import BODetector, BOParams
from trading_scanner.setups.liquidity_reversal import LRContext, LRParams, Trade
from trading_scanner.setups.trend_continuation import TCDetector, TCParams

NS = 1_000_000_000
M = 60 * NS


def ctx(delta=0.25, vol=150, med=100.0, spread=1, atr=10.0, regime="TREND_UP", blocked=()):
    return LRContext(atr_1m_ticks=atr, delta_ratio_5s=delta, volume_5s=vol, volume_5s_median=med, spread_ticks=spread,
                     in_entry_window=True, blocked_reasons=tuple(blocked), regime=regime)


def flat_bars(n, price=1000, rng=3, start=0):
    return [Bar((start + i) * M, (start + i + 1) * M, price, price + rng, price - rng, price) for i in range(n)]


def test_disabled_by_default_emits_nothing():
    tc, bo = TCDetector("ESZ4"), BODetector("ESZ4")
    bars = flat_bars(80)
    tc.on_bar_1m_close(bars, 80 * M, ctx())
    bo.on_bar_1m_close(bars, 80 * M, ctx())
    assert tc.impulse is None and bo.range is None and tc.transitions == [] and bo.transitions == []


# ---------- TC-v1 ----------
def _tc_setup(enabled=True):
    tc = TCDetector("ESZ4", TCParams(base=LRParams(risk_max_atr_mult=4.0)), enabled=enabled)
    bars = flat_bars(80)  # ATR ≈ 6
    # impulso: 5 barras subiendo 4 ticks cada una (neto 20 >= 1.5*6, ER = 1)
    px = 1000
    for i in range(5):
        bars.append(Bar((80 + i) * M, (81 + i) * M, px, px + 5, px - 1, px + 4))
        px += 4
    return tc, bars


def test_tc_positive_pullback_then_trigger():
    tc, bars = _tc_setup()
    tc.on_bar_1m_close(bars, 85 * M, ctx())
    assert tc.impulse is not None and tc.impulse.direction is Direction.LONG and tc.impulse.size == 21  # extreme 1021 - origin 1000
    # pullback 40 %: low 1021 - 8.4 ≈ 1013
    bars.append(Bar(85 * M, 86 * M, 1020, 1020, 1013, 1015))
    tc.on_bar_1m_close(bars, 86 * M, ctx())
    assert tc.impulse.in_band and tc.impulse.pullback_extreme == 1013
    sigs = tc.on_trade(Trade(86 * M + NS, 1021, 1), ctx(), atr_1m=6.0)  # > high última barra (1020) + 1
    assert len(sigs) == 1
    s = sigs[0]
    assert s.setup_version == "TC-v1" and s.stop_ticks == 1011 and s.risk_ticks_at_trigger == 10
    assert s.target_ticks_at_trigger == 1041 and tc.impulse is None


def test_tc_rejects_deep_pullback_expiry_and_contrary_delta():
    tc, bars = _tc_setup()
    tc.on_bar_1m_close(bars, 85 * M, ctx())
    bars.append(Bar(85 * M, 86 * M, 1020, 1020, 1005, 1006))  # retrace (1021-1005)/21 = 76 %
    tc.on_bar_1m_close(bars, 86 * M, ctx())
    assert tc.impulse is None and tc.rejections[-1].reason == "PULLBACK_GT_60PCT"

    tc2, bars2 = _tc_setup()
    tc2.on_bar_1m_close(bars2, 85 * M, ctx())
    for i in range(6):  # 6 barras sin entrar en banda (retrace < 25 %)
        bars2.append(Bar((85 + i) * M, (86 + i) * M, 1020, 1022, 1019, 1020))
        tc2.on_bar_1m_close(bars2, (86 + i) * M, ctx())
    assert tc2.rejections[-1].reason == "PULLBACK_WINDOW_EXPIRED"

    tc3, bars3 = _tc_setup()
    tc3.on_bar_1m_close(bars3, 85 * M, ctx())
    bars3.append(Bar(85 * M, 86 * M, 1020, 1020, 1013, 1015))
    tc3.on_bar_1m_close(bars3, 86 * M, ctx())
    assert tc3.on_trade(Trade(86 * M + NS, 1021, 1), ctx(delta=-0.3), atr_1m=6.0) == []
    assert tc3.rejections[-1].reason.startswith("DELTA_CONTRARY")


def test_tc_requires_confirmed_trend_regime():
    tc, bars = _tc_setup()
    tc.on_bar_1m_close(bars, 85 * M, ctx(regime="RANGE"))
    assert tc.impulse is None
    tc.on_bar_1m_close(bars, 85 * M, ctx(regime="UNKNOWN"))
    assert tc.impulse is None


# ---------- BO-v1 ----------
def _bo_setup():
    bo = BODetector("ESZ4", enabled=True)
    bars = flat_bars(40, price=1000, rng=3)  # anchura 6 <= 2×ATR(6); ER de cierres iguales → None → no arma
    # cierres alternando ±1 → ER bajo pero no None
    bars = [Bar(i * M, (i + 1) * M, 1000, 1003, 997, 1000 + ((-1) ** i)) for i in range(40)]
    return bo, bars


def test_bo_positive_break_and_acceptance():
    bo, bars = _bo_setup()
    bo.on_bar_1m_close(bars, 40 * M, ctx())
    assert bo.range is not None and (bo.range.high, bo.range.low) == (1003, 997)
    t0 = 40 * M + NS
    assert bo.on_trade(Trade(t0, 1005, 1), ctx()) == []  # ruptura (>= high+2)
    assert bo.range.break_at_ns == t0 and bo.range.direction is Direction.LONG
    for i in range(1, 5):
        assert bo.on_trade(Trade(t0 + i * NS, 1005 + (i % 2), 1), ctx()) == []  # fuera del rango, < 5 s
    sigs = bo.on_trade(Trade(t0 + 5 * NS, 1006, 1), ctx())  # 5 s completos, 6 trades
    assert len(sigs) == 1 and sigs[0].setup_version == "BO-v1"
    assert sigs[0].stop_ticks == 1001 and sigs[0].risk_ticks_at_trigger == 5 and bo.range is None


def test_bo_rejects_reentry_few_trades_and_wide_range():
    bo, bars = _bo_setup()
    bo.on_bar_1m_close(bars, 40 * M, ctx())
    t0 = 40 * M + NS
    bo.on_trade(Trade(t0, 1005, 1), ctx())
    bo.on_trade(Trade(t0 + NS, 1003, 1), ctx())  # vuelve al límite
    assert bo.range is None and bo.rejections[-1].reason == "REENTRY_BEFORE_ACCEPTANCE"

    bo2, bars2 = _bo_setup()
    bo2.on_bar_1m_close(bars2, 40 * M, ctx())
    bo2.on_trade(Trade(t0, 1005, 1), ctx())
    assert bo2.on_trade(Trade(t0 + 6 * NS, 1006, 1), ctx()) == []  # 2 trades en 6 s
    assert bo2.rejections[-1].reason == "ACCEPTANCE_LT_5_TRADES"

    bo3 = BODetector("ESZ4", enabled=True)
    wide = [Bar(i * M, (i + 1) * M, 1000, 1003, 997, 1000 + ((-1) ** i)) for i in range(40)]
    wide[30] = Bar(30 * M, 31 * M, 1000, 1030, 997, 1001)  # un pico dentro de las 15 previas: anchura 33 > 2×ATR
    bo3.on_bar_1m_close(wide, 40 * M, ctx())
    assert bo3.range is None


def test_bo_expires_without_break_and_does_not_consume_cooldown():
    bo, bars = _bo_setup()
    bo.on_bar_1m_close(bars, 40 * M, ctx())
    bars2 = bars + [Bar((40 + i) * M, (41 + i) * M, 1000, 1003, 997, 1000 + ((-1) ** i)) for i in range(11)]
    bo.on_bar_1m_close(bars2, 51 * M, ctx())
    assert bo.range is None and bo.transitions[-1].reason == "NO_BREAK_10MIN" and bo.cooldown_until is None
