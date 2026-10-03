"""Motor de features causal por contrato (ENG-05). Consume MarketEvent ya pasados por el QualityGate
y produce FeatureSnapshot as-of (spec §4). Unidades: ticks, contratos, segundos. null = ausencia.

Features v1 implementadas: F01, F02 (1m/5m/15m), F03 ATR14 1m, F04/F05 delta y ratio 5/10/60 s,
F06 CVD de sesión, F07 VWAP de sesión, F09 opening range, F11/F12 imbalance y su mediana 1 s,
F13 efficiency ratio 12 cierres 5m, F15 volumen 5 s relativo a mediana de bloques previos 30 min.
F08 (día anterior) se inyecta desde fuera (`set_prior_day_levels`) porque depende de la historia del
contrato elegido, no de este stream.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import dataclass

from trading_scanner.contracts import Aggressor, EventType, FeatureSnapshot, MarketEvent
from trading_scanner.features.bars import Bar, BarBuilder
from trading_scanner.features.indicators import atr_simple, efficiency_ratio, median, weighted_median
from trading_scanner.orderbook import BookSnapshot, BookTracker

NS = 1_000_000_000
FEATURE_VERSION = "features-v1"
MIN_F15_BLOCKS = 100


@dataclass
class _Trade:
    ts_event_ns: int
    available_at_ns: int
    price: int
    size: int
    aggressor: Aggressor


class FeatureEngine:
    def __init__(self, contract_id: str, *, session_open_ns: int, opening_range_end_ns: int,
                 contract_spec_version: str = "catalog-v1", f15_from_ns: int | None = None) -> None:
        self.contract_id = contract_id
        self.f15_from_ns = f15_from_ns  # si se fija, los bloques de 5 s anteriores no cuentan para la mediana de F15
        self.session_open_ns = session_open_ns
        self.opening_range_end_ns = opening_range_end_ns
        self.contract_spec_version = contract_spec_version
        self.bars_1m = BarBuilder(60 * NS)
        self.bars_5m = BarBuilder(300 * NS)
        self.bars_15m = BarBuilder(900 * NS)
        self.book = BookTracker(contract_id)
        self._trades: deque[_Trade] = deque()  # ventana trailing 60 s
        self._blocks_5s: deque[tuple[int, int]] = deque()  # (block_start, volume) últimos 30 min
        self._cur_block: tuple[int, int] | None = None
        self._imb_obs: deque[tuple[int, float]] = deque()  # (available_at, imbalance) último 1 s
        self.cvd = 0
        self.cvd_unknown = 0
        self.vwap_num = 0
        self.vwap_den = 0
        self.or_high: int | None = None
        self.or_low: int | None = None
        self.last_trade: _Trade | None = None
        self.prior_day_high: int | None = None
        self.prior_day_low: int | None = None
        self.max_input_available_ns = 0
        self._snap_count = 0

    def set_prior_day_levels(self, high: int, low: int) -> None:
        self.prior_day_high, self.prior_day_low = high, low

    # ---- ingesta ---------------------------------------------------------------------------------
    def apply(self, ev: MarketEvent) -> None:
        t = ev.available_at_ns
        self.max_input_available_ns = max(self.max_input_available_ns, t)
        for b in (self.bars_1m, self.bars_5m, self.bars_15m):
            b.observe(t)
        snap = self.book.apply(ev)
        if snap is not None:
            imb = snap.depth_imbalance(5)
            if imb is not None:
                self._imb_obs.append((t, imb))
        self._trim_imb(t)
        if ev.event_type is EventType.TRADE and ev.price_ticks is not None and ev.size_contracts:
            tr = _Trade(ev.ts_event_ns, t, ev.price_ticks, ev.size_contracts, ev.aggressor)
            self._ingest_trade(tr)
        self._trim_trades(t)

    def _ingest_trade(self, tr: _Trade) -> None:
        self.last_trade = tr
        for b in (self.bars_1m, self.bars_5m, self.bars_15m):
            b.add_trade(tr.ts_event_ns, tr.available_at_ns, tr.price, tr.size, tr.aggressor)
        self._trades.append(tr)
        if tr.ts_event_ns >= self.session_open_ns:
            if tr.aggressor is Aggressor.BUY:
                self.cvd += tr.size
            elif tr.aggressor is Aggressor.SELL:
                self.cvd -= tr.size
            else:
                self.cvd_unknown += tr.size
            self.vwap_num += tr.price * tr.size
            self.vwap_den += tr.size
            if tr.ts_event_ns < self.opening_range_end_ns:
                self.or_high = tr.price if self.or_high is None else max(self.or_high, tr.price)
                self.or_low = tr.price if self.or_low is None else min(self.or_low, tr.price)
        block = (tr.ts_event_ns // (5 * NS)) * 5 * NS
        if self.f15_from_ns is not None and block < self.f15_from_ns:
            return
        if self._cur_block is None or block != self._cur_block[0]:
            if self._cur_block is not None and block > self._cur_block[0]:
                self._blocks_5s.append(self._cur_block)
            if self._cur_block is None or block > self._cur_block[0]:
                self._cur_block = (block, 0)
        if self._cur_block[0] == block:
            self._cur_block = (block, self._cur_block[1] + tr.size)
        cutoff = block - 30 * 60 * NS
        while self._blocks_5s and self._blocks_5s[0][0] < cutoff:
            self._blocks_5s.popleft()

    def _trim_trades(self, now_ns: int) -> None:
        cutoff = now_ns - 60 * NS
        while self._trades and self._trades[0].available_at_ns < cutoff:
            self._trades.popleft()

    def _trim_imb(self, now_ns: int) -> None:
        cutoff = now_ns - 1 * NS
        while self._imb_obs and self._imb_obs[0][0] < cutoff:
            self._imb_obs.popleft()

    # ---- cálculo ---------------------------------------------------------------------------------
    def _delta(self, as_of_ns: int, window_s: int) -> tuple[int | None, float | None, str | None]:
        cutoff = as_of_ns - window_s * NS
        buy = sell = unknown = 0
        for tr in self._trades:
            if cutoff <= tr.available_at_ns <= as_of_ns:
                if tr.aggressor is Aggressor.BUY:
                    buy += tr.size
                elif tr.aggressor is Aggressor.SELL:
                    sell += tr.size
                else:
                    unknown += tr.size
        known = buy + sell
        if known == 0:
            return None, None, "no_known_aggressor_volume"
        if unknown > 0 and 100.0 * known / (known + unknown) < 95.0:
            return buy - sell, None, "aggressor_quality_below_95pct"
        return buy - sell, (buy - sell) / known, None

    def snapshot(self, as_of_ns: int) -> FeatureSnapshot:
        if as_of_ns < self.max_input_available_ns:
            raise ValueError("snapshot as_of anterior al último input consumido: no es causal")
        v: dict[str, float | int | str | None] = {}
        u: dict[str, str] = {}
        miss: dict[str, str] = {}

        def put(k: str, val, unit: str, reason: str | None = None):
            v[k] = val
            u[k] = unit
            if val is None:
                miss[k] = reason or "not_available"

        snap: BookSnapshot | None = self.book.snapshot
        lt = self.last_trade
        put("F01_last_trade", lt.price if lt else None, "ticks", "no_trade")
        put("F01_best_bid", snap.best_bid if snap else None, "ticks", "no_book")
        put("F01_best_ask", snap.best_ask if snap else None, "ticks", "no_book")
        put("F01_spread", snap.spread_ticks if snap else None, "ticks", "no_book")

        for name, b in (("1m", self.bars_1m), ("5m", self.bars_5m), ("15m", self.bars_15m)):
            last = b.finalized[-1] if b.finalized else None
            put(f"F02_close_{name}", last.close if last else None, "ticks", "no_finalized_bar")
            put(f"F02_volume_{name}", last.volume if last else None, "contracts", "no_finalized_bar")
        put("F02_bars_1m_finalized", len(self.bars_1m.finalized), "count")
        put("F02_late_revisions_1m", self.bars_1m.late_revisions, "count")

        atr = atr_simple(self.bars_1m.finalized, 14)
        put("F03_atr14_1m", atr, "ticks", "warmup_lt_15_bars")

        for w in (5, 10, 60):
            d, r, reason = self._delta(as_of_ns, w)
            put(f"F04_delta_{w}s", d, "contracts", reason)
            put(f"F05_delta_ratio_{w}s", r, "ratio", reason)

        put("F06_cvd_session", self.cvd if self.vwap_den else None, "contracts", "no_session_trades")
        put("F06_cvd_unknown_session", self.cvd_unknown if self.vwap_den else None, "contracts", "no_session_trades")
        put("F07_vwap_session", (self.vwap_num / self.vwap_den) if self.vwap_den else None, "ticks", "no_session_trades")
        put("F08_prior_day_high", self.prior_day_high, "ticks", "not_injected")
        put("F08_prior_day_low", self.prior_day_low, "ticks", "not_injected")
        or_ready = as_of_ns >= self.opening_range_end_ns + 250_000_000
        put("F09_or_high", self.or_high if or_ready else None, "ticks", "opening_range_not_closed")
        put("F09_or_low", self.or_low if or_ready else None, "ticks", "opening_range_not_closed")

        imb = snap.depth_imbalance(5) if snap else None
        put("F11_depth_imbalance_5", imb, "ratio", "no_book_or_empty")
        obs = [(x, t) for t, x in self._imb_obs if as_of_ns - NS <= t <= as_of_ns]
        if len(obs) >= 5:
            # ponderación por tiempo: duración de cada observación hasta la siguiente (o as_of)
            ts = sorted(t for _, t in obs)
            weights = []
            vals = {t: x for x, t in obs}
            for i, t in enumerate(ts):
                nxt = ts[i + 1] if i + 1 < len(ts) else as_of_ns
                weights.append((vals[t], max(nxt - t, 1)))
            put("F12_imbalance_median_1s", weighted_median(weights), "ratio")
        else:
            put("F12_imbalance_median_1s", None, "ratio", "lt_5_observations")

        closes_5m = [b.close for b in self.bars_5m.finalized[-12:]]
        er = efficiency_ratio(closes_5m) if len(closes_5m) == 12 else None
        put("F13_efficiency_ratio_5m", er, "ratio", "lt_12_bars_5m" if len(closes_5m) < 12 else "zero_path")

        prev_blocks = [vol for _, vol in self._blocks_5s]
        cur = self._cur_block[1] if self._cur_block else None
        if len(prev_blocks) >= MIN_F15_BLOCKS and cur is not None:
            med = median(prev_blocks)
            put("F15_volume_5s_rel", (cur / med) if med else None, "ratio", "median_zero")
            put("F15_median_5s", med, "contracts")
        else:
            put("F15_volume_5s_rel", None, "ratio", f"lt_{MIN_F15_BLOCKS}_valid_blocks")
            put("F15_median_5s", None, "contracts", f"lt_{MIN_F15_BLOCKS}_valid_blocks")

        self._snap_count += 1
        payload = json.dumps({"c": self.contract_id, "t": as_of_ns, "v": v}, sort_keys=True, default=str)
        sid = hashlib.sha256(payload.encode()).hexdigest()[:24]
        return FeatureSnapshot(
            id=f"fs-{self.contract_id}-{sid}", as_of_ns=as_of_ns,
            max_input_available_at_ns=self.max_input_available_ns, feature_version=FEATURE_VERSION,
            contract_spec_version=self.contract_spec_version, values=v, units=u, missing_reasons=miss,
            quality={"bars_1m_late_revisions": self.bars_1m.late_revisions, "book_resets": self.book.resets},
        )
