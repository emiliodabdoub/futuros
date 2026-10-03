"""ENG-01: reloj inyectable y ventanas por fecha con DST real."""

from datetime import date, time

import pytest

from trading_scanner.clock import (
    HERMOSILLO,
    NEW_YORK,
    ManualClock,
    ReplayClock,
    ns_to_datetime,
    pilot_window,
    to_utc_ns,
)

NS = 1_000_000_000


def test_manual_clock_only_moves_forward():
    c = ManualClock(10)
    c.advance(5)
    assert c.now_ns() == 15
    c.set(20)
    with pytest.raises(ValueError):
        c.set(19)
    with pytest.raises(ValueError):
        c.advance(-1)


def test_replay_clock_rejects_out_of_order_availability():
    r = ReplayClock()
    r.observe_available_at(100)
    r.observe_available_at(100)  # mismo instante permitido
    with pytest.raises(ValueError, match="fuera de orden"):
        r.observe_available_at(99)


def test_ny_offset_changes_with_dst_no_fixed_offset():
    # 2024-03-08 (EST, UTC-5) vs 2024-03-11 (EDT, UTC-4): 09:35 NY cae a distinta hora UTC.
    before = ns_to_datetime(to_utc_ns(date(2024, 3, 8), time(9, 35), NEW_YORK))
    after = ns_to_datetime(to_utc_ns(date(2024, 3, 11), time(9, 35), NEW_YORK))
    assert (before.hour, before.minute) == (14, 35)
    assert (after.hour, after.minute) == (13, 35)


def test_hermosillo_has_no_dst_so_gap_to_ny_varies():
    # Hermosillo es UTC-7 todo el año. En verano NY-Hermosillo = 3h; en invierno = 2h.
    summer = ns_to_datetime(to_utc_ns(date(2024, 9, 10), time(9, 35), NEW_YORK), HERMOSILLO)
    winter = ns_to_datetime(to_utc_ns(date(2024, 12, 10), time(9, 35), NEW_YORK), HERMOSILLO)
    assert (summer.hour, summer.minute) == (6, 35)
    assert (winter.hour, winter.minute) == (7, 35)


def test_pilot_window_ordering_and_predicates():
    w = pilot_window(date(2024, 9, 10))
    assert w.rth_open_ns < w.entry_start_ns < w.entry_end_ns < w.flat_by_ns < w.rth_close_ns
    assert w.opening_range_end_ns == w.entry_start_ns
    assert w.entry_end_ns - w.entry_start_ns == 115 * 60 * NS
    assert not w.accepts_new_entry(w.entry_start_ns - 1)
    assert w.accepts_new_entry(w.entry_start_ns)
    assert not w.accepts_new_entry(w.entry_end_ns)  # fin exclusivo
    assert not w.must_be_flat(w.flat_by_ns - 1)
    assert w.must_be_flat(w.flat_by_ns)
