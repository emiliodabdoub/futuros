"""ENG-04: libro por F_LAST y quality gate con fixtures sintéticos (resets, cruces, agresor, stale, secuencia)."""

from trading_scanner.contracts import Aggressor, BookLevel, EventType, MarketEvent
from trading_scanner.orderbook import BookTracker
from trading_scanner.quality import GateConfig, QualityGate

NS = 1_000_000_000
_seq = [0]


def ev(t_ns: int, etype=EventType.BOOK, *, bid=20000, ask=20001, last=True, price=None, size=None,
       aggr=Aggressor.UNKNOWN, flags=(), seq=None, bids=None, asks=None):
    _seq[0] += 1
    qf = list(flags) + (["F_LAST"] if last else [])
    if etype is EventType.TRADE:
        qf.append("BOOK_IS_PRE_TRADE")
    b = bids if bids is not None else ((BookLevel(price_ticks=bid, size_contracts=10),) if bid is not None else ())
    a = asks if asks is not None else ((BookLevel(price_ticks=ask, size_contracts=10),) if ask is not None else ())
    return MarketEvent(source="syn", dataset="syn", contract_id="ESZ4", record_index=_seq[0],
                       sequence=seq if seq is not None else _seq[0], ts_event_ns=t_ns, ts_vendor_recv_ns=t_ns,
                       available_at_ns=t_ns, event_type=etype, price_ticks=price, size_contracts=size,
                       aggressor=aggr, bid_levels=b, ask_levels=a, quality_flags=tuple(qf), raw_partition_hash="h")


# ---------- BookTracker ----------

def test_book_publishes_only_on_f_last():
    bt = BookTracker("ESZ4")
    assert bt.apply(ev(1, last=False, bid=19990)) is None
    assert bt.snapshot is None
    snap = bt.apply(ev(2, last=True, bid=20000))
    assert snap is not None and snap.best_bid == 20000 and snap.spread_ticks == 1
    assert bt.closed_events == 1


def test_trade_record_does_not_publish_until_following_f_last():
    bt = BookTracker("ESZ4")
    assert bt.apply(ev(1, EventType.TRADE, last=False, price=20001, size=3, aggr=Aggressor.BUY)) is None
    snap = bt.apply(ev(2, last=True))
    assert snap is not None and snap.as_of_ns == 2


def test_reset_clears_book_and_counts():
    bt = BookTracker("ESZ4")
    bt.apply(ev(1))
    bt.apply(ev(2, EventType.RESET, last=False, bid=None, ask=None))
    assert bt.snapshot is None and bt.resets == 1


def test_depth_imbalance_and_crossed():
    bt = BookTracker("ESZ4")
    snap = bt.apply(ev(1, bids=(BookLevel(price_ticks=20000, size_contracts=30), BookLevel(price_ticks=19999, size_contracts=10)),
                       asks=(BookLevel(price_ticks=20001, size_contracts=10),)))
    assert snap.depth_imbalance(5) == (40 - 10) / 50
    crossed = bt.apply(ev(2, bid=20002, ask=20001))
    assert crossed.crossed is True
    empty = bt.apply(ev(3, bids=(), asks=()))
    assert empty.depth_imbalance() is None and not empty.complete


# ---------- QualityGate ----------

def _warm(g: QualityGate, t0: int = 0):
    return g.apply(ev(t0 + 1, bid=20000, ask=20001))


def test_clean_feed_is_not_blocked():
    g = QualityGate("ESZ4")
    st = _warm(g)
    assert st.blocked is False and st.reasons == ()


def test_no_book_blocks_until_first_complete_snapshot():
    g = QualityGate("ESZ4")
    st = g.apply(ev(1, last=False))
    assert "NO_BOOK" in st.reasons
    st = g.apply(ev(2, last=True))
    assert st.blocked is False


def test_reset_blocks_until_recovered_and_requires_rewarm():
    g = QualityGate("ESZ4")
    _warm(g)
    st = g.apply(ev(2, EventType.RESET, last=False, bid=None, ask=None))
    assert "RESET_UNRECOVERED" in st.reasons and st.blocked
    st = g.apply(ev(3, last=True, bid=20000, ask=20001))
    assert st.blocked is False and st.rewarm_required is True
    g.acknowledge_rewarm()
    assert g.state.rewarm_required is False


def test_crossed_book_blocks_only_when_persistent():
    g = QualityGate("ESZ4", GateConfig(crossed_grace_ns=1 * NS))
    _warm(g)
    st = g.apply(ev(2 * NS, bid=20002, ask=20001))  # cruce momentáneo
    assert "CROSSED_BOOK_PERSISTENT" not in st.reasons
    st = g.apply(ev(2 * NS + 1_500_000_000, bid=20002, ask=20001))  # 1.5 s cruzado
    assert "CROSSED_BOOK_PERSISTENT" in st.reasons
    st = g.apply(ev(4 * NS, bid=20000, ask=20001))
    assert st.blocked is False


def test_unknown_aggressor_above_5pct_blocks():
    g = QualityGate("ESZ4", GateConfig(min_aggressor_volume=10))
    _warm(g)
    t = 2 * NS
    for i in range(9):
        g.apply(ev(t + i, EventType.TRADE, last=False, price=20001, size=10, aggr=Aggressor.BUY))
        g.apply(ev(t + i + 1, last=True))
    st = g.apply(ev(t + 20, EventType.TRADE, last=False, price=20001, size=10, aggr=Aggressor.UNKNOWN))
    assert st.aggressor_known_pct == 90.0 and "AGGRESSOR_UNKNOWN_HIGH" in st.reasons
    # al salir de la ventana trailing de 60 s el porcentaje se recalcula
    st = g.apply(ev(t + 61 * NS, EventType.TRADE, last=False, price=20001, size=100, aggr=Aggressor.SELL))
    assert st.aggressor_known_pct == 100.0 and "AGGRESSOR_UNKNOWN_HIGH" not in st.reasons


def test_stale_feed_blocks_after_5s_without_events():
    g = QualityGate("ESZ4")
    _warm(g)
    assert g.check_staleness(1 + 4 * NS).blocked is False
    assert "STALE_FEED" in g.check_staleness(1 + 6 * NS).reasons
    assert g.apply(ev(1 + 7 * NS)).blocked is False  # vuelve a llegar un evento


def test_sequence_jumps_are_counted_but_do_not_block():
    g = QualityGate("ESZ4")
    g.apply(ev(1, seq=100))
    st = g.apply(ev(2, seq=105))
    assert st.sequence_jumps == 1 and st.blocked is False


def test_off_grid_price_excludes_session():
    g = QualityGate("ESZ4")
    _warm(g)
    st = g.apply(ev(2, flags=("PRICE_OFF_GRID",)))
    assert st.session_excluded and "SESSION_EXCLUDED" in st.reasons
    assert g.apply(ev(3)).blocked is True  # ya no se levanta en la sesión


def test_status_not_trading_blocks():
    g = QualityGate("ESZ4")
    _warm(g)
    st = g.apply(ev(2, EventType.STATUS, last=False, bid=None, ask=None, flags=("STATUS_ACTION=CLOSE",)))
    assert "NOT_TRADING" in st.reasons
    st = g.apply(ev(3, EventType.STATUS, last=False, bid=None, ask=None, flags=("IS_TRADING", "IS_QUOTING")))
    assert st.blocked is False
