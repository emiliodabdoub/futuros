"""ENG-01: ContractSpec exige tick_value = tick_size × point_value (spec §2.1)."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from trading_scanner.contracts import ContractSpec


def _spec(**over):
    base = dict(
        contract_id="ESZ4", venue="CME", root="ES", expiry=date(2024, 12, 20),
        tick_size=Decimal("0.25"), point_value=Decimal("50"), tick_value=Decimal("12.50"),
        currency="USD", last_trading_date=date(2024, 12, 20),
    )
    base.update(over)
    return ContractSpec(**base)


def test_valid_spec():
    s = _spec()
    assert s.tick_value == Decimal("12.50")
    assert s.metadata_verified is False
    assert s.cutoff_date == date(2024, 12, 20)


def test_tick_value_mismatch_rejected():
    with pytest.raises(ValidationError, match="tick_value"):
        _spec(tick_value=Decimal("12.00"))


def test_cutoff_is_first_notice_when_earlier():
    s = _spec(contract_id="GCZ4", root="GC", venue="COMEX", tick_size=Decimal("0.10"),
              point_value=Decimal("100"), tick_value=Decimal("10.00"),
              expiry=date(2024, 12, 27), last_trading_date=date(2024, 12, 27),
              first_notice_date=date(2024, 11, 29))
    assert s.cutoff_date == date(2024, 11, 29)


def test_dates_after_expiry_rejected():
    with pytest.raises(ValidationError):
        _spec(last_trading_date=date(2024, 12, 21))
    with pytest.raises(ValidationError):
        _spec(first_notice_date=date(2024, 12, 21))


def test_frozen():
    s = _spec()
    with pytest.raises(ValidationError):
        s.tick_size = Decimal("0.5")  # type: ignore[misc]


def test_catalog_loads_all_three_roots_and_validates_tick_identity(catalog):
    assert catalog.roots() == {"ES", "NQ", "GC"}
    assert catalog.get("ESZ4").tick_value == Decimal("12.50")
    assert catalog.get("NQZ4").tick_value == Decimal("5.00")
    assert catalog.get("GCZ4").tick_value == Decimal("10.00")
    assert all(c.metadata_verified is False for c in catalog)
