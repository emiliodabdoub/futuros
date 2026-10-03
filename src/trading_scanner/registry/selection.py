"""Selección causal de contrato al inicio de sesión (spec §2.1, ADR-002)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from trading_scanner.contracts.instrument import ContractSpec
from trading_scanner.registry.calendar import TradingCalendar
from trading_scanner.registry.catalog import InstrumentCatalog

MIN_SESSIONS_TO_CUTOFF = 5  # "cinco o menos días hábiles" → excluido
MAX_CANDIDATES = 3  # "los próximos tres vencimientos elegibles"


class ContractUnresolvedError(RuntimeError):
    code = "CONTRACT_UNRESOLVED"

    def __init__(self, root: str, session_date: date, reason: str) -> None:
        self.root = root
        self.session_date = session_date
        self.reason = reason
        super().__init__(f"{self.code}: {root} {session_date}: {reason}")


class SessionVolumeSource(Protocol):
    """Volumen de la sesión completa `session_date` de un contrato, o None si no hay dato válido.

    El selector solo llama con la sesión anterior a la que se está resolviendo."""

    def session_volume(self, contract_id: str, session_date: date) -> int | None: ...


@dataclass(frozen=True)
class ConsideredContract:
    contract_id: str
    expiry: date
    cutoff_date: date
    sessions_to_cutoff: int
    eligible: bool
    exclusion_reason: str | None
    volume: int | None


@dataclass(frozen=True)
class ContractSelection:
    root: str
    session_date: date
    contract_id: str
    volume_session_date: date
    volume: int
    considered: tuple[ConsideredContract, ...]
    rule_version: str = "select-v1"


def select_contract(
    root: str,
    session_date: date,
    catalog: InstrumentCatalog,
    calendar: TradingCalendar,
    volumes: SessionVolumeSource,
) -> ContractSelection:
    candidates = catalog.outrights_for_root(root, not_expired_as_of=session_date)
    if not candidates:
        raise ContractUnresolvedError(root, session_date, "sin contratos no vencidos en el catálogo")

    volume_date = calendar.previous_session(session_date)
    considered: list[ConsideredContract] = []
    eligible: list[tuple[ContractSpec, int]] = []

    for c in candidates:
        n = calendar.sessions_after_until(session_date, c.cutoff_date)
        reason: str | None = None
        if c.cutoff_date < session_date:
            reason = "cutoff anterior a la sesión"
        elif n <= MIN_SESSIONS_TO_CUTOFF:
            reason = f"a {n} sesiones del cutoff (<= {MIN_SESSIONS_TO_CUTOFF})"
        is_eligible = reason is None and len(eligible) < MAX_CANDIDATES
        if reason is None and not is_eligible:
            reason = "fuera de los tres primeros elegibles"

        vol: int | None = None
        if is_eligible:
            vol = volumes.session_volume(c.contract_id, volume_date)
            if vol is not None and vol <= 0:
                vol = None
            if vol is not None:
                eligible.append((c, vol))
        considered.append(
            ConsideredContract(
                contract_id=c.contract_id,
                expiry=c.expiry,
                cutoff_date=c.cutoff_date,
                sessions_to_cutoff=n,
                eligible=is_eligible,
                exclusion_reason=reason,
                volume=vol,
            )
        )

    if not eligible:
        raise ContractUnresolvedError(
            root, session_date, "ningún contrato elegible con volumen previo válido"
        )

    # Mayor volumen; empate → vencimiento más cercano (la lista ya viene ordenada por expiry).
    best, best_vol = eligible[0]
    for c, v in eligible[1:]:
        if v > best_vol:
            best, best_vol = c, v

    return ContractSelection(
        root=root,
        session_date=session_date,
        contract_id=best.contract_id,
        volume_session_date=volume_date,
        volume=best_vol,
        considered=tuple(considered),
    )
