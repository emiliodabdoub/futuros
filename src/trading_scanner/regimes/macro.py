"""Calendario macro versionado (protocolo §8): bloquea nuevas entradas desde 5 min antes hasta 10 min
después de la publicación de eventos USD de alta relevancia (CPI, Employment Situation, FOMC, PCE, GDP).
No añade salida anticipada. Si el histórico no es point-in-time se marca `calendar_not_point_in_time`
y los resultados son exploratorios."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from trading_scanner.clock import to_utc_ns

NS = 1_000_000_000


@dataclass(frozen=True)
class MacroEvent:
    name: str
    category: str
    release_ns: int
    block_start_ns: int
    block_end_ns: int


class MacroCalendar:
    def __init__(self, events: list[MacroEvent], *, version: str, point_in_time: bool, verified: bool) -> None:
        self.events = sorted(events, key=lambda e: e.release_ns)
        self.version = version
        self.point_in_time = point_in_time
        self.verified = verified

    @classmethod
    def from_yaml(cls, path: Path) -> MacroCalendar:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        tz = ZoneInfo(raw.get("timezone", "America/New_York"))
        before = int(raw.get("block_before_min", 5)) * 60 * NS
        after = int(raw.get("block_after_min", 10)) * 60 * NS
        evs = []
        for e in raw.get("events", []):
            d = e["date"] if isinstance(e["date"], date) else date.fromisoformat(str(e["date"]))
            t = datetime.strptime(str(e["time"]), "%H:%M").time()
            rel = to_utc_ns(d, time(t.hour, t.minute), tz)
            evs.append(MacroEvent(e["name"], e["category"], rel, rel - before, rel + after))
        return cls(evs, version=str(raw.get("version", "unversioned")), point_in_time=bool(raw.get("point_in_time", False)),
                   verified=bool(raw.get("verified", False)))

    def blocking(self, now_ns: int) -> MacroEvent | None:
        for e in self.events:
            if e.block_start_ns <= now_ns < e.block_end_ns:
                return e
        return None

    def blocked_reasons(self, now_ns: int) -> tuple[str, ...]:
        e = self.blocking(now_ns)
        return (f"MACRO_BLOCK:{e.category}",) if e else ()

    def next_event_after(self, now_ns: int) -> MacroEvent | None:
        return next((e for e in self.events if e.release_ns > now_ns), None)
