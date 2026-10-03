"""Conversión exacta entre precio decimal y ticks enteros (ADR-001 §1)."""

from decimal import Decimal


class PriceNotOnGridError(ValueError):
    """El precio no es múltiplo exacto del tick_size."""


def price_to_ticks(price: Decimal | str | int, tick_size: Decimal | str) -> int:
    price_d = Decimal(str(price))
    tick_d = Decimal(str(tick_size))
    if tick_d <= 0:
        raise ValueError(f"tick_size debe ser > 0, recibido {tick_d}")
    q, r = divmod(price_d, tick_d)
    if r != 0:
        raise PriceNotOnGridError(f"precio {price_d} no está en la rejilla de tick {tick_d}")
    return int(q)


def ticks_to_price(ticks: int, tick_size: Decimal | str) -> Decimal:
    return Decimal(ticks) * Decimal(str(tick_size))


def ticks_to_usd(ticks: int, tick_value: Decimal | str) -> Decimal:
    """Valor monetario de una distancia en ticks (puede ser negativo)."""
    return Decimal(ticks) * Decimal(str(tick_value))
