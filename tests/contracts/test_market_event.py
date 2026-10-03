"""ENG-01: MarketEvent — invariantes de tiempo y null ≠ 0."""

import pytest
from pydantic import ValidationError

from trading_scanner.contracts import Aggressor, BookLevel, EventType, MarketEvent


def _ev(**over):
    base = dict(
        source="databento", dataset="GLBX.MDP3", contract_id="ESZ4", record_index=0,
        ts_event_ns=1_000, available_at_ns=1_250, event_type=EventType.BOOK,
        raw_partition_hash="abc",
    )
    base.update(over)
    return MarketEvent(**base)


def test_book_event_with_nulls_keeps_nulls():
    e = _ev()
    assert e.price_ticks is None
    assert e.size_contracts is None
    assert e.aggressor is Aggressor.UNKNOWN
    dumped = e.model_dump()
    assert dumped["price_ticks"] is None  # nunca 0


def test_available_before_event_rejected():
    with pytest.raises(ValidationError, match="available_at_ns"):
        _ev(available_at_ns=999)


def test_trade_requires_price_and_positive_size():
    with pytest.raises(ValidationError):
        _ev(event_type=EventType.TRADE)
    with pytest.raises(ValidationError):
        _ev(event_type=EventType.TRADE, price_ticks=20000, size_contracts=0)
    t = _ev(event_type=EventType.TRADE, price_ticks=20000, size_contracts=3, aggressor=Aggressor.BUY)
    assert t.size_contracts == 3


def test_spread_from_levels_and_none_when_absent():
    e = _ev(bid_levels=(BookLevel(price_ticks=19999, size_contracts=10),),
            ask_levels=(BookLevel(price_ticks=20001, size_contracts=7),))
    assert e.spread_ticks == 2
    assert _ev().spread_ticks is None


def test_crossed_book_is_not_rejected_by_contract_layer():
    # ADR-001 §5: el quality gate lo marca; el contrato no lo corrige ni lo rechaza.
    e = _ev(bid_levels=(BookLevel(price_ticks=20002, size_contracts=1),),
            ask_levels=(BookLevel(price_ticks=20001, size_contracts=1),))
    assert e.spread_ticks == -1


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        _ev(unexpected=1)
