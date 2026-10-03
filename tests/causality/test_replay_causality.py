"""ENG-05 aceptación: determinismo (dos replays → hashes idénticos) y causalidad (alterar el futuro no
cambia ningún snapshot anterior a t). Sintético + fixture real si está disponible."""

import hashlib
import json
from pathlib import Path

import pytest

from trading_scanner.contracts import Aggressor, BookLevel, EventType, MarketEvent
from trading_scanner.features import FeatureEngine
from trading_scanner.replay import Replay, merge_by_availability

NS = 1_000_000_000
ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "data" / "fixtures" / "ESU4.mbp-10.2024-09-10T1330-1331.dbn.zst"


def _ev(cid: str, t: int, i: int, *, trade=False, price=20000, size=1, aggr=Aggressor.BUY, bid=19999, ask=20001):
    return MarketEvent(source="syn", dataset="syn", contract_id=cid, record_index=i, sequence=i,
                       ts_event_ns=t, ts_vendor_recv_ns=t, available_at_ns=t + 100_000_000,
                       event_type=EventType.TRADE if trade else EventType.BOOK,
                       price_ticks=price if trade else None, size_contracts=size if trade else None,
                       aggressor=aggr if trade else Aggressor.UNKNOWN,
                       bid_levels=(BookLevel(price_ticks=bid, size_contracts=10),),
                       ask_levels=(BookLevel(price_ticks=ask, size_contracts=10),),
                       quality_flags=("F_LAST",), raw_partition_hash="h")


def _synthetic_streams(n_seconds: int = 120, mutate_after_ns: int | None = None):
    def stream(cid: str, base_price: int):
        i = 0
        for s in range(n_seconds):
            t = s * NS
            i += 1
            price = base_price + (s % 7) - 3
            if mutate_after_ns is not None and t >= mutate_after_ns:
                price += 500  # "futuro" alterado
            yield _ev(cid, t, i, trade=True, price=price, size=1 + s % 3, aggr=Aggressor.BUY if s % 2 else Aggressor.SELL)
            i += 1
            yield _ev(cid, t + 1000, i, bid=price - 1, ask=price + 1)
    return [stream("ESZ4", 20000), stream("NQZ4", 80000)]


def _run(streams, stop_at_ns=None):
    engines = {"ESZ4": FeatureEngine("ESZ4", session_open_ns=0, opening_range_end_ns=300 * NS),
               "NQZ4": FeatureEngine("NQZ4", session_open_ns=0, opening_range_end_ns=300 * NS)}
    snaps: list[tuple[int, str, dict]] = []

    def on_event(ev):
        engines[ev.contract_id].apply(ev)

    def on_epoch(t):
        for cid, eng in engines.items():
            s = eng.snapshot(t)
            snaps.append((t, cid, s.values))

    rp = Replay(streams, clock=None, stop_at_ns=stop_at_ns)
    rp.run(on_event, on_epoch)
    return snaps, rp


def _hash(snaps):
    return hashlib.sha256(json.dumps(snaps, sort_keys=True, default=str).encode()).hexdigest()


def test_merge_is_ordered_by_availability_and_stable():
    evs = list(merge_by_availability(_synthetic_streams(10)))
    avail = [e.available_at_ns for e in evs]
    assert avail == sorted(avail)
    assert {e.contract_id for e in evs} == {"ESZ4", "NQZ4"}


def test_two_replays_are_bit_identical():
    a, _ = _run(_synthetic_streams())
    b, _ = _run(_synthetic_streams())
    assert a and _hash(a) == _hash(b)


def test_altering_the_future_does_not_change_the_past():
    t_cut = 60 * NS
    base, _ = _run(_synthetic_streams())
    mutated, _ = _run(_synthetic_streams(mutate_after_ns=t_cut))
    past_base = [s for s in base if s[0] <= t_cut]
    past_mut = [s for s in mutated if s[0] <= t_cut]
    assert past_base and _hash(past_base) == _hash(past_mut)
    future_base = [s for s in base if s[0] > t_cut + 2 * NS]
    future_mut = [s for s in mutated if s[0] > t_cut + 2 * NS]
    assert _hash(future_base) != _hash(future_mut)  # el cambio sí se nota después


def test_epoch_decision_only_sees_events_available_before_epoch():
    seen_at_epoch: list[tuple[int, int]] = []
    eng = FeatureEngine("ESZ4", session_open_ns=0, opening_range_end_ns=300 * NS)
    rp = Replay([_synthetic_streams(5)[0]])
    rp.run(lambda e: eng.apply(e), lambda t: seen_at_epoch.append((t, eng.max_input_available_ns)))
    assert seen_at_epoch and all(max_in < t for t, max_in in seen_at_epoch)


def test_snapshot_rejects_non_causal_as_of():
    eng = FeatureEngine("ESZ4", session_open_ns=0, opening_range_end_ns=300 * NS)
    eng.apply(_ev("ESZ4", 10 * NS, 1))
    with pytest.raises(ValueError, match="causal"):
        eng.snapshot(10 * NS)  # available_at = 10 s + 100 ms > as_of


def test_missing_features_are_null_with_reason_not_zero():
    eng = FeatureEngine("ESZ4", session_open_ns=0, opening_range_end_ns=300 * NS)
    s = eng.snapshot(1)
    assert s.values["F03_atr14_1m"] is None and s.missing_reasons["F03_atr14_1m"] == "warmup_lt_15_bars"
    assert s.values["F05_delta_ratio_5s"] is None and "no_known_aggressor_volume" in s.missing_reasons["F05_delta_ratio_5s"]
    assert s.values["F15_volume_5s_rel"] is None


def test_real_fixture_replay_is_deterministic_and_matches_reference_volume(catalog):
    if not FIX.is_file():
        pytest.skip("fixture no disponible")
    pytest.importorskip("databento")
    from trading_scanner.adapters.market import iter_mbp10_events

    def run():
        eng = FeatureEngine("ESU4", session_open_ns=1725975000 * NS, opening_range_end_ns=1725975300 * NS)
        snaps = []
        rp = Replay([iter_mbp10_events(FIX, catalog.get("ESU4"), 118)])
        rp.run(eng.apply, lambda t: snaps.append((t, eng.snapshot(t).values)))
        eng.bars_1m.flush(eng.max_input_available_ns + NS)
        return snaps, eng, rp

    s1, eng, rp = run()
    s2, _, _ = run()
    assert _hash(s1) == _hash(s2)
    assert rp.events == 47_146 and rp.epochs >= 59
    assert eng.bars_1m.finalized and eng.bars_1m.finalized[0].volume == 9_471  # = ohlcv-1m del minuto
    assert eng.bars_1m.late_revisions == 0
    last = s1[-1][1]
    assert last["F01_spread"] == 1 and last["F06_cvd_unknown_session"] == 0
    bar = eng.bars_1m.finalized[0]
    assert bar.buy_volume + bar.sell_volume == 9_471 and bar.unknown_volume == 0
    assert eng.cvd == bar.buy_volume - bar.sell_volume == last["F06_cvd_session"]
