"""ENG-03 aceptación sobre un fixture REAL de 1 minuto (ESU4 2024-09-10 13:30–13:31 UTC, mbp-10).

El fixture es dato licenciado y vive fuera de git (data/fixtures). Se omite si no está.
Valores de referencia obtenidos el 3-oct-2026 con los esquemas ohlcv-1m y trades del mismo minuto:
volumen 9,471 contratos en 3,013 trades; 47,146 registros.
"""

from pathlib import Path

import pytest

from trading_scanner.contracts import Aggressor, EventType

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "data" / "fixtures" / "ESU4.mbp-10.2024-09-10T1330-1331.dbn.zst"
STATUS = ROOT / "data" / "raw" / "GLBX.MDP3" / "status" / "GLBX.MDP3.status.2024-09-05_2024-09-21.dbn.zst"
ESU4_ID = 118
REF_VOLUME, REF_TRADES, REF_RECORDS = 9_471, 3_013, 47_146


@pytest.fixture(scope="module")
def events(catalog):
    if not FIX.is_file():
        pytest.skip("fixture mbp-10 no disponible")
    pytest.importorskip("databento")
    from trading_scanner.adapters.market import AdapterStats, iter_mbp10_events

    stats = AdapterStats()
    evs = list(iter_mbp10_events(FIX, catalog.get("ESU4"), ESU4_ID, stats=stats))
    return evs, stats


def test_exact_mapping_counts(events):
    evs, stats = events
    assert stats.records == REF_RECORDS
    assert len(evs) == REF_RECORDS  # un solo instrumento en el archivo: nada se descarta
    assert stats.skipped_instruments == 0


def test_no_double_counting_of_volume(events):
    evs, stats = events
    trades = [e for e in evs if e.event_type is EventType.TRADE]
    assert len(trades) == REF_TRADES == stats.trades
    assert sum(e.size_contracts for e in trades) == REF_VOLUME == stats.trade_volume


def test_prices_on_grid_and_book_levels_sane(events):
    evs, stats = events
    assert stats.off_grid_prices == 0
    for e in evs:
        assert "PRICE_OFF_GRID" not in e.quality_flags
        assert len(e.bid_levels) <= 10 and len(e.ask_levels) <= 10
        if e.bid_levels and e.ask_levels:
            assert e.bid_levels[0].price_ticks < e.ask_levels[0].price_ticks  # sin cruces en este minuto
            assert all(e.bid_levels[i].price_ticks > e.bid_levels[i + 1].price_ticks for i in range(len(e.bid_levels) - 1))
            assert all(e.ask_levels[i].price_ticks < e.ask_levels[i + 1].price_ticks for i in range(len(e.ask_levels) - 1))


def test_aggressor_known_pct_meets_protocol_threshold(events):
    _, stats = events
    assert stats.aggressor_known_pct is not None and stats.aggressor_known_pct >= 95.0
    assert stats.aggressor_known_pct == 100.0  # en este minuto no hubo side N en trades


def test_trade_book_is_pre_trade_and_trades_never_carry_f_last(events):
    evs, _ = events
    trades = [e for e in evs if e.event_type is EventType.TRADE]
    assert all("BOOK_IS_PRE_TRADE" in e.quality_flags for e in trades)
    assert all("F_LAST" not in e.quality_flags for e in trades)
    # El primer trade del fixture: vendedor agresor (side A) a 5498.25 → SELL, 21993 ticks
    first = trades[0]
    assert first.aggressor is Aggressor.SELL and first.price_ticks == 21993 and first.size_contracts == 1


def test_availability_is_causal_and_ordered(events):
    evs, _ = events
    for e in evs:
        assert e.ts_vendor_recv_ns >= e.ts_event_ns
        assert e.available_at_ns == e.ts_vendor_recv_ns + 100_000_000
    seqs = [e.sequence for e in evs]
    assert seqs == sorted(seqs)
    avail = [e.available_at_ns for e in evs]
    assert avail == sorted(avail)


def test_book_events_have_no_trade_fields(events):
    evs, _ = events
    for e in evs:
        if e.event_type is EventType.BOOK:
            assert e.price_ticks is None and e.size_contracts is None and e.aggressor is Aggressor.UNKNOWN


def test_status_adapter(catalog):
    if not STATUS.is_file():
        pytest.skip("status no descargado")
    pytest.importorskip("databento")
    from trading_scanner.adapters.market import iter_status_events

    evs = list(iter_status_events(STATUS, catalog.get("ESU4"), ESU4_ID))
    assert evs and all(e.event_type is EventType.STATUS for e in evs)
    assert any("IS_TRADING" in e.quality_flags for e in evs)
    assert any("IS_TRADING" not in e.quality_flags for e in evs)  # cierres diarios 21:00Z
