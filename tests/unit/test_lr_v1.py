"""ENG-06 aceptación (spec §5.4): ejemplo positivo + seis rechazos obligatorios con motivo distinto,
más cooldown/intentos, fusión de niveles, duplicados, conflicto long/short y simetría short."""

import pytest

from trading_scanner.contracts import CandidateState, Direction
from trading_scanner.setups.liquidity_reversal import Level, LevelKind, LRContext, LRDetector, LRParams, Trade

NS = 1_000_000_000
T0 = 100 * NS
LEVEL = 20000


def ctx(delta=0.25, vol=120, med=100.0, spread=1, atr=20.0, window=True, blocked=()):
    return LRContext(atr_1m_ticks=atr, delta_ratio_5s=delta, volume_5s=vol, volume_5s_median=med,
                     spread_ticks=spread, in_entry_window=window, blocked_reasons=tuple(blocked))


def det(levels=None, **params):
    d = LRDetector("ESZ4", LRParams(**params))
    d.set_levels(levels or [Level(LevelKind.PRIOR_DAY_LOW, LEVEL)])
    return d


def tr(t_s: float, px: int, size: int = 1) -> Trade:
    return Trade(ts_ns=T0 + int(t_s * NS), price_ticks=px, size=size)


def run(d, seq, c=None):
    """seq: lista de (t_s, px) o (t_s, px, ctx). Devuelve señales acumuladas."""
    sigs = []
    for item in seq:
        t, px = item[0], item[1]
        cc = item[2] if len(item) > 2 else (c or ctx())
        sigs += d.on_trade(tr(t, px), cc)
    return sigs


# ---------- ejemplo positivo §5.4 ----------
POSITIVE = [(0, 20003), (5, 19997), (13, 20001), (17, 20003)]


def test_positive_example_emits_candidate_with_stop_target_and_ttl():
    d = det()
    sigs = run(d, POSITIVE)
    assert len(sigs) == 1
    s = sigs[0]
    assert s.direction is Direction.LONG and s.level.price_ticks == LEVEL
    assert s.sweep_extreme_ticks == 19997 and s.reclaim_price_ticks == 20001 and s.trigger_price_ticks == 20003
    assert s.stop_ticks == 19995  # extremo - 2
    assert s.risk_ticks_at_trigger == 8 and s.target_ticks_at_trigger == 20003 + 16
    assert s.expires_at_ns == s.created_at_ns + 2 * NS
    assert s.atr_1m_ticks_frozen == 20.0 and s.attempt == 1
    assert d.state_of(s.level.id) is CandidateState.IDLE  # consumido → cooldown
    states = [t.state for t in d.transitions]
    assert states == [CandidateState.ARMED, CandidateState.SWEPT, CandidateState.RECLAIMED, CandidateState.READY, CandidateState.CONSUMED]


# ---------- seis rechazos obligatorios ----------
def test_reject_no_reclaim_in_30s():
    d = det()
    run(d, [(0, 20003), (5, 19997)])
    d.on_time(T0 + 36 * NS)
    assert [r.reason for r in d.rejections] == ["NO_RECLAIM_30S"]


def test_reject_penetration_16_ticks_with_atr_20():
    d = det()  # pen_max = floor(0.75*20) = 15
    run(d, [(0, 20003), (5, 19984)])
    assert d.rejections[0].reason.startswith("PENETRATION_GT_MAX(16>15)")


def test_reject_delta_contrary():
    d = det()
    sigs = run(d, [(0, 20003), (5, 19997), (13, 20001), (17, 20003, ctx(delta=-0.30))])
    assert sigs == [] and d.rejections[0].reason == "DELTA_CONTRARY(-0.30)"


def test_reject_unknown_aggressor_above_5pct_via_quality_block():
    d = det()
    sigs = run(d, [(0, 20003), (5, 19997), (13, 20001), (17, 20003, ctx(blocked=("AGGRESSOR_UNKNOWN_HIGH",)))])
    assert sigs == [] and d.rejections[0].reason == "BLOCKED:AGGRESSOR_UNKNOWN_HIGH"


def test_reject_late_classification_is_ttl_expiry_of_signal():
    # La respuesta tardía de Jev la resuelve el scanner con expires_at: el candidato vive 2 s.
    d = det()
    s = run(d, POSITIVE)[0]
    assert s.expires_at_ns - s.created_at_ns == 2 * NS


def test_reject_new_low_after_reclaim():
    d = det()
    sigs = run(d, [(0, 20003), (5, 19997), (13, 20001), (15, 19996)])
    assert sigs == [] and d.rejections[0].reason == "NEW_EXTREME_AFTER_RECLAIM"


def test_all_six_rejections_have_distinct_reasons():
    reasons = set()
    for seq, extra in [
        ([(0, 20003), (5, 19997)], lambda d: d.on_time(T0 + 36 * NS)),
        ([(0, 20003), (5, 19984)], None),
        ([(0, 20003), (5, 19997), (13, 20001), (17, 20003, ctx(delta=-0.3))], None),
        ([(0, 20003), (5, 19997), (13, 20001), (17, 20003, ctx(blocked=("AGGRESSOR_UNKNOWN_HIGH",)))], None),
        ([(0, 20003), (5, 19997), (13, 20001), (15, 19996)], None),
        ([(0, 20003), (5, 19997), (13, 20001), (17, 20003, ctx(vol=40))], None),
    ]:
        d = det()
        run(d, seq)
        if extra:
            extra(d)
        assert len(d.rejections) == 1
        reasons.add(d.rejections[0].reason.split("(")[0])
    assert len(reasons) == 6


