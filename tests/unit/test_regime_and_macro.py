"""Régimen determinista (§4.1) con confirmación de 2 cierres, shock de volatilidad y calendario macro (§8)."""

from datetime import date, time
from pathlib import Path

from trading_scanner.clock import NEW_YORK, to_utc_ns
from trading_scanner.features.bars import Bar
from trading_scanner.regimes import MacroCalendar, Regime, RegimeTracker

NS = 1_000_000_000
M5 = 300 * NS
ROOT = Path(__file__).resolve().parents[2]


def bars_from_closes(closes, interval=M5, rng=4):
    out = []
    for i, c in enumerate(closes):
        out.append(Bar(i * interval, (i + 1) * interval, c, c + rng, c - rng, c))
    return out


def test_unknown_until_warmup_then_trend_up_needs_two_closes():
    rt = RegimeTracker()
    closes = [1000 + 3 * i for i in range(15)]  # tendencia limpia: ER=1, pendiente alta
    assert rt.on_bar_5m_close(bars_from_closes(closes[:10]), 1) is Regime.UNKNOWN
    r = rt.on_bar_5m_close(bars_from_closes(closes), 2)
    assert r is Regime.TREND_UP  # desde UNKNOWN se adopta de inmediato (no hay estado que proteger)
    # giro a rango: necesita dos cierres consecutivos
    flat = closes + [closes[-1] + ((-1) ** i) for i in range(12)]
    assert rt.on_bar_5m_close(bars_from_closes(flat[:-1]), 3) is Regime.TREND_UP
    assert rt.on_bar_5m_close(bars_from_closes(flat), 4) is Regime.RANGE
    assert rt.history == [(2, Regime.TREND_UP), (4, Regime.RANGE)]  # no se reescribe el pasado


def test_regime_change_not_confirmed_if_interrupted():
    rt = RegimeTracker()
    up = [1000 + 3 * i for i in range(15)]
    rt.on_bar_5m_close(bars_from_closes(up), 1)
    down = up + [up[-1] - 3 * i for i in range(1, 8)]
    rt.on_bar_5m_close(bars_from_closes(down), 2)  # 1.ª lectura TRANSITION/DOWN pendiente
    rt.on_bar_5m_close(bars_from_closes(up + [up[-1] + 3 * i for i in range(1, 8)]), 3)  # vuelve a UP → pendiente se resetea
    assert rt.regime is Regime.TREND_UP and rt._pending is None


def test_volatility_shock_blocks_5_minutes_and_extends():
    rt = RegimeTracker()
    b = bars_from_closes([1000] * 17, interval=60 * NS, rng=2)  # TR ~ 4 ticks
    assert rt.on_bar_1m_close(b, 100 * NS) is False
    b.append(Bar(17 * 60 * NS, 18 * 60 * NS, 1000, 1030, 1000, 1030))  # TR 30 > 3 × 4
    assert rt.on_bar_1m_close(b, 100 * NS) is True
    assert rt.blocked_reasons(100 * NS + 299 * NS) == ("REGIME_UNKNOWN", "VOL_SHOCK")
    assert "VOL_SHOCK" not in rt.blocked_reasons(100 * NS + 301 * NS)
    b.append(Bar(18 * 60 * NS, 19 * 60 * NS, 1030, 1070, 1030, 1070))
    assert rt.on_bar_1m_close(b, 200 * NS) is True and rt.shock_until_ns == 500 * NS and rt.shocks == 2


def test_macro_calendar_blocks_window_around_release():
    cal = MacroCalendar.from_yaml(ROOT / "configs" / "sessions" / "macro_calendar_2024.yaml")
    assert cal.verified is False and cal.point_in_time is False
    cpi = to_utc_ns(date(2024, 9, 11), time(8, 30), NEW_YORK)
    assert cal.blocked_reasons(cpi - 5 * 60 * NS) == ("MACRO_BLOCK:CPI",)
    assert cal.blocked_reasons(cpi + 9 * 60 * NS) == ("MACRO_BLOCK:CPI",)
    assert cal.blocked_reasons(cpi + 10 * 60 * NS) == ()
    assert cal.blocked_reasons(cpi - 6 * 60 * NS) == ()
    fomc = to_utc_ns(date(2024, 9, 18), time(14, 0), NEW_YORK)
    assert cal.blocking(fomc).category == "FOMC"
    assert cal.next_event_after(cpi).category == "FOMC"
