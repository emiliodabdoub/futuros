"""Relojes. Ningún módulo del scanner llama time.time() directamente (ADR-001 §6)."""

import time
from typing import Protocol


class Clock(Protocol):
    def now_ns(self) -> int: ...


class SystemClock:
    def now_ns(self) -> int:
        return time.time_ns()


class ManualClock:
    """Reloj de pruebas: se mueve solo cuando el test lo pide."""

    def __init__(self, start_ns: int = 0) -> None:
        if start_ns < 0:
            raise ValueError("start_ns >= 0")
        self._now = start_ns

    def now_ns(self) -> int:
        return self._now

    def set(self, ns: int) -> None:
        if ns < self._now:
            raise ValueError("el reloj no retrocede")
        self._now = ns

    def advance(self, delta_ns: int) -> None:
        if delta_ns < 0:
            raise ValueError("delta_ns >= 0")
        self._now += delta_ns


class ReplayClock:
    """Avanza únicamente con la disponibilidad de los eventos reproducidos (spec §3.3)."""

    def __init__(self, start_ns: int = 0) -> None:
        if start_ns < 0:
            raise ValueError("start_ns >= 0")
        self._now = start_ns

    def now_ns(self) -> int:
        return self._now

    def observe_available_at(self, available_at_ns: int) -> None:
        if available_at_ns < self._now:
            raise ValueError(
                f"evento fuera de orden: available_at {available_at_ns} < now {self._now}"
            )
        self._now = available_at_ns
