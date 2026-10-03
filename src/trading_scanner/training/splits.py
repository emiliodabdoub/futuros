"""Separación temporal preregistrada (protocolo §5.3–§5.4, ENG-09).

Una sola asignación global por fecha de sesión para todos los contratos. Purga: se elimina del bloque
anterior toda muestra cuyo intervalo de label [label_start, label_end] se solape con el bloque siguiente.
Embargo: una sesión completa sin muestras nuevas entre bloques (sus eventos sirven de warm-up, sus
labels no). Un mismo día de ES/NQ/GC nunca se reparte entre bloques.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class Block(str, Enum):
    TRAIN = "train"
    CALIBRATION = "calibration"
    POLICY_SELECTION = "policy_selection"
    TEST = "test"
    EMBARGO = "embargo"
    UNUSED = "unused"


@dataclass(frozen=True)
class Fold:
    name: str
    train: tuple[date, date]
    calibration: tuple[date, date]
    policy_selection: tuple[date, date]
    test: tuple[date, date]

    def blocks(self) -> list[tuple[Block, date, date]]:
        return [(Block.TRAIN, *self.train), (Block.CALIBRATION, *self.calibration),
                (Block.POLICY_SELECTION, *self.policy_selection), (Block.TEST, *self.test)]


def _d(y: int, m: int, d: int) -> date:
    return date(y, m, d)


FOLDS: dict[str, Fold] = {
    "F1": Fold("F1", (_d(2024, 1, 1), _d(2024, 12, 31)), (_d(2025, 1, 1), _d(2025, 2, 28)), (_d(2025, 3, 1), _d(2025, 3, 31)), (_d(2025, 4, 1), _d(2025, 6, 30))),
    "F2": Fold("F2", (_d(2024, 1, 1), _d(2025, 6, 30)), (_d(2025, 7, 1), _d(2025, 8, 31)), (_d(2025, 9, 1), _d(2025, 9, 30)), (_d(2025, 10, 1), _d(2025, 12, 31))),
    "F3": Fold("F3", (_d(2024, 1, 1), _d(2025, 12, 31)), (_d(2026, 1, 1), _d(2026, 2, 28)), (_d(2026, 3, 1), _d(2026, 3, 31)), (_d(2026, 4, 1), _d(2026, 6, 30))),
    # Holdout final: ajuste hasta abr-2026, calibración may-2026, umbrales jun-2026, test jul–sep 2026 (sellado).
    "HOLDOUT": Fold("HOLDOUT", (_d(2024, 1, 1), _d(2026, 4, 30)), (_d(2026, 5, 1), _d(2026, 5, 31)), (_d(2026, 6, 1), _d(2026, 6, 30)), (_d(2026, 7, 1), _d(2026, 9, 30))),
}


def assign_block(fold: Fold, session_date: date) -> Block:
    for block, start, end in fold.blocks():
        if start <= session_date <= end:
            return block
    return Block.UNUSED


@dataclass(frozen=True)
class LabeledSample:
    candidate_id: str
    session_date: date
    label_start_ns: int
    label_end_ns: int


def purge_and_embargo(fold: Fold, samples: list[LabeledSample], block_start_ns: dict[Block, int],
                      embargo_sessions: dict[Block, date]) -> dict[Block, list[LabeledSample]]:
    """Asigna cada muestra por su fecha; purga las del bloque anterior cuyo label_end entra en el bloque
    siguiente (`block_start_ns[next]`); descarta las muestras de la sesión de embargo previa a cada bloque.

    `block_start_ns`: instante UTC en que empieza cada bloque (primera sesión). `embargo_sessions`: la
    sesión completa inmediatamente anterior a cada bloque (sus muestras se descartan).
    """
    order = [Block.TRAIN, Block.CALIBRATION, Block.POLICY_SELECTION, Block.TEST]
    out: dict[Block, list[LabeledSample]] = {b: [] for b in order}
    out[Block.EMBARGO] = []
    embargo_days = set(embargo_sessions.values())
    for s in samples:
        b = assign_block(fold, s.session_date)
        if b is Block.UNUSED:
            continue
        if s.session_date in embargo_days:
            out[Block.EMBARGO].append(s)
            continue
        idx = order.index(b)
        if idx + 1 < len(order):
            nxt = order[idx + 1]
            if nxt in block_start_ns and s.label_end_ns >= block_start_ns[nxt]:
                out[Block.EMBARGO].append(s)  # purgada por solape de label con el bloque siguiente
                continue
        out[b].append(s)
    return out
