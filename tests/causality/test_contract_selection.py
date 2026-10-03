"""ENG-02 aceptación: roll sin volumen futuro (spec §2.1, ADR-002)."""

from datetime import date

import pytest

from trading_scanner.registry import ContractUnresolvedError, select_contract


class VolumeTable:
    """Fuente de volumen que EXPLOTA si se le pide una fecha >= la sesión que se resuelve."""

    def __init__(self, table: dict[tuple[str, date], int], resolving: date) -> None:
        self.table = table
        self.resolving = resolving
        self.calls: list[tuple[str, date]] = []

    def session_volume(self, contract_id: str, session_date: date) -> int | None:
        self.calls.append((contract_id, session_date))
        if session_date >= self.resolving:
            raise AssertionError(f"consulta no causal: {contract_id} {session_date} >= {self.resolving}")
        return self.table.get((contract_id, session_date))


def test_es_mid_september_picks_highest_previous_session_volume(catalog, calendar):
    s = date(2024, 9, 10)
    prev = date(2024, 9, 9)
    vols = VolumeTable({("ESU4", prev): 1_200_000, ("ESZ4", prev): 300_000, ("ESH5", prev): 1_000}, s)
    sel = select_contract("ES", s, catalog, calendar, vols)
    assert sel.contract_id == "ESU4"
    assert sel.volume_session_date == prev
    assert all(d == prev for _, d in vols.calls)


def test_roll_happens_when_front_is_within_five_sessions_of_cutoff(catalog, calendar):
    # ESU4 last trading 2024-09-20. El 2024-09-13 quedan 5 sesiones (16,17,18,19,20) → excluido.
    s = date(2024, 9, 13)
    prev = calendar.previous_session(s)
    vols = VolumeTable({("ESU4", prev): 9_999_999, ("ESZ4", prev): 500_000, ("ESH5", prev): 100}, s)
    sel = select_contract("ES", s, catalog, calendar, vols)
    assert sel.contract_id == "ESZ4"
    front = next(c for c in sel.considered if c.contract_id == "ESU4")
    assert front.eligible is False and front.sessions_to_cutoff == 5
    # al front excluido no se le consulta volumen
    assert ("ESU4", prev) not in vols.calls


def test_front_still_eligible_at_six_sessions(catalog, calendar):
    s = date(2024, 9, 12)  # sesiones hasta el 20: 13,16,17,18,19,20 = 6
    prev = calendar.previous_session(s)
    vols = VolumeTable({("ESU4", prev): 10, ("ESZ4", prev): 5}, s)
    assert select_contract("ES", s, catalog, calendar, vols).contract_id == "ESU4"


def test_gc_uses_first_notice_as_cutoff(catalog, calendar):
    # GCV4 first notice 2024-09-30; el 2024-09-23 quedan 5 sesiones (24..30) → excluido, gana GCZ4.
    s = date(2024, 9, 23)
    prev = calendar.previous_session(s)
    vols = VolumeTable({("GCV4", prev): 1_000_000, ("GCZ4", prev): 800_000, ("GCG5", prev): 10}, s)
    sel = select_contract("GC", s, catalog, calendar, vols)
    assert sel.contract_id == "GCZ4"
    v4 = next(c for c in sel.considered if c.contract_id == "GCV4")
    assert v4.cutoff_date == date(2024, 9, 30) and v4.eligible is False


def test_tie_goes_to_nearest_expiry(catalog, calendar):
    s = date(2024, 9, 10)
    prev = date(2024, 9, 9)
    vols = VolumeTable({("ESU4", prev): 100, ("ESZ4", prev): 100, ("ESH5", prev): 100}, s)
    assert select_contract("ES", s, catalog, calendar, vols).contract_id == "ESU4"


def test_only_first_three_eligible_are_considered(catalog, calendar):
    s = date(2024, 9, 10)
    prev = date(2024, 9, 9)
    vols = VolumeTable({("ESU4", prev): 1, ("ESZ4", prev): 1, ("ESH5", prev): 1, ("ESM5", prev): 10**9}, s)
    sel = select_contract("ES", s, catalog, calendar, vols)
    assert sel.contract_id == "ESU4"
    m5 = next(c for c in sel.considered if c.contract_id == "ESM5")
    assert m5.eligible is False and ("ESM5", prev) not in vols.calls


def test_no_valid_volume_is_unresolved_not_front_month(catalog, calendar):
    s = date(2024, 9, 10)
    vols = VolumeTable({("ESU4", date(2024, 9, 9)): 0}, s)  # 0 no es válido; el resto None
    with pytest.raises(ContractUnresolvedError) as ei:
        select_contract("ES", s, catalog, calendar, vols)
    assert ei.value.code == "CONTRACT_UNRESOLVED"


def test_unknown_root_is_unresolved(catalog, calendar):
    with pytest.raises(ContractUnresolvedError):
        select_contract("CL", date(2024, 9, 10), catalog, calendar, VolumeTable({}, date(2024, 9, 10)))


def test_selection_is_frozen(catalog, calendar):
    s = date(2024, 9, 10)
    sel = select_contract("ES", s, catalog, calendar, VolumeTable({("ESU4", date(2024, 9, 9)): 1}, s))
    with pytest.raises(AttributeError):
        sel.contract_id = "ESZ4"  # type: ignore[misc]


def test_hiding_future_data_does_not_change_selection(catalog, calendar):
    """Prueba de causalidad: añadir datos de la propia sesión o posteriores no altera el resultado."""
    s = date(2024, 9, 10)
    prev = date(2024, 9, 9)
    base = {("ESU4", prev): 100, ("ESZ4", prev): 200}
    with_future = dict(base)
    with_future[("ESU4", s)] = 10**9
    with_future[("ESU4", date(2024, 9, 11))] = 10**9
    a = select_contract("ES", s, catalog, calendar, VolumeTable(base, s))
    b = select_contract("ES", s, catalog, calendar, VolumeTable(with_future, s))
    assert a.contract_id == b.contract_id == "ESZ4"
    assert a.volume == b.volume
