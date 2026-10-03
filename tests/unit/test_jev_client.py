"""ENG-08: adapter Jev con transporte simulado — deadline, versiones, faltantes, caché, estado sin datos de cuenta."""

import json
from pathlib import Path

import pytest

from trading_scanner.adapters.jev import JevClient, JevConfig, JevResponse, build_state, validate_answers
from trading_scanner.contracts import Direction, FeatureSnapshot
from trading_scanner.setups.liquidity_reversal import Level, LevelKind, LRSignal

ROOT = Path(__file__).resolve().parents[2]
RUBRICS = json.loads((ROOT / "configs" / "questions" / "lr_v1_rubrics.json").read_text(encoding="utf-8"))
Q = RUBRICS["questions"]
NS = 1_000_000_000


def good_payload(model="jev-1.13.0"):
    ans = {}
    for qid, q in Q.items():
        if q["type"] == "choice":
            opts = list(q["criteria"])
            probs = {o: 0.0 for o in opts}
            probs[opts[0]] = 1.0
            ans[qid] = {"type": "choice", "choice": opts[0], "confidence": 0.9, "probabilities": probs}
        else:
            n = len(q["criteria"])
            ans[qid] = {"type": "score", "score": 2.0, "confidence": 0.5, "probabilities": {str(i): 1.0 / n for i in range(n)}}
    return {"model": model, "answers": ans, "usage": {"input_tokens": 2000, "output_tokens": 200}}


def fake_transport(payload=None, ok=True, status=200, elapsed_ms=400, error=None, calls=None):
    def t(body, timeout):
        if calls is not None:
            calls.append(body)
        return JevResponse(ok, status, payload if ok else None, elapsed_ms, error=error)
    return t


def test_ok_response_is_validated_and_versioned():
    c = JevClient("k", Q, transport=fake_transport(good_payload()))
    r = c.classify("c1", {"a": 1}, requested_at_ns=10 * NS, result_id="r1")
    assert r.validation_status == "OK" and r.resolved_model == "jev-1.13.0"
    assert r.received_at_ns == 10 * NS + 500_000_000  # latencia modelada 500 ms > 400 ms real
    assert set(r.distributions) == set(Q) and r.usage["input_tokens"] == 2000


def test_deadline_exceeded_marks_invalid():
    c = JevClient("k", Q, transport=fake_transport(good_payload(), elapsed_ms=1700))
    r = c.classify("c1", {"a": 1}, requested_at_ns=0, result_id="r")
    assert r.validation_status == "INVALID" and "deadline" in r.failure_reason
    assert r.received_at_ns == 1_700_000_000


def test_failure_has_no_retry_and_is_failed():
    calls = []
    c = JevClient("k", Q, transport=fake_transport(ok=False, status=529, error="HTTP_529", calls=calls))
    r = c.classify("c1", {"a": 1}, requested_at_ns=0, result_id="r")
    assert r.validation_status == "FAILED" and r.failure_reason == "HTTP_529" and len(calls) == 1
    r2 = c.classify("c1", {"a": 1}, requested_at_ns=0, result_id="r2")
    assert r2.validation_status == "FAILED" and len(calls) == 2  # no se cachean fallos; cada candidato una llamada


def test_missing_option_and_bad_sum_detected():
    p = good_payload()
    del p["answers"]["flow_alignment"]["probabilities"]["mixed"]
    p["answers"]["reversal_quality"]["probabilities"]["0"] = 0.9
    probs = validate_answers(p["answers"], Q)
    assert any("faltan opciones ['mixed']" in x for x in probs)
    assert any("reversal_quality: suma" in x for x in probs)


def test_cache_hits_by_state_hash_and_persists_to_disk(tmp_path):
    calls = []
    cfg = JevConfig(cache_dir=tmp_path)
    c = JevClient("k", Q, cfg, transport=fake_transport(good_payload(), calls=calls))
    c.classify("c1", {"x": 1}, 0, result_id="a")
    c.classify("c2", {"x": 1}, 5 * NS, result_id="b")  # mismo estado → caché
    c.classify("c3", {"x": 2}, 0, result_id="c")
    assert len(calls) == 2 and c.cache_hits == 1
    assert len(list(tmp_path.glob("*.json"))) == 2
    c2 = JevClient("k", Q, cfg, transport=fake_transport(good_payload(), calls=calls))
    c2.classify("c4", {"x": 1}, 0, result_id="d")
    assert len(calls) == 2  # leído de disco


def test_model_change_misses_cache():
    calls = []
    c = JevClient("k", Q, JevConfig(model="jev-1.13.0"), transport=fake_transport(good_payload(), calls=calls))
    c.classify("c1", {"x": 1}, 0, result_id="a")
    c2 = JevClient("k", Q, JevConfig(model="jev-latest"), transport=fake_transport(good_payload(), calls=calls))
    c2.classify("c1", {"x": 1}, 0, result_id="b")
    assert len(calls) == 2


def test_build_state_has_units_side_and_no_account_data():
    sig = LRSignal(id="s", contract_id="ESZ4", level=Level(LevelKind.PRIOR_DAY_LOW, 20000), direction=Direction.LONG,
                   created_at_ns=0, expires_at_ns=2 * NS, trigger_price_ticks=20003, reclaim_price_ticks=20001,
                   sweep_extreme_ticks=19997, stop_ticks=19995, risk_ticks_at_trigger=8, target_ticks_at_trigger=20019,
                   atr_1m_ticks_frozen=20.0, delta_ratio_5s=0.25, volume_5s_rel_median=1.4, spread_ticks=1, attempt=1)
    snap = FeatureSnapshot(id="f", as_of_ns=1, max_input_available_at_ns=1, feature_version="v", contract_spec_version="c",
                           values={"F05_delta_ratio_5s": 0.25, "F07_vwap_session": 20009.0, "F11_depth_imbalance_5": None},
                           units={}, missing_reasons={"F11_depth_imbalance_5": "no_book"})
    st = build_state(sig, snap, [{"o": 0, "h": 1, "l": -1, "c": 0}] * 15, {"bid": [], "ask": []}, {"flags": []})
    assert st["proposed_side"] == "LONG" and st["units"]["price"] == "ticks"
    assert st["vwap_distance_ticks"] == -6 and len(st["bars_1m"]) == 12 and st["missing"] == ["F11_depth_imbalance_5"]
    assert not ({"account", "capital", "api_key"} & set(st))


def test_no_key_fails_cleanly():
    c = JevClient(None, Q)
    r = c.classify("c1", {"x": 1}, 0, result_id="r")
    assert r.validation_status == "FAILED" and r.failure_reason == "NO_KEY" and r.received_at_ns is None
