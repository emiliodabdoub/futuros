"""ENG-03 (parcial): el catálogo coincide exactamente con las definitions de Databento.

Se omite si la muestra no está en data/raw (datos licenciados, fuera de git)."""

from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEFN = ROOT / "data" / "raw" / "GLBX.MDP3" / "definition" / "GLBX.MDP3.definition.2024-09-05_2024-09-21.dbn.zst"
PILOT = ["ESU4", "ESZ4", "NQU4", "NQZ4", "GCZ4"]


@pytest.fixture(scope="module")
def definitions():
    if not DEFN.is_file():
        pytest.skip("muestra piloto no descargada")
    db = pytest.importorskip("databento")
    df = db.DBNStore.from_file(DEFN).to_df().sort_index()
    return df.groupby("raw_symbol").tail(1).set_index("raw_symbol")


def test_pilot_contracts_present_and_are_outright_futures(definitions):
    for sym in PILOT:
        assert sym in definitions.index, sym
        row = definitions.loc[sym]
        assert row["security_type"] == "FUT"
        assert row["instrument_class"] == "F"  # F = futuro outright; S sería spread
        assert int(row["leg_count"]) == 0


def test_tick_size_and_point_value_match_catalog(catalog, definitions):
    for sym in PILOT:
        spec = catalog.get(sym)
        row = definitions.loc[sym]
        assert Decimal(str(row["min_price_increment"])) == spec.tick_size, sym
        assert Decimal(str(row["unit_of_measure_qty"])) == spec.point_value, sym
        assert row["currency"] == spec.currency


def test_expiry_date_matches_catalog(catalog, definitions):
    for sym in PILOT:
        exp = definitions.loc[sym]["expiration"]
        assert exp.date() == catalog.get(sym).expiry, sym
