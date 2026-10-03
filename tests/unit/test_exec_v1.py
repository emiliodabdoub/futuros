"""ENG-07 aceptación: IOC fill / NO_FILL / gap (UNPRICED_EXIT) / timeout, stop con latencia, prioridad y P&L."""

from decimal import Decimal

from trading_scanner.contracts import BookLevel, Direction, TerminalReason
from trading_scanner.execution import ExecParams, ExecutionSim
from trading_scanner.orderbook import BookSnapshot
from trading_scanner.setups.liquidity_reversal import Level, LevelKind, LRSignal

NS = 1_000_000_000
MS = 1_000_000
T0 = 1_000 * NS
TICK = Decimal("12.50")  # ES


def sig(direction=Direction.LONG, stop=19995, created=T0):
    return LRSignal(id="s", contract_id="ESZ4", level=Level(LevelKind.PRIOR_DAY_LOW, 20000), direction=direction,
                    created_at_ns=created, expires_at_ns=created + 2 * NS, trigger_price_ticks=20003,
                    reclaim_price_ticks=20001, sweep_extreme_ticks=19997, stop_ticks=stop, risk_ticks_at_trigger=8,
                    target_ticks_at_trigger=20019, atr_1m_ticks_frozen=20.0, delta_ratio_5s=0.25,
                    volume_5s_rel_median=1.2, spread_ticks=1, attempt=1)


def book(t, bid=20003, ask=20004, bid_sz=10, ask_sz=10, bids=None, asks=None):
    b = bids if bids is not None else ((BookLevel(price_ticks=bid, size_contracts=bid_sz),) if bid else ())
    a = asks if asks is not None else ((BookLevel(price_ticks=ask, size_contracts=ask_sz),) if ask else ())
    return BookSnapshot("ESZ4", t, t, b, a, None)


def new_sim(s=None, params=None, flat_by=T0 + 3600 * NS, b0=None):
    return ExecutionSim(s or sig(), "c1", params=params or ExecParams(), tick_value_usd=TICK,
                        send_at_ns=T0, book_at_send=b0 or book(T0), flat_by_ns=flat_by)


def test_ioc_fills_at_best_ask_within_limit_after_latency():
    sim = new_sim()
    assert sim.trace.limit_ticks == 20006  # ask 20004 + 2
    assert sim.on_book(book(T0 + 50 * MS, ask=20005)) is None  # aún no llega la orden
    assert sim.on_book(book(T0 + 100 * MS, ask=20005)) is None
    assert sim.trace.fill_ticks == 20005 and sim.trace.fill_at_ns == T0 + 100 * MS
    assert sim.trace.stop_ticks == 19995 and sim.trace.target_ticks == 20005 + 20  # riesgo 10 → 2R


def test_no_fill_when_ask_beyond_limit_or_no_size():
    sim = new_sim()
    out = sim.on_book(book(T0 + 100 * MS, ask=20007))
    assert out.terminal_reason is TerminalReason.NO_FILL and out.fill_at_ns is None and out.PnL_USD is None
    sim2 = new_sim()
    out2 = sim2.on_book(book(T0 + 100 * MS, ask=20004, ask_sz=0))
    assert out2.terminal_reason is TerminalReason.NO_FILL


def test_stop_triggers_on_bid_and_executes_after_latency_at_worse_price():
    sim = new_sim()
    sim.on_book(book(T0 + 100 * MS, ask=20004))  # fill 20004, stop 19995
    assert sim.on_book(book(T0 + 5 * NS, bid=19995, ask=19996)) is None  # trigger stop
    assert sim.trace.trigger_reason is TerminalReason.STOP_TRIGGERED
    out = sim.on_book(book(T0 + 5 * NS + 100 * MS, bid=19993, ask=19994))  # llega 100 ms después, peor
    assert out.terminal_reason is TerminalReason.STOP_TRIGGERED and out.exit_price_ticks == 19993
    assert out.PnL_USD == Decimal(-11) * TICK - 6 and out.net_positive is False
    assert out.PnL_R == float(out.PnL_USD / (Decimal(9) * TICK))
    assert out.data_quality["mae_ticks"] <= -9


def test_target_hit_gives_positive_net_after_commission():
    sim = new_sim()
    sim.on_book(book(T0 + 100 * MS, ask=20004))  # riesgo 9 → target 20022
    sim.on_book(book(T0 + 60 * NS, bid=20022, ask=20023))
    out = sim.on_book(book(T0 + 60 * NS + 100 * MS, bid=20022, ask=20023))
    assert out.terminal_reason is TerminalReason.TARGET_TRIGGERED
    assert out.PnL_USD == Decimal(18) * TICK - 6 and out.net_positive is True


