"""ENG-09/ENG-10: folds y purga, modelo base + temperatura + métricas, ranking RAEV con NO TRADE, risk engine."""

from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from trading_scanner.models import BaseRateModel, TemperatureScaler, brier_multiclass, ece, log_loss
from trading_scanner.risk import RiskEngine, RiskProfile
from trading_scanner.scanner import RankingPolicy, Scores, rank, score
from trading_scanner.training import FOLDS, Block, LabeledSample, assign_block, purge_and_embargo

NS = 1_000_000_000


# ---------- splits ----------
def test_global_assignment_by_date_matches_protocol_table():
    f1 = FOLDS["F1"]
    assert assign_block(f1, date(2024, 9, 10)) is Block.TRAIN  # muestra piloto: train en los 3 folds
    assert all(assign_block(FOLDS[k], date(2024, 9, 10)) is Block.TRAIN for k in ("F1", "F2", "F3"))
    assert assign_block(f1, date(2025, 2, 15)) is Block.CALIBRATION
    assert assign_block(f1, date(2025, 3, 3)) is Block.POLICY_SELECTION
    assert assign_block(f1, date(2025, 5, 1)) is Block.TEST
    assert assign_block(f1, date(2025, 8, 1)) is Block.UNUSED
    assert assign_block(FOLDS["F3"], date(2026, 8, 1)) is Block.UNUSED  # holdout jamás entra a F3
    assert assign_block(FOLDS["HOLDOUT"], date(2026, 8, 1)) is Block.TEST


def test_purge_removes_samples_overlapping_next_block_and_embargo_session():
    f1 = FOLDS["F1"]
    cal_start = 1_000 * NS
    samples = [
        LabeledSample("a", date(2024, 12, 30), 900 * NS, 950 * NS),      # train limpio
        LabeledSample("b", date(2024, 12, 30), 990 * NS, 1_001 * NS),    # label entra en calibración → purgar
        LabeledSample("c", date(2024, 12, 31), 995 * NS, 999 * NS),      # sesión de embargo → descartar
        LabeledSample("d", date(2025, 1, 2), 1_010 * NS, 1_020 * NS),    # calibración
        LabeledSample("e", date(2024, 12, 30), 900 * NS, 950 * NS),      # otro contrato mismo día: mismo bloque
    ]
    out = purge_and_embargo(f1, samples, {Block.CALIBRATION: cal_start}, {Block.CALIBRATION: date(2024, 12, 31)})
    assert [s.candidate_id for s in out[Block.TRAIN]] == ["a", "e"]
    assert {s.candidate_id for s in out[Block.EMBARGO]} == {"b", "c"}
    assert [s.candidate_id for s in out[Block.CALIBRATION]] == ["d"]


# ---------- modelos ----------
def test_base_rate_shrinks_towards_total_and_never_zero():
    m = BaseRateModel(["TARGET", "STOP", "TIME"], shrink_k=10).fit(
        ["LR/LONG"] * 90 + ["LR/SHORT"] * 10, ["TARGET"] * 40 + ["STOP"] * 50 + ["TARGET"] * 5 + ["STOP"] * 5)
    p_short = m.predict_proba("LR/SHORT")
    assert p_short.sum() == pytest.approx(1.0) and (p_short > 0).all()  # TIME nunca 0
    assert m.predict_proba("LR/UNSEEN") == pytest.approx(m._total, abs=1e-9)
    assert m.support("LR/LONG") == 90 and m.support("LR/UNSEEN") == 0


def test_temperature_scaling_reduces_log_loss_and_rejects_missing_class():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 3, 500)
    noisy = np.where(rng.random(500) < 0.35, rng.integers(0, 3, 500), y)  # el modelo "cree" en una etiqueta ruidosa
    logits = np.eye(3)[noisy] * 6.0 + rng.normal(0, 0.5, (500, 3))  # sobreconfiado: logits grandes con 35 % de error
    base = log_loss(np.exp(logits) / np.exp(logits).sum(1, keepdims=True), y)
    ts = TemperatureScaler().fit(logits, y, 3)
    assert ts.valid and ts.temperature > 1.0
    assert log_loss(ts.transform(logits), y) < base
    bad = TemperatureScaler().fit(logits[y != 2], y[y != 2], 3)
    assert not bad.valid and "sin soporte" in bad.reason
    with pytest.raises(RuntimeError):
        bad.transform(logits)


def test_metrics_have_counts():
    p = np.array([[0.9, 0.1], [0.2, 0.8], [0.6, 0.4], [0.3, 0.7]])
    y = np.array([0, 1, 0, 1])
    assert brier_multiclass(p, y) < 0.5 and log_loss(p, y) < 0.5
    e, bins = ece(p, y, n_bins=5)
    assert 0 <= e <= 1 and sum(b["n"] for b in bins if b["class"] == 0) == 4


