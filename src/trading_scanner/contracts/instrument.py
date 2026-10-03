"""Metadata de contrato outright (spec §2.1)."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractSpec(BaseModel):
    """Un vencimiento concreto. `metadata_verified=False` hasta contrastar con definitions del proveedor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_id: str = Field(min_length=1, description="Símbolo outright, p.ej. ESZ4")
    venue: str = Field(min_length=1)
    root: str = Field(min_length=1)
    expiry: date
    tick_size: Decimal = Field(gt=0)
    point_value: Decimal = Field(gt=0)
    tick_value: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    first_notice_date: date | None = None
    last_trading_date: date
    metadata_verified: bool = False

    @model_validator(mode="after")
    def _check_consistency(self) -> "ContractSpec":
        expected = self.tick_size * self.point_value
        if self.tick_value != expected:
            raise ValueError(
                f"{self.contract_id}: tick_value {self.tick_value} != "
                f"tick_size×point_value {expected}"
            )
        if self.last_trading_date > self.expiry:
            raise ValueError(f"{self.contract_id}: last_trading_date posterior a expiry")
        if self.first_notice_date is not None and self.first_notice_date > self.expiry:
            raise ValueError(f"{self.contract_id}: first_notice_date posterior a expiry")
        return self

    @property
    def cutoff_date(self) -> date:
        """Primero entre first notice y último día de negociación (spec §2.1)."""
        if self.first_notice_date is None:
            return self.last_trading_date
        return min(self.first_notice_date, self.last_trading_date)