# ---------- otras reglas ----------
def test_confirmation_window_10s_and_armed_timeout_5min():
    d = det()
    run(d, [(0, 20003), (5, 19997), (13, 20001)])
    d.on_time(T0 + 24 * NS)
    assert d.rejections[0].reason == "NO_CONFIRMATION_10S"
    d2 = det()
    run(d2, [(0, 20003)])
    d2.on_time(T0 + 301 * NS)
    assert d2.transitions[-1].state is CandidateState.EXPIRED and d2.rejections == []  # expirar no consume intento


def test_cooldown_10min_and_max_2_attempts_per_day():
    d = det()
    assert len(run(d, POSITIVE)) == 1
    shifted = lambda off: [(t + off, px) for t, px in POSITIVE]
    assert run(d, shifted(60)) == []  # dentro del cooldown: ni se arma
    assert len(run(d, shifted(700))) == 1  # 2.º intento tras 10 min
    assert run(d, shifted(1400)) == []  # 3.º intento no permitido


def test_risk_out_of_range_rejected_not_widened():
    d = det()  # risk_max = ceil(1.5*20) = 30; risk_min 4
    # extremo 19999 (pen 1 no arma sweep: pen_min 2) → usar extremo 19998, stop 19996, trigger 20000 → riesgo 4 OK
    # riesgo 3: extremo 19998, reclaim 20001 exige >= nivel+1; trigger = reclaim+2 = 20003 → riesgo 7. Forzar riesgo < 4 imposible
    # con estos parámetros; probamos el límite superior con ATR pequeño: ATR 6 → risk_max 9
    sigs = run(d, [(0, 20002, ctx(atr=6.0)), (5, 19996, ctx(atr=6.0)), (13, 20001, ctx(atr=6.0)), (17, 20004, ctx(atr=6.0))])
    assert sigs == [] and d.rejections[0].reason.startswith("RISK_OUT_OF_RANGE(10 not in [4,9])")


def test_spread_veto():
    d = det(max_spread_ticks=2)
    sigs = run(d, [(0, 20003), (5, 19997), (13, 20001), (17, 20003, ctx(spread=3))])
    assert sigs == [] and d.rejections[0].reason == "SPREAD_GT_MAX(3)"


def test_outside_window_or_unknown_regime_never_arms():
    d = det()
    run(d, [(0, 20003, ctx(window=False))])
    assert d.transitions == []
    run(d, [(1, 20003, ctx(blocked=("REGIME_UNKNOWN",)))])
    assert d.transitions == []


def test_levels_within_2_ticks_are_merged_with_prior_day_priority():
    d = det([Level(LevelKind.OR_LOW, 20001), Level(LevelKind.PRIOR_DAY_LOW, 20000), Level(LevelKind.PRIOR_DAY_HIGH, 20500)])
    ids = sorted(d._machines)
    assert ids == ["prior_day_high@20500", "prior_day_low@20000"]
    assert d._machines["prior_day_low@20000"].level.merged_with == (("or_low", 20001),)


def test_two_unmerged_levels_same_event_oldest_armed_wins():
    d = det([Level(LevelKind.PRIOR_DAY_LOW, 20000), Level(LevelKind.OR_LOW, 19990)], proximity_min_ticks=20)
    # ambos niveles se arman (prox 20 ticks); barrida hasta 19988 (pen 12 ≤ 15) y reclaim arriba de ambos
    sigs = run(d, [(0, 20003), (1, 20002), (5, 19988), (13, 20001), (17, 20003)])
    assert len(sigs) == 1 and sigs[0].level.price_ticks == 20000  # armado primero
    assert any(r.reason == "DUPLICATE_OF_EVENT" for r in d.rejections)


def test_short_is_symmetric():
    d = det([Level(LevelKind.PRIOR_DAY_HIGH, 20000)])
    sigs = run(d, [(0, 19997), (5, 20003), (13, 19999), (17, 19997)], ctx(delta=-0.25))
    assert len(sigs) == 1
    s = sigs[0]
    assert s.direction is Direction.SHORT and s.stop_ticks == 20005 and s.risk_ticks_at_trigger == 8
    assert s.target_ticks_at_trigger == 19997 - 16


def test_conflicting_setups_abstain_white_box():
    """Con las reglas de LR-v1 un mismo trade casi nunca dispara long y short (el reclaim de uno cruza el
    trigger del otro), pero la spec §5.3 exige la rama: se fuerzan ambas máquinas en RECLAIMED."""
    d = det([Level(LevelKind.PRIOR_DAY_LOW, 20000), Level(LevelKind.PRIOR_DAY_HIGH, 20010)])
    lo, hi = d._machines["prior_day_low@20000"], d._machines["prior_day_high@20010"]
    for m, extreme, rp in ((lo, 19997, 20001), (hi, 20013, 20007)):
        m.state, m.armed_at, m.atr_frozen, m.pen_min, m.pen_max = CandidateState.RECLAIMED, T0, 20.0, 2, 15
        m.swept_at, m.extreme, m.reclaim_at, m.reclaim_px = T0 + 5 * NS, extreme, T0 + 13 * NS, rp
    # 20004 cumple long (>= 20001+2) y short (<= 20007-2) a la vez; delta neutro no veta a ninguno... usamos |delta|>=0.2 para ambos signos imposible,
    # así que el veto de flujo se evita con delta_ratio_min=0 en este detector:
    d.p = LRParams(delta_ratio_min=0.0)
    sigs = d.on_trade(tr(17, 20004), ctx(delta=0.0))
    assert sigs == [] and {r.reason for r in d.rejections} == {"CONFLICTING_SETUPS"}
    assert lo.state is CandidateState.IDLE and hi.state is CandidateState.IDLE and lo.attempts == hi.attempts == 1
