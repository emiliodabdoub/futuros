"""Ventanas de sesión por fecha, con zonas horarias reales (spec §2 D02/D03, ADR-001 §7)."""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
HERMOSILLO = ZoneInfo("America/Hermosillo")
UTC = timezone.utc

NS_PER_S = 1_000_000_000


def to_utc_ns(d: date, t: time, tz: ZoneInfo) -> int:
    """Instante UTC en ns del reloj de pared `t` del día `d` en la zona `tz` (conversión por fecha)."""
    local = datetime.combine(d, t, tzinfo=tz)
    utc = local.astimezone(UTC)
    return int(utc.timestamp()) * NS_PER_S + utc.microsecond * 1000


def ns_to_datetime(ns: int, tz: ZoneInfo = UTC) -> datetime:
    return datetime.fromtimestamp(ns / NS_PER_S, tz=UTC).astimezone(tz)


@dataclass(frozen=True)
class SessionWindow:
    """Ventana del piloto para una fecha concreta, todo en ns UTC."""

    session_date: date
    rth_open_ns: int  # 09:30 NY
    opening_range_end_ns: int  # 09:35 NY (OR de F09)
    entry_start_ns: int  # 09:35 NY (D02)
    entry_end_ns: int  # 11:30 NY (D02)
    flat_by_ns: int  # 11:45 NY (D03)
    rth_close_ns: int  # 16:00 NY (F08)

    def accepts_new_entry(self, now_ns: int) -> bool:
        return self.entry_start_ns <= now_ns < self.entry_end_ns

    def must_be_flat(self, now_ns: int) -> bool:
        return now_ns >= self.flat_by_ns


def pilot_window(session_date: date) -> SessionWindow:
    ny = NEW_YORK
    return SessionWindow(
        session_date=session_date,
        rth_open_ns=to_utc_ns(session_date, time(9, 30), ny),
        opening_range_end_ns=to_utc_ns(session_date, time(9, 35), ny),
        entry_start_ns=to_utc_ns(session_date, time(9, 35), ny),
        entry_end_ns=to_utc_ns(session_date, time(11, 30), ny),
        flat_by_ns=to_utc_ns(session_date, time(11, 45), ny),
        rth_close_ns=to_utc_ns(session_date, time(16, 0), ny),
    )