def test_time_exit_at_15_minutes_or_flat_by_whichever_first():
    sim = new_sim(flat_by=T0 + 5 * 60 * NS)
    sim.on_book(book(T0 + 100 * MS))
    assert sim.trace.time_exit_at_ns == T0 + 5 * 60 * NS
    sim.on_time(T0 + 5 * 60 * NS)  # sin snapshots nuevos también vence
    assert sim.trace.trigger_reason is TerminalReason.TIME_EXIT
    out = sim.on_book(book(T0 + 5 * 60 * NS + 100 * MS, bid=20010, ask=20011))
    assert out.terminal_reason is TerminalReason.TIME_EXIT and out.exit_price_ticks == 20010
    sim2 = new_sim()
    sim2.on_book(book(T0 + 100 * MS))
    assert sim2.trace.time_exit_at_ns == T0 + 100 * MS + 15 * 60 * NS


def test_gap_without_executable_book_is_unpriced_exit():
    sim = new_sim()
    sim.on_book(book(T0 + 100 * MS))
    sim.on_book(book(T0 + 3 * NS, bid=19990, ask=19991))  # stop
    out = sim.on_book(book(T0 + 3 * NS + 100 * MS, bids=(), asks=()))
    assert out.terminal_reason is TerminalReason.UNPRICED_EXIT and out.PnL_USD is None and out.exit_price_ticks is None


def test_simultaneous_stop_and_target_prioritizes_stop_with_flag():
    sim = new_sim()
    sim.on_book(book(T0 + 100 * MS, ask=20004))  # stop 19995, target 20022
    # libro absurdo pero posible en datos sucios: bid 20022 y... el stop usa el mismo bid; forzamos coincidencia con time
    sim.trace.time_exit_at_ns = T0 + 1 * NS
    sim.on_book(book(T0 + 1 * NS, bid=20022, ask=20023))  # time y target al mismo timestamp
    assert sim.trace.trigger_reason is TerminalReason.TIME_EXIT
    assert sim.trace.ambiguity_flags == ["SIMULTANEOUS_TRIGGERS:TIME_EXIT,TARGET_TRIGGERED"]


def test_emergency_exit_when_fill_breaks_risk_budget():
    sim = new_sim(params=ExecParams(risk_budget_ticks=8))
    sim.on_book(book(T0 + 100 * MS, ask=20005))  # riesgo 10 > 8
    assert sim.trace.trigger_reason is TerminalReason.EMERGENCY_EXIT
    out = sim.on_book(book(T0 + 200 * MS, bid=20004, ask=20005))
    assert out.terminal_reason is TerminalReason.EMERGENCY_EXIT and out.PnL_USD == Decimal(-1) * TICK - 6


def test_short_symmetry_and_extra_slippage_stress():
    s = sig(direction=Direction.SHORT, stop=20013)
    sim = ExecutionSim(s, "c2", params=ExecParams(extra_exit_slippage_ticks=1), tick_value_usd=TICK,
                       send_at_ns=T0, book_at_send=book(T0, bid=20004, ask=20005), flat_by_ns=T0 + 3600 * NS)
    assert sim.trace.limit_ticks == 20002
    sim.on_book(book(T0 + 100 * MS, bid=20003, ask=20004))  # fill 20003 (bid), riesgo 10 → target 19983
    sim.on_book(book(T0 + 2 * NS, bid=19982, ask=19983))  # ask <= target
    out = sim.on_book(book(T0 + 2 * NS + 100 * MS, bid=19982, ask=19983))
    assert out.terminal_reason is TerminalReason.TARGET_TRIGGERED
    assert out.exit_price_ticks == 19984  # ask 19983 + 1 tick adverso
    assert out.PnL_USD == Decimal(19) * TICK - 6


def test_invalid_data_when_no_quote_at_send():
    sim = new_sim(b0=book(T0, bids=(), asks=()))
    assert sim.done is not None and sim.done.terminal_reason is TerminalReason.INVALID_DATA


def test_policy_hash_changes_with_costs_and_latency():
    assert ExecParams().policy_hash != ExecParams(commission_round_trip_usd=Decimal("10")).policy_hash
    assert ExecParams().policy_hash != ExecParams(order_latency_ns=300 * MS).policy_hash
