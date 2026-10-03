"""Liquidity Reversal LR-v1 (spec §5): reglas ejecutables, máquina de estados y emisión de candidatos.

Unidades: ticks, contratos, ns. Todo parámetro es de investigación (spec §5.1), congelado en LRParams.
El detector NO consulta Jev ni decide ejecución: emite LRSignal (READY) con stop absoluto y TTL; el
scanner/risk engine deciden después. Long: barrida de un nivel BAJO y reclaim al alza. Short: simétrico
(signo `sgn`). Las condiciones de flujo y volumen se evalúan en el instante del trigger, nunca con una
vela futura. Un extremo de barrida congelado no se mueve: si se extiende tras el reclaim, se invalida.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from trading_scanner.contracts import CandidateState, Direction

NS = 1_000_000_000
LR_VERSION = "LR-v1"


class LevelKind(str, Enum):
    PRIOR_DAY_HIGH = "prior_day_high"
    PRIOR_DAY_LOW = "prior_day_low"
    OR_HIGH = "or_high"
    OR_LOW = "or_low"


@dataclass(frozen=True)
class LRParams:
    proximity_min_ticks: int = 2
    proximity_atr_mult: float = 0.25
    penetration_min_ticks: int = 2
    penetration_max_atr_mult: float = 0.75
    reclaim_timeout_ns: int = 30 * NS
    reclaim_ticks: int = 1
    delta_ratio_min: float = 0.20
    volume_5s_min_rel_median: float = 0.50
    confirm_move_ticks: int = 2
    confirm_window_ns: int = 10 * NS
    stop_buffer_ticks: int = 2
    risk_min_ticks: int = 4
    risk_max_atr_mult: float = 1.5
    target_r: float = 2.0
    armed_timeout_ns: int = 5 * 60 * NS
    cooldown_ns: int = 10 * 60 * NS
    max_attempts_per_day: int = 2
    candidate_ttl_ns: int = 2 * NS
    merge_distance_ticks: int = 2
    max_spread_ticks: int = 2  # ES 2, NQ 3, GC 3 (spec §5.2); se fija por contrato al construir


@dataclass(frozen=True)
class Level:
    kind: LevelKind
    price_ticks: int
    merged_with: tuple[tuple[str, int], ...] = ()

    @property
    def id(self) -> str:
        return f"{self.kind.value}@{self.price_ticks}"

    @property
    def direction(self) -> Direction:
        return Direction.LONG if self.kind in (LevelKind.PRIOR_DAY_LOW, LevelKind.OR_LOW) else Direction.SHORT


@dataclass(frozen=True)
class Trade:
    ts_ns: int  # available_at (tiempo causal)
    price_ticks: int
    size: int


@dataclass(frozen=True)
class LRContext:
    """Estado as-of que el detector necesita; lo arma el scanner desde FeatureSnapshot + gate + calendario."""

    atr_1m_ticks: float | None
    delta_ratio_5s: float | None
    volume_5s: int | None
    volume_5s_median: float | None
    spread_ticks: int | None
    in_entry_window: bool
    blocked_reasons: tuple[str, ...] = ()  # calidad, régimen UNKNOWN, shock, macro…

    @property
    def blocked(self) -> bool:
        return bool(self.blocked_reasons)


@dataclass(frozen=True)
class Transition:
    level_id: str
    direction: Direction
    state: CandidateState
    at_ns: int
    reason: str | None = None


@dataclass(frozen=True)
class LRSignal:
    """Candidato READY inmutable (spec §5.2 paso 5)."""

    id: str
    contract_id: str
    level: Level
    direction: Direction
    created_at_ns: int
    expires_at_ns: int
    trigger_price_ticks: int
    reclaim_price_ticks: int
    sweep_extreme_ticks: int
    stop_ticks: int
    risk_ticks_at_trigger: int
    target_ticks_at_trigger: int
    atr_1m_ticks_frozen: float
    delta_ratio_5s: float
    volume_5s_rel_median: float
    spread_ticks: int
    attempt: int
    setup_version: str = LR_VERSION


@dataclass
class _Machine:
    level: Level
    direction: Direction
    state: CandidateState = CandidateState.IDLE
    armed_at: int | None = None
    atr_frozen: float | None = None
    pen_min: int = 0
    pen_max: int = 0
    swept_at: int | None = None
    extreme: int | None = None
    reclaim_at: int | None = None
    reclaim_px: int | None = None
    attempts: int = 0
    cooldown_until: int | None = None
    log: list[Transition] = field(default_factory=list)

    @property
    def sgn(self) -> int:
        return 1 if self.direction is Direction.LONG else -1

    def go(self, state: CandidateState, at: int, reason: str | None = None) -> None:
        self.state = state
        self.log.append(Transition(self.level.id, self.direction, state, at, reason))

    def terminate(self, at: int, terminal: CandidateState, reason: str, *, attempt: bool) -> Transition:
        self.go(terminal, at, reason)
        if attempt:
            self.attempts += 1
            self.cooldown_until = at
        self.state = CandidateState.IDLE
        self.armed_at = self.swept_at = self.extreme = self.reclaim_at = self.reclaim_px = None
        return self.log[-1]


class LRDetector:
    def __init__(self, contract_id: str, params: LRParams | None = None) -> None:
        self.contract_id = contract_id
        self.p = params or LRParams()
        self._machines: dict[str, _Machine] = {}
        self._signals = 0
        self.rejections: list[Transition] = []

    @property
    def transitions(self) -> list[Transition]:
        return sorted((t for m in self._machines.values() for t in m.log), key=lambda t: t.at_ns)

    def state_of(self, level_id: str) -> CandidateState:
        return self._machines[level_id].state

    # ---- niveles ---------------------------------------------------------------------------------
    def set_levels(self, levels: list[Level]) -> list[Level]:
        """Fusiona niveles de la misma dirección a <= merge_distance (prioridad día anterior; se guardan
        ambas referencias). Reinicia las máquinas: llamar una vez por sesión."""
        merged: list[Level] = []
        prio = sorted(levels, key=lambda l: (0 if "prior_day" in l.kind.value else 1, l.price_ticks))
        for lv in prio:
            near = [m for m in merged if m.direction is lv.direction
                    and abs(m.price_ticks - lv.price_ticks) <= self.p.merge_distance_ticks]
            if near:
                m = near[0]
                merged[merged.index(m)] = Level(m.kind, m.price_ticks, m.merged_with + ((lv.kind.value, lv.price_ticks),))
            else:
                merged.append(lv)
        self._machines = {lv.id: _Machine(lv, lv.direction) for lv in merged}
        return merged

    # ---- eventos ---------------------------------------------------------------------------------
    def on_time(self, now_ns: int) -> None:
        """Vencimientos por tiempo (ARMED 5 min, reclaim 30 s, confirmación 10 s) sin necesidad de trade."""
        for m in self._machines.values():
            self._expire(m, now_ns)

    def on_trade(self, tr: Trade, ctx: LRContext) -> list[LRSignal]:
        ready: list[tuple[_Machine, LRSignal]] = []
        for m in self._machines.values():
            sig = self._step(m, tr, ctx)
            if sig is not None:
                ready.append((m, sig))
        if not ready:
            return []
        longs = [r for r in ready if r[1].direction is Direction.LONG]
        shorts = [r for r in ready if r[1].direction is Direction.SHORT]
        if longs and shorts:  # spec §5.3: abstención para el contrato en este epoch
            for m, _ in ready:
                self.rejections.append(m.terminate(tr.ts_ns, CandidateState.INVALIDATED, "CONFLICTING_SETUPS", attempt=True))
            return []
        out: list[LRSignal] = []
        for group in (longs, shorts):
            if not group:
                continue
            group.sort(key=lambda r: r[0].armed_at or 0)  # gana el armado más antiguo
            for m, _ in group[1:]:
                self.rejections.append(m.terminate(tr.ts_ns, CandidateState.INVALIDATED, "DUPLICATE_OF_EVENT", attempt=True))
            m, sig = group[0]
            m.go(CandidateState.READY, tr.ts_ns, "trigger")
            m.terminate(tr.ts_ns, CandidateState.CONSUMED, "candidate_emitted", attempt=True)
            out.append(sig)
        return out

    # ---- máquina -----------------------------------------------------------------------------------
    def _reject(self, m: _Machine, at: int, reason: str) -> None:
        self.rejections.append(m.terminate(at, CandidateState.INVALIDATED, reason, attempt=True))

    def _expire(self, m: _Machine, now: int) -> None:
        p = self.p
        if m.state is CandidateState.ARMED and now - m.armed_at > p.armed_timeout_ns:
            m.terminate(now, CandidateState.EXPIRED, "ARMED_TIMEOUT_5MIN", attempt=False)
        elif m.state is CandidateState.SWEPT and now - m.swept_at > p.reclaim_timeout_ns:
            self._reject(m, now, "NO_RECLAIM_30S")
        elif m.state is CandidateState.RECLAIMED and now - m.reclaim_at > p.confirm_window_ns:
            self._reject(m, now, "NO_CONFIRMATION_10S")

    def _can_arm(self, m: _Machine, now: int) -> bool:
        if m.attempts >= self.p.max_attempts_per_day:
            return False
        return m.cooldown_until is None or now - m.cooldown_until >= self.p.cooldown_ns

    def _step(self, m: _Machine, tr: Trade, ctx: LRContext) -> LRSignal | None:
        p, s, lv, px, now = self.p, m.sgn, m.level.price_ticks, tr.price_ticks, tr.ts_ns
        self._expire(m, now)

        if m.state is CandidateState.IDLE:
            if not self._can_arm(m, now) or ctx.blocked or not ctx.in_entry_window or ctx.atr_1m_ticks is None:
                return None
            atr = ctx.atr_1m_ticks
            prox = max(p.proximity_min_ticks, math.ceil(p.proximity_atr_mult * atr))
            pen_max = math.floor(p.penetration_max_atr_mult * atr)
            dist = s * (px - lv)  # long: precio arriba del nivel → positivo
            if 0 < dist <= prox and pen_max >= p.penetration_min_ticks:
                m.armed_at, m.atr_frozen, m.pen_min, m.pen_max = now, atr, p.penetration_min_ticks, pen_max
                m.go(CandidateState.ARMED, now, f"dist={dist} prox={prox} pen_max={pen_max}")
            return None

        if m.state is CandidateState.ARMED:
            pen = s * (lv - px)
            if pen >= m.pen_min:
                if pen > m.pen_max:
                    self._reject(m, now, f"PENETRATION_GT_MAX({pen}>{m.pen_max})")
                    return None
                m.swept_at, m.extreme = now, px
                m.go(CandidateState.SWEPT, now, f"pen={pen}")
            return None

        if m.state is CandidateState.SWEPT:
            pen = s * (lv - px)
            if pen > s * (lv - m.extreme):
                m.extreme = px
                if pen > m.pen_max:
                    self._reject(m, now, f"PENETRATION_GT_MAX({pen}>{m.pen_max})")
                    return None
            if s * (px - lv) >= p.reclaim_ticks:
                m.reclaim_at, m.reclaim_px = now, px
                m.go(CandidateState.RECLAIMED, now, f"reclaim_px={px} extreme={m.extreme}")
            return None

        if m.state is CandidateState.RECLAIMED:
            if s * (m.extreme - px) > 0:
                self._reject(m, now, "NEW_EXTREME_AFTER_RECLAIM")
                return None
            if s * (px - m.reclaim_px) < p.confirm_move_ticks:
                return None
            # Trigger de movimiento: evaluar todo lo demás EN ESTE instante.
            reason = self._veto(m, ctx)
            if reason:
                self._reject(m, now, reason)
                return None
            stop = m.extreme - s * p.stop_buffer_ticks
            risk = s * (px - stop)
            risk_max = math.ceil(p.risk_max_atr_mult * m.atr_frozen)
            if not (p.risk_min_ticks <= risk <= risk_max):
                self._reject(m, now, f"RISK_OUT_OF_RANGE({risk} not in [{p.risk_min_ticks},{risk_max}])")
                return None
            self._signals += 1
            return LRSignal(
                id=f"lr-{self.contract_id}-{now}-{self._signals}", contract_id=self.contract_id, level=m.level,
                direction=m.direction, created_at_ns=now, expires_at_ns=now + p.candidate_ttl_ns,
                trigger_price_ticks=px, reclaim_price_ticks=m.reclaim_px, sweep_extreme_ticks=m.extreme,
                stop_ticks=stop, risk_ticks_at_trigger=risk,
                target_ticks_at_trigger=px + s * math.ceil(p.target_r * risk),
                atr_1m_ticks_frozen=m.atr_frozen, delta_ratio_5s=ctx.delta_ratio_5s,
                volume_5s_rel_median=ctx.volume_5s / ctx.volume_5s_median, spread_ticks=ctx.spread_ticks,
                attempt=m.attempts + 1,
            )
        return None

    def _veto(self, m: _Machine, ctx: LRContext) -> str | None:
        p = self.p
        if ctx.blocked:
            return "BLOCKED:" + ",".join(ctx.blocked_reasons)
        if not ctx.in_entry_window:
            return "OUTSIDE_ENTRY_WINDOW"
        if ctx.delta_ratio_5s is None:
            return "DELTA_RATIO_MISSING"
        if ctx.volume_5s is None or not ctx.volume_5s_median:
            return "VOLUME_REFERENCE_MISSING"
        if m.sgn * ctx.delta_ratio_5s < p.delta_ratio_min:
            return f"DELTA_CONTRARY({ctx.delta_ratio_5s:+.2f})"
        if ctx.volume_5s < p.volume_5s_min_rel_median * ctx.volume_5s_median:
            return "VOLUME_5S_BELOW_50PCT_MEDIAN"
        if ctx.spread_ticks is None or ctx.spread_ticks > p.max_spread_ticks:
            return f"SPREAD_GT_MAX({ctx.spread_ticks})"
        return None
