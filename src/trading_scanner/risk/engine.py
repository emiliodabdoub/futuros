"""Risk engine paper (spec §9.3, ENG-10). Autoridad final sobre el ganador del ranking.

Perfil sintético: pérdida acumulada máxima 5,000 USD; límite diario 500 USD; riesgo planificado máximo
por trade 100 USD incluyendo comisión y reserva de salida. Una posición global (D07): ES y NQ no se
abren a la vez (y nada se abre si hay posición). Sin fraccionar contratos ni micros con libro del mini.
Daily gate = realizado + unrealized liquidable + fees + reservas. Al tocar la pérdida diaria: bloquear
entradas y cerrar según política, sin esperar a Jev. No martingale, no averaging-down.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class RiskProfile:
    max_cumulative_loss_usd: Decimal = Decimal("5000")
    max_daily_loss_usd: Decimal = Decimal("500")
    max_planned_risk_per_trade_usd: Decimal = Decimal("100")
    exit_reserve_ticks: int = 2  # reserva por salida con latencia/slippage
    commission_round_trip_usd: Decimal = Decimal("6")
    max_open_positions: int = 1
    correlated_groups: tuple[frozenset[str], ...] = (frozenset({"ES", "NQ"}),)


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    planned_risk_usd: Decimal
    reasons: tuple[str, ...]


@dataclass
class RiskEngine:
    profile: RiskProfile = field(default_factory=RiskProfile)
    cumulative_pnl_usd: Decimal = Decimal("0")
    daily_realized_usd: Decimal = Decimal("0")
    open_positions: dict[str, str] = field(default_factory=dict)  # candidate_id → root
    halted_today: bool = False
    _reserved_usd: Decimal = Decimal("0")

    def new_session(self) -> None:
        self.daily_realized_usd = Decimal("0")
        self.halted_today = False
        self._reserved_usd = Decimal("0")

    def planned_risk(self, risk_ticks: int, tick_value_usd: Decimal) -> Decimal:
        return (Decimal(risk_ticks + self.profile.exit_reserve_ticks) * tick_value_usd) + self.profile.commission_round_trip_usd

    def evaluate(self, candidate_id: str, root: str, risk_ticks: int, tick_value_usd: Decimal,
                 unrealized_liquidable_usd: Decimal = Decimal("0")) -> RiskDecision:
        p = self.profile
        reasons: list[str] = []
        planned = self.planned_risk(risk_ticks, tick_value_usd)
        if self.halted_today:
            reasons.append("DAILY_HALT")
        if planned > p.max_planned_risk_per_trade_usd:
            reasons.append(f"PLANNED_RISK_{planned}>{p.max_planned_risk_per_trade_usd}")
        if len(self.open_positions) >= p.max_open_positions:
            reasons.append("POSITION_LIMIT")
        for grp in p.correlated_groups:
            if root in grp and any(r in grp for r in self.open_positions.values()):
                reasons.append("CORRELATED_EXPOSURE")
        daily_gate = self.daily_realized_usd + unrealized_liquidable_usd - self._reserved_usd - planned
        if daily_gate <= -p.max_daily_loss_usd:
            reasons.append("DAILY_LOSS_BUDGET")
        if self.cumulative_pnl_usd + unrealized_liquidable_usd - planned <= -p.max_cumulative_loss_usd:
            reasons.append("CUMULATIVE_LOSS_BUDGET")
        return RiskDecision(not reasons, planned, tuple(reasons))

    def open(self, candidate_id: str, root: str, planned_risk_usd: Decimal) -> None:
        self.open_positions[candidate_id] = root
        self._reserved_usd += planned_risk_usd

    def close(self, candidate_id: str, pnl_usd: Decimal | None, planned_risk_usd: Decimal) -> None:
        self.open_positions.pop(candidate_id, None)
        self._reserved_usd -= planned_risk_usd
        if pnl_usd is not None:
            self.daily_realized_usd += pnl_usd
            self.cumulative_pnl_usd += pnl_usd
        if self.daily_realized_usd <= -self.profile.max_daily_loss_usd:
            self.halted_today = True

    def must_flatten(self, unrealized_liquidable_usd: Decimal) -> bool:
        """Con posición abierta: si realizado + liquidable toca el límite diario, cerrar según política."""
        return bool(self.open_positions) and (self.daily_realized_usd + unrealized_liquidable_usd) <= -self.profile.max_daily_loss_usd
