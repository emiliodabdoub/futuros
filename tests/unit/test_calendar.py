"""ENG-02: calendario de sesiones de investigación."""

from datetime import date

from trading_scanner.registry import TradingCalendar


def test_weekend_and_holiday_are_not_sessions(calendar):
    assert not calendar.is_session(date(2024, 9, 7))  # sábado
    assert not calendar.is_session(date(2024, 9, 2))  # Labor Day
    assert calendar.is_session(date(2024, 9, 3))
    assert calendar.verified is False


def test_previous_session_skips_holiday_and_weekend(calendar):
    assert calendar.previous_session(date(2024, 9, 3)) == date(2024, 8, 30)
    assert calendar.previous_session(date(2024, 9, 9)) == date(2024, 9, 6)


def test_half_day_is_session_but_not_pilot_session(calendar):
    d = date(2024, 11, 29)
    assert calendar.is_session(d)
    assert not calendar.is_pilot_session(d)


def test_sessions_after_until_counts_exclusive_start_inclusive_end():
    cal = TradingCalendar()
    # lunes 9-sep → viernes 13-sep: mar, mié, jue, vie = 4
    assert cal.sessions_after_until(date(2024, 9, 9), date(2024, 9, 13)) == 4
    assert cal.sessions_after_until(date(2024, 9, 9), date(2024, 9, 9)) == 0
    assert cal.sessions_after_until(date(2024, 9, 9), date(2024, 9, 1)) == 0
