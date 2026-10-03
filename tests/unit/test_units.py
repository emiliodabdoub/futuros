"""ENG-01: validación de unidades (ticks exactos, sin redondeo silencioso)."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from trading_scanner.contracts import PriceNotOnGridError, price_to_ticks, ticks_to_price, ticks_to_usd


def test_es_price_to_ticks_exact():
    assert price_to_ticks("5000.25", "0.25") == 20001
    assert price_to_ticks(Decimal("5000.00"), Decimal("0.25")) == 20000


def test_gc_price_to_ticks_exact():
    assert price_to_ticks("2500.10", "0.10") == 25001


def test_off_grid_price_raises_instead_of_rounding():
    with pytest.raises(PriceNotOnGridError):
        price_to_ticks("5000.30", "0.25")
    with pytest.raises(PriceNotOnGridError):
        price_to_ticks("2500.05", "0.10")


def test_float_artifacts_do_not_leak():
    # 0.1 * 3 en float no es 0.3; en Decimal sí.
    assert price_to_ticks("0.30", "0.10") == 3


def test_ticks_to_usd_signed():
    assert ticks_to_usd(9, "12.50") == Decimal("112.50")
    assert ticks_to_usd(-4, "12.50") == Decimal("-50.00")


def test_invalid_tick_size():
    with pytest.raises(ValueError):
        price_to_ticks("1", "0")


@given(ticks=st.integers(min_value=-10_000_000, max_value=10_000_000),
       tick=st.sampled_from(["0.25", "0.10", "0.01", "0.5", "1"]))
def test_round_trip(ticks: int, tick: str):
    assert price_to_ticks(ticks_to_price(ticks, tick), tick) == ticks
