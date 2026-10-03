"""Adapter Databento DBN (mbp-10 y status) → MarketEvent (ENG-03). Semántica verificada en ADR-003.

Hechos del formato (Databento GLBX.MDP3, comprobados sobre datos reales el 3-oct-2026):
- Precios en punto fijo 1e-9 (`FIXED_PRICE_SCALE`); `UNDEF_PRICE` = sentinel de nivel vacío.
- `action`: A/C/M = cambio de libro, T = trade, R = clear/reset del libro.
- `side` en un trade = lado agresor: B → comprador agresor (BUY), A → vendedor agresor (SELL), N → desconocido.
- Los 10 niveles de un registro T son el estado del libro ANTES de aplicar el trade; el registro de
  libro que le sigue (con flag F_LAST) es el estado posterior. Un trade nunca lleva F_LAST.
- El volumen se cuenta SOLO en registros T (coincide exactamente con ohlcv-1m y con el esquema trades).
- `ts_recv` >= `ts_event` siempre; `sequence` es monótono dentro del archivo.

Rendimiento: se lee con `to_ndarray(count=…)` por bloques y columnas convertidas a listas Python
(órdenes de magnitud más rápido que iterar los objetos MBP10Msg). Los niveles son NamedTuple.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from trading_scanner.contracts import SCHEMA_VERSION, Aggressor, BookLevel, ContractSpec, EventType, MarketEvent

FIXED_PRICE_SCALE = 1_000_000_000
UNDEF_PRICE = 9_223_372_036_854_775_807
F_LAST = 128  # último registro del evento/paquete
F_SNAPSHOT = 32
F_BAD_TS_RECV = 8
F_MAYBE_BAD_BOOK = 4

DEFAULT_DISTRIBUTION_DELAY_NS = 100_000_000  # protocolo §7.1, caso base: 100 ms tras recepción del proveedor
CHUNK = 250_000

_ACTION_TO_TYPE = {b"A": EventType.BOOK, b"C": EventType.BOOK, b"M": EventType.BOOK, b"T": EventType.TRADE,
                   b"R": EventType.RESET, b"F": EventType.BOOK, b"N": EventType.BOOK}
_SIDE_TO_AGGRESSOR = {b"B": Aggressor.BUY, b"A": Aggressor.SELL, b"N": Aggressor.UNKNOWN}
_FLAG_NAMES = ((F_LAST, "F_LAST"), (F_SNAPSHOT, "F_SNAPSHOT"), (F_BAD_TS_RECV, "F_BAD_TS_RECV"), (F_MAYBE_BAD_BOOK, "F_MAYBE_BAD_BOOK"))


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
    skipped_time: int = 0
    flags_seen: dict[int, int] = field(default_factory=dict)

    @property
    def aggressor_known_pct(self) -> float | None:
        return None if self.trade_volume == 0 else 100.0 * self.aggressor_known_volume / self.trade_volume


def _tick_scaled(spec: ContractSpec) -> int:
    tick_scaled = int(spec.tick_size * FIXED_PRICE_SCALE)
    if Decimal(tick_scaled) != spec.tick_size * FIXED_PRICE_SCALE:
        raise ValueError(f"tick_size {spec.tick_size} no representable en escala 1e-9")
    return tick_scaled


def iter_mbp10_events(
    path: Path,
    spec: ContractSpec,
    instrument_id: int,
    *,
    dataset: str = "GLBX.MDP3",
    distribution_delay_ns: int = DEFAULT_DISTRIBUTION_DELAY_NS,
    stats: AdapterStats | None = None,
    start_ns: int | None = None,
    end_ns: int | None = None,
    chunk: int = CHUNK,
) -> Iterator[MarketEvent]:
    """Convierte un archivo DBN mbp-10 en MarketEvent del contrato `spec` (filtrando por instrument_id).

    `available_at_ns = ts_recv + distribution_delay_ns` (recepción del proveedor + retraso modelado,
    spec §3.3). No se infiere el agresor; no se corrige el libro; las anomalías van en quality_flags.
    `start_ns`/`end_ns` filtran por ts_recv antes de construir el evento. Siempre se construye con
    validación pydantic (medido: más rápido que model_construct en pydantic 2.13).
    """
    import databento as db

    tick = _tick_scaled(spec)
    phash = file_sha256(path)[:16]
    st = stats if stats is not None else AdapterStats()
    store = db.DBNStore.from_file(path)
    if str(store.metadata.schema) != "mbp-10":
        raise ValueError(f"esquema inesperado: {store.metadata.schema}")
    build = MarketEvent
    bid_px_cols = [f"bid_px_{i:02d}" for i in range(10)]
    ask_px_cols = [f"ask_px_{i:02d}" for i in range(10)]
    bid_sz_cols = [f"bid_sz_{i:02d}" for i in range(10)]
    ask_sz_cols = [f"ask_sz_{i:02d}" for i in range(10)]
    bid_ct_cols = [f"bid_ct_{i:02d}" for i in range(10)]
    ask_ct_cols = [f"ask_ct_{i:02d}" for i in range(10)]
    idx = -1

    for arr in store.to_ndarray(count=chunk):
        n = len(arr)
        col = lambda name: arr[name].tolist()  # noqa: E731
        ts_event_l, ts_recv_l, inst_l = col("ts_event"), col("ts_recv"), col("instrument_id")
        act_l, side_l, px_l, sz_l, fl_l, seq_l = col("action"), col("side"), col("price"), col("size"), col("flags"), col("sequence")
        bpx = [col(c) for c in bid_px_cols]
        apx = [col(c) for c in ask_px_cols]
        bsz = [col(c) for c in bid_sz_cols]
        asz = [col(c) for c in ask_sz_cols]
        bct = [col(c) for c in bid_ct_cols]
        act_ = [col(c) for c in ask_ct_cols]
        st.records += n
        for i in range(n):
            idx += 1
            if inst_l[i] != instrument_id:
                st.skipped_instruments += 1
                continue
            ts_recv = ts_recv_l[i]
            if (start_ns is not None and ts_recv < start_ns) or (end_ns is not None and ts_recv >= end_ns):
                st.skipped_time += 1
                continue
            flags = fl_l[i]
            st.flags_seen[flags] = st.flags_seen.get(flags, 0) + 1
            action = act_l[i]
            etype = _ACTION_TO_TYPE.get(action)
            if etype is None:
                raise ValueError(f"action desconocida {action!r} en record {idx}")
            qflags = [name for bit, name in _FLAG_NAMES if flags & bit]
            off = False

            bids: list[BookLevel] = []
            for k in range(10):
                p = bpx[k][i]
                if p == UNDEF_PRICE:
                    continue
                s_ = bsz[k][i]
                if s_ == 0:
                    continue
                q, r = divmod(p, tick)
                if r:
                    off = True
                    continue
                bids.append(BookLevel(q, s_, bct[k][i]))
            asks: list[BookLevel] = []
            for k in range(10):
                p = apx[k][i]
                if p == UNDEF_PRICE:
                    continue
                s_ = asz[k][i]
                if s_ == 0:
                    continue
                q, r = divmod(p, tick)
                if r:
                    off = True
                    continue
                asks.append(BookLevel(q, s_, act_[k][i]))

            price_ticks: int | None = None
            p = px_l[i]
            if p != UNDEF_PRICE:
                q, r = divmod(p, tick)
                if r:
                    off = True
                else:
                    price_ticks = q
            if off:
                st.off_grid_prices += 1
                qflags.append("PRICE_OFF_GRID")

            aggressor = Aggressor.UNKNOWN
            size: int | None = None
            if etype is EventType.TRADE:
                aggressor = _SIDE_TO_AGGRESSOR.get(side_l[i], Aggressor.UNKNOWN)
                size = sz_l[i]
                st.trades += 1
                st.trade_volume += size
                if aggressor is not Aggressor.UNKNOWN:
                    st.aggressor_known_volume += size
                qflags.append("BOOK_IS_PRE_TRADE")
                if price_ticks is None:
                    qflags.append("TRADE_PRICE_UNDEF")
                    etype = EventType.CORRECTION
                elif size <= 0:
                    qflags.append("TRADE_SIZE_INVALID")
                    etype = EventType.CORRECTION
            elif etype is EventType.RESET:
                st.resets += 1
            else:
                price_ticks = None  # el precio de un registro de libro es el nivel tocado, no un trade

            ts_event = ts_event_l[i]
            yield build(
                schema_version=SCHEMA_VERSION, source="databento", dataset=dataset, contract_id=spec.contract_id,
                channel_id=None, sequence=seq_l[i], record_index=idx, ts_event_ns=ts_event, ts_vendor_recv_ns=ts_recv,
                ts_local_recv_ns=None, available_at_ns=(ts_recv if ts_recv > ts_event else ts_event) + distribution_delay_ns,
                event_type=etype, price_ticks=price_ticks, size_contracts=size, aggressor=aggressor,
                bid_levels=tuple(bids), ask_levels=tuple(asks), quality_flags=tuple(qflags), raw_partition_hash=phash,
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
    name = lambda v: getattr(v, "name", str(v))  # noqa: E731  enums databento_dbn
    for idx, rec in enumerate(store):
        if rec.instrument_id != instrument_id:
            continue
        ts_event, ts_recv = int(rec.ts_event), int(rec.ts_recv)
        qflags = [f"STATUS_ACTION={name(rec.action)}", f"STATUS_REASON={name(rec.reason)}", f"TRADING_EVENT={name(rec.trading_event)}"]
        if bool(rec.is_trading):
            qflags.append("IS_TRADING")
        if bool(rec.is_quoting):
            qflags.append("IS_QUOTING")
        yield MarketEvent(
            source="databento", dataset=dataset, contract_id=spec.contract_id, channel_id=None, sequence=None,
            record_index=idx, ts_event_ns=ts_event, ts_vendor_recv_ns=ts_recv,
            available_at_ns=max(ts_recv, ts_event) + distribution_delay_ns, event_type=EventType.STATUS,
            quality_flags=tuple(qflags), raw_partition_hash=phash,
        )
