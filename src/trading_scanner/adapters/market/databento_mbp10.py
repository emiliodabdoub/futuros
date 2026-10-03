"""Adapter Databento DBN (mbp-10 y status) → MarketEvent (ENG-03). Semántica verificada en ADR-003.

Hechos del formato (Databento GLBX.MDP3, comprobados sobre datos reales el 3-oct-2026):
- Precios en punto fijo 1e-9 (`FIXED_PRICE_SCALE`); `UNDEF_PRICE` = sentinel de nivel vacío.
- `action`: A/C/M = cambio de libro, T = trade, R = clear/reset del libro.
- `side` en un trade = lado agresor: B → comprador agresor (BUY), A → vendedor agresor (SELL), N → desconocido.
- Los 10 niveles de un registro T son el estado del libro ANTES de aplicar el trade; el registro de
  libro que le sigue (con flag F_LAST) es el estado posterior. Un trade nunca lleva F_LAST.
- El volumen se cuenta SOLO en registros T (coincide exactamente con ohlcv-1m y con el esquema trades).
- `ts_recv` >= `ts_event` siempre; `sequence` es monótono dentro del archivo.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from trading_scanner.contracts import Aggressor, BookLevel, ContractSpec, EventType, MarketEvent

FIXED_PRICE_SCALE = 1_000_000_000
UNDEF_PRICE = 9_223_372_036_854_775_807
F_LAST = 128  # último registro del evento/paquete
F_SNAPSHOT = 32
F_BAD_TS_RECV = 8
F_MAYBE_BAD_BOOK = 4

DEFAULT_DISTRIBUTION_DELAY_NS = 100_000_000  # protocolo §7.1, caso base: 100 ms tras recepción del proveedor

_ACTION_TO_TYPE = {"A": EventType.BOOK, "C": EventType.BOOK, "M": EventType.BOOK,
                   "T": EventType.TRADE, "R": EventType.RESET, "F": EventType.BOOK, "N": EventType.BOOK}
_SIDE_TO_AGGRESSOR = {"B": Aggressor.BUY, "A": Aggressor.SELL, "N": Aggressor.UNKNOWN}


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class AdapterStats:
    records: int = 0
    trades: int = 0
    trade_volume: int = 0
    aggressor_known_volume: int = 0
    resets: int = 0
    off_grid_prices: int = 0
    skipped_instruments: int = 0
    flags_seen: dict[int, int] = field(default_factory=dict)

    @property
    def aggressor_known_pct(self) -> float | None:
        return None if self.trade_volume == 0 else 100.0 * self.aggressor_known_volume / self.trade_volume


def _px_to_ticks(px: int, tick_scaled: int) -> tuple[int | None, bool]:
    """Devuelve (ticks, off_grid). Precio UNDEF → (None, False)."""
    if px == UNDEF_PRICE:
        return None, False
    q, r = divmod(px, tick_scaled)
    if r != 0:
        return None, True
    return int(q), False


def _levels(rec, prefix: str, tick_scaled: int) -> tuple[tuple[BookLevel, ...], bool]:
    out: list[BookLevel] = []
    off = False
    for lvl in rec.levels:
        px = getattr(lvl, f"{prefix}_px")
        sz = getattr(lvl, f"{prefix}_sz")
        ct = getattr(lvl, f"{prefix}_ct")
        ticks, bad = _px_to_ticks(px, tick_scaled)
        off = off or bad
        if ticks is None or sz == 0:
            continue
        out.append(BookLevel(price_ticks=ticks, size_contracts=int(sz), order_count=int(ct)))
    return tuple(out), off


def iter_mbp10_events(
    path: Path,
    spec: ContractSpec,
    instrument_id: int,
    *,
    dataset: str = "GLBX.MDP3",
    distribution_delay_ns: int = DEFAULT_DISTRIBUTION_DELAY_NS,
    stats: AdapterStats | None = None,
) -> Iterator[MarketEvent]:
    """Convierte un archivo DBN mbp-10 en MarketEvent del contrato `spec` (filtrando por instrument_id).

    `available_at_ns = ts_recv + distribution_delay_ns` (recepción del proveedor + retraso modelado,
    spec §3.3). No se infiere el agresor; no se corrige el libro; las anomalías van en quality_flags.
    """
    import databento as db

    tick_scaled = int(spec.tick_size * FIXED_PRICE_SCALE)
    if Decimal(tick_scaled) != spec.tick_size * FIXED_PRICE_SCALE:
        raise ValueError(f"tick_size {spec.tick_size} no representable en escala 1e-9")
    phash = file_sha256(path)[:16]
    st = stats if stats is not None else AdapterStats()
    store = db.DBNStore.from_file(path)
    if str(store.metadata.schema) != "mbp-10":
        raise ValueError(f"esquema inesperado: {store.metadata.schema}")

    for idx, rec in enumerate(store):
        st.records += 1
        if rec.instrument_id != instrument_id:
            st.skipped_instruments += 1
            continue
        flags = int(rec.flags)
        st.flags_seen[flags] = st.flags_seen.get(flags, 0) + 1
        action = str(rec.action)
        etype = _ACTION_TO_TYPE.get(action)
        if etype is None:
            raise ValueError(f"action desconocida {action!r} en record {idx}")

        qflags: list[str] = []
        if flags & F_LAST:
            qflags.append("F_LAST")
        if flags & F_SNAPSHOT:
            qflags.append("F_SNAPSHOT")
        if flags & F_BAD_TS_RECV:
            qflags.append("F_BAD_TS_RECV")
        if flags & F_MAYBE_BAD_BOOK:
            qflags.append("F_MAYBE_BAD_BOOK")

        price_ticks, off = _px_to_ticks(int(rec.price), tick_scaled)
        bids, off_b = _levels(rec, "bid", tick_scaled)
        asks, off_a = _levels(rec, "ask", tick_scaled)
        if off or off_b or off_a:
            st.off_grid_prices += 1
            qflags.append("PRICE_OFF_GRID")

        aggressor = Aggressor.UNKNOWN
        size: int | None = None
        if etype is EventType.TRADE:
            aggressor = _SIDE_TO_AGGRESSOR.get(str(rec.side), Aggressor.UNKNOWN)
            size = int(rec.size)
            st.trades += 1
            st.trade_volume += size
            if aggressor is not Aggressor.UNKNOWN:
                st.aggressor_known_volume += size
            qflags.append("BOOK_IS_PRE_TRADE")
            if price_ticks is None:
                qflags.append("TRADE_PRICE_UNDEF")
                # MarketEvent exige precio en TRADE: degradar a CORRECTION con flag para no perder el registro
                etype = EventType.CORRECTION
        elif etype is EventType.RESET:
            st.resets += 1
        else:
            price_ticks = None  # el precio del registro de libro es el nivel tocado; no es un trade

        ts_event = int(rec.ts_event)
        ts_recv = int(rec.ts_recv)
        yield MarketEvent(
            source="databento",
            dataset=dataset,
            contract_id=spec.contract_id,
            channel_id=None,
            sequence=int(rec.sequence),
            record_index=idx,
            ts_event_ns=ts_event,
            ts_vendor_recv_ns=ts_recv,
            ts_local_recv_ns=None,
            available_at_ns=max(ts_recv, ts_event) + distribution_delay_ns,
            event_type=etype,
            price_ticks=price_ticks,
            size_contracts=size,
            aggressor=aggressor,
            bid_levels=bids,
            ask_levels=asks,
            quality_flags=tuple(qflags),
            raw_partition_hash=phash,
        )


def iter_status_events(
    path: Path,
    spec: ContractSpec,
    instrument_id: int,
    *,
    dataset: str = "GLBX.MDP3",
    distribution_delay_ns: int = DEFAULT_DISTRIBUTION_DELAY_NS,
) -> Iterator[MarketEvent]:
    """Esquema status → MarketEvent STATUS con flags IS_TRADING/IS_QUOTING y action/reason/trading_event."""
    import databento as db

    phash = file_sha256(path)[:16]
    store = db.DBNStore.from_file(path)
    for idx, rec in enumerate(store):
        if rec.instrument_id != instrument_id:
            continue
        ts_event, ts_recv = int(rec.ts_event), int(rec.ts_recv)
        name = lambda v: getattr(v, "name", str(v))  # enums databento_dbn (StatusAction.TRADING, …)
        qflags = [f"STATUS_ACTION={name(rec.action)}", f"STATUS_REASON={name(rec.reason)}",
                  f"TRADING_EVENT={name(rec.trading_event)}"]
        if bool(rec.is_trading):
            qflags.append("IS_TRADING")
        if bool(rec.is_quoting):
            qflags.append("IS_QUOTING")
        yield MarketEvent(
            source="databento", dataset=dataset, contract_id=spec.contract_id, channel_id=None,
            sequence=None, record_index=idx, ts_event_ns=ts_event, ts_vendor_recv_ns=ts_recv,
            available_at_ns=max(ts_recv, ts_event) + distribution_delay_ns, event_type=EventType.STATUS,
            quality_flags=tuple(qflags), raw_partition_hash=phash,
        )
