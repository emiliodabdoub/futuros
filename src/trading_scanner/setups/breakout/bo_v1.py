"""Breakout BO-v1 (spec §6.2). Definido pero DESHABILITADO por defecto (D06).

- Cada minuto completo: evaluar las 15 barras 1m previas (sin la barra en formación). Armar rango si
  anchura <= 2 × ATR14 y efficiency ratio de esos cierres <= 0.25. Congelar high/low y ATR.
- Expira si no rompe en 10 min. Ruptura: trade >= high + 2 (long) o <= low − 2 (short).
- Aceptación: 5 s completos tras la ruptura con todos los trades fuera del límite, mínimo 5 trades,
  delta ratio 5 s >= 0.20 a favor y volumen 5 s >= mediana de F15 (100 %). Reentrada antes de
  confirmar invalida el intento; nuevo rango requiere cooldown 10 min.
- Stop long = high − 2; short = low + 2. Riesgo/target 2R/tiempo de LR. Stop estrecho rechaza, no se amplía.
"""

from __future__ import annotations

from dataclasses import dataclass

from trading_scanner.contracts import CandidateState, Direction
from trading_scanner.features.bars import Bar
from trading_scanner.features.indicators import atr_simple, efficiency_ratio
from trading_scanner.setups.common import NS, SetupSignal, Transition, common_veto, make_signal, risk_check
from trading_scanner.setups.liquidity_reversal.lr_v1 import LRContext, LRParams, Trade

BO_VERSION = "BO-v1"


@dataclass(frozen=True)
class BOParams:
    range_bars: int = 15
    width_atr_max: float = 2.0
    er_max: float = 0.25
    break_ticks: int = 2
    accept_ns: int = 5 * NS
    accept_min_trades: int = 5
    expire_ns: int = 10 * 60 * NS
    cooldown_ns: int = 10 * 60 * NS
    stop_inside_ticks: int = 2
    volume_rel_min: float = 1.0
    base: LRParams = LRParams()


@dataclass
class _Range:
    high: int
    low: int
    atr: float
    armed_at_ns: int
    break_at_ns: int | None = None
    direction: Direction | None = None
    trades_since_break: int = 0


class BODetector:
    def __init__(self, contract_id: str, params: BOParams | None = None, *, enabled: bool = False) -> None:
        self.contract_id = contract_id
        self.p = params or BOParams()
        self.enabled = enabled
        self.range: _Range | None = None
        self.cooldown_until: int | None = None
        self.transitions: list[Transition] = []
        self.rejections: list[Transition] = []
        self._n = 0

    def _log(self, state: CandidateState, at: int, reason: str | None = None, direction: Direction = Direction.LONG) -> Transition:
        t = Transition("range", direction, state, at, reason)
        self.transitions.append(t)
        return t

    def _reject(self, at: int, reason: str) -> None:
        assert self.range is not None
        self.rejections.append(self._log(CandidateState.INVALIDATED, at, reason, self.range.direction or Direction.LONG))
        self.range = None
        self.cooldown_until = at

    def on_bar_1m_close(self, bars: list[Bar], closed_at_ns: int, ctx: LRContext) -> None:
        if not self.enabled:
            return
        p = self.p
        if self.range is not None:
            if self.range.break_at_ns is None and closed_at_ns - self.range.armed_at_ns > p.expire_ns:
                self.transitions.append(Transition("range", Direction.LONG, CandidateState.EXPIRED, closed_at_ns, "NO_BREAK_10MIN"))
                self.range = None  # expirar no consume cooldown
            return
        if self.cooldown_until is not None and closed_at_ns - self.cooldown_until < p.cooldown_ns:
            return
        if ctx.blocked or len(bars) < p.range_bars + 15:
            return
        window = bars[-p.range_bars:]
        atr = atr_simple(bars, 14)
        if atr is None or atr <= 0:
            return
        hi, lo = max(b.high for b in window), min(b.low for b in window)
        er = efficiency_ratio([b.close for b in window])
        if hi - lo <= p.width_atr_max * atr and er is not None and er <= p.er_max:
            self.range = _Range(hi, lo, atr, closed_at_ns)
            self._log(CandidateState.ARMED, closed_at_ns, f"range {lo}-{hi} atr={atr:.1f} er={er:.2f}")

    def on_trade(self, tr: Trade, ctx: LRContext) -> list[SetupSignal]:
        r = self.range
        if not self.enabled or r is None:
            return []
        p, px, now = self.p, tr.price_ticks, tr.ts_ns
        if r.break_at_ns is None:
            if px >= r.high + p.break_ticks:
                r.break_at_ns, r.direction = now, Direction.LONG
                self._log(CandidateState.SWEPT, now, f"break_up {px}", Direction.LONG)
            elif px <= r.low - p.break_ticks:
                r.break_at_ns, r.direction = now, Direction.SHORT
                self._log(CandidateState.SWEPT, now, f"break_down {px}", Direction.SHORT)
            return []
        sgn = 1 if r.direction is Direction.LONG else -1
        limit = r.high if sgn > 0 else r.low
        if sgn * (px - limit) <= 0:  # reentra al rango antes de confirmar
            self._reject(now, "REENTRY_BEFORE_ACCEPTANCE")
            return []
        r.trades_since_break += 1
        if now - r.break_at_ns < p.accept_ns:
            return []
        if r.trades_since_break < p.accept_min_trades:
            self._reject(now, f"ACCEPTANCE_LT_{p.accept_min_trades}_TRADES")
            return []
        reason = common_veto(ctx, sgn, p.base, volume_rel_min=p.volume_rel_min)
        if reason:
            self._reject(now, reason)
            return []
        stop = (r.high - p.stop_inside_ticks) if sgn > 0 else (r.low + p.stop_inside_ticks)
        risk, rr = risk_check(px, stop, sgn, r.atr, p.base)
        if rr:
            self._reject(now, rr)
            return []
        self._n += 1
        sig = make_signal(id=f"bo-{self.contract_id}-{now}-{self._n}", contract_id=self.contract_id, version=BO_VERSION,
                          direction=r.direction, now=now, px=px, stop=stop, risk=risk, atr=r.atr, ctx=ctx, p=p.base,
                          reference={"range_high": r.high, "range_low": r.low, "break_at_ns": r.break_at_ns})
        self._log(CandidateState.READY, now, "accepted", r.direction)
        self._log(CandidateState.CONSUMED, now, "candidate_emitted", r.direction)
        self.range = None
        self.cooldown_until = now
        return [sig]
