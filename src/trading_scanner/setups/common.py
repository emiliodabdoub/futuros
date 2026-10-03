"""Tipos compartidos por TC-v1 y BO-v1 (ENG-11). LR-v1 conserva su LRSignal; ExecutionSim usa duck typing
(id, contract_id, direction, stop_ticks, created_at_ns, expires_at_ns)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from trading_scanner.contracts import CandidateState, Direction
from trading_scanner.setups.liquidity_reversal.lr_v1 import LRContext, LRParams, Transition

NS = 1_000_000_000


@dataclass(frozen=True)
class SetupSignal:
    id: str
    contract_id: str
    setup_version: str
    direction: Direction
    created_at_ns: int
    expires_at_ns: int
    trigger_price_ticks: int
    stop_ticks: int
    risk_ticks_at_trigger: int
    target_ticks_at_trigger: int
    atr_1m_ticks_frozen: float
    delta_ratio_5s: float
    volume_5s_rel_median: float
    spread_ticks: int
    reference: dict[str, int | float] = field(default_factory=dict)


def common_veto(ctx: LRContext, sgn: int, p: LRParams, *, volume_rel_min: float) -> str | None:
    """Vetos compartidos en el instante del trigger: bloqueos, ventana, flujo, volumen, spread."""
    if ctx.blocked:
        return "BLOCKED:" + ",".join(ctx.blocked_reasons)
    if not ctx.in_entry_window:
        return "OUTSIDE_ENTRY_WINDOW"
    if ctx.delta_ratio_5s is None:
        return "DELTA_RATIO_MISSING"
    if ctx.volume_5s is None or not ctx.volume_5s_median:
        return "VOLUME_REFERENCE_MISSING"
    if sgn * ctx.delta_ratio_5s < p.delta_ratio_min:
        return f"DELTA_CONTRARY({ctx.delta_ratio_5s:+.2f})"
    if ctx.volume_5s < volume_rel_min * ctx.volume_5s_median:
        return f"VOLUME_5S_BELOW_{int(volume_rel_min * 100)}PCT_MEDIAN"
    if ctx.spread_ticks is None or ctx.spread_ticks > p.max_spread_ticks:
        return f"SPREAD_GT_MAX({ctx.spread_ticks})"
    return None


def risk_check(px: int, stop: int, sgn: int, atr: float, p: LRParams) -> tuple[int, str | None]:
    risk = sgn * (px - stop)
    risk_max = math.ceil(p.risk_max_atr_mult * atr)
    if not (p.risk_min_ticks <= risk <= risk_max):
        return risk, f"RISK_OUT_OF_RANGE({risk} not in [{p.risk_min_ticks},{risk_max}])"
    return risk, None


def make_signal(*, id: str, contract_id: str, version: str, direction: Direction, now: int, px: int, stop: int,
                risk: int, atr: float, ctx: LRContext, p: LRParams, reference: dict) -> SetupSignal:
    sgn = 1 if direction is Direction.LONG else -1
    assert ctx.delta_ratio_5s is not None and ctx.volume_5s is not None and ctx.volume_5s_median
    return SetupSignal(id=id, contract_id=contract_id, setup_version=version, direction=direction, created_at_ns=now,
                       expires_at_ns=now + p.candidate_ttl_ns, trigger_price_ticks=px, stop_ticks=stop,
                       risk_ticks_at_trigger=risk, target_ticks_at_trigger=px + sgn * math.ceil(p.target_r * risk),
                       atr_1m_ticks_frozen=atr, delta_ratio_5s=ctx.delta_ratio_5s,
                       volume_5s_rel_median=ctx.volume_5s / ctx.volume_5s_median, spread_ticks=ctx.spread_ticks or 0,
                       reference=reference)


__all__ = ["SetupSignal", "common_veto", "risk_check", "make_signal", "CandidateState", "Transition", "NS"]