# ---------- ranking ----------
def _scores(ev_usd, lo_usd, pnl, risk_ticks=8, tv=Decimal("12.50"), pol=None):
    return score(risk_ticks=risk_ticks, tick_value_usd=tv, pnl_samples_usd=np.array(pnl, dtype=float),
                 ev_usd=ev_usd, lower95_ev_usd=lo_usd, policy=pol or RankingPolicy())


def test_score_formulas_and_support():
    pnl = np.concatenate([np.full(95, 20.0), np.full(5, -200.0)])
    s = _scores(ev_usd=20.0, lo_usd=10.0, pnl=pnl)  # R = 100 USD
    assert s.R_price_usd == Decimal("100.00") and s.EV_R == 0.2 and s.lower95_EV_R == 0.1
    assert s.tail_R == pytest.approx(2.0)  # ES95 de pérdidas = 200 / 100
    assert s.uncertainty_R == pytest.approx(0.1)
    assert s.RAEV_R == pytest.approx(0.2 - 0.1 * 2.0 - 0.1)
    assert _scores(20.0, 10.0, pnl[:10]).support_status == "INSUFFICIENT_SUPPORT"


def test_rank_vetoes_and_no_trade():
    ok = _scores(30.0, 10.0, [10.0] * 30)              # EV_R .3, lo .1, tail 0 → RAEV .1
    low_ev = _scores(5.0, 1.0, [10.0] * 30)            # EV_R .05 < .10
    neg_lo = _scores(30.0, -1.0, [10.0] * 30)
    nosup = _scores(30.0, 10.0, [10.0] * 5)
    ordered, sel = rank([("a", "NQ", ok, 0.06), ("b", "ES", low_ev, 0.06), ("c", "GC", neg_lo, 0.06), ("d", "ES", nosup, 0.06)], RankingPolicy())
    assert sel == "a" and [r.candidate_id for r in ordered][0] == "a"
    assert {r.candidate_id: r.exclusion_reason for r in ordered if not r.eligible} == {"b": "EV_R<0.1", "c": "lower95_EV_R<=0", "d": "INSUFFICIENT_SUPPORT"}
    _, none_sel = rank([("b", "ES", low_ev, 0.06)], RankingPolicy())
    assert none_sel is None  # NO TRADE


def test_tie_break_cost_then_risk_then_fixed_order():
    s = _scores(30.0, 10.0, [10.0] * 30)
    s_same = Scores(s.R_price_usd, s.EV_R + 0.005, s.lower95_EV_R, s.tail_R, s.uncertainty_R, s.RAEV_R + 0.005, s.support, "OK")
    _, sel = rank([("gc", "GC", s_same, 0.06), ("es", "ES", s, 0.06)], RankingPolicy())
    assert sel == "es"  # empate <= 0.01 R → mismo costo y riesgo → orden fijo ES antes que GC
    _, sel2 = rank([("gc", "GC", s_same, 0.05), ("es", "ES", s, 0.06)], RankingPolicy())
    assert sel2 == "gc"  # menor costo relativo gana el empate


# ---------- riesgo ----------
def test_risk_engine_budget_one_position_and_correlation():
    r = RiskEngine(RiskProfile())
    tv = Decimal("12.50")
    d = r.evaluate("c1", "ES", risk_ticks=5, tick_value_usd=tv)  # (5+2)*12.5 + 6 = 93.5
    assert d.approved and d.planned_risk_usd == Decimal("93.5")
    assert not r.evaluate("c2", "ES", risk_ticks=6, tick_value_usd=tv).approved  # 106 > 100: abstenerse, no fraccionar
    r.open("c1", "ES", d.planned_risk_usd)
    assert "POSITION_LIMIT" in r.evaluate("c3", "GC", 4, Decimal("10")).reasons
    assert "CORRELATED_EXPOSURE" in r.evaluate("c4", "NQ", 4, Decimal("5")).reasons
    r.close("c1", Decimal("-480"), d.planned_risk_usd)
    assert not r.halted_today
    d2 = r.evaluate("c5", "GC", 4, Decimal("10"))
    assert "DAILY_LOSS_BUDGET" in d2.reasons  # -480 - 66 <= -500
    r.open("c5", "GC", Decimal("66"))
    r.close("c5", Decimal("-30"), Decimal("66"))
    assert r.halted_today and "DAILY_HALT" in r.evaluate("c6", "ES", 4, tv).reasons
    r.new_session()
    assert r.evaluate("c7", "ES", 4, tv).approved and r.cumulative_pnl_usd == Decimal("-510")


def test_must_flatten_when_unrealized_hits_daily_limit():
    r = RiskEngine()
    r.open("c1", "ES", Decimal("93.5"))
    r.daily_realized_usd = Decimal("-450")
    assert not r.must_flatten(Decimal("-20"))
    assert r.must_flatten(Decimal("-60"))
