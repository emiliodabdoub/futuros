"""Calendario de sesiones de investigación (ADR-002). Festivos y medias jornadas vienen de config;
deben contrastarse con el calendario oficial del venue antes de materializar manifiestos."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml


@dataclass(frozen=True)
class TradingCalendar:
    holidays: frozenset[date] = field(default_factory=frozenset)
    half_days: frozenset[date] = field(default_factory=frozenset)
    verified: bool = False

    @classmethod
    def from_yaml(cls, path: Path) -> TradingCalendar:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            holidays=frozenset(_as_date(d) for d in raw.get("holidays", [])),
            half_days=frozenset(_as_date(d) for d in raw.get("half_days", [])),
            verified=bool(raw.get("verified", False)),
        )

    def is_session(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.holidays

    def is_pilot_session(self, d: date) -> bool:
        """Sesión válida para el piloto: no festivo ni media jornada (D02: debe caber la ventana completa)."""
        return self.is_session(d) and d not in self.half_days

    def previous_session(self, d: date) -> date:
        cur = d - timedelta(days=1)
        for _ in range(60):
            if self.is_session(cur):
                return cur
            cur -= timedelta(days=1)
        raise ValueError(f"sin sesión previa en 60 días antes de {d}")

    def next_session(self, d: date) -> date:
        cur = d + timedelta(days=1)
        for _ in range(60):
            if self.is_session(cur):
                return cur
            cur += timedelta(days=1)
        raise ValueError(f"sin sesión siguiente en 60 días después de {d}")

    def sessions_after_until(self, start_exclusive: date, end_inclusive: date) -> int:
        """Número de sesiones en (start_exclusive, end_inclusive]. Negativo nunca; 0 si end <= start."""
        if end_inclusive <= start_exclusive:
            return 0
        n = 0
        cur = start_exclusive + timedelta(days=1)
        while cur <= end_inclusive:
            if self.is_session(cur):
                n += 1
            cur += timedelta(days=1)
        return n


def _as_date(v: object) -> date:
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v))
