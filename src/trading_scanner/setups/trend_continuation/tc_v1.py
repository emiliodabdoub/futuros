"""Trend Continuation TC-v1 (spec §6.1). Definido pero DESHABILITADO por defecto (D06): se activa por
configuración en un experimento versionado propio, nunca como sustituto tras observar pérdidas de LR.

- Precondición: régimen TREND_UP/DOWN confirmado y 60 min de contexto válido (ctx.regime + warm-up).
- Al cierre de cada barra 1m: impulso con las últimas 5 barras si desplazamiento neto >= 1.5 × ATR1m
  (ATR de ANTES de esas 5 barras) y efficiency ratio de sus cierres >= 0.60, en la dirección del régimen.
- Se congela origen, extremo y tamaño; primer impulso elegible mientras no haya otro armado.
- En las siguientes 5 barras: pullback de 25–60 % del impulso; > 60 % o vencimiento invalida.
- Dentro de la banda, trigger por trade que supere high de la última barra 1m completa + 1 tick (long)
  con delta ratio 5 s >= 0.20 a favor y volumen de confirmación de LR (>= 50 % mediana).
- Extremo del pullback congelado al trigger; stop 2 ticks detrás; target 2R; 15 min; riesgo/spread/TTL de LR.
- Sin retest, trailing ni piramidación. Un intento por impulso; cooldown 10 min.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from trading_scanner.contracts import CandidateState, Direction
from trading_scanner.features.bars import Bar
from trading_scanner.features.indicators import atr_simple, efficiency_ratio
from trading_scanner.setups.common import NS, SetupSignal, Transition, common_veto, make_signal, risk_check
from trading_scanner.setups.liquidity_reversal.lr_v1 import LRContext, LRParams, Trade

TC_VERSION = "TC-v1"


@dataclass(frozen=True)
class TCParams:
    impulse_bars: int = 5
    impulse_atr_mult: float = 1.5
    impulse_er_min: float = 0.60
    pullback_min: float = 0.25
    pullback_max: float = 0.60
    pullback_window_bars: int = 5
    trigger_offset_ticks: int = 1
    stop_buffer_ticks: int = 2
    cooldown_ns: int = 10 * 60 * NS
    context_min_bars_1m: int = 60
    base: LRParams = LRParams()


@dataclass
class _Impulse:
    direction: Direction
    origin: int
    extreme: int
    size: int
    armed_at_ns: int
    bars_since: int = 0
    in_band: bool = False
    pullback_extreme: int | None = None
    last_bar_high: int | None = None
    last_bar_low: int | None = None


class TCDetector:
    def __init__(self, contract_id: str, params: TCParams | None = None, *, enabled: bool = False) -> None:
        self.contract_id = contract_id
        self.p = params or TCParams()
        self.enabled = enabled
        self.impulse: _Impulse | None = None
        self.cooldown_until: int | None = None
        self.transitions: list[Transition] = []
        self.rejections: list[Transition] = []
        self._n = 0

    def _log(self, state: CandidateState, at: int, reason: str | None = None, direction: Direction = Direction.LONG) -> Transition:
        t = Transition("impulse", direction, state, at, reason)
        self.transitions.append(t)
        return t

    def _reject(self, at: int, reason: str) -> None:
        assert self.impulse is not None
        self.rejections.append(self._log(CandidateState.INVALIDATED, at, reason, self.impulse.direction))
        self.impulse = None
        self.cooldown_until = at

    # ---- cierre de barra 1m ----------------------------------------------------------------------
    def on_bar_1m_close(self, bars: list[Bar], closed_at_ns: int, ctx: LRContext) -> None:
        if not self.enabled:
            return
        p = self.p
        if self.impulse is not None:
            imp = self.impulse
            imp.bars_since += 1
            last = bars[-1]
            imp.last_bar_high, imp.last_bar_low = last.high, last.low
            sgn = 1 if imp.direction is Direction.LONG else -1
            retrace_px = last.low if sgn > 0 else last.high
            retrace = sgn * (imp.extreme - retrace_px) / imp.size if imp.size else 0.0
            if imp.pullback_extreme is None or sgn * (imp.pullback_extreme - retrace_px) > 0:
                imp.pullback_extreme = retrace_px
            if retrace > p.pullback_max:
                self._reject(closed_at_ns, f"PULLBACK_GT_{int(p.pullback_max * 100)}PCT")
                return
            if retrace >= p.pullback_min:
                imp.in_band = True
            if imp.bars_since > p.pullback_window_bars and not imp.in_band:
                self._reject(closed_at_ns, "PULLBACK_WINDOW_EXPIRED")
            return
        # armar un impulso nuevo
        if self.cooldown_until is not None and closed_at_ns - self.cooldown_until < p.cooldown_ns:
            return
        if ctx.blocked or ctx.regime not in ("TREND_UP", "TREND_DOWN") or len(bars) < p.context_min_bars_1m:
            return
        if len(bars) < p.impulse_bars + p.base.risk_min_ticks + 15:
            return
        window = bars[-p.impulse_bars:]
        atr_before = atr_simple(bars[:-p.impulse_bars], 14)
        if atr_before is None or atr_before <= 0:
            return
        closes = [b.close for b in window]
        net = closes[-1] - window[0].open
        er = efficiency_ratio([window[0].open] + closes)
        direction = Direction.LONG if ctx.regime == "TREND_UP" else Direction.SHORT
        sgn = 1 if direction is Direction.LONG else -1
        if er is None or er < p.impulse_er_min or sgn * net < p.impulse_atr_mult * atr_before:
            return
        extreme = max(b.high for b in window) if sgn > 0 else min(b.low for b in window)
        self.impulse = _Impulse(direction, window[0].open, extreme, abs(extreme - window[0].open), closed_at_ns,
                                last_bar_high=window[-1].high, last_bar_low=window[-1].low)
        self._log(CandidateState.ARMED, closed_at_ns, f"impulse net={net} er={er:.2f} atr={atr_before:.1f}", direction)

    # ---- trades ----------------------------------------------------------------------------------
    def on_trade(self, tr: Trade, ctx: LRContext, atr_1m: float | None) -> list[SetupSignal]:
        imp = self.impulse
        if not self.enabled or imp is None or not imp.in_band or atr_1m is None:
            return []
        p, sgn, px = self.p, (1 if imp.direction is Direction.LONG else -1), tr.price_ticks
        ref = imp.last_bar_high if sgn > 0 else imp.last_bar_low
        if ref is None or sgn * (px - (ref + sgn * p.trigger_offset_ticks)) < 0:
            return []
        reason = common_veto(ctx, sgn, p.base, volume_rel_min=p.base.volume_5s_min_rel_median)
        if reason:
            self._reject(tr.ts_ns, reason)
            return []
        assert imp.pullback_extreme is not None
        stop = imp.pullback_extreme - sgn * p.stop_buffer_ticks
        risk, rr = risk_check(px, stop, sgn, atr_1m, p.base)
        if rr:
            self._reject(tr.ts_ns, rr)
            return []
        self._n += 1
        sig = make_signal(id=f"tc-{self.contract_id}-{tr.ts_ns}-{self._n}", contract_id=self.contract_id, version=TC_VERSION,
                          direction=imp.direction, now=tr.ts_ns, px=px, stop=stop, risk=risk, atr=atr_1m, ctx=ctx, p=p.base,
                          reference={"origin": imp.origin, "extreme": imp.extreme, "size": imp.size, "pullback_extreme": imp.pullback_extreme})
        self._log(CandidateState.READY, tr.ts_ns, "trigger", imp.direction)
        self._log(CandidateState.CONSUMED, tr.ts_ns, "candidate_emitted", imp.direction)
        self.impulse = None
        self.cooldown_until = tr.ts_ns
        return [sig]
