"""EXEC-v1: política de ejecución simulada y etiquetado de outcomes (spec §7, ENG-07).

Entrada: un contrato, orden marketable-limit IOC. Long: límite = ask al enviar + 2 ticks; al llegar
(latencia de orden) se consume el libro disponible hasta el límite; sin cantidad → NO_FILL. Sin reintento.
Salidas sintéticas que TOMAN liquidez: long, stop dispara con bid <= stop, target con bid >= target; tras
el disparo se aplica latencia de salida y se ejecuta contra el libro disponible en ese momento (no se
garantiza el precio de barrera). TIME_EXIT a los 15 min del fill o a las 11:45 NY, lo primero.
Coincidencia de triggers en el mismo timestamp: prioridad conservadora stop → time → target + flag.
Sin libro ejecutable al salir: UNPRICED_EXIT (nunca se asume fill al último precio).
Fill que viola el presupuesto de riesgo: cerrar de inmediato y etiquetar EMERGENCY_EXIT.
Fricción: comisión round-trip sintética (USD 6 placeholder de ingeniería, no tarifa de broker) y slippage
adverso adicional por salida (0/1/2 ticks) como stress. El spread ya está en bid/ask: no se resta dos veces.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal

from trading_scanner.contracts import Direction, Outcome, TerminalReason
from trading_scanner.orderbook import BookSnapshot
from trading_scanner.setups.liquidity_reversal import LRSignal

NS = 1_000_000_000


@dataclass(frozen=True)
class ExecParams:
    entry_limit_offset_ticks: int = 2
    order_latency_ns: int = 100_000_000
    exit_latency_ns: int = 100_000_000
    max_hold_ns: int = 15 * 60 * NS
    commission_round_trip_usd: Decimal = Decimal("6")  # placeholder sintético (spec §7.3)
    extra_exit_slippage_ticks: int = 0
    target_r: float = 2.0
    risk_budget_ticks: int | None = None  # p.ej. ceil(1.5*ATR) congelado; None = sin presupuesto adicional

    @property
    def policy_hash(self) -> str:
        payload = json.dumps({k: str(v) for k, v in self.__dict__.items()}, sort_keys=True)
        return "exec-v1-" + hashlib.sha256(payload.encode()).hexdigest()[:12]


@dataclass
class ExecutionTrace:
    sent_at_ns: int
    limit_ticks: int
    arrival_ns: int
    fill_at_ns: int | None = None
    fill_ticks: int | None = None
    stop_ticks: int | None = None
    target_ticks: int | None = None
    time_exit_at_ns: int | None = None
    trigger_at_ns: int | None = None
    trigger_reason: TerminalReason | None = None
    exit_arrival_ns: int | None = None
    exit_at_ns: int | None = None
    exit_ticks: int | None = None
    mae_ticks: int = 0
    mfe_ticks: int = 0
    ambiguity_flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class ExecutionSim:
    """Una posición por instancia. Alimentar con cada BookSnapshot cerrado (F_LAST) posterior al envío."""

    def __init__(self, signal: LRSignal, candidate_id: str, *, params: ExecParams, tick_value_usd: Decimal,
                 send_at_ns: int, book_at_send: BookSnapshot, flat_by_ns: int) -> None:
        self.sig = signal
        self.candidate_id = candidate_id
        self.p = params
        self.tick_value = tick_value_usd
        self.flat_by_ns = flat_by_ns
        self.sgn = 1 if signal.direction is Direction.LONG else -1
        self.done: Outcome | None = None
        ref = book_at_send.best_ask if self.sgn > 0 else book_at_send.best_bid
        if ref is None:
            self.trace = ExecutionTrace(send_at_ns, 0, send_at_ns)
            self.done = self._terminal(TerminalReason.INVALID_DATA, send_at_ns, note="sin cotización al enviar")
            return
        self.trace = ExecutionTrace(sent_at_ns=send_at_ns, limit_ticks=ref + self.sgn * params.entry_limit_offset_ticks,
                                    arrival_ns=send_at_ns + params.order_latency_ns)
        self._pending_exit: tuple[TerminalReason, int] | None = None  # (motivo, llegada de la orden de salida)

    # ---- API -------------------------------------------------------------------------------------
    def on_book(self, snap: BookSnapshot) -> Outcome | None:
        if self.done is not None:
            return self.done
        t = snap.as_of_ns
        tr = self.trace
        if tr.fill_at_ns is None:
            if t < tr.arrival_ns:
                return None
            return self._try_fill(snap)
        if self._pending_exit is not None:
            reason, arrival = self._pending_exit
            if t >= arrival:
                return self._execute_exit(snap, reason)
            self._track_excursion(snap)
            return None
        self._track_excursion(snap)
        return self._check_triggers(snap)

    def on_time(self, now_ns: int) -> Outcome | None:
        """Sin snapshots nuevos también puede vencer el tiempo (libro sin cambios)."""
        if self.done is not None or self.trace.fill_at_ns is None or self._pending_exit is not None:
            return None
        if now_ns >= self.trace.time_exit_at_ns:
            self._arm_exit(TerminalReason.TIME_EXIT, self.trace.time_exit_at_ns)
        return None

    # ---- entrada ---------------------------------------------------------------------------------
    def _try_fill(self, snap: BookSnapshot) -> Outcome | None:
        tr, s = self.trace, self.sgn
        levels = snap.asks if s > 0 else snap.bids
        fill = None
        for lvl in levels:  # ya ordenados de mejor a peor
            if s * (lvl.price_ticks - tr.limit_ticks) > 0:
                break
            if lvl.size_contracts >= 1:
                fill = lvl.price_ticks
                break
        if fill is None:
            tr.notes.append("IOC sin cantidad ejecutable hasta el límite")
            self.done = self._terminal(TerminalReason.NO_FILL, snap.as_of_ns)
            return self.done
        tr.fill_at_ns, tr.fill_ticks = snap.as_of_ns, fill
        tr.stop_ticks = self.sig.stop_ticks
        risk = s * (fill - tr.stop_ticks)
        tr.target_ticks = fill + s * int(round(self.p.target_r * risk))
        tr.time_exit_at_ns = min(tr.fill_at_ns + self.p.max_hold_ns, self.flat_by_ns)
        if risk <= 0 or (self.p.risk_budget_ticks is not None and risk > self.p.risk_budget_ticks):
            tr.notes.append(f"fill {fill} deja riesgo {risk} fuera de presupuesto → EMERGENCY_EXIT")
            self._arm_exit(TerminalReason.EMERGENCY_EXIT, snap.as_of_ns)
        return None

    # ---- salidas ---------------------------------------------------------------------------------
    def _track_excursion(self, snap: BookSnapshot) -> None:
        mark = snap.best_bid if self.sgn > 0 else snap.best_ask  # precio al que podríamos salir
        if mark is None or self.trace.fill_ticks is None:
            return
        pnl = self.sgn * (mark - self.trace.fill_ticks)
        self.trace.mfe_ticks = max(self.trace.mfe_ticks, pnl)
        self.trace.mae_ticks = min(self.trace.mae_ticks, pnl)

    def _check_triggers(self, snap: BookSnapshot) -> Outcome | None:
        tr, s, t = self.trace, self.sgn, snap.as_of_ns
        mark = snap.best_bid if s > 0 else snap.best_ask
        hits: list[TerminalReason] = []
        if mark is not None and s * (mark - tr.stop_ticks) <= 0:
            hits.append(TerminalReason.STOP_TRIGGERED)
        if t >= tr.time_exit_at_ns:
            hits.append(TerminalReason.TIME_EXIT)
        if mark is not None and s * (mark - tr.target_ticks) >= 0:
            hits.append(TerminalReason.TARGET_TRIGGERED)
        if not hits:
            return None
        if len(hits) > 1:
            tr.ambiguity_flags.append("SIMULTANEOUS_TRIGGERS:" + ",".join(h.value for h in hits))
        # prioridad conservadora stop → time → target (ya en ese orden)
        self._arm_exit(hits[0], t)
        return None

    def _arm_exit(self, reason: TerminalReason, trigger_at: int) -> None:
        self.trace.trigger_at_ns, self.trace.trigger_reason = trigger_at, reason
        self._pending_exit = (reason, trigger_at + self.p.exit_latency_ns)
        self.trace.exit_arrival_ns = trigger_at + self.p.exit_latency_ns

    def _execute_exit(self, snap: BookSnapshot, reason: TerminalReason) -> Outcome:
        tr, s = self.trace, self.sgn
        levels = snap.bids if s > 0 else snap.asks  # tomamos liquidez del lado contrario
        px = next((l.price_ticks for l in levels if l.size_contracts >= 1), None)
        if px is None:
            tr.notes.append("sin libro ejecutable al llegar la orden de salida")
            self.done = self._terminal(TerminalReason.UNPRICED_EXIT, snap.as_of_ns)
            return self.done
        px -= s * self.p.extra_exit_slippage_ticks
        tr.exit_at_ns, tr.exit_ticks = snap.as_of_ns, px
        self.done = self._terminal(reason, snap.as_of_ns)
        return self.done

    # ---- outcome ---------------------------------------------------------------------------------
    def _terminal(self, reason: TerminalReason, at_ns: int, note: str | None = None) -> Outcome:
        tr = self.trace
        if note:
            tr.notes.append(note)
        pnl_usd = pnl_r = None
        net_pos = None
        costs = Decimal("0")
        if tr.fill_ticks is not None and tr.exit_ticks is not None:
            ticks = self.sgn * (tr.exit_ticks - tr.fill_ticks)
            costs = self.p.commission_round_trip_usd
            pnl_usd = Decimal(ticks) * self.tick_value - costs
            risk = self.sgn * (tr.fill_ticks - tr.stop_ticks)
            pnl_r = float(pnl_usd / (Decimal(risk) * self.tick_value)) if risk > 0 else None
            net_pos = pnl_usd > 0
        return Outcome(
            candidate_id=self.candidate_id, execution_policy_hash=self.p.policy_hash, simulated_or_observed="simulated",
            fill_at_ns=tr.fill_at_ns, fill_price_ticks=tr.fill_ticks, trigger_at_ns=tr.trigger_at_ns,
            exit_at_ns=tr.exit_at_ns, exit_price_ticks=tr.exit_ticks, terminal_reason=reason,
            net_positive=net_pos, costs_USD=costs, PnL_USD=pnl_usd, PnL_R=pnl_r,
            label_start_ns=self.sig.created_at_ns, label_end_ns=at_ns,
            data_quality={"mae_ticks": tr.mae_ticks, "mfe_ticks": tr.mfe_ticks, "notes": list(tr.notes),
                          "limit_ticks": tr.limit_ticks, "stop_ticks": tr.stop_ticks, "target_ticks": tr.target_ticks},
            ambiguity_flags=tuple(tr.ambiguity_flags),
        )
