from pathlib import Path

import pytest

from trading_scanner.registry import InstrumentCatalog, TradingCalendar

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def catalog() -> InstrumentCatalog:
    return InstrumentCatalog.from_yaml_dir(ROOT / "configs" / "instruments")


@pytest.fixture(scope="session")
def calendar() -> TradingCalendar:
    return TradingCalendar.from_yaml(ROOT / "configs" / "sessions" / "cme_research.yaml")
