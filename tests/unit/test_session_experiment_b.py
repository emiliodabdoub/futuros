"""Experimento B en SessionRunner: la orden sale cuando existe la respuesta Jev (<= TTL); si tarda o falla, expira."""

import json
from datetime import date
from pathlib import Path

from trading_scanner.adapters.jev import JevClient, JevConfig, JevResponse
from trading_scanner.clock import pilot_window
from trading_scanner.contracts import BookLevel, Direction
from trading_scanner.orderbook import BookSnapshot
from trading_scanner.registry import InstrumentCatalog
from trading_scanner.replay.session import SessionRunner
from trading_scanner.setups.liquidity_reversal import Level, LevelKind, LRSignal
from tests.unit.test_jev_client import Q, good_payload, fake_transport  # reutiliza fixtures

NS = 1_000_000_000
ROOT = Path(__file__).resolve().parents[2]


def _sig(t):
    return LRSignal(id=f"s{t}", contract_id="ESU4", level=Level(LevelKind.PRIOR_DAY_LOW, 20000), direction=Direction.LONG,
                    created_at_ns=t, expires_at_ns=t + 2 * NS, trigger_price_ticks=20003, reclaim_price_ticks=20001,
                    sweep_extreme_ticks=19997, stop_ticks=19995, risk_ticks_at_trigger=8, target_ticks_at_trigger=20019,
                    atr_1m_ticks_frozen=20.0, delta_ratio_5s=0.25, volume_5s_rel_median=1.2, spread_ticks=1, attempt=1)


def _snap(t, bid=20003, ask=20004):
    return BookSnapshot("ESU4", t, t, (BookLevel(bid, 10),), (BookLevel(ask, 10),), None)


def _runner(transport, latency_ns):
    cat = InstrumentCatalog.from_yaml_dir(ROOT / "configs" / "instruments")
    jev = JevClient("k", Q, JevConfig(simulated_latency_ns=latency_ns), transport=transport)
    sr = SessionRunner(pilot_window(date(2024, 9, 10)), jev=jev)
    sr.add_contract(cat.get("ESU4"), 118, [])
    return sr, sr.runs["ESU4"]


def test_order_waits_for_jev_response_then_sends_within_ttl():
    sr, r = _runner(fake_transport(good_payload()), latency_ns=500_000_000)
    t = 10 * NS
    sr._classify(r, _sig(t), _snap(t))
    assert r.classifications[f"s{t}"].validation_status == "OK" and r.pending_b and r.active is None
    sr._flush_pending_b(r, t + 400_000_000, _snap(t + 400_000_000))  # aún no "existe" la respuesta
    assert r.active is None and r.pending_b
    sr._flush_pending_b(r, t + 600_000_000, _snap(t + 600_000_000))
    assert r.active is not None and r.active.trace.sent_at_ns == t + 600_000_000 and not r.pending_b


def test_late_response_expires_candidate_without_fallback():
    sr, r = _runner(fake_transport(good_payload()), latency_ns=2_500_000_000)
    t = 10 * NS
    sr._classify(r, _sig(t), _snap(t))
    assert r.jev_expired == 1 and not r.pending_b and r.active is None


def test_failed_classification_rejects_candidate():
    sr, r = _runner(fake_transport(ok=False, status=529, error="HTTP_529"), latency_ns=500_000_000)
    t = 10 * NS
    sr._classify(r, _sig(t), _snap(t))
    assert r.classifications[f"s{t}"].validation_status == "FAILED" and r.jev_expired == 1 and r.active is None


def test_price_drift_over_2_ticks_at_arrival_expires():
    sr, r = _runner(fake_transport(good_payload()), latency_ns=500_000_000)
    t = 10 * NS
    sr._classify(r, _sig(t), _snap(t))
    sr._flush_pending_b(r, t + NS, _snap(t + NS, bid=20009, ask=20010))  # ask 20010 vs trigger 20003
    assert r.jev_expired == 1 and r.active is None
