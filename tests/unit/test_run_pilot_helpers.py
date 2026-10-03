"""Helpers de scripts/run_pilot.py: descubrimiento de archivos diarios por nombre y fuente de volumen causal."""

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import run_pilot as rp  # noqa: E402


def test_discover_files_parses_batch_day_names(tmp_path):
    for n in ("glbx-mdp3-20240905.mbp-10.dbn.zst", "glbx-mdp3-20240920.mbp-10.dbn.zst", "manifest.json"):
        (tmp_path / n).write_bytes(b"")
    files = rp.discover_files(tmp_path)
    assert set(files) == {date(2024, 9, 5), date(2024, 9, 20)}
    assert files[date(2024, 9, 5)].name.startswith("glbx-mdp3-20240905")


def test_agg_volumes_only_answers_for_known_day_and_instrument():
    aggs = {"2024-09-09": {"instruments": {"118": {"volume": 1_200_000}, "183748": {"volume": 300_000}}}}
    v = rp.AggVolumes(aggs, {"ESU4": 118, "ESZ4": 183748, "NQU4": 4358})
    assert v.session_volume("ESU4", date(2024, 9, 9)) == 1_200_000
    assert v.session_volume("ESZ4", date(2024, 9, 9)) == 300_000
    assert v.session_volume("NQU4", date(2024, 9, 9)) is None  # sin datos → None, nunca 0 inventado
    assert v.session_volume("ESU4", date(2024, 9, 10)) is None


def test_pilot_sessions_are_the_ten_weekdays_of_the_sample():
    assert len(rp.PILOT_SESSIONS) == 10
    assert rp.PILOT_SESSIONS[0] == date(2024, 9, 9) and rp.PILOT_SESSIONS[-1] == date(2024, 9, 20)
