"""Orquestador de una sesión del piloto (replay end-to-end sin Jev ni selector; fase A del experimento):
adapter → QualityGate → FeatureEngine → LR-v1 → EXEC-v1, por contrato. Produce un reporte auditable.

Niveles de LR: high/low del día anterior (F08) inyectados desde `prior_levels` y opening range (F09)
calculado en la sesión. Régimen/shock/macro se integran en ENG-09+; aquí `blocked` = gate + ventana.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from trading_scanner.adapters.jev import JevClient, build_state
from trading_scanner.adapters.market import AdapterStats, iter_mbp10_events
from trading_scanner.clock import SessionWindow
from trading_scanner.contracts import ClassificationResult, ContractSpec, EventType, MarketEvent, Outcome
from trading_scanner.execution import ExecParams, ExecutionSim
from trading_scanner.features import FeatureEngine
from trading_scanner.quality import QualityGate
from trading_scanner.regimes import MacroCalendar, RegimeTracker
from trading_scanner.replay.engine import Replay
from trading_scanner.setups.liquidity_reversal import Level, LevelKind, LRContext, LRDetector, LRParams, LRSignal, Trade

NS = 1_000_000_000


@dataclass
class ContractRun:
    spec: ContractSpec
    instrument_id: int
    files: list[Path]
    gate: QualityGate
    engine: FeatureEngine
    lr: LRDetector
    regime: RegimeTracker = field(default_factory=RegimeTracker)
    stats: AdapterStats = field(default_factory=AdapterStats)
    levels_set: bool = False
    signals: list[LRSignal] = field(default_factory=list)
    outcomes: list[Outcome] = field(default_factory=list)
    active: ExecutionSim | None = None
    classifications: dict[str, ClassificationResult] = field(default_factory=dict)
    pending_b: list[tuple[LRSignal, int]] = field(default_factory=list)  # (señal, received_at) esperando a enviar
    jev_expired: int = 0
    blocked_epochs: int = 0
    epochs: int = 0
    block_reasons: dict[str, int] = field(default_factory=dict)
    last_snapshot_values: dict | None = None


class SessionRunner:
    def __init__(self, window: SessionWindow, *, lr_params_by_root: dict[str, LRParams] | None = None,
                 exec_params: ExecParams | None = None, prior_levels: dict[str, tuple[int, int]] | None = None,
                 event_start_ns: int | None = None, event_end_ns: int | None = None,
                 macro: MacroCalendar | None = None, jev: JevClient | None = None) -> None:
        self.window = window
        self.macro = macro
        self.jev = jev  # experimento B: si hay cliente, la orden se envía al "existir" la respuesta (<= TTL)
        self.event_start_ns = event_start_ns  # filtro barato del adapter (ts_recv); None = todo el archivo
        self.event_end_ns = event_end_ns
        self.lr_params_by_root = lr_params_by_root or {}
        self.exec_params = exec_params or ExecParams()
        self.prior_levels = prior_levels or {}
        self.runs: dict[str, ContractRun] = {}

    def add_contract(self, spec: ContractSpec, instrument_id: int, files: list[Path]) -> None:
        eng = FeatureEngine(spec.contract_id, session_open_ns=self.window.rth_open_ns,
                            opening_range_end_ns=self.window.opening_range_end_ns)
        if spec.contract_id in self.prior_levels:
            eng.set_prior_day_levels(*self.prior_levels[spec.contract_id])
        lr = LRDetector(spec.contract_id, self.lr_params_by_root.get(spec.root, LRParams()))
        run = ContractRun(spec, instrument_id, files, QualityGate(spec.contract_id), eng, lr)
        # régimen y shock se alimentan al cierre de barra (nunca con la barra en formación)
        eng.bars_5m.on_finalize = lambda bar, r=run: r.regime.on_bar_5m_close(r.engine.bars_5m.finalized, bar.finalized_at_ns)
        eng.bars_1m.on_finalize = lambda bar, r=run: r.regime.on_bar_1m_close(r.engine.bars_1m.finalized, bar.finalized_at_ns)
        self.runs[spec.contract_id] = run

    # ---- ejecución -------------------------------------------------------------------------------
    def run(self) -> dict[str, ContractRun]:
        streams = []
        for r in self.runs.values():
            streams.append(self._stream(r))
        rp = Replay(streams, stop_at_ns=self.event_end_ns or self.window.rth_close_ns)
        rp.run(self._on_event, self._on_epoch)
        for r in self.runs.values():
            if r.active is not None and r.active.done is None:
                r.active.on_time(self.window.rth_close_ns)
        return self.runs

    def _stream(self, r: ContractRun):
        for f in r.files:
            yield from iter_mbp10_events(f, r.spec, r.instrument_id, stats=r.stats,
                                         start_ns=self.event_start_ns, end_ns=self.event_end_ns)

    def _ctx(self, r: ContractRun, now: int) -> LRContext:
        v = r.last_snapshot_values or {}
        reasons = list(r.gate.state.reasons)
        return LRContext(atr_1m_ticks=v.get("F03_atr14_1m"), delta_ratio_5s=v.get("F05_delta_ratio_5s"),
                         volume_5s=None, volume_5s_median=v.get("F15_median_5s"),
                         spread_ticks=v.get("F01_spread"), in_entry_window=self.window.accepts_new_entry(now),
                         blocked_reasons=tuple(reasons))

    def _on_event(self, ev: MarketEvent) -> None:
        r = self.runs[ev.contract_id]
        st = r.gate.apply(ev)
        r.engine.apply(ev)
        snap = r.gate.snapshot
        if r.active is not None and snap is not None and r.active.done is None:
            out = r.active.on_book(snap)
            if out is not None:
                r.outcomes.append(out)
                r.active = None
        if ev.event_type is not EventType.TRADE or ev.price_ticks is None:
            return
        if not r.levels_set and ev.available_at_ns >= self.window.entry_start_ns:
            self._set_levels(r)
        if not r.levels_set:
            return
        blocked = tuple(st.reasons) + r.regime.blocked_reasons(ev.available_at_ns) + (self.macro.blocked_reasons(ev.available_at_ns) if self.macro else ())
        # F15 en el instante: volumen del bloque 5s actual desde el engine
        cur = r.engine._cur_block[1] if r.engine._cur_block else None
        v = r.last_snapshot_values or {}
        ctx = LRContext(atr_1m_ticks=v.get("F03_atr14_1m"), delta_ratio_5s=self._delta_now(r, ev.available_at_ns),
                        volume_5s=cur, volume_5s_median=v.get("F15_median_5s"), spread_ticks=snap.spread_ticks if snap else None,
                        in_entry_window=self.window.accepts_new_entry(ev.available_at_ns), blocked_reasons=blocked)
        sigs = r.lr.on_trade(Trade(ev.available_at_ns, ev.price_ticks, ev.size_contracts or 0), ctx)
        for s in sigs:
            r.signals.append(s)
            if self.jev is None:
                self._send(r, s, ev.available_at_ns, snap)
            else:
                self._classify(r, s, snap)
        self._flush_pending_b(r, ev.available_at_ns, snap)

    def _send(self, r: ContractRun, s: LRSignal, at_ns: int, snap: BookSnapshot | None) -> None:
        if r.active is None and snap is not None:  # una posición por contrato (D07: una total → ENG-10)
            r.active = ExecutionSim(s, s.id, params=self.exec_params, tick_value_usd=r.spec.tick_value,
                                    send_at_ns=at_ns, book_at_send=snap, flat_by_ns=self.window.flat_by_ns)
            if r.active.done is not None:
                r.outcomes.append(r.active.done)
                r.active = None

    def _classify(self, r: ContractRun, s: LRSignal, snap: BookSnapshot | None) -> None:
        """Experimento B: una llamada por candidato con el snapshot congelado; la respuesta solo existe en
        received_at. Si llega después del TTL o falla, el candidato expira (sin retry, sin fallback a A)."""
        assert self.jev is not None
        fs = r.engine.snapshot(max(s.created_at_ns, r.engine.max_input_available_ns))
        bars = [{"o": b.open, "h": b.high, "l": b.low, "c": b.close, "v": b.volume} for b in r.engine.bars_1m.finalized[-12:]]
        depth = {"bid": [[l.price_ticks, l.size_contracts] for l in snap.bids[:5]], "ask": [[l.price_ticks, l.size_contracts] for l in snap.asks[:5]]} if snap else None
        state = build_state(s, fs, bars, depth, {"flags": list(r.gate.state.reasons), "aggressor_known_pct": r.gate.state.aggressor_known_pct})
        res = self.jev.classify(s.id, state, s.created_at_ns, result_id=f"cls-{s.id}")
        r.classifications[s.id] = res
        if res.validation_status != "OK" or res.received_at_ns is None or res.received_at_ns > s.expires_at_ns:
            r.jev_expired += 1
            return
        r.pending_b.append((s, res.received_at_ns))

    def _flush_pending_b(self, r: ContractRun, now_ns: int, snap: BookSnapshot | None) -> None:
        if not r.pending_b or snap is None:
            return
        keep = []
        for s, received_at in r.pending_b:
            if now_ns < received_at:
                keep.append((s, received_at))
                continue
            if now_ns > s.expires_at_ns:
                r.jev_expired += 1
                continue
            # la referencia no debe haberse alejado > 2 ticks del trigger (spec §5.2 paso 6)
            ref = snap.best_ask if s.direction.value == "LONG" else snap.best_bid
            if ref is None or abs(ref - s.trigger_price_ticks) > 2:
                r.jev_expired += 1
                continue
            self._send(r, s, now_ns, snap)
        r.pending_b = keep

    def _delta_now(self, r: ContractRun, now: int) -> float | None:
        _, ratio, _ = r.engine._delta(now, 5)
        return ratio

    def _set_levels(self, r: ContractRun) -> None:
        eng = r.engine
        levels: list[Level] = []
        if eng.prior_day_high is not None:
            levels += [Level(LevelKind.PRIOR_DAY_HIGH, eng.prior_day_high), Level(LevelKind.PRIOR_DAY_LOW, eng.prior_day_low)]
        if eng.or_high is not None and eng.or_low is not None:
            levels += [Level(LevelKind.OR_HIGH, eng.or_high), Level(LevelKind.OR_LOW, eng.or_low)]
        if levels:
            r.lr.set_levels(levels)
            r.levels_set = True

    def _on_epoch(self, t: int) -> None:
        for r in self.runs.values():
            r.epochs += 1
            st = r.gate.check_staleness(t)
            reasons = tuple(st.reasons) + r.regime.blocked_reasons(t) + (self.macro.blocked_reasons(t) if self.macro else ())
            if reasons:
                r.blocked_epochs += 1
                for reason in reasons:
                    r.block_reasons[reason] = r.block_reasons.get(reason, 0) + 1
            r.last_snapshot_values = r.engine.snapshot(t).values
            r.lr.on_time(t)
            if r.active is not None and r.active.done is None:
                r.active.on_time(t)


def summarize(runs: dict[str, ContractRun]) -> dict:
    out = {}
    for cid, r in runs.items():
        outs = r.outcomes
        pnl = sum((o.PnL_USD for o in outs if o.PnL_USD is not None), Decimal("0"))
        out[cid] = {
            "records": r.stats.records, "trades": r.stats.trades, "volume": r.stats.trade_volume,
            "aggressor_known_pct": None if r.stats.aggressor_known_pct is None else round(r.stats.aggressor_known_pct, 3),
            "resets": r.stats.resets, "off_grid": r.stats.off_grid_prices, "provider_flags": r.gate.state.provider_flags,
            "sequence_jumps": r.gate.state.sequence_jumps, "epochs": r.epochs, "blocked_epochs": r.blocked_epochs,
            "block_reasons": r.block_reasons, "bars_1m": len(r.engine.bars_1m.finalized),
            "late_revisions_1m": r.engine.bars_1m.late_revisions, "or": [r.engine.or_high, r.engine.or_low],
            "regime_history": [(t, reg.value) for t, reg in r.regime.history], "shocks": r.regime.shocks,
            "jev_classified": len(r.classifications), "jev_expired": r.jev_expired,
            "lr_transitions": len(r.lr.transitions), "lr_rejections": {}, "signals": len(r.signals),
            "outcomes": {o.terminal_reason.value: sum(1 for x in outs if x.terminal_reason is o.terminal_reason) for o in outs},
            "pnl_usd_net": str(pnl),
        }
        for rej in r.lr.rejections:
            k = rej.reason.split("(")[0]
            out[cid]["lr_rejections"][k] = out[cid]["lr_rejections"].get(k, 0) + 1
    return out
