"""Ranking v1 por unidad de riesgo (spec §9.2, ENG-10).

R_price_USD = distancia entrada-stop × valor por tick
EV_R = EV_net_USD / R_price_USD
tail_R = ES95(max(0, -net_PnL_USD)) / R_price_USD      (media del peor 5 % de pérdidas)
uncertainty_R = max(0, EV_R - lower95_EV_R)
RAEV_R = EV_R - λ·tail_R - γ·uncertainty_R              (λ = 0.10, γ = 1 fijos en v1)

Umbrales de investigación: EV_R >= 0.10, lower95_EV_R > 0, RAEV_R > 0. Sin soporte para cola o
incertidumbre → NO TRADE. Empate (<= 0.01 R): menor costo relativo, menor riesgo USD, orden fijo ES/NQ/GC.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

import numpy as np

INSTRUMENT_ORDER = {"ES": 0, "NQ": 1, "GC": 2}


@dataclass(frozen=True)
class RankingPolicy:
    ev_r_min: float = 0.10
    lambda_tail: float = 0.10
    gamma_uncertainty: float = 1.0
    tie_tolerance_r: float = 0.01
    es_quantile: float = 0.95
    min_support: int = 20  # muestras mínimas de P&L para estimar cola

    @property
    def policy_hash(self) -> str:
        return "rank-v1-" + hashlib.sha256(json.dumps(self.__dict__, sort_keys=True).encode()).hexdigest()[:12]


@dataclass(frozen=True)
class Scores:
    R_price_usd: Decimal
    EV_R: float
    lower95_EV_R: float
    tail_R: float
    uncertainty_R: float
    RAEV_R: float
    support: int
    support_status: str


def expected_shortfall(losses_usd: np.ndarray, q: float) -> float:
    """ES_q de las pérdidas (valores >= 0). Convención: media de las observaciones >= cuantil q (tipo 'higher')."""
    if len(losses_usd) == 0:
        return float("nan")
    thr = np.quantile(losses_usd, q, method="higher")
    tail = losses_usd[losses_usd >= thr]
    return float(tail.mean())


def score(*, risk_ticks: int, tick_value_usd: Decimal, pnl_samples_usd: np.ndarray, ev_usd: float,
          lower95_ev_usd: float, policy: RankingPolicy) -> Scores:
    r_usd = Decimal(risk_ticks) * tick_value_usd
    if r_usd <= 0:
        raise ValueError("riesgo de precio debe ser > 0")
    r = float(r_usd)
    ev_r = ev_usd / r
    lo_r = lower95_ev_usd / r
    n = int(len(pnl_samples_usd))
    if n < policy.min_support:
        return Scores(r_usd, ev_r, lo_r, float("nan"), float("nan"), float("nan"), n, "INSUFFICIENT_SUPPORT")
    losses = np.maximum(0.0, -pnl_samples_usd)
    tail_r = expected_shortfall(losses, policy.es_quantile) / r
    unc_r = max(0.0, ev_r - lo_r)
    raev = ev_r - policy.lambda_tail * tail_r - policy.gamma_uncertainty * unc_r
    return Scores(r_usd, ev_r, lo_r, tail_r, unc_r, raev, n, "OK")


@dataclass(frozen=True)
class RankedCandidate:
    candidate_id: str
    root: str
    scores: Scores
    relative_cost: float  # costos_USD / R_price_USD
    eligible: bool
    exclusion_reason: str | None


def rank(cands: list[tuple[str, str, Scores, float]], policy: RankingPolicy) -> tuple[list[RankedCandidate], str | None]:
    """cands: (candidate_id, root, scores, relative_cost). Devuelve lista ordenada y el seleccionado o None (NO TRADE)."""
    ranked: list[RankedCandidate] = []
    for cid, root, s, cost in cands:
        reason = None
        if s.support_status != "OK":
            reason = s.support_status
        elif s.EV_R < policy.ev_r_min:
            reason = f"EV_R<{policy.ev_r_min}"
        elif s.lower95_EV_R <= 0:
            reason = "lower95_EV_R<=0"
        elif s.RAEV_R <= 0:
            reason = "RAEV_R<=0"
        ranked.append(RankedCandidate(cid, root, s, cost, reason is None, reason))

    def key(rc: RankedCandidate):
        return (-round(rc.scores.RAEV_R / policy.tie_tolerance_r) if rc.eligible else float("inf"),
                rc.relative_cost, float(rc.scores.R_price_usd), INSTRUMENT_ORDER.get(rc.root, 99))

    eligible = sorted((r for r in ranked if r.eligible), key=key)
    ordered = eligible + [r for r in ranked if not r.eligible]
    return ordered, (eligible[0].candidate_id if eligible else None)
