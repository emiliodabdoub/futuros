"""Catálogo de contratos cargado desde configs/instruments/*.yaml."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path

import yaml

from trading_scanner.contracts.instrument import ContractSpec


class InstrumentCatalog:
    def __init__(self, contracts: Iterable[ContractSpec]) -> None:
        self._by_id: dict[str, ContractSpec] = {}
        for c in contracts:
            if c.contract_id in self._by_id:
                raise ValueError(f"contract_id duplicado: {c.contract_id}")
            self._by_id[c.contract_id] = c

    @classmethod
    def from_yaml_dir(cls, directory: Path) -> InstrumentCatalog:
        contracts: list[ContractSpec] = []
        for path in sorted(directory.glob("*.yaml")):
            contracts.extend(cls._load_file(path))
        return cls(contracts)

    @staticmethod
    def _load_file(path: Path) -> list[ContractSpec]:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        defaults = {
            "venue": raw.get("venue"),
            "root": raw.get("root"),
            "tick_size": raw.get("tick_size"),
            "point_value": raw.get("point_value"),
            "tick_value": raw.get("tick_value"),
            "currency": raw.get("currency"),
            "metadata_verified": raw.get("metadata_verified", False),
        }
        out: list[ContractSpec] = []
        for entry in raw.get("contracts", []):
            merged = {k: v for k, v in defaults.items() if v is not None}
            merged.update(entry)
            # Decimal exacto desde texto: nunca pasar floats de YAML.
            for k in ("tick_size", "point_value", "tick_value"):
                if k in merged:
                    merged[k] = str(merged[k])
            out.append(ContractSpec.model_validate(merged))
        return out

    def get(self, contract_id: str) -> ContractSpec:
        try:
            return self._by_id[contract_id]
        except KeyError:
            raise KeyError(f"contrato desconocido: {contract_id}") from None

    def roots(self) -> set[str]:
        return {c.root for c in self._by_id.values()}

    def outrights_for_root(self, root: str, not_expired_as_of: date | None = None) -> list[ContractSpec]:
        """Contratos del root ordenados por vencimiento; opcionalmente solo los con expiry >= fecha."""
        items = [c for c in self._by_id.values() if c.root == root]
        if not_expired_as_of is not None:
            items = [c for c in items if c.expiry >= not_expired_as_of]
        return sorted(items, key=lambda c: (c.expiry, c.contract_id))

    def __len__(self) -> int:
        return len(self._by_id)

    def __iter__(self):
        return iter(self._by_id.values())
