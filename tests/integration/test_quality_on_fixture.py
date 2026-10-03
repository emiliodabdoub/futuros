"""ENG-04 sobre el minuto real: el gate no bloquea un feed limpio y el libro cierra por F_LAST."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "data" / "fixtures" / "ESU4.mbp-10.2024-09-10T1330-1331.dbn.zst"


def test_gate_on_real_minute(catalog):
    if not FIX.is_file():
        pytest.skip("fixture no disponible")
    pytest.importorskip("databento")
    from trading_scanner.adapters.market import iter_mbp10_events
    from trading_scanner.quality import QualityGate

    g = QualityGate("ESU4")
    blocked_after_warm = 0
    snaps = 0
    for i, e in enumerate(iter_mbp10_events(FIX, catalog.get("ESU4"), 118)):
        st = g.apply(e)
        if g.snapshot is not None:
            snaps += 1
            if st.blocked:
                blocked_after_warm += 1
    assert blocked_after_warm == 0
    assert g.book.closed_events > 40_000  # casi todos los registros cierran evento (F_LAST en 44,133)
    assert g.state.sequence_jumps > 0  # stream filtrado por instrumento: saltos normales, no bloquean
    assert g.state.aggressor_known_pct == 100.0
    assert g.snapshot.complete and not g.snapshot.crossed and g.snapshot.spread_ticks == 1
