"""Quality gate operativo por contrato (spec §3.4, protocolo §4, ENG-04).

Bloquea candidatos (no corrige datos) cuando:
- RESET_UNRECOVERED: hubo reset y aún no se cerró un libro completo después.
- CROSSED_BOOK_PERSISTENT: bid >= ask durante más de `crossed_grace_ns`.
- PRICE_OFF_GRID / NEGATIVE_SIZE / INCOMPLETE_METADATA: evento inválido (bloquea el resto de la sesión
  si `invalid_blocks_session`).
- AGGRESSOR_UNKNOWN_HIGH: menos de `min_aggressor_known_pct` del volumen con agresor conocido en la
  ventana trailing `aggressor_window_ns`.
- STALE_FEED: sin ningún evento del contrato durante `stale_after_ns` (umbral operativo, no prueba
  universal de feed caído; se evalúa con `check_staleness(now)`).
- NOT_TRADING: el último STATUS dice que el instrumento no está en negociación.

Los saltos de `sequence` en un stream filtrado por instrumento NO son pérdida de paquetes (la secuencia
es por canal, ADR-003): se cuentan como `sequence_jumps` para diagnóstico pero no bloquean. La
pérdida real se detecta por flags del proveedor (F_BAD_TS_RECV, F_MAYBE_BAD_BOOK, F_SNAPSHOT) y resets.
Tras un bloqueo transitorio que se levanta, `rewarm_required=True` hasta que el consumidor lo confirme.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from trading_scanner.contracts import Aggressor, EventType, MarketEvent
from trading_scanner.orderbook import BookSnapshot, BookTracker

NS = 1_000_000_000


@dataclass(frozen=True)
class GateConfig:
    stale_after_ns: int = 5 * NS
    crossed_grace_ns: int = 1 * NS
    aggressor_window_ns: int = 60 * NS
    min_aggressor_known_pct: float = 95.0
    min_aggressor_volume: int = 20  # por debajo no se evalúa el porcentaje
    invalid_blocks_session: bool = True


@dataclass
class QualityState:
    blocked: bool = False
    reasons: tuple[str, ...] = ()
    session_excluded: bool = False
    rewarm_required: bool = False
    sequence_jumps: int = 0
    provider_flags: dict[str, int] = field(default_factory=dict)
    aggressor_known_pct: float | None = None
    last_event_available_ns: int | None = None


class QualityGate:
    def __init__(self, contract_id: str, config: GateConfig | None = None) -> None:
        self.contract_id = contract_id
        self.cfg = config or GateConfig()
        self.book = BookTracker(contract_id)
        self.state = QualityState()
        self._last_seq: int | None = None
        self._reset_pending = False
        self._crossed_since: int | None = None
        self._trading: bool | None = None
        self._trades: deque[tuple[int, int, bool]] = deque()  # (available_at, size, known)
        self._was_blocked = False

    # ---- eventos -------------------------------------------------------------------------------
    def apply(self, ev: MarketEvent) -> QualityState:
        if ev.contract_id != self.contract_id:
            raise ValueError("contrato distinto")
        st = self.state
        st.last_event_available_ns = ev.available_at_ns
        for f in ev.quality_flags:
            if f.startswith("F_") or f in ("PRICE_OFF_GRID", "TRADE_PRICE_UNDEF"):
                st.provider_flags[f] = st.provider_flags.get(f, 0) + 1

        # Validez del evento
        invalid: list[str] = []
        if "PRICE_OFF_GRID" in ev.quality_flags:
            invalid.append("PRICE_OFF_GRID")
        if ev.size_contracts is not None and ev.size_contracts < 0:
            invalid.append("NEGATIVE_SIZE")
        if invalid and self.cfg.invalid_blocks_session:
            st.session_excluded = True

        # Secuencia (diagnóstico, no bloqueo)
        if ev.sequence is not None and self._last_seq is not None and ev.sequence > self._last_seq + 1:
            st.sequence_jumps += 1
        if ev.sequence is not None:
            self._last_seq = ev.sequence

        # Status
        if ev.event_type is EventType.STATUS:
            self._trading = "IS_TRADING" in ev.quality_flags

        # Reset
        if ev.event_type is EventType.RESET:
            self._reset_pending = True

        # Trades → ventana de agresor
        if ev.event_type is EventType.TRADE and ev.size_contracts:
            self._trades.append((ev.available_at_ns, ev.size_contracts, ev.aggressor is not Aggressor.UNKNOWN))
        cutoff = ev.available_at_ns - self.cfg.aggressor_window_ns
        while self._trades and self._trades[0][0] < cutoff:
            self._trades.popleft()

        # Libro
        snap = self.book.apply(ev)
        if snap is not None:
            if self._reset_pending and snap.complete:
                self._reset_pending = False
            if snap.crossed:
                if self._crossed_since is None:
                    self._crossed_since = ev.available_at_ns
            else:
                self._crossed_since = None

        return self._evaluate(ev.available_at_ns, invalid)

    def check_staleness(self, now_ns: int) -> QualityState:
        """Llamar en cada epoch del replay/scanner: un libro sin cambios puede ser válido, pero sin
        ningún evento durante `stale_after_ns` el contrato se bloquea (umbral operativo, spec §3.4)."""
        return self._evaluate(now_ns, [])

    # ---- evaluación ----------------------------------------------------------------------------
    def _evaluate(self, now_ns: int, invalid: list[str]) -> QualityState:
        st = self.state
        reasons: list[str] = list(invalid)
        if st.session_excluded:
            reasons.append("SESSION_EXCLUDED")
        if self._reset_pending:
            reasons.append("RESET_UNRECOVERED")
        if self.book.snapshot is None:
            reasons.append("NO_BOOK")
        elif not self.book.snapshot.complete:
            reasons.append("INCOMPLETE_BOOK")
        if self._crossed_since is not None and now_ns - self._crossed_since > self.cfg.crossed_grace_ns:
            reasons.append("CROSSED_BOOK_PERSISTENT")
        if st.last_event_available_ns is not None and now_ns - st.last_event_available_ns > self.cfg.stale_after_ns:
            reasons.append("STALE_FEED")
        if self._trading is False:
            reasons.append("NOT_TRADING")

        vol = sum(s for _, s, _ in self._trades)
        known = sum(s for _, s, k in self._trades if k)
        st.aggressor_known_pct = (100.0 * known / vol) if vol else None
        if vol >= self.cfg.min_aggressor_volume and st.aggressor_known_pct is not None \
                and st.aggressor_known_pct < self.cfg.min_aggressor_known_pct:
            reasons.append("AGGRESSOR_UNKNOWN_HIGH")

        blocked = bool(reasons)
        if self._was_blocked and not blocked:
            st.rewarm_required = True
        self._was_blocked = blocked
        st.blocked = blocked
        st.reasons = tuple(reasons)
        return st

    def acknowledge_rewarm(self) -> None:
        self.state.rewarm_required = False

    @property
    def snapshot(self) -> BookSnapshot | None:
        return self.book.snapshot
