"""Replay causal multi-contrato (ENG-05, spec §3.3).

Orden global por `available_at_ns`; desempate por (source, contract, channel, sequence, record_index).
El ReplayClock solo avanza con la disponibilidad. Epochs de 1 s: el callback de epoch se dispara
ANTES de entregar el primer evento cuya disponibilidad cruza la frontera, de modo que una decisión en
el epoch T solo ve eventos con available_at < T.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable, Iterable, Iterator

from trading_scanner.clock import ReplayClock
from trading_scanner.contracts import MarketEvent

NS = 1_000_000_000


def _key(ev: MarketEvent) -> tuple:
    return (ev.available_at_ns, ev.source, ev.contract_id, ev.channel_id or 0, ev.sequence or 0, ev.record_index)


def merge_by_availability(streams: Iterable[Iterator[MarketEvent]]) -> Iterator[MarketEvent]:
    """k-way merge estable. Cada stream debe venir ordenado por available_at (el adapter lo garantiza)."""
    heap: list[tuple[tuple, int, MarketEvent, Iterator[MarketEvent]]] = []
    for i, it in enumerate(streams):
        first = next(it, None)
        if first is not None:
            heapq.heappush(heap, (_key(first), i, first, it))
    last_key: tuple | None = None
    while heap:
        key, i, ev, it = heapq.heappop(heap)
        if last_key is not None and key < last_key:
            raise ValueError("stream fuera de orden por available_at")
        last_key = key
        yield ev
        nxt = next(it, None)
        if nxt is not None:
            nk = _key(nxt)
            if nk < key:
                raise ValueError(f"stream {i} retrocede en available_at")
            heapq.heappush(heap, (nk, i, nxt, it))


class Replay:
    def __init__(self, streams: Iterable[Iterator[MarketEvent]], *, epoch_ns: int = NS,
                 clock: ReplayClock | None = None, stop_at_ns: int | None = None) -> None:
        self._merged = merge_by_availability(streams)
        self.clock = clock or ReplayClock()
        self.epoch_ns = epoch_ns
        self.stop_at_ns = stop_at_ns
        self.events = 0
        self.epochs = 0

    def run(self, on_event: Callable[[MarketEvent], None],
            on_epoch: Callable[[int], None] | None = None) -> None:
        next_epoch: int | None = None
        for ev in self._merged:
            t = ev.available_at_ns
            if self.stop_at_ns is not None and t >= self.stop_at_ns:
                break
            if on_epoch is not None:
                if next_epoch is None:
                    next_epoch = (t // self.epoch_ns + 1) * self.epoch_ns
                while t >= next_epoch:
                    self.clock.observe_available_at(next_epoch)
                    on_epoch(next_epoch)
                    self.epochs += 1
                    next_epoch += self.epoch_ns
            self.clock.observe_available_at(t)
            on_event(ev)
            self.events += 1
